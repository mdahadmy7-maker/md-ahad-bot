import asyncio
import logging
import os
import time
import uuid
import hashlib
import json
import base64
import random
from urllib.parse import urlparse, parse_qs
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"

# আপনার সফল ব্যালেন্স API
BALANCE_API_URL = "https://api.ar-lottery01.com/api/Lottery/GetBalance"
LATEST_RANDOM = "572476389394" 
LATEST_SIGNATURE = "5D81D38ACC8FAEBA9F1F1675F946ADC5" 
LATEST_TIMESTAMP = "1794239224"

# বাজি ধরার API এবং পিরিয়ড API
BET_API_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": 0.0, "target": 0, "steps": 0, 
            "step_amounts": [], "current_step": 0, "trade_running": False, 
            "task": None, "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True, "real_uid": "Unknown", "lottery_token": None
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. হেল্পার ফাংশন
# ═══════════════════════════════════════════
def generate_signature(payload_dict):
    if 'signature' in payload_dict: del payload_dict['signature']
    if 'timestamp' in payload_dict: del payload_dict['timestamp']
    
    sorted_dict = {}
    for key in sorted(payload_dict.keys()):
        if payload_dict[key] != "" and payload_dict[key] is not None:
            sorted_dict[key] = payload_dict[key]
            
    json_string = json.dumps(sorted_dict, separators=(',', ':'))
    return hashlib.md5(json_string.encode('utf-8')).hexdigest().upper()

def decode_jwt_payload(token):
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
    except Exception:
        return {}

def fetch_game_balance(lottery_token):
    final_url = f"{BALANCE_API_URL}?language=en&random={LATEST_RANDOM}&signature={LATEST_SIGNATURE}&timestamp={LATEST_TIMESTAMP}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {lottery_token}",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0"
    }
    try:
        res = requests.get(final_url, headers=headers, timeout=15).json()
        if res.get("code") == 0:
            return float(res["data"]["balance"])
        return 0.00
    except:
        return 0.00

# ⭐ পিরিয়ড নাম্বার বের করার ফাংশন (পুরো নাম্বার)
def get_next_period_and_prediction():
    try:
        res = requests.get(HISTORY_API, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        list_data = res.get("data", {}).get("list", [])
        if not list_data: return None, "BigSmall_Big"
        
        latest_period = str(list_data[0].get("issueNumber", ""))
        next_period = str(int(latest_period) + 1) # পরবর্তী পিরিয়ড
        
        # ডামি প্রেডিকশন লজিক
        last_num = int(list_data[0].get("number", 0))
        prediction = "BigSmall_Small" if last_num >= 5 else "BigSmall_Big"
        
        return next_period, prediction
    except:
        return None, "BigSmall_Big"

def place_bet(lottery_token, issue_number, amount, prediction):
    current_timestamp = int(time.time())
    random_str = random.randint(100000000000, 999999999999)
    
    payload = {
        "gameCode": "WinGo_30S",
        "issueNumber": str(issue_number),
        "amount": int(amount),
        "betMultiple": 1,
        "betContent": prediction,
        "language": "en",
        "random": random_str,
        "timestamp": current_timestamp
    }
    payload["signature"] = generate_signature(payload.copy())

    headers = {
        "authority": "api.ar-lottery01.com",
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {lottery_token}",
        "content-type": "application/json",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
    }

    try:
        res = requests.post(BET_API_URL, json=payload, headers=headers, timeout=15)
        return res.status_code, res.text
    except Exception as e:
        return 500, str(e)

# ═══════════════════════════════════════════
# ৩. লগইন এবং ড্যাশবোর্ড
# ═══════════════════════════════════════════
async def api_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone.strip() 
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **CONNECTING TO SITE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")

    current_timestamp = int(time.time())
    payload = {
        "username": login_phone, "pwd": password, "phonetype": 1, "logintype": "mobile",
        "packId": "", "deviceId": uuid.uuid4().hex, "pixelId": "", "fbcId": "", "fbc": "", 
        "fbp": "", "adId": "", "language": 0, "random": uuid.uuid4().hex, "timestamp": current_timestamp
    }
    payload["signature"] = generate_signature(payload.copy())

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin0.com",
        "referer": "https://dkwin0.com/",
        "user-agent": "Mozilla/5.0",
        "x-app-type": "H5",
        "ar-origin": "https://dkwin0.com"
    }

    try:
        await ctx.bot.edit_message_text(chat_id=uid, message_id=status_msg.message_id, text="🔄 **LOGGING IN**\n[█████░░░░░] 50%")
        response = await asyncio.to_thread(requests.post, LOGIN_URL, json=payload, headers=headers, timeout=15)
        res_data = response.json()

        if res_data.get("code") == 0:
            token = res_data["data"]["token"]
            lottery_login_url = res_data["data"]["lotteryLoginUrl"]
            
            jwt_data = decode_jwt_payload(token)
            real_uid = jwt_data.get("UserId", "Unknown")
            state["real_uid"] = real_uid
            
            if login_phone not in state["accounts"]:
                state["accounts"].append(login_phone)

            parsed_url = urlparse(lottery_login_url)
            lottery_token = parse_qs(parsed_url.query).get("Token", [""])[0]
            state["lottery_token"] = lottery_token 

            await ctx.bot.edit_message_text(chat_id=uid, message_id=status_msg.message_id, text="🔄 **FETCHING BALANCE**\n[█████████░] 90%")
            balance = await asyncio.to_thread(fetch_game_balance, lottery_token)
            state["balance"] = balance
            
            await status_msg.delete()
            masked_phone = "****" + login_phone[-4:]

            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 UID: `{real_uid}`\n"
                f"📱 Phone: `{masked_phone}`\n"
                f"💰 Balance: **৳ {balance:.2f}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

        else:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\nকারণ: {res_data.get('msg')}")

    except Exception as e:
        await status_msg.delete()
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **NETWORK ERROR:** {str(e)[:100]}")

# ═══════════════════════════════════════════
# ৪. টেলিগ্রাম হ্যান্ডলারস (ওয়েলকাম মেসেজ ও ফ্লো)
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    # ⭐ আপনার হুবহু ওয়েলকাম মেসেজ
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        f"👥 Accounts: {len(state['accounts'])}/6\n"
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
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"╔════════════════════════╗\n║  🔐 ACCOUNT LOGIN 🔐  ║\n╚════════════════════════╝\n☎️ Number : {text}\n\n🔑 Now enter your password:\nYour message will be deleted immediately for security.")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        await api_login(uid, ctx, state["temp_phone"], state["temp_password"])
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text(f"╔════════════════════════╗\n║   🚀 START YOUR TARGET 🚀   ║\n╚════════════════════════╝\n💰 YOUR BALANCE\n৳ {state.get('balance', 0.00):.2f}\n\n🎯 Enter your TARGET profit amount:")
        return
        
    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            state["awaiting"] = "steps"
            await update.message.reply_text(f"🎯 Target: ৳ {target_amount:.2f}\n\n🚀 Enter your STEP COUNT (e.g. 5):")
        except: await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError()
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
        except: await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            if amount <= 0: raise ValueError()
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
                await update.message.reply_text("⚙️ Configuration Done! Press START TRADE to begin.", reply_markup=inline_kb)
        except: await update.message.reply_text("❌ ভুল ফরম্যাট!")
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
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your DKWIN phone number:")
        
    elif data == "start_trade_btn":
        state["trade_running"] = True
        await query.edit_message_text("✅ **TRADE STARTED...**\n\nবট এখন অটোমেটিক বাজি ধরবে।")
        
        step_idx = 0
        while state["trade_running"] and step_idx < len(state["step_amounts"]):
            amount = state["step_amounts"][step_idx]
            
            # ⭐ পুরো পিরিয়ড নাম্বার বের করা (কোনো ৪ ডিজিটে কাটা নেই)
            issue_number, prediction = get_next_period_and_prediction()
            if not issue_number:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ পিরিয়ড পাওয়া যায়নি!")
                state["trade_running"] = False
                break
                
            # ব্যালেন্স চেক
            current_bal = fetch_game_balance(state["lottery_token"])
            if current_bal < amount:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**\nপ্রয়োজন: ৳{amount}, আছে: ৳{current_bal:.2f}। ট্রেড বন্ধ হচ্ছে।")
                state["trade_running"] = False
                break

            # ⭐ এখানে পুরো পিরিয়ড নাম্বারটি মেসেজে দেখানো হচ্ছে
            await ctx.bot.send_message(chat_id=uid, text=f"🎯 **PLACING BET...**\n🆔 Period: `{issue_number}`\n💰 Amount: ৳{amount}\n📊 Prediction: `{prediction}`", parse_mode="Markdown")
            
            # API-তে সম্পূর্ণ পিরিয়ড নাম্বার পাঠানো হচ্ছে
            status_code, res_text = place_bet(state["lottery_token"], issue_number, amount, prediction)
            
            if status_code == 200 and '"code":0' in res_text:
                await ctx.bot.send_message(chat_id=uid, text=f"✅ **BET SUCCESSFUL!**\nসার্ভার রেসপন্স: `{res_text[:50]}...`", parse_mode="Markdown")
                step_idx += 1 
            else:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **BET FAILED! (Status: {status_code})**\nসার্ভার রেসপন্স: `{res_text[:100]}`", parse_mode="Markdown")
                state["trade_running"] = False
                break
                
            await asyncio.sleep(30)
            
        if step_idx >= len(state["step_amounts"]):
            await ctx.bot.send_message(chat_id=uid, text="🏁 **সব স্টেপ শেষ হয়েছে!**")
            state["trade_running"] = False

    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

def main():
    if not BOT_TOKEN:
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