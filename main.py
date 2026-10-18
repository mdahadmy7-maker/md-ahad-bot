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
# 🔧 আপনার সাইটের API লিংক (F12 Network থেকে দেখে নিন)
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAGHxO0ZNcoSVb3N5u1dSXcWa1_nszIRlxM"  # ← আপনার BotFather থেকে পাওয়া টোকেন
LOGIN_API_URL = "https://api.xxxxx.com/api/v1/login"  # ← আপনার লগইন API URL
BALANCE_API_URL = "https://api.xxxxx.com/api/v1/balance"  # ← আপনার ব্যালেন্স API URL (বা user/info)

# ═══════════════════════════════════════════
# PATTERN SEED (প্রেডিকশন সিকোয়েন্স)
# ═══════════════════════════════════════════
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
            "token": "", "phone": ""
        }
    return user_state[uid]

def gen_period(mode="30s"):
    intervals = {"30s": 30, "1m": 60, "3m": 180, "5m": 300}
    interval = intervals.get(mode, 30)
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    diff = int((now - midnight).total_seconds())
    idx = diff // interval + 1
    date_part = now.strftime("%Y%m%d")
    period_id = f"{date_part}{str(idx).zfill(5)}"
    seconds_left = interval - (diff % interval)
    return {"id": period_id, "index": idx, "left": seconds_left}

# ═══════════════════════════════════════════
# API ফাংশনসমূহ
# ═══════════════════════════════════════════
async def api_login(phone, password):
    # ব্রাউজারের মতো ডিভাইস আইডি ও র‍্যান্ডম কী
    device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    random_str = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    timestamp = int(time.time())
    
    # ⚠️ গুরুত্বপূর্ণ: এখানে আপনার সাইটের আসল সিগনেচার পদ্ধতি বসাতে হবে।
    # আপাতত একটি ডামি সিগনেচার দেওয়া হলো (কাজ না করলে সোর্স কোড থেকে আসলটা বের করুন)
    signature = "1EFC4E6797FE1A0EDFDB3664BB51197A" 

    payload = {
        "username": phone,
        "pwd": password,
        "phonetype": 0,
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
        "signature": signature,
        "timestamp": timestamp
    }
    
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LOGIN_API_URL, json=payload, headers=headers, timeout=10) as res:
                data = await res.json()
                logger.info(f"Login Response: {data}")
                
                if data.get("code") == 0 or data.get("msg") == "Succeed":
                    token = data.get("data", {}).get("token", "")
                    return True, token
                return False, data.get("msg", "লগইন ব্যর্থ")
    except Exception as e:
        return False, str(e)

async def api_get_balance(token):
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}", 
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BALANCE_API_URL, headers=headers, timeout=10) as res:
                data = await res.json()
                logger.info(f"Balance Response: {data}")
                
                if data.get("code") == 0:
                    balance = data.get("data", {}).get("balance", 0.0)
                    return True, balance
                return False, "ব্যালেন্স পাওয়া যায়নি"
    except Exception as e:
        return False, str(e)

# ═══════════════════════════════════════════
# টেলিগ্রাম কমান্ড হ্যান্ডলার
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
        "🐐 *PREMIUM AUTO BET BOT* 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📱 আপনার অ্যাকাউন্টের ফোন নম্বর দিন:",
        parse_mode="Markdown"
    )
    state["awaiting"] = "phone"

async def text_handler(update, ctx):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    # ১. ফোন নম্বর গ্রহণ
    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            f"📱 Number: `{text}`\n\n"
            f"🔑 আপনার পাসওয়ার্ড দিন:",
            parse_mode="Markdown"
        )
        return

    # ২. পাসওয়ার্ড গ্রহণ এবং API চেক
    if state.get("awaiting") == "password":
        password = text
        phone = state.get("phone")
        state["awaiting"] = None
        
        msg = await update.message.reply_text("⏳ Checking Account... Please wait.")
        
        # লগইন চেক
        login_success, token_or_msg = await api_login(phone, password)
        
        if login_success:
            state["token"] = token_or_msg
            await msg.edit_text("✅ Login Successful! Fetching Balance...")
            
            # ব্যালেন্স চেক
            bal_success, balance = await api_get_balance(state["token"])
            if bal_success:
                state["logged_in"] = True
                await msg.edit_text(
                    f"🎉 *ACCOUNT VERIFIED!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📱 Number: `{phone}`\n"
                    f"💰 *Real Balance: {balance}*\n"
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
            await msg.edit_text(
                f"❌ *LOGIN FAILED!*\n"
                f"কারণ: {token_or_msg}",
                parse_mode="Markdown"
            )
        return

    # ৩. বেট স্টেপস গ্রহণ (গেম সিলেক্ট করার পর)
    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            parts = [p for p in parts if p > 0]
            if not parts: raise ValueError()
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(
                f"✅ *STEPS SAVED*\n"
                f"📊 `{', '.join(str(int(x)) if x == int(x) else str(x) for x in parts)}`\n\n"
                f"🎯 এখন *TARGET PROFIT* দিন:\n_Example: 500_",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! এভাবে লিখুন: `10,20,40,80,160`", parse_mode="Markdown")
        return

    # ৪. টার্গেট গ্রহণ এবং অটো বেট চালু
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
                f"⏳ প্রথম সিগন্যাল আসছে...",
                parse_mode="Markdown"
            )
            if state.get("task"): state["task"].cancel()
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        except:
            await update.message.reply_text("❌ সংখ্যা সঠিকভাবে লিখুন। _Example: 500_", parse_mode="Markdown")
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
            f"💰 *BET STEPS* লিখুন (কমা দিয়ে):\n"
            f"_Example: 10,20,40,80,160_",
            parse_mode="Markdown"
        )

async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    try:
        await asyncio.sleep(3)
        while state["running"]:
            p = gen_period(state["game"])
            
            # এখানে আসল বেট পড়ার লজিক বসবে (পরে যোগ করব)
            # আপাতত শুধু সিগন্যাল দেখাবে
            
            pred = PATTERN_SEED[p["index"] % len(PATTERN_SEED)]
            state["last_prediction"] = pred["s"]
            emoji = "🟢" if pred["s"] == "BIG" else "🔵"
            
            await ctx.bot.send_message(
                chat_id=uid,
                text=(
                    f"{emoji} *NEW SIGNAL — WinGo {state['game']}*\n"
                    f"📅 Period: `{p['id']}`\n"
                    f"⏱️ Time Left: *{p['left']}s*\n"
                    f"🔮 Signal: *{pred['s']}* ({pred['n']})\n"
                    f"💰 Next Bet: *{state['steps'][state['step_idx']]}*\n"
                    f"💵 Balance: *Check API*"
                ),
                parse_mode="Markdown"
            )
            interval = {"30s": 30, "1m": 60, "3m": 180, "5m": 300}.get(state["game"], 30)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("🤖 Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()