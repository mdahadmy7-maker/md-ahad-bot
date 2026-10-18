import asyncio
import logging
import os
import aiohttp
import hashlib
import uuid
import time
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAHStYqC8f3OSE65wYmyxmC8gvqKDw2B57Y") 

# আপনার সাইটের সঠিক API লিংক
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
# ২. API ফাংশন (লগইন এবং ব্যালেন্স)
# ───────────────────────────────────────────
async def api_login(phone, password):
    device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    random_str = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    timestamp = int(time.time())
    
    # আপনার সাইটের সফল সিগনেচার
    signature = "1EFC4E6797FE1A0EDFDB3664BB51197A" 

    payload = {
        "username": phone, "pwd": password, "phonetype": 0, "logintype": "mobile",
        "packId": "", "deviceId": device_id, "pixelId": "", "fbcId": "", "fbc": "",
        "fbp": "", "adId": "", "language": 0, "random": random_str,
        "signature": signature, "timestamp": timestamp
    }
    
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LOGIN_API_URL, json=payload, headers=headers, timeout=15) as res:
                data = await res.json()
                if data.get("code") == 0 or data.get("msg") == "Succeed":
                    token = data.get("data", {}).get("token", "")
                    return True, token
                return False, data.get("msg", "ভুল নাম্বার বা পাসওয়ার্ড!")
    except Exception as e:
        return False, str(e)

async def api_get_balance(token):
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GET_USER_INFO_URL, headers=headers, timeout=10) as res:
                data = await res.json()
                if data.get("code") == 0:
                    user_data = data.get("data", {})
                    balance = user_data.get("amount", "0.00")
                    user_id = user_data.get("userId", "Unknown")
                    return True, balance, user_id
                return False, "ব্যালেন্স পাওয়া যায়নি", "Unknown"
    except Exception as e:
        return False, str(e), "Unknown"

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

    # ১. ফোন নম্বর গ্রহণ
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

    # ২. পাসওয়ার্ড গ্রহণ এবং API লগইন
    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        # পাসওয়ার্ড মেসেজ ডিলিট করা
        try: await update.message.delete()
        except: pass
        
        # লোডিং মেসেজ
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        for i in range(1, 11):
            await asyncio.sleep(0.1) # দ্রুত লোডিং
            filled = "█" * i
            empty = "░" * (10 - i)
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {i*10}%", parse_mode="Markdown")
            except: pass
        
        # API লগইন কল
        login_success, token_or_msg = await api_login(state["phone"], state["password"])
        
        if login_success:
            state["token"] = token_or_msg
            # API ব্যালেন্স কল
            bal_success, balance, user_id = await api_get_balance(state["token"])
            
            if bal_success:
                state["logged_in"] = True
                state["balance"] = balance
                state["account_uid"] = user_id
                
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
                await loading_msg.edit_text(login_msg_text, parse_mode="Markdown", reply_markup=markup)
                
            else:
                await loading_msg.edit_text(f"✅ লগইন হয়েছে, কিন্তু ব্যালেন্স আনতে সমস্যা: {balance}")
        else:
            state["logged_in"] = False
            await loading_msg.edit_text(f"❌ **LOGIN FAILED**\n{token_or_msg}\n\nদয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।", parse_mode="Markdown")
        return

    # ৩. অন্যান্য বাটন
    if text == "🚀 START YOUR TARGET":
        await update.message.reply_text("⏳ এই ফিচারটি পরবর্তী ধাপে যুক্ত হবে।")
        return
    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 **STOPPED**")
        return
    if text == "🚪 LOGOUT":
        state["logged_in"] = False
        state["token"] = ""
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
    if not BOT_TOKEN or BOT_TOKEN == "আপনার_বট_টোকেন_এখানে_দিন":
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