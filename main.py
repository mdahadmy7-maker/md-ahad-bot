import asyncio
import logging
import random
import os
import re
import aiohttp
import hashlib
import uuid
import time
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAFqxoU8330Tgqjbs8GNzblIfUQqnnJ7wPg") 

# আপনার সাইটের সফল API লিংক
LOGIN_API_URL = "https://api.hgnicepayapi.com/api/v1/Login"     
GET_USER_INFO_URL = "https://api.hgnicepayapi.com/api/v1/GetUserInfo" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "task": None, "steps": [], "step_idx": 0, 
            "target": 0, "profit": 0, "bet_choice": "RANDOM",
            "balance": "0.00", "account_uid": "Unknown", "token": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. API ফাংশন (লগইন এবং ব্যালেন্স)
# ───────────────────────────────────────────
async def api_login(phone, password):
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
        async with aiohttp.ClientSession() as session:
            async with session.post(LOGIN_API_URL, json=payload, headers=headers, timeout=15) as res:
                data = await res.json()
                if data.get("code") == 0 or data.get("msg") == "Succeed":
                    token = data.get("data", {}).get("token", "")
                    return True, token
                return False, data.get("msg", "Wrong account or password")
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
                    balance = data.get("data", {}).get("amount", 0.0)
                    return True, balance
                return False, "ব্যালেন্স পাওয়া যায়নি"
    except Exception as e:
        return False, str(e)

# ───────────────────────────────────────────
# ৩. মূল অটো-বেট লুপ (API দিয়ে লগইন)
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    
    # ১. API লগইন
    login_success, token_or_msg = await api_login(state["phone"], state["password"])
    
    if not login_success:
        await ctx.bot.send_message(
            chat_id=uid, 
            text=f"❌ **LOGIN FAILED**\n{token_or_msg}\n\nদয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।",
            parse_mode="Markdown"
        )
        state["running"] = False
        return
        
    state["token"] = token_or_msg
    # ২. API ব্যালেন্স
    bal_success, balance = await api_get_balance(state["token"])
    
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
        
        # লগইন সফল হলে ড্যাশবোর্ড মেসেজ (আপনার ডিজাইন)
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
        
        # এখানে পরবর্তী ধাপে Playwright দিয়ে আসল বাজি ধরার লজিক বসবে
        # আপাতত বেট লুপ ডেমো হিসেবে চলবে
        while state["running"]:
            if not state["steps"]:
                await asyncio.sleep(2)
                continue
                
            current_amount = state["steps"][state["step_idx"]]
            await ctx.bot.send_message(chat_id=uid, text=f"⏳ পরবর্তী ধাপে এখানে {current_amount} টাকা বাজি ধরবে।")
            await asyncio.sleep(5) # ডেমো অপেক্ষা
    else:
        await ctx.bot.send_message(chat_id=uid, text=f"✅ লগইন হয়েছে, কিন্তু ব্যালেন্স আনতে সমস্যা: {balance}")
        state["running"] = False

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    
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

    # ২. পাসওয়ার্ড গ্রহণ এবং লোডিং অ্যানিমেশন
    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        for i in range(1, 11):
            await asyncio.sleep(0.3)
            filled = "█" * i
            empty = "░" * (10 - i)
            percent = i * 10
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown")
            except: pass
        
        # লগইন এবং ব্যালেন্স চেক টাস্ক শুরু
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        return

    # ৩. START YOUR TARGET বাটন
    if text == "🚀 START YOUR TARGET":
        if not state["logged_in"]:
            state["awaiting"] = "steps"
            await update.message.reply_text(
                "💰 **BET STEPS** লিখুন (কমা দিয়ে):\n"
                "_Example: 2,4,8,16,32_",
                parse_mode="Markdown"
            )
        else:
            state["running"] = True
            await update.message.reply_text("🚀 বেটিং পুনরায় শুরু হচ্ছে...")
            if state.get("task"): state["task"].cancel()
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        return

    # ৪. STOP TRADE বাটন
    if text == "🛑 STOP TRADE":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🛑 **TRADE STOPPED**\nAutoTrading session paused.", parse_mode="Markdown")
        return

    # ৫. LOGOUT বাটন
    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        state["token"] = ""
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 **LOGGED OUT**\nYour session has ended successfully.", parse_mode="Markdown")
        return

    # ৬. স্টেপ গ্রহণ
    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(f"✅ STEPS SAVED: `{parts}`\n\n🎯 **TARGET PROFIT** দিন (যেমন: 100):", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! আবার লিখুন (যেমন: 2,4,8):")
        return

    # ৭. টার্গেট গ্রহণ
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["profit"] = 0
            state["awaiting"] = None
            
            keyboard = [
                [InlineKeyboardButton("🟠 BIG", callback_data="choice_BIG"), InlineKeyboardButton("🔵 SMALL", callback_data="choice_SMALL")],
                [InlineKeyboardButton("🎲 RANDOM", callback_data="choice_RANDOM")]
            ]
            await update.message.reply_text("✅ টার্গেট সেভ হয়েছে।\n🎯 বাজি ধরার মোড সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন:")
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
                "📱 **Enter your HGNICE phone number:**\n\n"
                "_Everyone uses their own account — your session is private._"
            ),
            parse_mode="Markdown"
        )
        
    elif data.startswith("choice_"):
        state["bet_choice"] = data.split("_")[1]
        state["running"] = True
        await query.edit_message_text(
            f"🚀 **AUTO BETTING STARTED**\n🎯 Target: {state['target']} ৳\n📈 Steps: {state['steps']}\n🎲 Choice: {state['bet_choice']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 STOP", callback_data="stop_bet")]])
        )
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        
    elif data == "stop_bet":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await query.edit_message_text("🛑 **AUTO BETTING STOPPED**", parse_mode="Markdown")

# ───────────────────────────────────────────
# ৫. মেইন ফাংশন
# ───────────────────────────────────────────
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
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