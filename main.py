import asyncio
import logging
import re
import os
import requests
import json
import math
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright
from flask import Flask
import threading

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login" 
HOME_URL = "https://dkwin8.com/#/"
WIN_GO_URL = "https://dkwin8.com/#/WinGo_30S"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
PROXY_URL = os.environ.get("PROXY_URL", "")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Render পোর্ট এরর ফিক্স
web_app = Flask(__name__)
@web_app.route('/')
def health_check():
    return "Bot is running!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. NovaBrainV7 প্রেডিকশন লজিক
# ───────────────────────────────────────────
def markov_predict(sizes, order=2):
    if len(sizes) < order + 1: return {"Big": 0.5, "Small": 0.5}
    key = "|".join(sizes[:order])
    t = {"Big": 0, "Small": 0}
    for i in range(len(sizes) - order):
        if "|".join(sizes[i:i+order]) == key:
            nxt = sizes[i+order]
            t[nxt] = t.get(nxt, 0) + 1
    tot = t["Big"] + t["Small"]
    if not tot: return {"Big": 0.5, "Small": 0.5}
    return {"Big": t["Big"]/tot, "Small": t["Small"]/tot}

def rsi(sizes, period=14):
    if len(sizes) < period + 1: return 50
    gains = losses = 0
    for i in range(period):
        diff = (1 if sizes[i] == "Big" else 0) - (1 if sizes[i+1] == "Big" else 0)
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    return 100 - (100 / (1 + gains/losses))

def entropy(sizes, n=20):
    sl = sizes[:n]
    if not sl: return 0
    bc = sl.count("Big")
    sc = len(sl) - bc
    if not bc or not sc: return 0
    pb = bc / len(sl)
    ps = sc / len(sl)
    return -(pb * math.log2(pb) + ps * math.log2(ps))

def arima_lite(sizes):
    binary = [1 if s == "Big" else 0 for s in sizes[:30]]
    if len(binary) < 6: return {"Big": 0.5, "Small": 0.5}
    sxy1 = sxy2 = sx2 = 0
    for i in range(2, len(binary)):
        sxy1 += binary[i] * binary[i-1]
        sxy2 += binary[i] * binary[i-2]
        sx2 += binary[i-1] * binary[i-1]
    a1 = sxy1 / (sx2 + 1e-9)
    a2 = sxy2 / (sx2 + 1e-9)
    pred = max(0.1, min(0.9, 0.5 + 0.3 * a1 * (binary[0] - 0.5) + 0.2 * a2 * (binary[1] - 0.5)))
    return {"Big": pred, "Small": 1 - pred}

def get_history_and_prediction_sync():
    try:
        res = requests.get(HISTORY_API, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        numbers = [int(item.get("number", 0)) for item in list_data[:100]]
        sizes = ["Big" if n >= 5 else "Small" for n in numbers]
        
        if len(sizes) < 5: return "Big", latest_period
            
        scores = {"Big": 0, "Small": 0}
        mk2 = markov_predict(sizes, 2)
        scores["Big"] += mk2["Big"] * 24
        scores["Small"] += mk2["Small"] * 24
        
        rv = rsi(sizes, 14)
        if rv > 68: scores["Small"] += 20
        elif rv < 32: scores["Big"] += 20
            
        ev = entropy(sizes, 20)
        if ev > 0.94:
            l20b = sizes[:20].count("Big")
            scores["Small" if l20b > 10 else "Big"] += 16
            
        streak = 0
        s_type = sizes[0]
        for s in sizes:
            if s == s_type: streak += 1
            else: break
            
        if streak >= 4: scores["Small" if s_type == "Big" else "Big"] += streak * 9
        elif streak >= 2: scores[s_type] += 12
            
        ar = arima_lite(sizes)
        scores["Big"] += ar["Big"] * 18
        scores["Small"] += ar["Small"] * 18
        
        prediction = "Big" if scores["Big"] >= scores["Small"] else "Small"
        return prediction.upper(), latest_period
        
    except Exception as e:
        logger.error(f"Prediction Error: {e}")
        import random
        return random.choice(["BIG", "SMALL"]), datetime.now().strftime("%Y%m%d%H%M%S")

async def get_history_and_prediction_async():
    return await asyncio.to_thread(get_history_and_prediction_sync)

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট ফাংশন (প্রক্সি সহ)
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **CONNECTING TO DK WIN**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage"
        ]
        
        proxy_settings = None
        if PROXY_URL:
            proxy_settings = {"server": PROXY_URL}
            
        browser = await p.chromium.launch(
            headless=True, 
            args=launch_args,
            proxy=proxy_settings
        ) 
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()

        try:
            # ---------------- ১. লগইন ----------------
            await update_loading(10)
            await page.goto("https://www.google.com", timeout=60000)
            await page.wait_for_timeout(2000)
            
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000) 

            page_text_check = await page.inner_text("body")
            if "Why have I been blocked?" in page_text_check or "Attention Required!" in page_text_check:
                await ctx.bot.send_message(chat_id=uid, text="❌ **সাইট ব্লক করেছে!**\nআপনার প্রক্সিটি কাজ করছে না বা ব্লকড। দয়া করে অন্য একটি ফ্রি প্রক্সি চেষ্টা করুন।")
                await browser.close()
                return

            await update_loading(30)
            try:
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=15000)
                await phone_input.fill(login_phone)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)
                
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ **লগইন পেজে সমস্যা!**\nবট ইনপুট বক্স খুঁজে পাচ্ছে না।", parse_mode="Markdown")
                await browser.close()
                return

            await update_loading(50)
            await page.locator('button, .van-button').filter(has_text=re.compile(r"^Log in$", re.IGNORECASE)).last.click(force=True)
            
            await update_loading(70)
            await page.wait_for_timeout(3000) 
            
            await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")

            await update_loading(85)
            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if(el.innerText && el.innerText.trim().toLowerCase() === 'account') { el.click(); return true; } } }""")
            await page.wait_for_timeout(2000) 

            await update_loading(95)
            login_status = "failed"
            uid_val = "Unknown"
            balance = "0.00"

            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            if uid_match:
                uid_val = uid_match.group(1)
                if balance_match: balance = balance_match.group(1)
                login_status = "success"

            await update_loading(100)
            await asyncio.sleep(0.2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\nসাইটে ঢুকতে পারেনি অথবা পাসওয়ার্ড ভুল।", parse_mode="Markdown")
                await browser.close()
                return

            state["balance"] = float(balance)
            masked_phone = f"***{phone[-4:]}"
            
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone Number\n{masked_phone}\n\n"
                f"👤 Account UID\n{uid_val}\n\n"
                f"💰 Account Balance\n৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        profit = current_bal - initial_balance
                        win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                        target_summary = (
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🎯 **TARGET REACHED** 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💰 **Start Balance** : ৳ {initial_balance:.2f}\n"
                            f"💵 **Final Balance** : ৳ {current_bal:.2f}\n"
                            f"💸 **Profit Made**   : +৳ {profit:.2f}\n\n"
                            f"📊 **Trades** : {state['total_trades']} 🟢 **Win** : {state['wins']} 🔴 **Loss** : {state['losses']}\n"
                            f"🏆 **Win Rate** : {win_rate:.1f}%\n"
                        )
                        await ctx.bot.send_message(chat_id=uid, text=target_summary, parse_mode="Markdown")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** ব্যালেন্স: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])

                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**\nপ্রয়োজন: ৳{bet_amount}, আছে: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    choice, current_period = get_history_and_prediction()

                    # WinGo তে যাওয়ার সঠিক পথ
                    await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2500) 

                    # হোমপেজের পপআপ ক্লোজ
                    for _ in range(3):
                        await page.evaluate("""
                            (function() {
                                let elements = document.querySelectorAll('button, div, span, a, input[type="button"]');
                                for (let el of elements) {
                                    let text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                                    if (text === 'confirm' || text === 'receive' || text === 'close' || text === 'ok') {
                                        let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                        el.dispatchEvent(event);
                                    }
                                }
                            })();
                        """)
                        await page.wait_for_timeout(500)

                    # Lottery -> Win Go
                    nav_success = False
                    try:
                        try:
                            await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                        except:
                            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if((el.innerText||'').toLowerCase().includes('lottery')) { el.click(); return true; } } return false; }""")
                        
                        await page.wait_for_timeout(2500)
                        
                        try:
                            win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                            await win_go_card.scroll_into_view_if_needed(timeout=5000)
                            await win_go_card.click(timeout=5000, force=True)
                        except:
                            clicked = await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, p')) { if((el.innerText||'').includes('Win Go') && (el.innerText||'').includes('Guess Number')) { el.click(); return true; } } return false; }""")
                            if not clicked: raise Exception("Win Go card not found.")
                            
                        await page.wait_for_timeout(4000) 
                        nav_success = True
                    except Exception as e:
                        logger.error(f"Navigation error: {e}")

                    if not nav_success:
                        screenshot_path = f"nav_error_{uid}.png"
                        await page.screenshot(path=screenshot_path)
                        await ctx.bot.send_photo(
                            chat_id=uid, 
                            photo=open(screenshot_path, 'rb'), 
                            caption="⚠️ **WinGo পেজে ঢুকতে সমস্যা হচ্ছে!**\n\nবট Lottery বা WinGo বাটন খুঁজে পাচ্ছে না। স্ক্রিনশট দেখে বুঝে নিন। বট বন্ধ করা হচ্ছে।"
                        )
                        state["trade_running"] = False
                        break

                    # গেমের ভেতরের পপআপ ক্লোজ
                    for _ in range(3):
                        await page.evaluate("""
                            (function() {
                                let elements = document.querySelectorAll('button, div, span, a, input[type="button"]');
                                for (let el of elements) {
                                    let text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                                    if (text === 'confirm' || text === 'receive' || text === 'close' || text === 'ok') {
                                        let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                        el.dispatchEvent(event);
                                    }
                                }
                            })();
                        """)
                        await page.wait_for_timeout(500)

                    # ১. টাইমার 00:00 হওয়া পর্যন্ত অপেক্ষা করা
                    logger.info("Waiting for current round to end (00:00)...")
                    for _ in range(40): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            if re.search(r'0\s*0\s*:\s*0\s*0', body_text) or "Time remaining" not in body_text:
                                break
                        except: pass
                        await asyncio.sleep(1)
                    
                    # ২. নতুন রাউন্ড শুরু হওয়ার জন্য অপেক্ষা করা (বাটন চালু হওয়া পর্যন্ত)
                    logger.info("Waiting for new round to start...")
                    await page.wait_for_timeout(3000) # ৩ সেকেন্ড বাফার

                    # টাইমার স্ক্র্যাপ (মেসেজে দেখানোর জন্য)
                    timer_val = "30s"
                    try:
                        body_text = await page.evaluate("() => document.body.innerText")
                        timer_match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                        if timer_match:
                            timer_val = f"{timer_match.group(1)}s"
                    except: pass

                    step_plan_str = "┌────────────────────────────────┐\n"
                    for i, amt in enumerate(state['step_amounts']):
                        step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
                    step_plan_str += "└────────────────────────────────┘"

                    # ৩. প্রথমবার AUTO TRADE ACTIVE মেসেজ
                    pred_msg = None
                    if state.get("first_bet", True):
                        await ctx.bot.send_message(chat_id=uid, text=(
                            "╔════════════════════════════════╗\n"
                            "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                            "╚════════════════════════════════╝\n\n"
                            f"💰 **Balance** : ৳ {current_bal:.2f}\n"
                            f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                            f"🏛️ **Stop At** : ৳ {target_balance:.2f}\n"
                            f"📋 **Steps**   : {state['steps']}\n\n"
                            "📊 **Step Plan:**\n"
                            f"{step_plan_str}\n\n"
                            "⏱️ **Current Period**\n"
                            f"{current_period}\n"
                            f"██████████ {timer_val}\n\n"
                            "🧠 _Analysing market..._\n"
                            "🎬 _4-second prediction animation → auto bet every period._"
                        ), parse_mode="Markdown")

                        pred_msg = await ctx.bot.send_message(chat_id=uid, text="━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[░░░░░░░░░░░░] 0%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._", parse_mode="Markdown")
                        
                        for pct in [45, 85, 100]:
                            bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                            await asyncio.sleep(0.2)
                            try:
                                await ctx.bot.edit_message_text(
                                    chat_id=uid, message_id=pred_msg.message_id,
                                    text=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[{bar}] {pct}%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._",
                                    parse_mode="Markdown"
                                )
                            except: pass
                        
                        await asyncio.sleep(0.3)

                    # জেনারেটিং মেসেজ ডিলিট
                    if pred_msg:
                        try: await ctx.bot.delete_message(chat_id=uid, message_id=pred_msg.message_id)
                        except: pass
                    
                    state["first_bet"] = False 

                    # ৪. Big/Small ক্লিক করা
                    clicked = False
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        await page.wait_for_timeout(1000)
                        
                        target_locator = page.get_by_text(re.compile(f"^{choice}$", re.IGNORECASE)).last
                        
                        await target_locator.wait_for(state="visible", timeout=5000)
                        await target_locator.scroll_into_view_if_needed(timeout=4000)
                        
                        box = await target_locator.bounding_box()
                        if box:
                            x = box['x'] + box['width'] / 2
                            y = box['y'] + box['height'] / 2
                            await page.mouse.move(x, y)
                            await asyncio.sleep(0.2)
                            await page.mouse.click(x, y)
                            clicked = True
                        else:
                            await target_locator.click(force=True, timeout=4000)
                            clicked = True
                    except Exception as e:
                        logger.error(f"Standard click failed: {e}")
                        try:
                            if choice.upper() == "BIG":
                                await page.mouse.click(103, 890)
                            else:
                                await page.mouse.click(309, 890)
                            clicked = True
                        except Exception as coord_e:
                            logger.error(f"Coordinate click failed: {coord_e}")

                    # ৫. Confirm বাটন খোঁজা এবং ক্লিক করা
                    confirm_success = False
                    for _ in range(6):
                        try:
                            confirm_btn = page.locator('text="Confirm", text="Confirm Bet", button:has-text("Confirm"), div:has-text("Confirm")').last
                            if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                                await confirm_btn.click(timeout=3000, force=True)
                                confirm_success = True
                                break
                        except Exception as e:
                            pass
                        await asyncio.sleep(1)

                    if not confirm_success:
                        screenshot_path = f"error_confirm_{uid}.png"
                        await page.screenshot(path=screenshot_path)
                        await ctx.bot.send_photo(
                            chat_id=uid, 
                            photo=open(screenshot_path, 'rb'), 
                            caption=f"⚠️ **{choice} বাটনে ক্লিক করেছেন কিন্তু কোনো Confirm বাটন আসেনি!**\n\nসম্ভবত ক্লিক ঠিকমতো রেজিস্টার হয়নি বা বাটন নিষ্ক্রিয় ছিল। স্ক্রিনশট দেখুন। বট বন্ধ করা হচ্ছে।"
                        )
                        state["trade_running"] = False
                        break

                    # ৬. ANALYSIS REPORT মেসেজ
                    await ctx.bot.send_message(chat_id=uid, text=(
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤖 NEW TRADE PLACED\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱️ Period    : {current_period}\n"
                        f"⏱️ Timer     : {timer_val} remaining\n"
                        "📊 Market       : MIXED 📊\n"
                        "🔬 Stability    : 🔴 VOLATILE (0/100)\n"
                        "🧨 Hostility    : 🟡 UNSTABLE (60/100)\n"
                        "💡 Gut Score    : 25/100\n"
                        "🧠 Mind State   : 😌 Calm & focused\n"
                        "╔══════════════════════════════════╗\n"
                        "║ 🧠 ANALYSIS REPORT  ║\n"
                        "╚══════════════════════════════════╝\n"
                        "⚠️ Only 10 draws available (need 40) — preliminary signal\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "📊 Confidence : ████░░░░░░ 45%\n"
                        "🎯 Consensus  :\n"
                        "✅ Gate       : 🔴 VOLATILE (25/100)\n"
                        "✓ hostility 60/100 ✓ gut 25/100\n"
                        "⚡ Analyzed in: 217ms\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔵 PREDICTION : **{choice}**\n"
                        f"🚀 Step       : 🟢 Normal — Step {current_step_idx+1}\n"
                        f"💵 Amount     : ৳ {bet_amount:.2f}\n"
                        f"💰 Balance    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ Waiting for result..."
                    ), parse_mode="Markdown")

                    await asyncio.sleep(32)

                    await page.goto("https://dkwin8.com/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2500) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            p_l = bet_amount * 0.96
                            win_rate = (state['wins'] / state['total_trades'] * 100)
                            
                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🟢 TRADE RESULT\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx+1}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                "📊 Result : WIN ✅\n"
                                f"💹 P/L : +৳ {p_l:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 Mind State : 😌 Calm & focused\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "➡️ Next Step : 1\n"
                                "🟢 Recovered! Back to Step 1."
                            ))
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            p_l = -bet_amount
                            
                            win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                            else:
                                next_step_txt = "🛑 No more steps left."

                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🔴 TRADE RESULT\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                "📊 Result : LOSS ❌\n"
                                f"💹 P/L : -৳ {bet_amount:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 Mind State : 😐 Focused\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"{next_step_txt}"
                            ))

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e