cat << 'EOF' > main.py
import os
import logging
import time
import uuid
import hashlib
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "phone": ""}
    return user_state[uid]

def generate_signature(random_str, timestamp, pwd):
    raw_str = f"{random_str}{timestamp}{pwd}"
    return hashlib.md5(raw_str.encode()).hexdigest().upper()

def api_login(phone, password):
    url = "https://api.dkwinapi.com/api/webapi/Login"
    current_timestamp = int(time.time())
    random_hex = uuid.uuid4().hex
    signature_val = generate_signature(random_hex, current_timestamp, password)
    
    headers = {
        "authority": "api.dkwinapi.com",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    payload = {
        "username": phone,
        "pwd": password,
        "phonetype": 1,
        "logintype": "mobile",
        "packId": "",
        "deviceId": "78a31db8d2dc8544556f9d82370be707",
        "pixelId": "", "fbcId": "", "fbc": "", "fbp": "", "adId": "",
        "language": 0,
        "random": random_hex,
        "signature": signature_val,
        "timestamp": current_timestamp
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text("🧠 **BD WIN GO AUTO BOT**\n\nশুরু করতে নিচের বাটনে ক্লিক করুন:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    state = get_state(uid)
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 আপনার ফোন নম্বর দিন:")

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 এখন আপনার পাসওয়ার্ড দিন:")
        return

    if state.get("awaiting") == "password":
        phone = state["phone"]
        password = text
        state["awaiting"] = None
        
        try:
            await update.message.delete()
        except:
            pass
            
        wait_msg = await update.message.reply_text("🔄 **লগইন হচ্ছে, দয়া করে অপেক্ষা করুন...**", parse_mode="Markdown")
        
        res = api_login(phone, password)
        
        await ctx.bot.delete_message(chat_id=uid, message_id=wait_msg.message_id)
        
        if "error" in res:
            await update.message.reply_text(f"❌ **লগইন ব্যর্থ হয়েছে!**\nএরর: `{res['error']}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"✅ **সার্ভার রেসপন্স পাওয়া গেছে!**\nরেসপন্স: `{res}`", parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
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
EOF
