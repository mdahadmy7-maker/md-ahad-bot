import asyncio
import logging
import os
import time
import uuid
import hashlib
import json
import base64
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") # এখানে আপনার টেলিগ্রাম বটের টোকেন দিন
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, 
            "temp_phone": "", 
            "temp_password": "",
            "balance": "0.00", 
            "user_id": "Unknown",
            "token": None
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. সিগনেচার এবং JWT ডিকোডার
# ═══════════════════════════════════════════
def generate_signature(payload_data):
    sorted_keys = sorted(payload_data.keys())
    filtered_data = {}
    for key in sorted_keys:
        val = payload_data[key]
        if val is not None and val != "":
            filtered_data[key] = val
            
    json_string = json.dumps(filtered_data, separators=(',', ':'))
    
    # ⚠️ যদি সিগনেচার ভুল দেখায়, তবে এখানে সিক্রেট কী লাগবে
    raw_string = json_string 
    signature = hashlib.md5(raw_string.encode('utf-8')).hexdigest().upper()
    return signature

def decode_jwt_payload(token):
    """JWT টোকেন থেকে UID এবং ব্যালেন্স বের করার ফাংশন"""
    try:
        payload = token.split('.')[1]
        # Base64 ডিকোড করার জন্য প্যাডিং ঠিক করা
        payload += '=' * (-len(payload) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload)
        decoded_json = json.loads(decoded_bytes.decode('utf-8'))
        return decoded_json
    except Exception as e:
        logger.error(f"JWT decode error: {e}")
        return {}

# ═══════════════════════════════════════════
# ৩. API লগইন ফাংশন
# ═══════════════════════════════════════════
async def api_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **CONNECTING TO API...**\nলগইন করা হচ্ছে, অপেক্ষা করুন...", parse_mode="Markdown")

    current_timestamp = int(time.time())
    random_str = uuid.uuid4().hex
    device_id = uuid.uuid4().hex

    payload = {
        "username": login_phone,
        "pwd": password,
        "phonetype": 1,
        "logintype": "mobile",
        "packId": "",
        "deviceId": device_id,
        "pixelId": "",
        "fbcId": "",
        "fbc": "",
        "fbp": "",
        "adId": "",
        "language": 0,
        "random": random_str,
        "timestamp": current_timestamp
    }

    signature = generate_signature(payload)
    payload["signature"] = signature

    headers = {
        "accept": "application/json, text/plain, */*",
        "ar-origin": "https://dkwin0.com",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin0.com",
        "referer": "https://dkwin0.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    try:
        response = requests.post(LOGIN_URL, json=payload, headers=headers, timeout=15)
        res_data = response.json()

        if res_data.get("code") == 0:
            # সফল লগইন
            token = res_data["data"]["token"]
            
            # টোকেন থেকে ডাটা বের করা (এখানেই UID এবং Balance আছে)
            jwt_data = decode_jwt_payload(token)
            
            real_uid = jwt_data.get("UserId", "Unknown")
            real_balance = jwt_data.get("Amount", "0.00")
            user_name = jwt_data.get("UserName", login_phone)

            state["token"] = token
            state["user_id"] = real_uid
            state["balance"] = real_balance

            await status_msg.delete()

            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone : {user_name}\n\n"
                f"👤 Real UID : `{real_uid}`\n\n"
                f"💰 Real Balance : **৳ {real_balance}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 API Engine: ONLINE\n"
                "🚀 Ready to trade"
            )
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

        else:
            await status_msg.delete()
            error_msg = res_data.get("msg", "Unknown Error")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\n\nকারণ: {error_msg}\n\nসম্ভাব্য কারণ:\n১. পাসওয়ার্ড ভুল।\n২. সিগনেচার ভুল (Secret Key মেলেনি)।")

    except Exception as e:
        await status_msg.delete()
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **NETWORK ERROR:** {str(e)[:100]}")

# ═══════════════════════════════════════════
# ৪. টেলিগ্রাম হ্যান্ডলারস
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET (API MODE)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 Access  : Private\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 প্রথমে আপনার একাউন্টে লগইন করুন।\n"
        "লগইন করতে **/login** কমান্ডটি দিন অথবা নিচের বাটনে ক্লিক করুন।"
    )
    reply_keyboard = [[KeyboardButton("🔐 LOGIN")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if text == "🔐 LOGIN" or text == "/login":
        state["awaiting"] = "phone"
        await update.message.reply_text("📱 আপনার DKWIN ফোন নাম্বার দিন:\n(যেমন: 017XXXXXXXX)")
        return

    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "🔑 এখন আপনার পাসওয়ার্ড দিন:\n\n"
            "🔒 _নিরাপত্তার জন্য পাসওয়ার্ড দেওয়ার পর আপনার মেসেজটি ডিলিট হয়ে যাবে।_",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        
        # পাসওয়ার্ড মেসেজটি ডিলিট করে দেওয়া (নিরাপত্তার জন্য)
        try: await update.message.delete()
        except: pass
        
        # লগইন ফাংশন কল করা
        await api_login(uid, ctx, state["temp_phone"], state["temp_password"])
        return

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "balance": "0.00", "user_id": "Unknown", "token": None
    }
    await update.message.reply_text("🔄 সব ডাটা রিসেট হয়েছে। /start দিন।")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("login", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 API Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()