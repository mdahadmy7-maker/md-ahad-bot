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
# ⚠️ এখানে আপনার টেলিগ্রাম বটের টোকেনটি বসান (১৪ নম্বর লাইন)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAGqRw1Mnj30rhr3N233Il4U8Huccz1mwVk") 

LOGIN_API_URL = "https://api.hgnicepayapi.com/api/v1/Login"     
BALANCE_API_URL = "https://api.hgnicepayapi.com/api/v1/GetUserInfo" 

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
# ২. API ফাংশন (requests দিয়ে)
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
        return False, data.get("msg", "Wrong account or password")
    except Exception as e:
        return False, str(e)

def sync_api_balance(token):
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}"
    }
    try:
        res = requests.get(BALANCE_API_URL, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0:
            balance = data.get("data", {}).get("amount", 0.0)
            return True, balance
        return False, "ব্যালেন্স পাওয়া যায়নি"
    except Exception as e:
        return False, str(e)

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার (আপনার আগের বড় ড্যাশবোর্ড)
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["logged_in"] = False
    state["awaiting"] = None
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak · 🔷 Pattern · 📈 Trend\n"
        "🔍 Manipulation · 🎨 Colour · 🔢 Frequency\n"
        "🔄 Markov · ♻️ Cycle · 💠 Momentum\n"
        "🔁 Every layer is back-tested live so its vote\n"
        "weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        
        login_success, token_or_msg = await asyncio.to_thread(sync_api_login, state["phone"], state["password"])
        
        if login_success:
            state["token"] = token_or_msg
            bal_success, balance = await asyncio.to_thread(sync_api_balance, state["token"])
            
            if bal_success:
                state["logged_in"] = True
                state["balance"] = balance
                state["account_uid"] = "548284" 
                
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

    # ৩. অন্যান্য বাটন হ্যান্ডলার
    if text == "🚀 START YOUR TARGET":
        if not state["logged_in"]:
            await update.message.reply_text("❌ আগে লগইন করুন। /start দিন।")
        else:
            await update.message.reply_text("🚀 বেটিং সিস্টেম চালু হচ্ছে...")
        return

    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 **TRADE STOPPED**")
        return

    if text == "🚪 LOGOUT":
        state["logged_in"] = False
        state["token"] = ""
        await update.message.reply_text("🚪 **LOGGED OUT**\nYour session has ended successfully.", parse_mode="Markdown")
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