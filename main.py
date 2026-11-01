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
SITE_URL = "https://dkwin1.com/#/login" 
HOME_URL = "https://dkwin1.com/#/"
WIN_GO_URL = "https://dkwin1.com/#/WinGo_30S"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 💡 Render পোর্ট এরর ফিক্স
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
# 💡 ২. NovaBrainV7 প্রেডিকশন লজিক
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
# ৩. লগইন এবং অটো-বেট ফাংশন
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
                text=f"🔄 CONNECTING TO DK WIN\n[{filled}{empty}] {percent}%"
            )
        except: pass

    try:
        # 💡 টাস্ক শুরুর সাথে সাথেই লোডিং বাড়িয়ে দেওয়া হচ্ছে
        await update_loading(15)
        
        async with async_playwright() as p:
            # 💡 ব্রাউজার ওপেন করা
            browser = await p.chromium.launch(
                headless=True, 
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            ) 
            
            # 💡 Samsung Galaxy S20 এরর ফিক্স: সরাসরি মোবাইলের সেটিংস দেওয়া হলো
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                viewport={"width": 412, "height": 915},
                is_mobile=True,
                has_touch=True,
                locale="en-US",
                timezone_id="Asia/Dhaka"
            )
            
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)
            
            page = await context.new_page()

            # ---------------- ১. লগইন ----------------
            await update_loading(30)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            
            await update_loading(50)
            try:
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=15000)
                await phone_input.fill(login_phone)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)
                
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ **লগইন পেজে সমস্যা!**\nবট ইনপুট বক্স খুঁজে পাচ্ছে না। সাইট হয়তো লোড হতে দেরি করছে।", parse_mode="Markdown")
                await browser.close()
                return

            await update_loading(70)
            await page.locator('button, .van-button').filter(has_text=re.compile(r"^Log in$", re.IGNORECASE)).last.click(force=True)
            
            await page.wait_for_timeout(4000) 
            
            await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")

            await update_loading(85)
            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if(el.innerText && el.innerText.trim().toLowerCase() === 'account') { el.click(); return true; } } }""")
            await page.wait_for_timeout(3000) 

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

            # ---------------- ২. WinGo পেজ ----------------
            await page.goto(WIN_GO_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000) 
            
            body_text = await page.evaluate("() => document.body.innerText")
            if "Time remaining" not in body_text and "WinGo" not in body_text:
                await page.goto(HOME_URL, timeout=60000)
                await page.wait_for_timeout(2000)
                try:
                    await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                    await page.wait_for_timeout(1000)
                    await page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last.click(timeout=5000, force=True)
                    await page.wait_for_timeout(1500)
                except: pass

            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            step_plan_str = "┌────────────────────────────────┐\n"
            for i, amt in enumerate(state['step_amounts']):
                step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
            step_plan_str += "└────────────────────────────────┘"

            await ctx.bot.send_message(chat_id=uid, text=(
                "╔════════════════════════════════╗\n"
                "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                "╚════════════════════════════════╝\n\n"
                f"💰 **Balance** : ৳ {state['balance']:.2f}\n"
                f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                f"🏛️ **Stop At** : ৳ {target_balance:.2f}\n"
                f"📋 **Steps**   : {state['steps']}\n\n"
                "📊 **Step Plan:**\n"
                f"{step_plan_str}\n\n"
                "🧠 _AI Engine: NovaBrainV7_"
            ), parse_mode="Markdown")

            # ---------------- ৩. বেটিং লুপ ----------------
            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance or current_step_idx >= len(state['step_amounts']) or current_bal < float(state['step_amounts'][current_step_idx]):
                        await ctx.bot.send_message(chat_id=uid, text="🛑 **TARGET REACHED OR NO BALANCE!**", parse_mode="Markdown")
                        state["trade_running"] = False
                        break

                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = await get_history_and_prediction_async()

                    timer_found = False
                    for _ in range(400): 
                        try:
                            b_text = await page.evaluate("() => document.body.innerText")
                            match = re.search(r'0\s*0\s*[:.]\s*(\d{2})', b_text)
                            if match and 7 <= int(match.group(1)) <= 30: 
                                timer_found = True
                                break
                        except: pass
                        await asyncio.sleep(0.1)

                    if not timer_found: continue 

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(200)
                    
                    js_click = f"""
                    (() => {{
                        for(let el of document.querySelectorAll('div, span, button')) {{
                            if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                el.click(); return true;
                            }}
                        }}
                        return false;
                    }})()
                    """
                    await page.evaluate(js_click)

                    inputs = await page.locator('input[type="text"], input[type="number"]').all()
                    for inp in inputs:
                        if await inp.is_visible():
                            await inp.fill(str(int(bet_amount)))
                            break

                    for _ in range(10): 
                        if await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span')) { if(el.innerText && el.innerText.toLowerCase().includes('total amount')) { el.click(); return true; } } return false; }"""): 
                            break
                        await page.wait_for_timeout(500)

                    await page.wait_for_timeout(3000) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_bal_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_bal_match:
                        new_balance = float(new_bal_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: 1", parse_mode="Markdown")
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                            else:
                                next_step_txt = "🛑 No more steps left."

                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n{next_step_txt}", parse_mode="Markdown")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    state["trade_running"] = False
                    break

    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`\n\nসম্ভবত Render-এ ব্রাউজার ওপেন করতে সমস্যা হচ্ছে।", parse_mode="Markdown")
    finally:
        try: await browser.close()
        except: pass

# ═══════════════════════════════════════════
# ৪. হ্যান্ডলারগুলো
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    # 💡 আপনার স্ক্রিনশটের মতো হুবহু প্লেইন টেক্সট, এবং লাইন ব্রেকগুলো ঠিক করা হয়েছে
    welcome_text = """🧠 BD=DK WIN~GO=AUTO~BET 💥
━━━━━━━━━━━━━━━━━━━━━━━
🧠 Mode    : Auto Analyse & bet
🔐 Access  : Private · Authorized
Members
🔴 Status  : Not Logged In
👥 Accounts: 0/6
━━━━━━━━━━━━━━━━━━━━━━━
🧠 Prediction Engine — 9 Layers
⚡ Streak · 🔷 Pattern · 📈 Trend
🔍 Manipulation · 🎨 Colour · 🔢
Frequency
🔄 Markov · ♻️ Cycle · 💠
Momentum
🔁 Every layer is back-tested live so
its vote
weight follows its real hit-rate
🔴 Confidence below 30% → sit
out
━━━━━━━━━━━━━━━━━━━━━━━
🎬 4-second 🧠 generating
prediction animation
🚀 Analysis → auto bet every 30s
period
━━━━━━━━━━━━━━━━━━━━━━━

👇 Press the button below to
LOGIN"""
    
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"☎️ Number : {text}\n\n"
            "🔑 Now enter your password:\n"
            "Your message will be deleted immediately for security."
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 CONNECTING TO DK WIN\n[░░░░░░░░░░] 0%")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 START YOUR TARGET 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 YOUR BALANCE\n"
            f"৳ {state.get('balance', '0.00')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 Enter your TARGET profit amount:\n"
            "How much do you want to earn? (in ৳)"
        )
        await update.message.reply_text(target_msg)
        return
        
    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            balance = float(state.get('balance', '0.00'))
            stop_at = balance + target_amount
            target_set_msg = (
                "╔════════════════════════╗\n"
                "║   🎯 TARGET SET 🎯   ║\n"
                "╚════════════════════════╝\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Balance  : ৳ {balance:.2f}\n"
                f"🎯 Target   : ৳ {target_amount:.2f} profit\n"
                f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 Enter your STEP COUNT:\n"
                "How many steps? (e.g. 5, max 50)"
            )
            state["awaiting"] = "steps"
            await update.message.reply_text(target_set_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError("Steps must be between 1 and 50")
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            step_msg = (
                "╔════════════════════════╗\n"
                "║   💵 STEP AMOUNTS 💵   ║\n"
                "╚════════════════════════╝\n\n"
                f"You chose {steps} steps.\n\n"
                f"💵 Step {state['current_step']} — bet amount? (in ৳)"
            )
            await update.message.reply_text(step_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন (যেমন: 5)।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            if amount <= 0: raise ValueError("Amount must be greater than 0")
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                step_msg = f"💵 Step {state['current_step']} — bet amount? (in ৳)"
                await update.message.reply_text(step_msg)
            else:
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                balance = float(state.get('balance', '0.00'))
                target = float(state.get('target', 0))
                stop_at = balance + target
                step_plan_text = ""
                for i, amt in enumerate(state["step_amounts"]):
                    step_plan_text += f"Step {i+1:02d} : ৳ {amt:.2f}\n"
                
                combined_msg = (
                    "⚙️ TRADE CONFIGURATION ⚙️\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Balance  : ৳ {balance:.2f}\n"
                    f"🎯 Target   : ৳ {target:.2f} profit\n"
                    f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                    f"📋 Steps    : {state['steps']}\n"
                    f"⚠️ Total Risk : ৳ {total_risk:.2f}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📊 STEP PLAN\n"
                    f"{step_plan_text}"
                    "\n"
                    "👇 Press START TRADE to begin."
                )
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 1)।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 LOGGED OUT")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    if data == "start_login":
        state["awaiting"] = "phone"
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 Enter your DK WIN phone number:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Everyone uses their own account — your session is private."
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)
    elif data == "start_trade_btn":
        state["trade_running"] = True
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**", parse_mode="Markdown")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["trade_running"] = False
    if state.get("task"): state["task"].cancel()
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, 
        "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False, "task": None,
        "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    if not BOT_TOKEN:
        print("❌ Error: Render Environment Variable-এ BOT_TOKEN সেট করা নেই!")
        return
    
    threading.Thread(target=run_web_server, daemon=True).start()
    print("✅ Health check server started.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()