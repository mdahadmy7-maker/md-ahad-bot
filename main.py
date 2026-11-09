import asyncio
import logging
import os
import time
import uuid
import hashlib
import json
import base64
import re
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, 
            "temp_phone": "", 
            "temp_password": "",
            "balance": "0.00", 
            "user_id": "Unknown",
            "token": None
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. সিগনেচার এবং JWT ডিকোডার
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

# ═══════════════════════════════════════════
# ৩. Playwright দিয়ে ব্যালেন্স বের করা (Debug স্ক্রিনশট সহ)
# ═══════════════════════════════════════════
async def fetch_balance_via_browser(uid, ctx, lottery_login_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}, is_mobile=True
        )
        page = await context.new_page()
        try:
            await page.goto(lottery_login_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(7) # পেজ পুরো লোড হওয়ার অপেক্ষা
            
            # ⭐ ডিবাগ স্ক্রিনশট নেওয়া
            ss_path = f"balance_debug_{uid}.png"
            await page.screenshot(path=ss_path)
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_path, 'rb'), caption="🔍 ব্যালেন্স স্ক্র্যাপ করার সময় সাইটটি এমন দেখাচ্ছে:")
            try: os.remove(ss_path)
            except: pass

            # পেজ থেকে ব্যালেন্স খোঁজা
            page_text = await page.inner_text("body")
            
            # সম্ভাব্য সব রেজেক্স ট্রাই করা
            match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if not match:
                match = re.search(r'[৳]\s*([\d.]+)', page_text)
            if not match:
                match = re.search(r'([\d.]+)\s*[৳]', page_text)
                
            return match.group(1) if match else "0.00"
        except Exception as e:
            logger.error(f"Browser Error: {e}")
            return "0.00"
        finally:
            await browser.close()

# ═══════════════════════════════════════════
# ৪. মেইন লগইন ফাংশন
# ═══════════════════════════════════════════
async def api_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone.strip() 
    
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **লগইন করা হচ্ছে...**", parse_mode="Markdown")

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
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5",
        "ar-origin": "https://dkwin0.com"
    }

    try:
        response = await asyncio.to_thread(requests.post, LOGIN_URL, json=payload, headers=headers, timeout=15)
        res_data = response.json()

        if res_data.get("code") == 0:
            token = res_data["data"]["token"]
            lottery_login_url = res_data["data"]["lotteryLoginUrl"]
            
            jwt_data = decode_jwt_payload(token)
            real_uid = jwt_data.get("UserId", "Unknown")
            
            state["token"] = token
            state["user_id"] = real_uid

            await ctx.bot.edit_message_text(chat_id=uid, message_id=status_msg.message_id, text="🔄 **ব্যালেন্স চেক করা হচ্ছে...**\n(স্ক্রিনশট পাঠানো হচ্ছে, অপেক্ষা করুন)")
            
            # ব্যালেন্স চেক (প্লেরাইট দিয়ে)
            balance = await fetch_balance_via_browser(uid, ctx, lottery_login_url)
            state["balance"] = balance

            await status_msg.delete()

            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone : {login_phone}\n\n"
                f"👤 Real UID : `{real_uid}`\n\n"
                f"💰 Real Balance : **৳ {balance}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Engine: ONLINE\n"
                "🚀 Ready to trade"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")], 
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

        else:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\nকারণ: {res_data.get('msg')}")

    except Exception as e:
        await status_msg.delete()
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **ERROR:** {str(e)[:100]}")

# ═══════════════════════════════════════════
# ৫. টেলিগ্রাম হ্যান্ডলারস
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    welcome_text = "🧠 **BD=WIN~GO=AUTO~BET**\n👇 লগইন করতে নিচের বাটনে ক্লিক করুন।"
    reply_keyboard = [[KeyboardButton("🔐 LOGIN")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if text == "🔐 LOGIN" or text == "/login":
        state["awaiting"] = "phone"
        await update.message.reply_text("📱 আপনার DKWIN ফোন নাম্বার দিন:\n(যেমন: 8801745701676)")
        return

    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 এখন আপনার পাসওয়ার্ড দিন:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        await api_login(uid, ctx, state["temp_phone"], state["temp_password"])
        return

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("login", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()