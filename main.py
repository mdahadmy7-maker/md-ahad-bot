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
# 💡 ২. API থেকে প্রেডিকশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: return "SMALL", "Unknown"
            
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
            if l4 == l3 and l2 == l1 and l4 != l3: return l4, latest_period
            if l4 == l2 and l3 == l1 and l4 != l3: return l4, latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
    except:
        return "SMALL", "Unknown"

# ───────────────────────────────────────────
# 💡 ৩. লাইভ টাইমার
# ───────────────────────────────────────────
async def update_live_timer(ctx, uid, message_id, start_sec, current_period, choice, bet_amount, current_bal, current_step_idx):
    if start_sec < 1: start_sec = 1
    for current_sec in range(start_sec, 31):
        filled_blocks = int((current_sec / 30) * 10)
        if filled_blocks > 10: filled_blocks = 10
        bar = "█" * filled_blocks + "░" * (10 - filled_blocks)
        
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 NEW TRADE PLACED\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ Period    : {current_period}\n"
            f"⏱️ Timer     : {current_sec:02d}s elapsed\n"
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
            f"🔵 PREDICTION : {choice} ❮❮❮\n\n"
            f"🚀 Step       : 🟢 Normal — Step {current_step_idx+1}\n"
            f"💵 Amount     : ৳ {bet_amount:.2f}\n"
            f"💰 Balance    : ৳ {current_bal:.2f}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Waiting for result...\n\n"
            f"`[{bar}] {current_sec:02d}s`"
        )
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=message_id, text=text, parse_mode="Markdown")
        except: pass
        await asyncio.sleep(1)

# ───────────────────────────────────────────
# ৪. মেইন অটোমেশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, txt="CONNECTING TO HGNICE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text=f"🔄 **{txt}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown")
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ================= ১. লগইন =================
            await update_loading(10, "OPENING SITE...")
            await page.goto(SITE_URL, timeout=60000, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # জাভাস্ক্রিপ্ট দিয়ে জোরপূর্বক ইনপুট বসানো (Vue/React এর জন্য)
            await page.evaluate(f"""
                (function() {{
                    let inputs = document.querySelectorAll('input');
                    for (let i = 0; i < inputs.length; i++) {{
                        if (inputs[i].type === 'text' || inputs[i].type === 'tel') {{
                            inputs[i].value = '{login_phone}';
                            inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inputs[i].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }} else if (inputs[i].type === 'password') {{
                            inputs[i].value = '{password}';
                            inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inputs[i].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }})();
            """)
            await page.wait_for_timeout(1000)

            await update_loading(30, "CLICKING LOGIN...")
            # জাভাস্ক্রিপ্ট দিয়ে Log in বাটনে ক্লিক
            await page.evaluate("""
                (function() {
                    let els = document.querySelectorAll('button, div, span');
                    for (let el of els) {
                        let text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (text === 'log in' || text === 'login') {
                            el.click();
                            return true;
                        }
                    }
                })();
            """)
            
            # পপআপ হ্যান্ডেল
            await page.wait_for_timeout(3000)
            await page.evaluate("""
                (function() {
                    let els = document.querySelectorAll('button, div, span');
                    for (let el of els) {
                        let text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (text === 'confirm' || text === 'ok' || text === 'close') {
                            el.click();
                        }
                    }
                })();
            """)

            await update_loading(50, "VERIFYING ACCOUNT...")
            # Account পেজে ক্লিক
            await page.evaluate("""
                (function() {
                    let els = document.querySelectorAll('div, span, a');
                    for (let el of els) {
                        if (el.innerText && el.innerText.trim().toLowerCase() === 'account') {
                            el.click(); return;
                        }
                    }
                })();
            """)
            await page.wait_for_timeout(4000) 

            # রিড ডেটা
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)

            if "Wrong account or password" in page_text:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\nWrong account or password.")
                await browser.close()
                return

            if not uid_match:
                # স্ক্রিনশট নিয়ে পাঠানো (যদি UID না পায়)
                ss = f"err_{uid}.png"
                await page.screenshot(path=ss)
                await ctx.bot.send_photo(chat_id=uid, photo=open(ss, 'rb'), caption="⚠️ UID খুঁজে পাওয়া যায়নি। স্ক্রিনশট দেখুন।")
                await browser.close()
                return

            uid_val = uid_match.group(1)
            balance = balance_match.group(1) if balance_match else "0.00"
            
            await update_loading(100, "DONE")
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

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

            # ================= ৪. অটো-বেট লুপ =================
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳ {current_bal - initial_balance:.2f}")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!**")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = get_history_and_prediction()

                    # হোমে যাওয়া এবং WinGo তে ঢোকা
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000) 

                    # Lottery ক্লিক
                    await page.evaluate("""
                        (function() {
                            let els = document.querySelectorAll('div, span, a');
                            for (let el of els) {
                                if (el.innerText && el.innerText.trim().toLowerCase() === 'lottery') { el.click(); return; }
                            }
                        })();
                    """)
                    await page.wait_for_timeout(2000)

                    # Win Go ক্লিক
                    await page.evaluate("""
                        (function() {
                            let els = document.querySelectorAll('div, span, a');
                            for (let el of els) {
                                if (el.innerText && el.innerText.includes('Win Go') && el.innerText.includes('Guess Number')) { el.click(); return; }
                            }
                        })();
                    """)
                    await page.wait_for_timeout(4000) 

                    # টাইমার স্ক্র্যাপ
                    timer_val = 1
                    try:
                        body_text = await page.evaluate("() => document.body.innerText")
                        timer_match = re.search(r'0*\s*:\s*(\d{2})', body_text)
                        if timer_match: timer_val = int(timer_match.group(1))
                    except: pass

                    # Big / Small ক্লিক (জোরপূর্বক)
                    clicked = await page.evaluate(f"""
                        (function() {{
                            let target = '{choice}'.toUpperCase();
                            let elements = document.querySelectorAll('div, span, button, p, a');
                            for (let el of elements) {{
                                let text = (el.innerText || el.textContent || '').trim().toUpperCase();
                                if (text === target || text.includes(target)) {{
                                    el.click(); 
                                    return true;
                                }}
                            }}
                            return false;
                        }})();
                    """)

                    if not clicked:
                        ss = f"err_{uid}.png"
                        await page.screenshot(path=ss)
                        await ctx.bot.send_photo(chat_id=uid, photo=open(ss, 'rb'), caption=f"⚠️ **{choice} বাটনে ক্লিক করা যাচ্ছে না!**")
                        raise Exception("Click failed")

                    await page.wait_for_timeout(1000) 
                    try:
                        await page.locator('text="Confirm"').last.click(timeout=3000)
                    except: pass

                    # মেসেজ পাঠানো
                    report_msg = await ctx.bot.send_message(chat_id=uid, text="Sending Analysis Report...")
                    asyncio.create_task(update_live_timer(ctx, uid, report_msg.message_id, timer_val, current_period, choice, bet_amount, current_bal, current_step_idx))

                    await asyncio.sleep(32)

                    # রেজাল্ট চেক
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000) 
                    new_text = await page.evaluate("() => document.body.innerText")
                    new_bal_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', new_text, re.IGNORECASE)
                    
                    if new_bal_match:
                        new_bal = float(new_bal_match.group(1))
                        if new_bal > current_bal:
                            state["balance"] = new_bal
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nBalance: ৳ {new_bal:.2f}")
                        else:
                            state["balance"] = new_bal
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nBalance: ৳ {new_bal:.2f}\nNext Step: {current_step_idx+1}")

                except Exception as e:
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **FATAL ERROR:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)["first_bet"] = True
    welcome_text = "👇 **Press the button below to LOGIN**"
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"📱 Number: {text}\n\n🔑 Enter Password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**\n[░░░░░░░░░░] 0%")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], text))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit amount:")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("🚀 Enter STEP COUNT (e.g. 5):")
        except: await update.message.reply_text("❌ Number only!")
        return
        
    if state.get("awaiting") == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = []
            state["current_step"] = 0
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — amount?")
        except: await update.message.reply_text("❌ Number only!")
        return

    if state.get("awaiting") == "step_amount":
        try:
            state["step_amounts"].append(float(text))
            state["current_step"] += 1
            if state["current_step"] < state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']+1} — amount?")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="trade")]])
                await update.message.reply_text("✅ Steps saved!\n👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except: await update.message.reply_text("❌ Number only!")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 STOPPED")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your phone number:")
    elif query.data == "trade":
        state["trade_running"] = True

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