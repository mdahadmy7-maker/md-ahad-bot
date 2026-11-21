import os
import sys

try:
    import requests
    from telegram import Update
except ImportError:
    os.system(f'{sys.executable} -m pip install requests python-telegram-bot==20.7')
    import requests
    from telegram import Update

import asyncio
import logging
import json
import time
import hashlib
import random
import uuid
import subprocess
from urllib.parse import urlparse, parse_qs
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "9032921988:AAF_Za5BVO0urlUpMMtngU6kBlca1P-uhPs")
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"
HISTORY_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
BET_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
DEVICE_ID = "4aa593880f5c671907b460252b022635"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "temp_phone": "", "lottery_token": ""}
    return user_state[uid]

def generate_login_signature(payload_dict):
    if 'signature' in payload_dict: del payload_dict['signature']
    if 'timestamp' in payload_dict: del payload_dict['timestamp']
    sorted_dict = {k: payload_dict[k] for k in sorted(payload_dict.keys()) if payload_dict[k] != "" and payload_dict[k] is not None}
    return hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode('utf-8')).hexdigest().upper()

def login_and_get_token(phone, password):
    current_timestamp = int(time.time())
    payload = {
        "username": phone, "pwd": password, "phonetype": 1, "logintype": "mobile",
        "packId": "", "deviceId": DEVICE_ID, "pixelId": "", "fbcId": "", "fbc": "", 
        "fbp": "", "adId": "", "language": 0, "random": uuid.uuid4().hex, "timestamp": current_timestamp
    }
    payload["signature"] = generate_login_signature(payload.copy())
    headers = {
        "accept": "application/json, text/plain, */*", "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        response = requests.post(LOGIN_URL, json=payload, headers=headers, timeout=15)
        res_data = response.json()
        if res_data.get("code") == 0:
            lottery_token = parse_qs(urlparse(res_data["data"].get("lotteryLoginUrl", "")).query).get("Token", [""])[0]
            return True, lottery_token or res_data["data"].get("token", "")
        return False, res_data.get('msg')
    except Exception as e:
        return False, str(e)

def fire_bet_via_termux(token, amount, choice, max_retries=5):
    for attempt in range(max_retries):
        try:
            hist_res = requests.get(HISTORY_URL, timeout=10)
            latest_period = int(hist_res.json()['data']['list'][0]['issueNumber'])
            next_issue = str(latest_period + 1)
            
            payload = {
                "gameCode": "WinGo_30S", "issueNumber": str(next_issue),
                "amount": int(amount), "betMultiple": 1, "betContent": f"BigSmall_{choice}",
                "language": "en", "random": random.randint(100000000000, 999999999999),
                "timestamp": int(time.time())
            }
            payload_for_sig = payload.copy()
            del payload_for_sig["timestamp"]
            sorted_dict = {k: payload_for_sig[k] for k in sorted(payload_for_sig.keys())}
            payload["signature"] = hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode()).hexdigest().upper()
            
            data_str = json.dumps(payload, separators=(',', ':'))

            curl_cmd = [
                "curl", "-s", BET_URL,
                "-H", "authority: api.ar-lottery01.com",
                "-H", "accept: application/json, text/plain, */*",
                "-H", "accept-language: en-US,en;q=0.9",
                "-H", f"authorization: Bearer {token}",
                "-H", "content-type: application/json",
                "-H", "origin: https://dkwin8.com",
                "-H", "referer: https://dkwin8.com/",
                "-H", 'sec-ch-ua: "Chromium";v="139", "Not;A=Brand";v="99"',
                "-H", "sec-ch-ua-mobile: ?1",
                "-H", 'sec-ch-ua-platform: "Android"',
                "-H", "sec-fetch-dest: empty",
                "-H", "sec-fetch-mode: cors",
                "-H", "sec-fetch-site: cross-site",
                "-H", "user-agent: Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                "--data-raw", data_str
            ]

            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)
            response_text = result.stdout.strip()
            
            if not response_text:
                 return False, "❌ curl থেকে কোনো রেসপন্স আসেনি।"

            res_json = json.loads(response_text)
            if res_json.get("code") == 0:
                return True, f"🎉✅ বেট সফল!\nPeriod: {next_issue}\nChoice: {choice}"
            elif res_json.get("msgCode") in [404, 411]: 
                time.sleep(2); continue 
            elif res_json.get("code") == 401:
                return False, "❌ টোকেন এক্সপায়ার!"
            else:
                return False, f"❌ ফেইল: {res_json.get('msg')}"
        except Exception as e:
            time.sleep(2)
    return False, "❌ বারবার চেষ্টা করেও বেট পড়ানো যায়নি।"

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text("👇 Press the button below to LOGIN", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text; state["awaiting"] = "password"
        await update.message.reply_text("🔑 Now enter your password:"); return
    if state.get("awaiting") == "password":
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        msg = await update.message.reply_text("🔄 CONNECTING...")
        success, token = await asyncio.to_thread(login_and_get_token, state["temp_phone"], text)
        try: await ctx.bot.delete_message(chat_id=uid, message_id=msg.message_id)
        except: pass
        if not success:
            await update.message.reply_text(f"❌ Login Failed: {token}"); return
        state["lottery_token"] = token 
        reply_keyboard = [[KeyboardButton("🚀 FIRE BET (1 Taka Big)"), KeyboardButton("🚀 FIRE BET (1 Taka Small)")], [KeyboardButton("🛑 STOP")]]
        await update.message.reply_text("✅ LOGIN SUCCESSFUL!\n👇 বাটনে চাপ দিন।", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)); return
    if "FIRE BET" in text:
        if not state.get("lottery_token"):
            await update.message.reply_text("❌ আগে লগইন করুন!"); return
        choice = "Big" if "Big" in text else "Small"
        msg = await update.message.reply_text(f"⏳ curl দিয়ে হিট করা হচ্ছে ({choice})...")
        success, response_msg = await asyncio.to_thread(fire_bet_via_termux, state["lottery_token"], 1, choice)
        await msg.edit_text(response_msg); return
    if text == "🛑 STOP":
        await update.message.reply_text("🛑 স্টপ।"); return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "start_login":
        get_state(update.effective_user.id)["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=update.effective_user.id, text="📱 Enter your phone number:")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Bot started from GitHub...")
    app.run_polling()

if __name__ == "__main__":
    main()