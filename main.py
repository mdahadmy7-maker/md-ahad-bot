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

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.site/#/login"
HOME_URL = "https://www.hgnice.site/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "balance": "0.00", "target": 0, "steps": 0, "step_amounts": [], 
            "current_step": 0, "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. প্রেডিকশন লজিক
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
    
    async def status_msg(text):
        try:
            await ctx.bot.send_message(chat_id=uid, text=f"🔍 **DEBUG:** {text}")
        except: pass

    async def update_loading(percent):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        async def log_bet_api(request):
            if request.method == "POST" and "WinGoBet" in request.url:
                try:
                    await ctx.bot.send_message(chat_id=uid, text=f"🚨 **BET API CAPTURED!**\n`{request.post_data}`", parse_mode="Markdown")
                except: pass
        page.on("request", log_bet_api)

        try:
            # ---------------- ১. লগইন ----------------
            await status_msg("Opening Login Page...")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            await status_msg("Filling credentials...")
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except Exception as e:
                await status_msg(f"Fill error: {str(e)[:50]}")

            await status_msg("Clicking Login Button...")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            await status_msg("Handling popups...")
            for _ in range(5):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)

            await status_msg("Checking login status...")
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
                    login_status = "failed"
                    break
                
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(500)

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
                await browser.close()
                return

            state["balance"] = float(balance)
            if loading_msg_id: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)

            await ctx.bot.send_message(
                chat_id=uid, 
                text=f"🎉 **LOGIN SUCCESSFUL** ✅\n💰 Balance: ৳ {balance}",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE")]], resize_keyboard=True)
            )

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. WinGo পেজে যাওয়া ----------------
            await status_msg("Navigating to Game Page...")
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) 
            
            nav_success = False
            for attempt in range(15):
                body_text = await page.evaluate("() => document.body.innerText")
                if "Time remaining" in body_text or ("Big" in body_text and "Small" in body_text):
                    nav_success = True
                    await status_msg("Game Page Loaded!")
                    break
                
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)
                
                try:
                    await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a, p')) { let t = (el.innerText||'').toLowerCase(); if(t === 'lottery' || (t.includes('win go') && t.includes('guess number'))) { el.click(); } } }""")
                except: pass
                await page.wait_for_timeout(1500) 

            if not nav_success:
                await ctx.bot.send_message(chat_id=uid, text="❌ **WinGo পেজে ঢুকতে সমস্যা হচ্ছে!** স্ক্রিনে পপআপ থাকতে পারে।")
                state["trade_running"] = False
                await browser.close()
                return

            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            await ctx.bot.send_message(chat_id=uid, text=f"🚀 **AUTO TRADE ACTIVE**\n🎯 Target: ৳{state['target']}\n📋 Steps: {state['steps']}\n\n_Waiting for new result to tap..._")

            # ---------------- ৫. মেইন বেটিং লুপ ----------------
            last_period_on_screen = ""

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance or current_step_idx >= len(state['step_amounts']) or current_bal < float(state['step_amounts'][current_step_idx]):
                        await ctx.bot.send_message(chat_id=uid, text="🛑 **TARGET REACHED OR NO BALANCE!**")
                        state["trade_running"] = False
                        break

                    body_text = await page.evaluate("() => document.body.innerText")
                    period_matches = re.findall(r'\b(202\d{14})\b', body_text)
                    
                    if not period_matches:
                        await asyncio.sleep(0.5)
                        continue
                        
                    current_period = period_matches[0]

                    timer_match = re.search(r'0\s*0\s*[:.]\s*(\d{2})', body_text)
                    current_sec = 30
                    if timer_match: current_sec = int(timer_match.group(1))

                    if current_period != last_period_on_screen:
                        await status_msg(f"New Period Detected: {current_period} (Timer: {current_sec}s)")
                        last_period_on_screen = current_period
                        
                        if current_sec < 7:
                            await status_msg("Timer too low, skipping...")
                            await asyncio.sleep(2)
                            continue

                        bet_amount = float(state['step_amounts'][current_step_idx])
                        choice, api_period = await get_history_and_prediction_async()
                        await status_msg(f"Prediction: {choice}. Clicking...")

                        # 💡 Big/Small ক্লিক
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        await page.wait_for_timeout(300)
                        
                        js_click_script = f"""
                        (() => {{
                            let els = document.querySelectorAll('div, span, button');
                            for (let el of els) {{
                                if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                    let rect = el.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) {{
                                        el.click();
                                        return true;
                                    }}
                                }}
                            }}
                            return false;
                        }})()
                        """
                        clicked = await page.evaluate(js_click_script)
                        
                        if not clicked:
                            try:
                                if choice.upper() == "BIG": await page.mouse.click(103, 890)
                                else: await page.mouse.click(309, 890)
                            except: pass

                        await status_msg("Entering Amount...")
                        try:
                            inputs = await page.locator('input[type="text"], input[type="number"]').all()
                            for inp in inputs:
                                if await inp.is_visible():
                                    await inp.click(force=True)
                                    await page.keyboard.press("Control+A")
                                    await page.keyboard.press("Backspace")
                                    await inp.type(str(int(bet_amount)), delay=20)
                                    break
                        except: pass

                        try:
                            agree_box = page.locator('text="I agree"').last
                            if await agree_box.count() > 0 and await agree_box.is_visible():
                                await agree_box.click(force=True, timeout=1000)
                                await page.wait_for_timeout(200)
                        except: pass

                        await status_msg("Clicking Total Amount...")
                        js_confirm_bet = """
                        (() => {
                            for(let el of document.querySelectorAll('button, div, span')) {
                                if(el.innerText && el.innerText.toLowerCase().includes('total amount')) {
                                    el.click(); 
                                    return true;
                                }
                            }
                            return false;
                        })()
                        """
                        confirm_success = False
                        for _ in range(10): 
                            confirm_success = await page.evaluate(js_confirm_bet)
                            if confirm_success: break
                            await page.wait_for_timeout(500)

                        if not confirm_success:
                            try: await page.mouse.click(309, 880)
                            except: pass

                        await page.wait_for_timeout(2000)
                        proof_path = f"proof_success_{uid}.png"
                        await page.screenshot(path=proof_path)
                        
                        await ctx.bot.send_photo(
                            chat_id=uid, 
                            photo=open(proof_path, 'rb'), 
                            caption=f"✅ **BET PLACED!**\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}"
                        )

                        await asyncio.sleep(25)
                        await page.evaluate("window.scrollTo(0, 0);")
                        await page.wait_for_timeout(2000) 
                        
                        new_page_text = await page.evaluate("() => document.body.innerText")
                        new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                        
                        if new_balance_match:
                            new_balance = float(new_balance_match.group(1))
                            state['total_trades'] += 1
                            
                            if new_balance > current_bal:
                                state["balance"] = new_balance
                                state["wins"] += 1
                                current_step_idx = 0
                                await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: 1")
                            else:
                                state["balance"] = new_balance
                                state["losses"] += 1
                                current_step_idx += 1
                                
                                if current_step_idx < len(state['step_amounts']):
                                    next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                                else:
                                    next_step_txt = "🛑 No more steps left."

                                await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n{next_step_txt}")

                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        await page.wait_for_timeout(1000)
                    else:
                        await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# হ্যান্ডলারগুলো
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 NovaBrainV7 Engine\n"
        "🚀 Analysis → auto bet every 30s period\n\n"
        "👇 Press the button below to LOGIN"
    )
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number : {text}\n🔑 Now enter your password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text(f"💰 YOUR BALANCE\n৳ {state.get('balance', '0.00')}\n\n🎯 Enter your TARGET profit amount:")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text(f"🎯 Target: ৳ {float(text):.2f}\n\n🚀 Enter your STEP COUNT:")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — bet amount?")
        except ValueError:
            await update.message.reply_text("❌ সংখ্যা দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            state["step_amounts"].append(float(text))
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount?")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]])
                await update.message.reply_text("⚙️ CONFIGURATION DONE.\n👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ সংখ্যা দিন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        await update.message.reply_text("🚪 LOGGED OUT")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your HGNICE phone number:")
    elif query.data == "start_trade_btn":
        state["trade_running"] = True
    elif query.data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()