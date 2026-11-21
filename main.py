import os
import sys

try:
    import requests
    import curl_cffi
    from curl_cffi import requests as cffi_requests
    from telegram import Update
except ImportError:
    os.system(f'{sys.executable} -m pip install requests python-telegram-bot==20.7 curl_cffi')
    import requests
    import curl_cffi
    from curl_cffi import requests as cffi_requests
    from telegram import Update

import asyncio
import logging
import json
import time
import uuid
import hashlib
import base64
import random
from urllib.parse import urlparse, parse_qs
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = "9032921988:AAHAUaTKEB26sJ3_ZNqW0uWdDKFtaWngEbE" 
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"
BET_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
DEVICE_ID = "4aa593880f5c671907b460252b022635"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", 
            "auth_token": "", 
            "logged_in_uid": "", 
            "amount": 1, "choice": "Big"
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. কিবোর্ড ডিজাইন
# ───────────────────────────────────────────
def get_main_keyboard(amount, choice):
    keyboard = [
        [KeyboardButton("➖ Amount"), KeyboardButton("➕ Amount")],
        [KeyboardButton(f"🚀 FIRE BET ({amount} Taka {choice})")],
        [KeyboardButton("🛑 STOP")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ───────────────────────────────────────────
# ৩. হেল্পার ফাংশন
# ───────────────────────────────────────────
def generate_login_signature(payload_dict):
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

def login_api(phone, password):
    current_timestamp = int(time.time())
    payload = {
        "username": phone, "pwd": password, "phonetype": 1, "logintype": "mobile",
        "packId": "", "deviceId": DEVICE_ID, "pixelId": "", "fbcId": "", "fbc": "", 
        "fbp": "", "adId": "", "language": 0, "random": uuid.uuid4().hex, "timestamp": current_timestamp
    }
    payload["signature"] = generate_login_signature(payload.copy())

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }

    try:
        response = requests.post(LOGIN_URL, json=payload, headers=headers, timeout=15)
        res_data = response.json()
        
        if res_data.get("code") == 0:
            token = res_data["data"]["token"] 
            jwt_data = decode_jwt_payload(token)
            real_uid = jwt_data.get("UserId", "Unknown")
            return True, real_uid, token
        else:
            return False, "Unknown", res_data.get('msg')
    except Exception as e:
        return False, "Error", str(e)

def place_bet_api(auth_token, amount, choice):
    try:
        # ১. লাইভ চলমান ইস্যু নম্বর বের করা (এটি GET রিকোয়েস্ট, ব্লক হয় না)
        draw_url = f"https://draw.ar-lottery01.com/WinGo/WinGo_30S.json?ts={int(time.time()*1000)}"
        draw_res = requests.get(draw_url, timeout=10)
        current_issue = str(draw_res.json()['current']['issueNumber'])
        
        # ২. সিগনেচার তৈরি
        c_ts = int(time.time())
        # 💡 এখানে randrange এররটি ঠিক করা হয়েছে (১০০ বিলিয়ন থেকে ৯৯৯ বিলিয়ন)
        c_rnd = random.randint(100000000000, 999999999999) 
        
        bet_content = f"BigSmall_{choice}"
        
        payload_to_sign = {
            "gameCode": "WinGo_30S", "issueNumber": current_issue, "amount": int(amount),
            "betMultiple": 1, "betContent": bet_content, "language": "en", "random": int(c_rnd)
        }
        s_dict = {k: payload_to_sign[k] for k in sorted(payload_to_sign.keys())}
        sig = hashlib.md5(json.dumps(s_dict, separators=(',', ':')).encode()).hexdigest().upper()
        
        # ৩. ফাইনাল পেলোড
        new_payload = {
            "gameCode": "WinGo_30S", "issueNumber": current_issue, "amount": int(amount),
            "betMultiple": 1, "betContent": bet_content, "language": "en",
            "random": c_rnd, "signature": sig, "timestamp": c_ts
        }

        # ৪. আপনার সফল cURL-এর হুবহু হেডার
        headers = {
            "authority": "api.ar-lottery01.com",
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {auth_token}",
            "content-type": "application/json",
            "origin": "https://dkwin8.com",
            "referer": "https://dkwin8.com/",
            "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }

        # 💡 ৫. curl_cffi ব্যবহার করে রিকোয়েস্ট (Chrome ব্রাউজার ইমিটেশন)
        res = cffi_requests.post(BET_URL, json=new_payload, headers=headers, impersonate="chrome110", timeout=15)
        
        if not res.text.strip():
             return False, "❌ সার্ভার খালি রেসপন্স দিয়েছে (WAF Block)।"

        res_json = res.json()
        if res_json.get("code") == 0:
            return True, f"🎉 বেট সফল! Period: {current_issue} | {amount} Taka {choice}"
        else:
            return False, f"❌ ফেইল: {res_json.get('msg')}"
            
    except Exception as e:
        return False, f"❌ এরর: {str(e)}"

# ───────────────────────────────────────────
# ৪. হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
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
        await update.message.reply_text("🔑 Now enter your password:")
        return

    if state.get("awaiting") == "password":
        state["awaiting"] = None 
        try: await update.message.delete() 
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO SERVER...**", parse_mode="Markdown")
        
        success, uid_val, token_or_error = await asyncio.to_thread(login_api, state["temp_phone"], text)
        
        try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg.message_id)
        except: pass

        if not success:
            await update.message.reply_text(f"❌ Login Failed: {token_or_error}")
            return
            
        state["auth_token"] = token_or_error 
        state["logged_in_uid"] = uid_val
        
        await update.message.reply_text(
            f"✅ **LOGIN SUCCESSFUL!**\nUID: {uid_val}\n\n"
            "👇 এখন আপনি ➕ বা ➖ চেপে বেটের টাকা বাড়াতে/কমাতে পারেন, তারপর FIRE BET চাপুন।", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(state["amount"], state["choice"])
        )
        return

    if text == "➕ Amount":
        state["amount"] += 1
        await update.message.reply_text(
            f"✅ বেট অ্যামাউন্ট বাড়ানো হয়েছে: **{state['amount']} Taka**", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(state["amount"], state["choice"])
        )
        return

    if text == "➖ Amount":
        if state["amount"] > 1:
            state["amount"] -= 1
        await update.message.reply_text(
            f"✅ বেট অ্যামাউন্ট কমানো হয়েছে: **{state['amount']} Taka**", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(state["amount"], state["choice"])
        )
        return
        
    if text.startswith("🚀 FIRE BET"):
        if not state.get("auth_token"):
            await update.message.reply_text("❌ আগে লগইন করুন!")
            return
            
        msg = await update.message.reply_text(f"⏳ **{state['amount']} Taka {state['choice']}** তে বেট পড়ছে...", parse_mode="Markdown")
        
        success, response_msg = await asyncio.to_thread(
            place_bet_api, 
            state["auth_token"], 
            state["amount"], 
            state["choice"]
        )
        
        await msg.edit_text(response_msg)
        return
        
    if text == "🛑 STOP":
        await update.message.reply_text("🛑 স্টপ করা হয়েছে।")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your phone number:")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "এখানে_আপনার_টেলিগ্রাম_বটের_টোকেন_দিন":
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