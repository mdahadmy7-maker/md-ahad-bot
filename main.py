import asyncio
import logging
import os
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAGqRw1Mnj30rhr3N233Il4U8Huccz1mwVk") 
SITE_URL = "https://www.hgnice.vip"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 🌐 Flask ওয়েবসাইট (ব্রাউজার লিংকের জন্য)
web_app = Flask(__name__)
bot_app = None

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ───────────────────────────────────────────
# ২. Playwright লজিক (ব্রাউজার ওপেন করে লগইন)
# ───────────────────────────────────────────
async def playwright_login(phone, password, chat_id):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await stealth_async(page)

        try:
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            await page.get_by_placeholder("Please enter the phone number").fill(phone)
            await page.get_by_placeholder("Password").fill(password)
            await page.locator('text="Log in"').last.click()
            await page.wait_for_timeout(6000)
            
            # ভুল পাসওয়ার্ড চেক
            error_popup = page.locator('text="Wrong account or password"').first
            if await error_popup.is_visible():
                await browser.close()
                await bot_app.bot.send_message(chat_id=chat_id, text="❌ **LOGIN FAILED**\nভুল নাম্বার বা পাসওয়ার্ড!", parse_mode="Markdown")
                return

            # ব্যালেন্স ও UID বের করা
            await page.wait_for_timeout(4000)
            page_text = await page.inner_text("body")
            
            import re
            uid_match = re.search(r'(?:UID|Account\s*UID|ID)\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total\s*)?[Bb]alance\s*[৳:]?\s*([\d.]+)', page_text)
            
            user_uid = uid_match.group(1) if uid_match else "Unknown"
            balance = balance_match.group(1) if balance_match else "0.00"
            
            await browser.close()
            
            # আপনার স্ক্রিনশটের মতো ড্যাশবোর্ড
            msg = (
                "┌────────────────────────┐\n"
                "    🎉 LOGIN SUCCESSFUL ✅\n"
                "└────────────────────────┘\n\n"
                "━━━━━━━━━━━━━━━━━\n"
                "☎️ **Phone Number**\n"
                f"****{phone[-4:]}\n\n"
                "👤 **Account UID**\n"
                f"{user_uid}\n\n"
                "💰 **Account Balance**\n"
                f"৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━\n\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press **START YOUR TARGET** to begin"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")],
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await bot_app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", reply_markup=markup)

        except Exception as e:
            await browser.close()
            await bot_app.bot.send_message(chat_id=chat_id, text=f"⚠️ **SYSTEM ERROR**\n{str(e)}", parse_mode="Markdown")

# ───────────────────────────────────────────
# ৩. Flask রুট (ব্রাউজার লিংক)
# ───────────────────────────────────────────
@web_app.route('/login')
def login_page():
    phone = request.args.get('phone')
    password = request.args.get('password')
    chat_id = request.args.get('chat_id')
    
    if not phone or not password or not chat_id:
        return "Missing parameters", 400
    
    def run_login():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(playwright_login(phone, password, int(chat_id)))
        loop.close()

    threading.Thread(target=run_login).start()
    return "Checking your account, please wait for a message on Telegram."

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"logged_in": False, "awaiting": None, "phone": "", "password": ""}
    return user_state[uid]

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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

    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"📱 Number: {text}\n\n🔑 **Enter your password:**", parse_mode="Markdown")
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**", parse_mode="Markdown")
        
        # ⚠️ এখানে আপনার Render বা Railway-এর আসল লিংকটি বসান
        render_url = "https://md-ahad-bot.up.railway.app" # উদাহরনস্বরূপ, আপনার নিজের লিংক বসান
        link = f"{render_url}/login?phone={state['phone']}&password={state['password']}&chat_id={uid}"
        
        link_buttons = [[InlineKeyboardButton("🌐 Click to Login", url=link)]]
        await loading_msg.edit_text(
            "✅ আপনার তথ্য পেয়েছি। লগইন চেক করতে নিচের বাটনে ক্লিক করুন।",
            reply_markup=InlineKeyboardMarkup(link_buttons)
        )
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 **Enter your HGNICE phone number:**", parse_mode="Markdown")

# ───────────────────────────────────────────
# ৫. মেইন ফাংশন
# ───────────────────────────────────────────
def main():
    global bot_app
    threading.Thread(target=run_web_server, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Bot started...")
    bot_app.run_polling()

if __name__ == "__main__":
    main()