import asyncio
import logging
import requests
import json
import re
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = "8850232346:AAEUh-lBN2hW0i3WRqR_CJUsGi3CSmSU7HU" 
LOGIN_URL = "https://api.hgnicepayapi.com/api/webapi/Login"
USER_INFO_URL = "https://api.hgnicepayapi.com/api/webapi/GetUserInfo"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, "steps": 0
        }
    return user_state[uid]

async def api_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    
    headers = {
        "authority": "api.hgnicepayapi.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "ar-origin": "https://www.hgnice.vip",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://www.hgnice.vip",
        "referer": "https://www.hgnice.vip/",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    }

    login_payload = {
        "username": phone,
        "pwd": password,
        "phonetype": 0,
        "logintype": "mobile",
        "packId": "",
        "deviceId": "6c872674c682a8f66a5ef13954daf91b",
        "pixelId": "",
        "fbcId": "",
        "fbc": "",
        "fbp": "",
        "adId": "",
        "language": 0,
        "random": "f6dd624a23b343ee9d7e53fd01b8cc66",
        "signature": "F9FF4A78B3914639BB25FCD184E650C8", 
        "timestamp": 1792437970 
    }

    try:
        # --- ধাপ ১: লগইন ---
        response = requests.post(LOGIN_URL, json=login_payload, headers=headers, timeout=15)
        data = response.json()
        
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass

        if data.get("code") != 0:
            err_msg = data.get("msg", "Wrong account or password")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ LOGIN FAILED ({phone})\n\n{err_msg}")
            return

        # --- ধাপ ২: টোকেন নিয়ে ডেটা আনা ---
        user_data = data.get("data", {})
        token = user_data.get("token", "")
        
        headers["authorization"] = f"Bearer {token}"
        info_payload = {
            "language": 0,
            "random": "5f8cc6db4f79466498af393f4cefa024",
            "signature": "1B8641B191D774437D642C99F656F62B",
            "timestamp": 1792440119
        }
        
        uid_val = "Unknown"
        balance = "0.00"

        try:
            info_response = requests.post(USER_INFO_URL, json=info_payload, headers=headers, timeout=10)
            info_data = info_response.json()
            if info_data.get("code") == 0:
                info_d = info_data.get("data", {})
                balance = info_d.get("amount", "0.00")
                uid_val = info_d.get("userId", "Unknown")
        except Exception as e:
            logger.error(f"Info API error: {e}")

        account_info = {
            "phone": phone, "password": password, "uid": uid_val,
            "balance": balance, "token": token
        }
        
        existing = False
        for acc in state["accounts"]:
            if acc["phone"] == phone:
                acc.update(account_info)
                existing = True
                break
        if not existing:
            state["accounts"].append(account_info)

        state["balance"] = balance
        masked_phone = f"***{phone[-4:]}"
        
        dashboard_msg = (
            "╔════════════════════════╗\n"
            "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"☎️ Phone Number\n{masked_phone}\n\n"
            f"👤 Account UID\n{uid_val}\n\n"
            f"💰 Account Balance\n৳ {balance}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🧠 Analysis Engine:  READY\n"
            "🚀 AutoTrade System: READY\n\n"
            "👇 Press START YOUR TARGET to begin"
        )
        
        reply_keyboard = [
            [KeyboardButton("🚀 START YOUR TARGET")],
            [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
        ]
        markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        
        await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=markup)
        
        if len(state["accounts"]) < 6:
            await ctx.bot.send_message(chat_id=uid, text=f"✅ অ্যাকাউন্ট সেভ হয়েছে ({len(state['accounts'])}/6)। নতুন অ্যাকাউন্ট যোগ করতে /start দিন।")

    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"❌ Network Error:\n{str(e)[:100]}")