import asyncio
import logging
import os
import aiohttp
import hashlib
import uuid
import time
import base64
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAGHxO0ZNcoSVb3N5u1dSXcWa1_nszIRlxM") 

# ⚠️ আপনার সাইটের আসল API লিংক এখানে বসান
LOGIN_API_URL = "https://api.hgnice.vip/api/v1/login"     # ← আসল লিংক বসান
BALANCE_API_URL = "https://api.hgnice.vip/api/v1/balance" # ← আসল লিংক বসান

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "balance": "0.00", "account_uid": "Unknown", "token": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. API ফাংশন: লগইন এবং ব্যালেন্স
# ───────────────────────────────────────────
async def api_login(phone, password):
    device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    random_str = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    timestamp = int(time.time())
    
    # আপনার আগের সফল সিগনেচার (প্রয়োজনে আপডেট করুন)
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
                return False, data.get("msg", "লগইন ব্যর্থ (Error 147)")
    except Exception as e:
        return False, str(e)

async def api_get_balance(token):
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BALANCE_API_URL, headers=headers, timeout=10) as res:
                data = await res.json()
                if data.get("code") == 0:
                    balance = data.get("data", {}).get("balance", 0.0)
                    return True, balance
                return False, "ব্যালেন্স পাওয়া যায়নি"
    except Exception as e:
        return False, str(e)

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["logged_in"] = False
    state["awaiting"] = None
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : API Balance Checker\n"
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

    # ২. পাসওয়ার্ড গ্রহণ এবং API চেক
    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        # পাসওয়ার্ড মেসেজটি ডিলিট করা
        try: await update.message.delete()
        except: pass
        
        # লোডিং মেসেজ
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO SERVER**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        for i in range(1, 11):
            await asyncio.sleep(0.2)
            filled = "█" * i
            empty = "░" * (10 - i)
            percent = i * 10
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO SERVER**\n[{filled}{empty}] {percent}%", parse_mode="Markdown")
            except: pass
        
        # লগইন API কল
        login_success, token_or_msg = await api_login(state["phone"], state["password"])
        
        if login_success:
            state["token"] = token_or_msg
            
            # ব্যালেন্স API কল
            bal_success, balance = await api_get_balance(state["token"])
            
            # টোকেন থেকে UID বের করা (Optional)
            uid_from_token = "Unknown"
            try:
                payload_b64 = state["token"].split('.')[1]
                payload_b64 += '=' * (-len(payload_b64) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload_b64))
                uid_from_token = decoded.get("UserId", "Unknown")
            except: pass

            if bal_success:
                state["logged_in"] = True
                state["balance"] = balance
                state["account_uid"] = uid_from_token

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
                    "✅ API Connected Successfully."
                )
                
                reply_keyboard = [[KeyboardButton("🔄 REFRESH BALANCE")], [KeyboardButton("🚪 LOGOUT")]]
                markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
                
                await loading_msg.edit_text(login_msg_text, parse_mode="Markdown", reply_markup=markup)
            else:
                await loading_msg.edit_text(f"✅ লগইন হয়েছে, কিন্তু ব্যালেন্স আনতে সমস্যা: {balance}")
        else:
            state["logged_in"] = False
            await loading_msg.edit_text(f"❌ **LOGIN FAILED**\nকারণ: {token_or_msg}\n\nদয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।", parse_mode="Markdown")
        return

    # ৩. রিফ্রেশ ব্যালেন্স বাটন
    if text == "🔄 REFRESH BALANCE":
        if not state["logged_in"]:
            await update.message.reply_text("❌ আপনি লগইন করা নেই। /start দিন।")
            return
        
        msg = await update.message.reply_text("⏳ Fetching latest balance...")
        bal_success, balance = await api_get_balance(state["token"])
        if bal_success:
            state["balance"] = balance
            await msg.edit_text(f"💰 **Updated Balance:** ৳ {balance}", parse_mode="Markdown")
        else:
            await msg.edit_text(f"❌ ব্যালেন্স আনা যায়নি। সেশন এক্সপায়ার হতে পারে।")
        return

    # ৪. লগআউট বাটন
    if text == "🚪 LOGOUT":
        state["logged_in"] = False
        state["token"] = ""
        await update.message.reply_text("🚪 **LOGGED OUT**\nYour session has ended successfully. /start to login again.", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True))
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    
    if data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(
            chat_id=uid,
            text=(
                "╔════════════════════════╗\n"
                "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
                "╚════════════════════════╝\n\n"
                "📱 **Enter your phone number:**\n\n"
                "_Everyone uses their own account — your session is private._"
            ),
            parse_mode="Markdown"
        )

# ───────────────────────────────────────────
# ৪. মেইন ফাংশন
# ───────────────────────────────────────────
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
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