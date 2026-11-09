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
from urllib.parse import urlparse, parse_qs
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"

# আপনার আগের সফল API (এটি কিছুক্ষণ পর এক্সপায়ার হতে পারে)
BALANCE_API_URL = "https://api.ar-lottery01.com/api/Lottery/GetBalance"
BALANCE_SIGNATURE = "5D81D38ACC8FAEBA9F1F1675F946ADC5" 
BALANCE_RANDOM = "572476389394"
BALANCE_TIMESTAMP = "1794239224"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "temp_phone": "", "temp_password": "", "balance": "0.00", "user_id": "Unknown", "token": None}
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
# ৩. API ব্যালেন্স (আপনার সফল পদ্ধতি)
# ═══════════════════════════════════════════
def fetch_balance_via_api(lottery_token):
    url = f"{BALANCE_API_URL}?language=en&random={BALANCE_RANDOM}&signature={BALANCE_SIGNATURE}&timestamp={BALANCE_TIMESTAMP}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {lottery_token}",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0 and float(data.get("data", {}).get("balance", 0)) > 0:
            return str(data.get("data", {}).get("balance"))
        return None # ফেইল করলে None দেবে
    except:
        return None

# ═══════════════════════════════════════════
# ৪. Playwright ব্যালেন্স (403 বাইপাস করার জন্য স্টিলথ মোড)
# ═══════════════════════════════════════════
async def fetch_balance_via_browser(uid, ctx, lottery_login_url):
    async with async_playwright() as p:
        # স্টিলথ আর্গুমেন্ট (বট ডিটেকশন এড়াতে)
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}, 
            is_mobile=True,
            has_touch=True,
            locale="en-US",
            timezone_id="Asia/Dhaka",
            extra_http_headers={
                "Referer": "https://dkwin8.com/",
                "Origin": "https://dkwin8.com"
            }
        )
        
        # ⭐ ব্রাউজারকে আসল মানুষের মতো সাজানোর স্ক্রিপ্ট
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)
        
        page = await context.new_page()
        try:
            await page.goto(lottery_login_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(8) # পেজ পুরো লোড হওয়ার অপেক্ষা
            
            # ডিবাগ স্ক্রিনশট
            ss_path = f"balance_debug_{uid}.png"
            await page.screenshot(path=ss_path)
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_path, 'rb'), caption="🔍 স্টিলথ মোডে সাইটটি এমন দেখাচ্ছে:")
            try: os.remove(ss_path)
            except: pass

            page_text = await page.inner_text("body")
            
            # 403 Forbidden চেক
            if "403" in page_text and "Forbidden" in page_text:
                return "BLOCKED"

            # ব্যালেন্স খোঁজা
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
# ৫. মেইন লগইন ফাংশন
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

            # Lottery Token বের করা
            parsed_url = urlparse(lottery_login_url)
            lottery_token = parse_qs(parsed_url.query).get("Token", [""])[0]

            await ctx.bot.edit_message_text(chat_id=uid, message_id=status_msg.message_id, text="🔄 **ব্যালেন্স চেক করা হচ্ছে...**\n(প্রথমে API, পরে ব্রাউজার চেক করা হবে)")
            
            balance = "0.00"
            
            # ১. প্রথমে আপনার সফল API দিয়ে চেষ্টা
            if lottery_token:
                api_balance = await asyncio.to_thread(fetch_balance_via_api, lottery_token)
                if api_balance:
                    balance = api_balance
                    logger.info("API method success!")

            # ২. যদি API ফেইল করে (সিগনেচার এক্সপায়ার), তবে স্টিলথ ব্রাউজার দিয়ে চেষ্টা
            if balance == "0.00":
                logger.info("API failed, trying stealth browser...")
                browser_balance = await fetch_balance_via_browser(uid, ctx, lottery_login_url)
                
                if browser_balance == "BLOCKED":
                    await status_msg.delete()
                    await ctx.bot.send_message(chat_id=uid, text="❌ **সার্ভার ব্লকড (403 Forbidden)**\n\nলটারি সাইটটি আমাদের সার্ভারের আইপি ব্লক করেছে। দয়া করে ব্যালেন্স ম্যানুয়ালি চেক করুন বা ভিন্ন কোনো সার্ভার ব্যবহার করুন।")
                    # আমরা লগইন সফল হলেও এখানেই থামব
                else:
                    balance = browser_balance

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