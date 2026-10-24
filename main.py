import asyncio
import logging
import re
import os
import requests
import json
import time
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.vip/#/login"
HOME_URL = "https://www.hgnice.vip/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
BET_API = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True, "token": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. API থেকে রেজাল্ট ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(HISTORY_API, headers=headers, timeout=10)
        data = res.json()
        
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        reversed_list = list(reversed(list_data))
        
        history = []
        for item in reversed_list:
            num = int(item.get("number", 0))
            history.append("SMALL" if num <= 4 else "BIG")
            
        if len(history) == 0: return "BIG", latest_period
        if len(history) < 3:
            return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
            
        if n >= 4:
            l4 = history[n-4]
            if l4 == l3 and l2 == l1 and l4 != l3:
                return l4, latest_period
            if l4 == l2 and l3 == l1 and l4 != l3:
                return l4, latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        fallback_period = datetime.now().strftime("%Y%m%d%H%M%S")
        return random.choice(["BIG", "SMALL"]), fallback_period

# ───────────────────────────────────────────
# 💡 ৩. API-এর মাধ্যমে বেট প্লেস করার ফাংশন
# ───────────────────────────────────────────
def place_bet_via_api(token, issue_number, amount, choice):
    bet_content = "BigSmall_Big" if choice.upper() == "BIG" else "BigSmall_Small"
    timestamp = int(time.time())
    random_num = random.randint(100000000000, 999999999999)
    
    # ⚠️ দ্রষ্টব্য: এটি আপনার দেওয়া স্ট্যাটিক সিগনেচার। 
    # যদি প্রতিবার সিগনেচার এরর দেয়, তবে আমাদের সাইটের JS থেকে সিগনেচার জেনারেটরের কোড বের করতে হবে।
    signature = "EFF38AC7BE22ADB66E82B27FBA14D4A0" 
    
    payload = {
        "gameCode": "WinGo_30S",
        "issueNumber": str(issue_number),
        "amount": int(amount),
        "betMultiple": 1,
        "betContent": bet_content,
        "language": "en",
        "random": random_num,
        "signature": signature,
        "timestamp": timestamp
    }
    
    headers = {
        'authority': 'api.ar-lottery01.com',
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': f'Bearer {token}',
        'content-type': 'application/json',
        'origin': 'https://www.hgnice.vip',
        'referer': 'https://www.hgnice.vip/',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
    }

    try:
        response = requests.post(BET_API, headers=headers, json=payload, timeout=10)
        res_data = response.json()
        logger.info(f"Bet API Response: {res_data}")
        return res_data
    except Exception as e:
        logger.error(f"Bet API Error: {e}")
        return None

# ───────────────────────────────────────────
# ৪. লগইন এবং অটো-বেট ফাংশন
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
        
        try:
            # ---------------- ১. লগইন ----------------
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            await update_loading(30)
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except: pass

            await update_loading(50)
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            await update_loading(70)
            for _ in range(10):
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
                await page.wait_for_timeout(400)

            await update_loading(85)
            # টোকেন সংগ্রহ করা
            token = ""
            for _ in range(10):
                token = await page.evaluate("() => localStorage.getItem('access_token') || localStorage.getItem('token')")
                if token: break
                await page.wait_for_timeout(500)

            await update_loading(95)
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
                    if balance_match: 
                        balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(500)

            await update_loading(100)
            await asyncio.sleep(0.2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
                await browser.close()
                return

            # টোকেন না পেলে ফলব্যাক হিসেবে আপনার দেওয়া টোকেনটি ব্যবহার করবে
            if not token:
                token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJUb2tlblR5cGUiOiJBY2Nlc3NfVG9rZW4iLCJUZW5hbnRJZCI6IjEwMDciLCJVc2VySWQiOiIxMDA3MDAwMDU1MzA4OCIsIkFnZW50Q29kZSI6IjEwMDcwMSIsIlRlbmFudEFjY291bnQiOiI1NTMwODgiLCJMb2dpbklQIjoiMjQwMDpjNjAwOjU0NjU6ZWUzNDo6MSIsIkxvZ2luVGltZSI6IjE3OTI4NjI2MDY1MTMiLCJTeXNDdXJyZW5jeSI6IkJEVCIsIlN5c0xhbmd1YWdlIjoiZW4iLCJEZXZpY2VUeXBlIjoiUEMiLCJMb3R0ZXJ5TGltaXRHcm91cE51bSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJuYmYiOjE3OTI4NjI2MTksImV4cCI6MTc5Mjg2NjIxOSwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.Mj2IrFXGR_kizIXR9SzfSy2mPJmmuu15WecsDVy4TeY"

            state["token"] = token
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

            # WinGo পেজে যাবে শুধু Period এবং ব্যালেন্স আপডেট দেখার জন্য
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                await page.wait_for_timeout(2000)
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except: pass
            await page.wait_for_timeout(3000)

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ (API দিয়ে) ----------------
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

                    # 💡 ১. টাইমার চেক (৩০ থেকে ৬)
                    logger.info("Waiting for the timer to show 06s-30s...")
                    timer_val = "0s"
                    valid_timer = False
                    
                    for _ in range(300): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            
                            if "Select Big" in body_text or "Total amount" in body_text or "0 0" == body_text.strip():
                                await asyncio.sleep(0.1)
                                continue

                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if match:
                                sec = int(match.group(1))
                                if 6 <= sec <= 30: 
                                    timer_val = f"{sec}s"
                                    valid_timer = True
                                    break
                                elif sec < 6:
                                    break
                        except: pass
                        await asyncio.sleep(0.1) 

                    if not valid_timer:
                        logger.warning("Timer dropped below 6s or not found. Waiting for next round...")
                        await asyncio.sleep(2)
                        continue 

                    step_plan_str = "┌────────────────────────────────┐\n"
                    for i, amt in enumerate(state['step_amounts']):
                        step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
                    step_plan_str += "└────────────────────────────────┘"

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
                            "🎬 _Prediction animation → auto bet every period._"
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

                    if pred_msg:
                        try: await ctx.bot.delete_message(chat_id=uid, message_id=pred_msg.message_id)
                        except: pass
                    
                    state["first_bet"] = False 

                    # 💡 ২. API দিয়ে বেট করা
                    logger.info(f"Placing bet via API for {choice} amount {bet_amount}")
                    api_response = place_bet_via_api(state["token"], current_period, bet_amount, choice)
                    
                    if not api_response or not api_response.get("success"):
                        # যদি স্ট্যাটিক সিগনেচার কাজ না করে, তবে এরর দেখাবে
                        error_msg = api_response.get("msg", "Unknown Error") if api_response else "No Response"
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **API BET FAILED!**\nError: {error_msg}\n\nসম্ভবত Signature বা Token এর মেয়াদ শেষ।")
                        state["trade_running"] = False
                        break

                    # 💡 ৩. ANALYSIS REPORT
                    await ctx.bot.send_message(chat_id=uid, text=(
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤖 NEW TRADE PLACED (API)\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱️ Period    : {current_period}\n"
                        f"⏱️ Timer     : {timer_val} remaining\n"
                        f"🔵 PREDICTION : **{choice}**\n"
                        f"🚀 Step       : 🟢 Normal — Step {current_step_idx+1}\n"
                        f"💵 Amount     : ৳ {bet_amount:.2f}\n"
                        f"💰 Balance    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ Waiting for result..."
                    ), parse_mode="Markdown")

                    # 💡 ৪. নতুন রেজাল্ট না আসা পর্যন্ত অপেক্ষা
                    logger.info("Waiting for new round to start...")
                    for _ in range(40): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if match:
                                sec = int(match.group(1))
                                if 28 <= sec <= 30:
                                    break
                        except: pass
                        await asyncio.sleep(1)
                    
                    # 💡 ৫. উপরে স্ক্রল করে ব্যালেন্স চেক করবে
                    logger.info("Scrolling up to check balance...")
                    await page.evaluate("window.scrollTo(0, 0);")
                    await page.wait_for_timeout(1500)
                    
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
                    
                    # 💡 ৬. নিচে স্ক্রল করে আবার গেমে ফিরে আসবে
                    logger.info("Scrolling down to resume betting...")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(1500)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nCould not place bet. Error: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            state["trade_running"] = False
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
        f"👥 Accounts: {len(state['accounts'])}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak · 🔷 Pattern · 📈 Trend\n"
        "🔍 Manipulation · 🎨 Colour · 🔢 Frequency\n"
        "🔄 Markov · ♻️ Cycle · 💠 Momentum\n"
        "🔁 Every layer is back-tested live so its vote\n"
        "weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
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
            "📱 Enter your HGNICE phone number:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Everyone uses their own account — your session is private."
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)
    elif data == "start_trade_btn":
        state["trade_running"] = True
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["trade_running"] = False
    if state.get("task"): state["task"].cancel()
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, 
        "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False, "task": None,
        "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True, "token": ""
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()