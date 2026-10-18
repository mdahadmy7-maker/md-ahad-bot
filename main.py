import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
import hashlib
import uuid
import time
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)

# ═══════════════════════════════════════════
# 🔧 কনফিগারেশন (এখানে আপনার তথ্য বসান)
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAGHxO0ZNcoSVb3N5u1dSXcWa1_nszIRlxM"       # ← আপনার BotFather থেকে পাওয়া টোকেন
LOGIN_API_URL = "https://api.xxxxx.com/api/v1/login"     # ← আপনার আসল লগইন লিংক
BALANCE_API_URL = "https://api.xxxxx.com/api/v1/balance" # ← আপনার আসল ব্যালেন্স লিংক
ACCESS_KEY = "tk"                       # ← বটে ঢোকার পাসকী

PATTERN_SEED = [
    {"s": "BIG", "n": 7}, {"s": "SMALL", "n": 2}, {"s": "SMALL", "n": 4},
    {"s": "BIG", "n": 9}, {"s": "BIG", "n": 6}, {"s": "SMALL", "n": 0},
    {"s": "BIG", "n": 8}, {"s": "SMALL", "n": 3}, {"s": "SMALL", "n": 1},
    {"s": "BIG", "n": 5}, {"s": "BIG", "n": 7}, {"s": "SMALL", "n": 4}
]

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "game": "30s", "awaiting": None,
            "steps": [10, 20, 40, 80, 160], "step_idx": 0,
            "target": 500, "profit": 0, "bets": 0, "wins": 0,
            "running": False, "task": None,
            "last_period": "", "last_prediction": "", "pending_win": None,
            "token": "", "phone": "", "real_balance": 0.0
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# API ফাংশনসমূহ
# ═══════════════════════════════════════════
async def api_login(phone, password):
    device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    random_str = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    timestamp = int(time.time())
    signature = "1EFC4E6797FE1A0EDFDB3664BB51197A" # ডামি সিগনেচার

    payload = {
        "username": phone, "pwd": password, "phonetype": 0, "logintype": "mobile",
        "packId": "", "deviceId": device_id, "pixelId": "", "fbcId": "", "fbc": "",
        "fbp": "", "adId": "", "language": 0, "random": random_str,
        "signature": signature, "timestamp": timestamp
    }
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LOGIN_API_URL, json=payload, headers=headers, timeout=10) as res:
                data = await res.json()
                if data.get("code") == 0 or data.get("msg") == "Succeed":
                    token = data.get("data", {}).get("token", "")
                    return True, token
                return False, data.get("msg", "লগইন ব্যর্থ")
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

# ═══════════════════════════════════════════
# টেলিগ্রাম হ্যান্ডলার
# ═══════════════════════════════════════════
async def cmd_start(update, ctx):
    uid = update.effective_user.id
    state = get_state(uid)
    state["logged_in"] = False
    state["running"] = False
    if state.get("task"):
        state["task"].cancel()
        state["task"] = None
        
    await update.message.reply_text(
        "🔐 *LIONEL MESSI 69™ PREMIUM HACK* 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🗝️ বটে ঢোকার পাসকী দিন:",
        parse_mode="Markdown"
    )
    state["awaiting"] = "access_key"

async def text_handler(update, ctx):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    # ১. পাসকী চেক
    if state.get("awaiting") == "access_key":
        if text.lower() == ACCESS_KEY.lower():
            state["awaiting"] = "phone"
            await update.message.reply_text(
                "✅ *পাসকী সঠিক!*\n\n📱 এখন আপনার অ্যাকাউন্টের ফোন নম্বর দিন:",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ ভুল পাসকী। আবার /start দিন।")
        return

    # ২. ফোন নম্বর নেওয়া
    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            f"📱 Number: `{text}`\n\n🔑 আপনার পাসওয়ার্ড দিন:",
            parse_mode="Markdown"
        )
        return

    # ৩. পাসওয়ার্ড নেওয়া এবং লগইন
    if state.get("awaiting") == "password":
        password = text
        phone = state.get("phone")
        state["awaiting"] = None
        
        msg = await update.message.reply_text("⏳ Checking Account... Please wait.")
        
        # লগইন কল
        login_success, token_or_msg = await api_login(phone, password)
        
        if login_success:
            state["token"] = token_or_msg
            
            # ব্যালেন্স কল
            bal_success, balance = await api_get_balance(state["token"])
            if bal_success:
                state["logged_in"] = True
                state["real_balance"] = balance
                await msg.edit_text(
                    f"🎉 *ACCOUNT VERIFIED!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📱 Number: `{phone}`\n"
                    f"💰 *Real Balance: ৳ {balance}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 গেম সিলেক্ট করুন:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎮 WinGo 30s", callback_data="game_30s"),
                         InlineKeyboardButton("⏱️ WinGo 1m", callback_data="game_1m")]
                    ])
                )
            else:
                await msg.edit_text(f"✅ লগইন হয়েছে, কিন্তু ব্যালেন্স আনতে সমস্যা: {balance}")
        else:
            state["logged_in"] = False
            await msg.edit_text(f"❌ *LOGIN FAILED!*\nকারণ: {token_or_msg}", parse_mode="Markdown")
        return

    # ৪. স্টেপ ও টার্গেট নেওয়া
    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            parts = [p for p in parts if p > 0]
            if not parts: raise ValueError()
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(
                f"✅ *STEPS SAVED*\n📊 `{parts}`\n\n🎯 এখন *TARGET PROFIT* দিন:",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! এভাবে লিখুন: `10,20,40,80`", parse_mode="Markdown")
        return

    if state.get("awaiting") == "target":
        try:
            tgt = float(text)
            if tgt <= 0: raise ValueError()
            state["target"] = tgt
            state["awaiting"] = None
            state["profit"] = 0
            state["bets"] = 0
            state["wins"] = 0
            state["step_idx"] = 0
            state["running"] = True
            state["pending_win"] = None
            
            await update.message.reply_text(
                f"🚀 *AUTO BETTING STARTED!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎮 Game: *WinGo {state['game']}*\n"
                f"💰 Steps: `{state['steps']}`\n"
                f"🎯 Target: *{tgt}*\n"
                f"⏳ সিগন্যাল আসছে...",
                parse_mode="Markdown"
            )
            if state.get("task"): state["task"].cancel()
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        except:
            await update.message.reply_text("❌ সংখ্যা সঠিকভাবে লিখুন।", parse_mode="Markdown")
        return

async def callback_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data

    if data.startswith("game_"):
        mode = data.split("_")[1]
        state["game"] = mode
        state["awaiting"] = "steps"
        await query.edit_message_text(
            f"🎮 *WinGo {mode.upper()} SELECTED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *BET STEPS* লিখুন (কমা দিয়ে):\n_Example: 10,20,40,80_",
            parse_mode="Markdown"
        )
    elif data == "stop_bet":
        state["running"] = False
        if state.get("task"):
            state["task"].cancel()
        await query.edit_message_text(
            f"🛑 *AUTO BETTING STOPPED*\n"
            f"💰 Profit: *{state['profit']}*\n"
            f"📊 Bets: {state['bets']} | Wins: {state['wins']}",
            parse_mode="Markdown"
        )

async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    try:
        await asyncio.sleep(3)
        while state["running"]:
            # এখানে সিগন্যাল জেনারেট হবে
            import random
            pred = random.choice([{"s": "BIG", "n": 7}, {"s": "SMALL", "n": 2}]) # ডেমো
            
            emoji = "🟢" if pred["s"] == "BIG" else "🔵"
            current_bet = state['steps'][state['step_idx']]
            
            await ctx.bot.send_message(
                chat_id=uid,
                text=(
                    f"{emoji} *NEW SIGNAL — WinGo {state['game']}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔮 Signal: *{pred['s']}*\n"
                    f"💰 Next Bet: *{current_bet}*\n"
                    f"💵 Profit: *{state['profit']}* / {state['target']}"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 STOP", callback_data="stop_bet")]])
            )
            
            # পরবর্তী রাউন্ড
            interval = {"30s": 30, "1m": 60}.get(state["game"], 30)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("🤖 Bot started successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()