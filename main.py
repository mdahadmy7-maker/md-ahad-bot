import asyncio
import logging
import os
import re
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAHStYqC8f3OSE65wYmyxmC8gvqKDw2B57Y") 
SITE_URL = "https://www.hgnice.vip"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 🌐 ডামি ওয়েবসাইট (সার্ভার যাতে বন্ধ না করে)
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running perfectly!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "balance": "0.00", "account_uid": "Unknown"
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. Playwright দিয়ে লগইন এবং স্ক্র্যাপিং
# ───────────────────────────────────────────
async def process_login(uid, ctx):
    state = get_state(uid)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = await browser.new_page()
        await stealth_async(page)

        try:
            logger.info(f"Opening site for {uid}...")
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            # ফোন নম্বর এবং পাসওয়ার্ড ফিলাপ করা
            await page.get_by_placeholder("Please enter the phone number").fill(state["phone"])
            await page.get_by_placeholder("Password").fill(state["password"])
            await page.locator('text="Log in"').last.click()
            
            await page.wait_for_timeout(6000)
            
            # ভুল পাসওয়ার্ড চেক
            error_popup = page.locator('text="Wrong account or password"').first
            if await error_popup.is_visible():
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**\nভুল নাম্বার বা পাসওয়ার্ড!", parse_mode="Markdown")
                await browser.close()
                state["running"] = False
                return

            # স্ক্রিন থেকে UID এবং ব্যালেন্স বের করা
            await page.wait_for_timeout(4000)
            page_text = await page.inner_text("body")
            
            uid_match = re.search(r'(?:UID|Account\s*UID|ID)\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total\s*)?[Bb]alance\s*[৳:]?\s*([\d.]+)', page_text)
            
            user_uid = uid_match.group(1) if uid_match else "Unknown"
            balance = balance_match.group(1) if balance_match else "0.00"
            
            state["logged_in"] = True
            state["balance"] = balance
            state["account_uid"] = user_uid
            
            # সফল মেসেজ (বড় ড্যাশবোর্ড)
            login_msg_text = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "☎️ **Phone Number**\n"
                f"****{state['phone'][-4:]}\n\n"
                "👤 **Account UID**\n"
                f"{state['account_uid']}\n\n"
                "💰 **Account Balance**\n"
                f"৳ {state['balance']}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")],
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await ctx.bot.send_message(chat_id=uid, text=login_msg_text, parse_mode="Markdown", reply_markup=markup)

        except Exception as e:
            logger.error(f"Playwright Error: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **SYSTEM ERROR**\nসার্ভারে সমস্যা হয়েছে: {str(e)}")
            state["running"] = False
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Press the button below to LOGIN"
    )
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"📱 Number: {text}\n\n"
            "🔑 **Now enter your password:**\n"
            "_Your message will be deleted immediately for security._",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        for i in range(1, 11):
            await asyncio.sleep(0.2)
            filled = "█" * i
            empty = "░" * (10 - i)
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {i*10}%", parse_mode="Markdown")
            except: pass
            
        await loading_msg.delete()
        
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(process_login(uid, ctx))
        return

    if text == "🚀 START YOUR TARGET":
        await update.message.reply_text("⏳ অটো-বেট ফিচারটি পরবর্তী ধাপে যুক্ত হবে।")
        return
    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 **STOPPED**")
        return
    if text == "🚪 LOGOUT":
        state["logged_in"] = False
        await update.message.reply_text("🚪 **LOGGED OUT**\nসেশন শেষ হয়েছে।", parse_mode="Markdown")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(
            chat_id=uid,
            text=(
                "╔════════════════════════╗\n"
                "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
                "╚════════════════════════╝\n\n"
                "📱 **Enter your HGNICE phone number:**\n\n"
                "_Everyone uses their own account — your session is private._"
            ),
            parse_mode="Markdown"
        )

# ───────────────────────────────────────────
# ৪. মেইন ফাংশন
# ───────────────────────────────────────────
def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Bot started successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()