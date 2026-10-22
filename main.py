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
WINGO_URL = "https://www.hgnice.vip/#/WinGo"
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
            "browser": None, "page": None, "playwright": None # 💡 ব্রাউজার দ্রুত রাখার জন্য
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. API থেকে রেজাল্ট ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            return "SMALL", "Unknown"
            
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
        return "SMALL", "Unknown"

# ───────────────────────────────────────────
# ৩. দ্রুত লগইন (নাম্বার ও পাসওয়ার্ড আলাদাভাবে নেওয়া)
# ───────────────────────────────────────────
async def prepare_login(uid, ctx, phone):
    """নাম্বার নেওয়ার সাথে সাথে ব্রাউজার ওপেন করে নাম্বার বসাবে"""
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    # আগের ব্রাউজার থাকলে বন্ধ করা
    if state.get("browser"):
        try: await state["browser"].close()
        except: pass

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        viewport={"width": 412, "height": 915}
    )
    page = await context.new_page()
    
    state["playwright"] = p
    state["browser"] = browser
    state["page"] = page

    try:
        await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
        logger.info(f"Phone filled for {login_phone}")
    except Exception as e:
        logger.error(f"Prepare login error: {e}")

async def execute_login(uid, ctx, loading_msg_id, password):
    """পাসওয়ার্ড নেওয়ার সাথে সাথে লগইন বাটনে ক্লিক করবে এবং ড্যাশবোর্ড আনবে"""
    state = get_state(uid)
    page = state.get("page")
    
    if not page:
        await ctx.bot.send_message(chat_id=uid, text="❌ Browser not ready. Please /start again.")
        return

    async def update_loading(percent):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **LOGGING IN**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    try:
        await update_loading(30)
        # ১. পাসওয়ার্ড বসানো
        await page.locator('input[type="password"]').first.fill(password)
        await update_loading(50)
        
        # ২. লগইন বাটনে ক্লিক
        try:
            await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
        except:
            await page.locator('button:has-text("Log in")').last.click(timeout=10000)
        
        await update_loading(70)
        # পপআপ হ্যান্ডেল করা (যদি থাকে)
        for _ in range(5):
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
            await page.wait_for_timeout(300)

        await update_loading(85)
        # Account পেজে যাওয়া
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
            await page.wait_for_timeout(2500) 
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
            balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
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
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({state['temp_phone']})")
            return

        state["balance"] = float(balance)
        masked_phone = f"***{state['temp_phone'][-4:]}"
        
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

    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Login Error:**\n`{str(e)[:100]}`")


# ───────────────────────────────────────────
# ৪. অটো-বেট লুপ (আগের মতোই, তবে পপআপ কিলার যুক্ত)
# ───────────────────────────────────────────
async def betting_loop(uid, ctx):
    state = get_state(uid)
    page = state.get("page")
    
    if not page:
        return

    initial_balance = state["balance"]
    target_balance = initial_balance + float(state['target'])
    current_step_idx = 0

    while state["trade_running"]:
        active_msg = None
        pred_msg = None
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
                await ctx.bot.send_message(chat_id=uid, text=target_summary)
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

            # WinGo পেজে যাওয়া
            await page.goto(WINGO_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000) 

            # 💡 ১. WinGo 30sec ট্যাবে ক্লিক করা
            try:
                await page.get_by_text("WinGo 30sec", exact=False).first.click(timeout=3000)
                await page.wait_for_timeout(1500)
            except: pass

            # 💡 ২. পপআপ (Announcement) বন্ধ করা - সবচেয়ে জরুরি অংশ
            for _ in range(5):
                try:
                    # "Confirm" বা "OK" লেখা যেকোনো বাটনে ক্লিক করবে
                    confirm_btn = page.locator('button:has-text("Confirm"), div:has-text("Confirm"), button:has-text("OK")').last
                    if await confirm_btn.is_visible(timeout=1000):
                        await confirm_btn.click(force=True, timeout=2000)
                        await page.wait_for_timeout(1000)
                except: pass

            timer_val = "30s"
            try:
                body_text = await page.evaluate("() => document.body.innerText")
                timer_match = re.search(r'(\d{2})\s*s', body_text, re.IGNORECASE)
                if timer_match: timer_val = f"{timer_match.group(1)}s"
            except: pass

            active_msg = await ctx.bot.send_message(chat_id=uid, text=(
                "╔════════════════════════════════╗\n"
                "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                "╚════════════════════════════════╝\n\n"
                f"💰 **Balance** : ৳ {current_bal:.2f}\n"
                f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                f"⏱️ **Current Period** : {current_period}\n"
                f"██████████ {timer_val}\n\n"
                "🧠 _Analysing market..._"
            ), parse_mode="Markdown")

            # 💡 Big / Small বাটনে ক্লিক করা
            clicked = False
            try:
                target_locator = page.locator(f'div:text-is("{choice}"), span:text-is("{choice}")').last
                await target_locator.wait_for(state="visible", timeout=15000)
                await target_locator.click(force=True, timeout=5000)
                clicked = True
            except Exception as e:
                logger.error(f"Primary click failed: {e}")
                try:
                    clicked = await page.evaluate(f"""
                        (function() {{
                            let target = '{choice}'.toUpperCase();
                            let elements = document.querySelectorAll('div, button, span');
                            for (let el of elements) {{
                                let text = (el.innerText || el.textContent || '').trim().toUpperCase();
                                if (text === target && el.getBoundingClientRect().width > 50) {{
                                    el.click(); 
                                    return true;
                                }}
                            }}
                            return false;
                        }})();
                    """)
                except: pass

            if not clicked:
                screenshot_path = f"error_{uid}.png"
                await page.screenshot(path=screenshot_path)
                await ctx.bot.send_photo(chat_id=uid, photo=open(screenshot_path, 'rb'), caption=f"⚠️ **{choice} বাটনে ক্লিক করা যাচ্ছে না!**")
                raise Exception(f"{choice} button not found.")

            await page.wait_for_timeout(1000) 
            
            try:
                await page.locator('text="Confirm"').last.click(force=True, timeout=3000)
            except: pass

            try: await ctx.bot.delete_message(chat_id=uid, message_id=active_msg.message_id)
            except: pass

            await ctx.bot.send_message(chat_id=uid, text=f"🤖 **NEW TRADE PLACED**\nPeriod: {current_period}\nPrediction: {choice}\nAmount: ৳ {bet_amount:.2f}\n\n⏳ Waiting for result...")

            await asyncio.sleep(32)

            # রেজাল্ট চেক করা
            await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) 
            
            new_page_text = await page.evaluate("() => document.body.innerText")
            new_balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
            
            if new_balance_match:
                new_balance = float(new_balance_match.group(1))
                state['total_trades'] += 1
                
                if new_balance > current_bal:
                    state["balance"] = new_balance
                    state["wins"] += 1
                    current_step_idx = 0
                    await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nP/L: +৳ {bet_amount * 0.96:.2f}\nBalance: ৳ {new_balance:.2f}")
                else:
                    state["balance"] = new_balance
                    state["losses"] += 1
                    current_step_idx += 1
                    await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nP/L: -৳ {bet_amount:.2f}\nBalance: ৳ {new_balance:.2f}\nNext Step: {current_step_idx+1}")

        except Exception as e:
            logger.error(f"Betting error: {e}")
            if active_msg:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=active_msg.message_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
            state["trade_running"] = False
            break

# ───────────────────────────────────────────
# ৫. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Press the button below to LOGIN"
    )
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    # ১. নাম্বার নেওয়া (ব্রাউজার ওপেন হবে)
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"☎️ Number : {text}\n\n"
            "🔑 Now enter your password:"
        )
        # ব্যাকগ্রাউন্ডে ব্রাউজার চালু করে নাম্বার বসানো
        await prepare_login(uid, ctx, text)
        return

    # ২. পাসওয়ার্ড নেওয়া (সাথে সাথে লগইন হবে)
    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **LOGGING IN**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        # আগে থেকে ওপেন থাকা ব্রাউজারে পাসওয়ার্ড বসিয়ে লগইন
        await execute_login(uid, ctx, loading_msg.message_id, text)
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 START YOUR TARGET 🚀   ║\n"
            "╚════════════════════════╝\n"
            f"💰 YOUR BALANCE: ৳ {state.get('balance', '0.00')}\n"
            "🎯 Enter your TARGET profit amount:"
        )
        await update.message.reply_text(target_msg)
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text(f"✅ Target: ৳ {text}\n\n🚀 Enter your STEP COUNT (e.g. 5):")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — bet amount? (in ৳)")
        except ValueError:
            await update.message.reply_text("❌ ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
            else:
                state["awaiting"] = None
                combined_msg = (
                    "⚙️ TRADE CONFIGURATION ⚙️\n"
                    f"💰 Balance  : ৳ {state.get('balance', '0.00'):.2f}\n"
                    f"🎯 Target   : ৳ {state['target']:.2f}\n"
                    f"📋 Steps    : {state['steps']}\n"
                    f"👇 Press START TRADE to begin."
                )
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ শুধু সংখ্যা লিখুন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        if state.get("browser"):
            try: await state["browser"].close()
            except: pass
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
        await query.message.delete()
        state["trade_running"] = True
        # এখান থেকে বেটিং লুপ শুরু হবে
        asyncio.create_task(betting_loop(uid, ctx))

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