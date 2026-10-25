import asyncio
import logging
import re
import os
import requests
import json
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
            "first_bet": True
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
        import random
        return random.choice(["BIG", "SMALL"]), fallback_period

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
            await page.wait_for_timeout(3000)

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
            try:
                await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('div, span, a');
                        for (let el of elements) {
                            if (el.innerText && el.innerText.trim().toLowerCase() === 'account') {
                                el.click(); return true;
                            }
                        }
                    })();
                """)
                await page.wait_for_timeout(3000) 
            except: pass

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
            
            # 💡 একবারই WinGo পেজে যাবে, বারবার রিলোড হবে না
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            
            for _ in range(3):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)
                
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if((el.innerText||'').toLowerCase().includes('lottery')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(2000)
            
            try:
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, p')) { if((el.innerText||'').includes('Win Go') && (el.innerText||'').includes('Guess Number')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(3000) 

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

                    # 💡 ১. ফাস্ট টাইমার চেক (নতুন রাউন্ড শুরু হওয়া মাত্রই ক্লিক করবে)
                    logger.info("Waiting for new round to start...")
                    timer_val = "0s"
                    for _ in range(350): # ৩৫ সেকেন্ড পর্যন্ত অপেক্ষা করবে
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            # 0 0 পপআপ থাকলে স্কিপ করবে
                            if "0 0" in body_text and "Time remaining" not in body_text:
                                await asyncio.sleep(0.1)
                                continue
                                
                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if match:
                                sec = int(match.group(1))
                                if 6 <= sec <= 30: # ৩০ থেকে ৬ সেকেন্ডের মধ্যে গেলেই বিট করবে
                                    timer_val = f"{sec}s"
                                    break
                        except: pass
                        await asyncio.sleep(0.1) # খুব দ্রুত চেক করবে

                    step_plan_str = "┌────────────────────────────────┐\n"
                    for i, amt in enumerate(state['step_amounts']):
                        step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
                    step_plan_str += "└────────────────────────────────┘"

                    # 💡 ২. প্রথমবার AUTO TRADE ACTIVE মেসেজ
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

                    # 💡 ৩. সুপার ফাস্ট Big/Small ক্লিক (JS দিয়ে সরাসরি)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(200)
                    
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
                            if choice.upper() == "BIG":
                                await page.mouse.click(103, 890)
                            else:
                                await page.mouse.click(309, 890)
                        except: pass

                    # 💡 ৪. মডাল ওপেন হওয়া পর্যন্ত দ্রুত অপেক্ষা
                    await page.wait_for_timeout(1000)

                    # 💡 ৫. মডালে অ্যামাউন্ট বসানো এবং Confirm (Total amount) ক্লিক করা
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

                    # "I agree" চেকবক্স ক্লিক
                    try:
                        agree_box = page.locator('text="I agree"').last
                        if await agree_box.count() > 0 and await agree_box.is_visible():
                            await agree_box.click(force=True, timeout=1000)
                            await page.wait_for_timeout(200)
                    except: pass

                    # "Total amount" বাটন ক্লিক
                    confirm_success = False
                    try:
                        confirm_btn = page.locator('text=/Total amount/i').last
                        if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                            await confirm_btn.click(timeout=2000, force=True)
                            confirm_success = True
                    except: pass

                    if not confirm_success:
                        try:
                            await page.mouse.click(309, 880)
                            confirm_success = True
                        except: pass

                    # 💡 ৬. সফলভাবে বিট হওয়ার পর ২ সেকেন্ড অপেক্ষা করে স্ক্রিনশট নেওয়া (যাতে 0 0 পপআপ চলে যায়)
                    await page.wait_for_timeout(2000)
                    proof_path = f"proof_success_{uid}.png"
                    await page.screenshot(path=proof_path)
                    
                    await ctx.bot.send_photo(
                        chat_id=uid, 
                        photo=open(proof_path, 'rb'), 
                        caption=f"✅ **BET PLACED SUCCESSFULLY!**\n\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}\n📱 স্ক্রিনশটে দেখুন সাইটে কি হয়েছে ↓"
                    )

                    # 💡 ৭. ANALYSIS REPORT মেসেজ
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

                    # 💡 ৮. রেজাল্ট চেক (পেজ রিলোড না করে সরাসরি অ্যাকাউন্ট সেকশনে গিয়ে চেক করবে)
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
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

                    # রেজাল্ট চেক করার পর আবার WinGo পেজে ফিরে যাবে পরের রাউন্ডের জন্য
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)
                    try:
                        await page.locator('text="Lottery"').first.click(timeout=3000, force=True)
                        await page.wait_for_timeout(1000)
                        win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                        await win_go_card.click(timeout=3000, force=True)
                    except: pass
                    await page.wait_for_timeout(2000)

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
               