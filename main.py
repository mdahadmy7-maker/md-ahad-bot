import asyncio
import logging
import os
import requests
import hashlib
import uuid
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAGqRw1Mnj30rhr3N233Il4U8Huccz1mwVk") 
LOGIN_API_URL = "https://api.hgnicepayapi.com/api/Login"     
GET_USER_INFO_URL = "https://api.hgnicepayapi.com/api/GetUserInfo" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "balance": "0.00", "account_uid": "Unknown", "token": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. API ফাংশন
# ───────────────────────────────────────────
def sync_api_login(phone, password):
    device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    random_str = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    timestamp = int(time.time())
    signature = "1EFC4E6797FE1A0EDFDB3664BB51197A" 

    payload = {
        "username": phone, "pwd": password, "phonetype": 0, "logintype": "mobile",
        "packId": "", "deviceId": device_id, "pixelId": "", "fbcId": "", "fbc": "",
        "fbp": "", "adId": "", "language": 0, "random": random_str,
        "signature": signature, "timestamp": timestamp
    }
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    
    try:
        res = requests.post(LOGIN_API_URL, json=payload, headers=headers, timeout=15)
        data = res.json()
        if data.get("code") == 0 or data.get("msg") == "Succeed":
            return True, data.get("data", {}).get("token", "")
        return False, data.get("msg", "ভুল পাসওয়ার্ড!")
    except Exception as e:
        return False, str(e)

def sync_api_balance(token):
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}"
    }
    try:
        res = requests.get(GET_USER_INFO_URL, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0:
            user_data = data.get("data", {})
            return True, user_data.get("amount", "0.00"), user_data.get("userId", "Unknown")
        return False, data.get("msg", "ব্যালেন্স পাওয়া যায়নি"), "Unknown"
    except Exception as e:
        return False, str(e), "Unknown"

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
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
        await update.message.reply_text(f"📱 Number: {text}\n\n🔑 **Now enter your password:**", parse_mode="Markdown")
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**", parse_mode="Markdown")
        
        login_success, token_or_msg = await asyncio.to_thread(sync_api_login, state["phone"], state["password"])
        
        if login_success:
            state["token"] = token_or_msg
            bal_success, balance, user_id = await asyncio.to_thread(sync_api_balance, state["token"])
            
            if bal_success:
                state["logged_in"] = True
                login_msg_text = (
                    "╔════════════════════════╗\n"
                    "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                    "╚════════════════════════╝\n"
                    f"☎️ Phone: ****{state['phone'][-4:]}\n"
                    f"👤 UID: {user_id}\n"
                    f"💰 Balance: ৳ {balance}"
                )
                reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
                markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
                await loading_msg.edit_text(login_msg_text, parse_mode="Markdown", reply_markup=markup)
            else:
                await loading_msg.edit_text(f"✅ লগইন হয়েছে, কিন্তু ব্যালেন্স আনতে সমস্যা: {balance}")
        else:
            await loading_msg.edit_text(f"❌ **LOGIN FAILED**\n{token_or_msg}", parse_mode="Markdown")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_login":
        get_state(update.effective_user.id)["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=update.effective_user.id, text="📱 **Enter your phone number:**", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()