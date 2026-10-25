import asyncio
import logging
import re
import os
import requests
import json
import time
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
LOGIN_API = "https://api.hgnicepayapi.com/api/webapi/Login"
BET_API = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
BALANCE_API = "https://api.ar-lottery01.com/api/Lottery/GetBalance"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True, "token": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. লাইভ পিরিয়ড ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_live_period():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(f"{HISTORY_API}?t={int(time.time())}", headers=headers, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if list_data:
            return str(list_data[0].get("issueNumber", "Unknown"))
    except: pass
    return None

def get_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(f"{HISTORY_API}?t={int(time.time())}", headers=headers, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: return "BIG"
        
        history = []
        for item in reversed(list_data):
            num = int(item.get("number", 0))
            history.append("SMALL" if num <= 4 else "BIG")
            
        if len(history) < 3: return "BIG"
        l1, l2, l3 = history[-1], history[-2], history[-3]
        if l1 == l2 == l3:
            return "SMALL" if l1 == 'BIG' else "BIG"
        return "SMALL" if l1 == 'BIG' else "BIG"
    except:
        return "BIG"

# ───────────────────────────────────────────
# 💡 ৩. API দিয়ে বেট করার ফাংশন
# ───────────────────────────────────────────
def place_bet_via_api(token, issue_number, amount, choice):
    bet_content = "BigSmall_Big" if choice.upper() == "BIG" else "BigSmall_Small"
    timestamp = int(time.time())
    random_num = random.randint(100000000000, 999999999999)
    
    # ⚠️ এখানে নতুন সিগনেচার বসাতে হবে
    signature = "3018A9A46AF9E0AD85DDE2F4CDE46C97" 
    
    payload = {
        "gameCode": "WinGo_30S",
        "issueNumber": str(issue_number),
        "amount": int(amount),
        "betMultiple": 1,
        "betContent": bet_content,
        "language": "en",
        "random": random_num,
        "signature": signature,
        "timestamp": timestamp
    }
    
    headers = {
        'authority': 'api.ar-lottery01.com',
        'accept': 'application/json',
        'authorization': f'Bearer {token}',
        'content-type': 'application/json',
        'origin': 'https://www.hgnice.vip',
        'referer': 'https://www.hgnice.vip/',
        'user-agent': 'Mozilla/5.0'
    }

    try:
        response = requests.post(BET_API, headers=headers, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Bet API Error: {e}")
        return None

# ───────────────────────────────────────────
# ৪. লগইন এবং অটো-বেট ফাংশন (API)
# ───────────────────────────────────────────
async def api_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    
    async def update_loading(percent, text="CONNECTING TO HGNICE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    # ---------------- ১. লগইন API ----------------
    await update_loading(20, "LOGGING IN VIA API")
    
    device_id = ''.join(random.choices('0123456789abcdef', k=32))
    
    login_payload = {
        "username": phone,
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
        "random": ''.join(random.choices('0123456789abcdef', k=32)),
        "signature": "85C3443C3CF5B878FAC5F734E4515168", # আপনার নতুন লগইন সিগনেচার
        "timestamp": int(time.time())
    }
    
    login_headers = {
        'authority': 'api.hgnicepayapi.com',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://www.hgnice.vip',
        'referer': 'https://www.hgnice.vip/',
        'user-agent': 'Mozilla/5.0'
    }
    
    try:
        res = requests.post(LOGIN_API, headers=login_headers, json=login_payload, timeout=15)
        login_data = res.json()
        if login_data.get("code") == 0:
            token = login_data["data"]["token"]
            state["token"] = token
            await update_loading(50, "LOGIN SUCCESSFUL")
        else:
            await update_loading(100, f"LOGIN FAILED: {login_data.get('msg')}")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\n{login_data}")
            return
    except Exception as e:
        await update_loading(100, f"API ERROR")
        await ctx.bot.send_message(chat_id=uid, text=f"❌ **API ERROR:**\n`{str(e)[:100]}`")
        return

    # ---------------- ২. ব্যালেন্স চেক API ----------------
    await update_loading(70, "FETCHING BALANCE")
    balance = "0.00"
    try:
        bal_url = f"{BALANCE_API}?language=en&random={random.randint(100000000000, 999999999999)}&signature=958B6C3ECB3352EEA5389E221BB74BCA&timestamp={int(time.time())}"
        bal_headers = {
            'authorization': f'Bearer {token}',
            'accept': 'application/json',
            'user-agent': 'Mozilla/5.0'
        }
        bal_res = requests.get(bal_url, headers=bal_headers, timeout=10)
        bal_data = bal_res.json()
        if bal_data.get("code") == 0:
            balance = str(bal_data["data"]["balance"])
    except Exception as e:
        logger.error(f"Balance API Error: {e}")

    await update_loading(100, "READY")
    await asyncio.sleep(0.5)
    
    if loading_msg_id:
        try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
        except: pass

    # ড্যাশবোর্ড মেসেজ
    dashboard_msg = (
        "╔════════════════════════╗\n"
        "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
        "╚════════════════════════╝\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"☎️ Phone Number\n{phone}\n\n"
        f"💰 Account Balance\n৳ {balance}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Analysis Engine:  READY\n"
        "🚀 AutoTrade System: READY\n\n"
        "👇 Press START YOUR TARGET to begin"
    )
    reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
    await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

    while not state.get("trade_running", False):
        await asyncio.sleep(1)
        if state.get("task") != asyncio.current_task():
            return

    # ---------------- ৩. অটো-বেট লুপ ----------------
    current_step_idx = 0

    while state["trade_running"]:
        try:
            if current_step_idx >= len(state['step_amounts']):
                await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!**")
                state["trade_running"] = False
                break
                
            bet_amount = float(state['step_amounts'][current_step_idx])
            
            choice = get_prediction()
            current_period = get_live_period()

            # টাইমার চেক
            logger.info("Waiting for timer (6s-30s)...")
            valid_timer = False
            timer_val = "0s"
            
            for _ in range(150): 
                now = datetime.now()
                seconds = now.second
                timer_sec = 30 - (seconds % 30)
                if 6 <= timer_sec <= 30:
                    timer_val = f"{timer_sec}s"
                    valid_timer = True
                    break
                await asyncio.sleep(0.2)

            if not valid_timer:
                await asyncio.sleep(1)
                continue

            # 💡 API দিয়ে বেট করা
            api_response = place_bet_via_api(state["token"], current_period, bet_amount, choice)
            
            if api_response and api_response.get("code") == 0:
                await ctx.bot.send_message(chat_id=uid, text=(
                    f"✅ **BET PLACED!**\n\n"
                    f"🎯 Prediction: **{choice}**\n"
                    f"💵 Amount: ৳ {bet_amount:.2f}\n"
                    f"⏱️ Period: {current_period}\n"
                    f"📊 Status: Success"
                ))
                current_step_idx = 0
            else:
                error_msg = api_response.get("msg", "Unknown Error") if api_response else "No Response"
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **BET FAILED!**\nError: {error_msg}")
                state["trade_running"] = False
                break
                
            # নতুন রাউন্ডের জন্য অপেক্ষা (৩২ সেকেন্ড)
            await asyncio.sleep(32)
                
        except Exception as e:
            logger.error(f"Betting loop error: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\n{str(e)[:50]}")
            state["trade_running"] = False
            break

# ───────────────────────────────────────────
# ৪. হ্যান্ডলারগুলো
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET (API VERSION)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 Access  : Private\n"
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
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number : {text}\n\n🔑 Now enter your password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(api_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter your TARGET profit amount (in ৳):")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text(f"🎯 Target: ৳ {state['target']}\n\n🚀 Enter your STEP COUNT:")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু সংখ্যা দিন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১-৫০ এর মধ্যে সংখ্যা দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text("⚙️ Configuration Done. Press START TRADE.", reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু সংখ্যা দিন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 LOGGED OUT")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    if data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your HGNICE phone number:")
    elif data == "start_trade_btn":
        state["trade_running"] = True
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["trade_running"] = False
    if state.get("task"): state["task"].cancel()
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "balance": "0.00", "target": 0, 
        "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False, "task": None,
        "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True, "token": ""
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()