import asyncio
import logging
import re
import os
import random
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login"
HOME_URL = "https://dkwin8.com/#/"
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
# ২. API থেকে রেজাল্ট ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
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
            
        if len(history) < 3:
            return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
    except Exception as e:
        logger.error(f"History API error: {e}")
        return "BIG", datetime.now().strftime("%Y%m%d%H%M%S")

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text_status="CONNECTING TO SITE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text_status}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except Exception: 
            pass

    async with async_playwright() as p:
        try:
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
        except Exception as e:
            logger.error(f"Browser launch failed: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ ব্রাউজার লঞ্চ করা যায়নি। দয়া করে প্লেরাইট ইনস্টল চেক করুন।")
            return

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800},
            is_mobile=True,
            has_touch=True
        )
        
        page = await context.new_page()
        
        try:
            await update_loading(10, "OPENING WEBSITE")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4) 

            await update_loading(30, "ENTERING CREDENTIALS")
            try:
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=20000)
                await phone_input.fill(login_phone)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)
            except Exception as e:
                logger.error(f"Input fill error: {e}")

            await update_loading(50, "LOGGING IN")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000, force=True)
            except Exception:
                pass
            
            await asyncio.sleep(6) 

            await update_loading(75, "FETCHING ACCOUNT DETAILS")
            try:
                account_tab = page.get_by_text("Account", exact=True).last
                if await account_tab.count() > 0:
                    await account_tab.click(force=True, timeout=10000)
                await asyncio.sleep(4) 
            except Exception: 
                pass

            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(15): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text or "incorrect" in page_text.lower():
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
                await asyncio.sleep(0.5)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except Exception: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\n\nসম্ভবত পাসওয়ার্ড ভুল অথবা সাইট বটকে ব্লক করেছে।")
                await browser.close()
                return

            state["balance"] = float(balance)
            dashboard_msg = f"🎉 **LOGIN SUCCESSFUL**\n👤 UID: {uid_val}\n💰 Balance: ৳ {balance}"
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

        except Exception as e:
            logger.error(f"Browser session error: {e}")
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except Exception: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:** `{str(e)[:100]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# হ্যান্ডলার এবং মূল কার্যক্রম
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text("🧠 **BD WIN GO AUTO BOT**\n\nশুরু করতে নিচের বাটনে ক্লিক করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 এখন আপনার পাসওয়ার্ড দিন:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except Exception: pass
        
        if state.get("task"): state["task"].cancel()
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO SITE**")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 আপনার টার্গেট প্রফিট অ্যামাউন্ট লিখুন (টাকায়):")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("📋 কতটি স্টেপ চালাতে চান তা লিখুন (যেমন: 5):")
        except ValueError:
            await update.message.reply_text("❌ শুধু সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 এর বেট অ্যামাউন্ট কত হবে?")
        except ValueError:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} এর বেট অ্যামাউন্ট দিন:")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text("⚙️ কনফিগারেশন সম্পন্ন! ট্রেড শুরু করতে নিচের বাটনে চাপুন:", reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন।")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    
    if data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 আপনার ফোন নম্বর দিন:")
    elif data == "start_trade_btn":
        state["trade_running"] = True
        await query.edit_message_text("🚀 ট্রেড শুরু হয়েছে...")
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN এনভায়রনমেন্ট ভ্যারিয়েবলে সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
    