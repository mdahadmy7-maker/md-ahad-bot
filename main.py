import asyncio
import logging
import re
import os
import requests
import hashlib
import uuid
import time
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
API_BASE = "https://api.hgnicepayapi.com/api/webapi" 
API_BET_BASE = "https://api.ar-lottery01.com/api"     
GAME_CODE = "WinGo_30S"
LANG_VAL = 0

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
            "token": "", "token_hdr": "Bearer "
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. এপিআই হেল্পার ফাংশন
# ═══════════════════════════════════════════
def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def build_sig(data):
    t = dict(data)
    t.pop("signature", None)
    t.pop("timestamp", None)
    t["language"] = LANG_VAL
    t["random"] = str(uuid.uuid4()).replace("-", "")
    clean = {k: v for k, v in t.items() if v is not None and v != ""}
    sorted_json = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    t["signature"] = md5(sorted_json).upper()[:32]
    t["timestamp"] = int(time.time())
    return t

def api_call(url_base, endpoint, data, token=None, token_hdr="Bearer "):
    body = build_sig(data)
    
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.hgnice.site",
        "Referer": "https://www.hgnice.site/",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    if token:
        headers["Authorization"] = token_hdr + token
        
    url = url_base + endpoint
    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        try:
            return r.json()
        except:
            return {"code": 999, "msg": f"HTML Response: {r.text[:100]}"}
    except Exception as e:
        return {"code": 999, "msg": f"Network Error: {str(e)}"}

def api_login(phone, pwd):
    data = {
        "username": phone, "pwd": pwd, "phonetype": 1,
        "logintype": "mobile", "packId": "",
        "deviceId": str(uuid.uuid4()).replace("-", ""), "pixelId": "", "fbcId": "",
        "fbc": "", "fbp": "", "adId": "", "language": LANG_VAL,
    }
    j = api_call(API_BASE, "/Login", data)
    return j

def api_balance(token, token_hdr):
    try:
        j = api_call(API_BASE, "/GetAllwallets", {}, token, token_hdr)
        if j and j.get("code") == 0:
            d = j.get("data") or {}
            lst = d.get("thidGameBalanceList", [])
            for item in lst:
                if item.get("vendorCode") == "ARGame":
                    return float(item.get("balance", 0) or 0)
    except: pass
    return 0.0

def get_latest_result():
    try:
        res = requests.get("https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json", timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if list_data:
            return str(list_data[0].get("issueNumber", "")), int(list_data[0].get("number", 0))
    except: pass
    return None, None

def get_prediction():
    _, last_num = get_latest_result()
    if last_num is not None:
        return "SMALL" if last_num >= 5 else "BIG"
    return "BIG"

def place_bet(token, token_hdr, issue, amount, pred):
    bet_content = "BigSmall_Big" if pred == "BIG" else "BigSmall_Small"
    data = {
        "gameCode": GAME_CODE,
        "issueNumber": issue,
        "amount": int(amount),
        "betMultiple": 1,
        "betContent": bet_content
    }
    j = api_call(API_BET_BASE, "/Lottery/WinGoBet", data, token, token_hdr)
    return j and j.get("code") == 0

# ═══════════════════════════════════════════
# ৩. মেইন এপিআই বেটিং লুপ
# ═══════════════════════════════════════════
async def run_api_bot(uid, ctx):
    state = get_state(uid)
    
    await ctx.bot.send_message(chat_id=uid, text="🔄 **API-তে লগইন করা হচ্ছে...**")
    
    # 💡 এখানে লগইন রেসপন্স চেক করা হচ্ছে
    login_resp = api_login(state["temp_phone"], state["temp_password"])
    
    if not login_resp or login_resp.get("code") != 0:
        err_msg = login_resp.get("msg") if login_resp else "No response"
        await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED!**\n\n**Error from Server:** `{err_msg}`\n\n_(সঠিক নাম্বার/পাসওয়ার্ড দিন অথবা আমাকে গেমের লগইন cURL দিন)_", parse_mode="Markdown")
        state["trade_running"] = False
        return
        
    d = login_resp.get("data") or {}
    state["token"] = d.get("token", "")
    state["token_hdr"] = d.get("tokenHeader", "Bearer ")
    
    balance = api_balance(state["token"], state["token_hdr"])
    state["balance"] = balance
    
    dashboard_msg = (
        "╔════════════════════════╗\n"
        "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
        "╚════════════════════════╝\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"☎️ Phone: ***{state['temp_phone'][-4:]}\n"
        f"💰 Balance: ৳ {balance:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Starting Auto Trade..."
    )
    await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown")
    
    target_bal = balance + float(state['target'])
    current_step_idx = 0
    last_seen_issue = ""
    
    await ctx.bot.send_message(chat_id=uid, text="🚀 **AUTO TRADE ACTIVE (API MODE)**", parse_mode="Markdown")
    
    while state["trade_running"]:
        try:
            current_issue, _ = get_latest_result()
            if not current_issue or current_issue == last_seen_issue:
                await asyncio.sleep(1)
                continue
                
            pred = get_prediction()
            bet_amount = state['step_amounts'][current_step_idx]
            
            current_bal = api_balance(state["token"], state["token_hdr"])
            state["balance"] = current_bal
            
            if current_bal >= target_bal:
                await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nBalance: ৳{current_bal:.2f}")
                state["trade_running"] = False
                break
                
            if current_bal < bet_amount:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **লো ব্যালেন্স!** ৳{current_bal:.2f}")
                state["trade_running"] = False
                break
                
            if current_step_idx >= len(state['step_amounts']):
                await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!**")
                state["trade_running"] = False
                break
                
            success = place_bet(state["token"], state["token_hdr"], current_issue, bet_amount, pred)
            
            if success:
                last_seen_issue = current_issue
                await ctx.bot.send_message(chat_id=uid, text=(
                    f"✅ **BET PLACED**\n"
                    f"⏱️ Period: {current_issue}\n"
                    f"🎯 Pred: **{pred}**\n"
                    f"💵 Amount: ৳{bet_amount:.2f}\n"
                    f"🚀 Step: {current_step_idx+1}"
                ), parse_mode="Markdown")
                
                await asyncio.sleep(32)
                
                new_bal = api_balance(state["token"], state["token_hdr"])
                p_l = new_bal - current_bal
                
                if p_l > 0:
                    state["wins"] += 1
                    current_step_idx = 0
                    await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!** +৳{p_l:.2f}\nBalance: ৳{new_bal:.2f}")
                else:
                    state["losses"] += 1
                    current_step_idx += 1
                    await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!** ৳{p_l:.2f}\nBalance: ৳{new_bal:.2f}")
            else:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ Bet failed. Retrying next round...")
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"Loop error: {e}")
            await asyncio.sleep(2)

# ═══════════════════════════════════════════
# ৪. টেলিগ্রাম হ্যান্ডলার
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : API Based Betting\n"
        "🔐 Access  : Private\n\n"
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
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter Password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        await update.message.reply_text("🔄 **CONNECTING TO API...**")
        state["trade_running"] = True
        state["task"] = asyncio.create_task(run_api_bot(uid, ctx))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit (৳):")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("📊 Enter STEP COUNT:")
        except: pass
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 amount (৳):")
        except: pass
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} amount (৳):")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
                await update.message.reply_text("👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except: pass
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🛑 TRADE STOPPED")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your phone number:")
    elif query.data == "start_trade_btn":
        if not state.get("step_amounts") or not state.get("target"):
            await ctx.bot.send_message(chat_id=uid, text="⚠️ আগে টার্গেট এবং স্টেপ সেট করুন।")
            state["awaiting"] = "target"
            await ctx.bot.send_message(chat_id=uid, text="🎯 Enter TARGET profit:")
            return
            
        state["trade_running"] = True
        await ctx.bot.send_message(chat_id=uid, text="🚀 Starting API Bot...")
        state["task"] = asyncio.create_task(run_api_bot(uid, ctx))

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()