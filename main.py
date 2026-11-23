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

# Render Keep-Alive এর জন্য (আপনার ফাইলে এটি মিসিং ছিল)
from flask import Flask
from threading import Thread

# ═══════════════════════════════════════════
# ১. কনফিগারেশন এবং কঠোর সিকিউরিটি
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9032921988:AAF_Za5BVO0urlUpMMtngU6kBlca1P-uhPs")

AUTHORIZED_USERS = [] 

def is_authorized(uid: int) -> bool:
    if not AUTHORIZED_USERS:
        return True
    return uid in AUTHORIZED_USERS

LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"
PANEL_URL = "https://api.ar-lottery01.com/api/Energy/GetPanel"
BET_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
HISTORY_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
DEVICE_ID = "4aa593880f5c671907b460252b022635"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

BOLD_DIGITS = str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵")
def bnum(x):
    return str(x).translate(BOLD_DIGITS)

def fmt_uid(uid):
    s = str(uid)
    if s.isdigit() and len(s) > 7:
        return s[-7:]
    return s

PATTERN_PREDICTION = ["Big", "Small", "Small", "Big"]

STEP_EXHAUSTED_MSG = (
    "<b>╔════════════════════════════╗</b>\n"
    "<b>║    ✨ 🔔 নতুন আপডেট! 🔔 ✨     ║</b>\n"
    "<b>╠════════════════════════════╣</b>\n"
    "<b>║                            ║</b>\n"
    "<b>║  💫 আপনার ধাপ অনুযায়ী ║</b>\n"
    "<b>║  সব কাজ সফলভাবে শেষ   ║</b>\n"
    "<b>║  হয়েছে। ✅            ║</b>\n"
    "<b>║                            ║</b>\n"
    "<b>║  🎊 স্বপ্ন পূরণের পথে  ║</b>\n"
    "<b>║  এগিয়ে চলুন,          ║</b>\n"
    "<b>║  সাফল্যের নতুন দিগন্ত  ║</b>\n"
    "<b>║  ছুঁয়ে চলুন। 🌸       ║</b>\n"
    "<b>║                            ║</b>\n"
    "<b>║  ✨ আজকের পরিশ্রম,     ║</b>\n"
    "<b>║  আগামী দিনের জয়,      ║</b>\n"
    "<b>║  সাহস নিয়ে এগিয়ে যান,║</b>\n"
    "<b>║  সাফল্য হবেই নিশ্চয়! 💖║</b>\n"
    "<b>║                            ║</b>\n"
    "<b>╠════════════════════════════╣</b>\n"
    "<b>║👇 𝗧𝘆𝗽𝗲 /𝘀𝘁𝗮𝗿𝘁 𝗮𝗻𝗱 𝗽𝗿𝗲𝘀𝘀 𝗟𝗢𝗚𝗜𝗡 𝗧𝗢 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻 𝗮𝗴𝗮𝗶𝗻.║</b>\n"
    "<b>╚════════════════════════════╝</b>"
)

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": 0.0, "target": 0, "steps": 0,
            "step_amounts": [], "current_step": 0, "trade_running": False,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True, "real_uid": "Unknown", "lottery_token": None,
            "token_expiry_time": 0, "last_betted_issue": None, "next_period": "----",
            "prediction_shown": False, "trade_task": None,
            "pattern_index": 0, "last_predicted_issue": None,
            "session": requests.Session()
        }
    return user_state[uid]

# ───────────────────────────────────────
# ২. সিগনেচার ও হেল্পার
# ───────────────────────────────────────
def generate_login_sig(payload_dict):
    if 'signature' in payload_dict: del payload_dict['signature']
    if 'timestamp' in payload_dict: del payload_dict['timestamp']
    sorted_dict = {k: payload_dict[k] for k in sorted(payload_dict.keys()) if payload_dict[k] != "" and payload_dict[k] is not None}
    return hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode('utf-8')).hexdigest().upper()

def generate_dynamic_sig(payload_dict):
    sorted_dict = {k: payload_dict[k] for k in sorted(payload_dict.keys())}
    return hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode('utf-8')).hexdigest().upper()

def decode_jwt_expiry(token):
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        decoded_data = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
        return int(decoded_data.get('exp', 0))
    except:
        return 0

def decode_jwt(token):
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
    except:
        return {}

def get_remaining_seconds(issue_number):
    try:
        s = str(issue_number)[:14]
        dt = time.strptime(s, "%Y%m%d%H%M%S")
        start_ts = time.mktime(dt)
        elapsed = time.time() - start_ts
        remaining = 30 - elapsed
        return max(0, int(remaining))
    except:
        return max(0, 30 - int(time.time()) % 30)

def build_timer_bar(seconds):
    filled = min(10, max(0, int(10 * seconds / 30)))
    bar = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {bnum(seconds)}𝘀"

def get_pattern_prediction(state, issue):
    if state.get("last_predicted_issue") != issue:
        pred = PATTERN_PREDICTION[state["pattern_index"] % len(PATTERN_PREDICTION)]
        state["pattern_index"] += 1
        state["last_predicted_issue"] = issue
        return pred
    return PATTERN_PREDICTION[(state["pattern_index"] - 1) % len(PATTERN_PREDICTION)]

# ───────────────────────────────────────
# ৩. API কল (লগইন এবং টোকেন ফিক্স করা হয়েছে)
# ───────────────────────────────────────
def refresh_token(session, phone, password):
    ts = int(time.time())
    payload = {
        "username": phone, "pwd": password, "phonetype": 1, "logintype": "mobile",
        "packId": "", "deviceId": DEVICE_ID, "pixelId": "", "fbcId": "", "fbc": "",
        "fbp": "", "adId": "", "language": 0, "random": uuid.uuid4().hex, "timestamp": ts
    }
    payload["signature"] = generate_login_sig(payload.copy())
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        res = session.post(LOGIN_URL, json=payload, headers=headers, timeout=15)
        data = res.json()
        if data.get("code") != 0:
            return False, data.get("msg"), None, None, None
        
        lottery_url = data["data"].get("lotteryLoginUrl", "")
        query_params = parse_qs(urlparse(lottery_url).query)
        sso_ticket = query_params.get("Token", [""])[0] or query_params.get("token", [""])[0]

        panel_rnd = random.randint(100000000000, 999999999999)
        panel_ts = int(time.time())
        panel_sig = generate_dynamic_sig({"gameCode": "WinGo_30S", "language": "en", "random": panel_rnd})
        panel_url = f"{PANEL_URL}?gameCode=WinGo_30S&language=en&random={panel_rnd}&signature={panel_sig}&timestamp={panel_ts}"
        
        # 🟢 FIX 1: origin এবং referer এখানেও dkwin9.com করা হলো
        panel_headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {sso_ticket}",
            "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }
        panel_res = session.get(panel_url, headers=panel_headers, timeout=10)
        
        # 🟢 FIX 2: হেডারের পাশাপাশি JSON বডি থেকেও টোকেন খোঁজা হবে
        auth_header = panel_res.headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            real_token = auth_header[7:]
            expiry = decode_jwt_expiry(real_token)
            real_uid = decode_jwt(real_token).get("UserId", "Unknown")
            return True, "Success", real_token, expiry, real_uid
        else:
            try:
                p_json = panel_res.json()
                if p_json.get("code") == 0 and "data" in p_json:
                    real_token = p_json["data"].get("token") or p_json["data"].get("Token")
                    if real_token:
                        if real_token.startswith("Bearer "):
                            real_token = real_token[7:]
                        expiry = decode_jwt_expiry(real_token)
                        real_uid = decode_jwt(real_token).get("UserId", "Unknown")
                        return True, "Success", real_token, expiry, real_uid
            except: pass
            
            logger.error(f"Panel Response Error: {panel_res.text}")
            return False, "No token in header or body", None, None, None
    except Exception as e:
        return False, str(e), None, None, None

def get_panel_data(session, real_token):
    panel_rnd = random.randint(100000000000, 999999999999)
    panel_ts = int(time.time())
    panel_sig = generate_dynamic_sig({"gameCode": "WinGo_30S", "language": "en", "random": panel_rnd})
    panel_url = f"{PANEL_URL}?gameCode=WinGo_30S&language=en&random={panel_rnd}&signature={panel_sig}&timestamp={panel_ts}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {real_token}",
        "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        res = session.get(panel_url, headers=headers, timeout=10)
        data = res.json()
        if data.get("code") == 0:
            return data["data"]["currentIssueNumber"], data["data"]["phase"]
    except:
        pass
    return None, None

def fetch_game_balance(session, real_token):
    bal_rnd = random.randint(100000000000, 999999999999)
    bal_ts = int(time.time())
    bal_sig = generate_dynamic_sig({"language": "en", "random": bal_rnd})
    bal_url = f"https://api.ar-lottery01.com/api/Lottery/GetBalance?language=en&random={bal_rnd}&signature={bal_sig}&timestamp={bal_ts}"
    bal_headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {real_token}",
        "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        bal_res = session.get(bal_url, headers=bal_headers, timeout=15)
        bal_data = bal_res.json()
        if bal_data.get("code") == 0:
            return float(bal_data['data']['balance'])
    except:
        pass
    return 0.00

def place_bet(session, real_token, issue_number, amount, choice):
    try:
        bet_content = f"BigSmall_{choice}"
        c_ts = int(time.time())
        c_rnd = random.randint(100000000000, 999999999999)
        sig = generate_dynamic_sig({
            "gameCode": "WinGo_30S", "issueNumber": str(issue_number), "amount": int(amount),
            "betMultiple": 1, "betContent": bet_content, "language": "en", "random": int(c_rnd)
        })
        bet_payload = {
            "gameCode": "WinGo_30S", "issueNumber": str(issue_number), "amount": int(amount),
            "betMultiple": 1, "betContent": bet_content, "language": "en",
            "random": c_rnd, "signature": sig, "timestamp": c_ts
        }
        json_string = json.dumps(bet_payload, separators=(',', ':'))
        bet_headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {real_token}",
            "content-type": "application/json",
            "origin": "https://dkwin9.com", "referer": "https://dkwin9.com/",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }
        bet_res = session.post(BET_URL, data=json_string, headers=bet_headers, timeout=15)
        return bet_res.status_code, bet_res.text
    except Exception as e:
        return 500, str(e)

def fetch_result(session, issue_number):
    try:
        res = session.get(HISTORY_URL, timeout=10)
        data = res.json()
        for item in data.get('data', {}).get('list', []):
            if str(item.get('issueNumber')) == str(issue_number):
                nums = item.get('number', '')
                if nums:
                    total = sum(int(x) for x in str(nums).split(','))
                    return "Big" if total >= 23 else "Small"
    except Exception as e:
        logger.error(f"fetch_result error: {e}")
    return None

# ───────────────────────────────────────
# ৪. মেসেজ বিল্ডার (আপনার আগের কোডের মতোই)
# ───────────────────────────────────────
def build_step_amounts_msg(steps):
    return f"<b>╔════════════════════════╗</b>\n<b>║   💵 𝗦𝗧𝗘𝗣 𝗔𝗠𝗢𝗨𝗡𝗧𝗦 💵   ║</b>\n<b>╚════════════════════════╝</b>\n\n<b>𝗬𝗼𝘂 𝗰𝗵𝗼𝘀𝗲 {bnum(steps)} 𝘀𝘁𝗲𝗽𝘀.</b>\n\n<b>💵 𝗦𝘁𝗲𝗽 𝟭 — 𝗯𝗲𝘁 𝗮𝗺𝗼𝘂𝗻𝘁? (𝗶𝗻 ৳)</b>"

def build_single_step_prompt(step_num):
    return f"<b>💵 𝗦𝘁𝗲𝗽 {bnum(step_num)} — 𝗯𝗲𝘁 𝗮𝗺𝗼𝘂𝗻𝘁? (𝗶𝗻 ৳)</b>"

def build_step_plan_bars(step_amounts):
    return "\n".join([f"<b>𝗦𝘁𝗲𝗽 {bnum(f'{i+1:02d}')} {'▰' * min(i + 1, 10)} ৳ {bnum(f'{amt:.2f}')}</b>" for i, amt in enumerate(step_amounts)])

def build_step_plan_tree(step_amounts):
    n = len(step_amounts)
    return "\n".join([f"<b>{'└─' if i == n - 1 else '├─'} 𝗦𝘁𝗲𝗽 {bnum(f'{i+1:02d}')} ➤ ৳ {bnum(f'{amt:.2f}')}</b>" for i, amt in enumerate(step_amounts)])

def build_config_msg(balance, target, stop_at, steps, step_amounts, current_issue):
    remaining = get_remaining_seconds(current_issue) if current_issue else 30
    return f"<b>╔════════════════════════╗</b>\n<b>║  ⚙️ 𝗧𝗥𝗔𝗗𝗘 𝗖𝗢𝗡𝗙𝗜𝗚𝗨𝗥𝗔𝗧𝗜𝗢𝗡 ⚙️   ║</b>\n<b>╚════════════════════════╝</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲  : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁   : ৳ {bnum(f'{target:.2f}')} 𝗽𝗿𝗼𝗳𝗶𝘁</b>\n<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁  : ৳ {bnum(f'{stop_at:.2f}')}</b>\n<b>📋 𝗦𝘁𝗲𝗽𝘀    : {bnum(steps)}</b>\n<b>⚠️ 𝗧𝗼𝘁𝗮𝗹 𝗥𝗶𝘀𝗸 : ৳ {bnum(f'{sum(step_amounts):.2f}')}</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>📊 𝗦𝗧𝗘𝗣 𝗣𝗟𝗔𝗡</b>\n{build_step_plan_bars(step_amounts)}\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>⏱️ 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗣𝗲𝗿𝗶𝗼𝗱 {bnum(current_issue) if current_issue else '----'} </b>\n<b>{build_timer_bar(remaining)}</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>🧠 𝗘𝗻𝗴𝗶𝗻𝗲: 𝟵 𝗹𝗮𝘆𝗲𝗿𝘀 + 𝗹𝗶𝘃𝗲 𝗯𝗮𝗰𝗸𝘁𝗲𝘀𝘁</b>\n<b>👇 𝗣𝗿𝗲𝘀𝘀 𝗦𝗧𝗔𝗥𝗧 𝗧𝗥𝗔𝗗𝗘 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻.</b>"

def build_auto_trade_msg(balance, target, stop_at, steps, step_amounts, current_issue):
    remaining = get_remaining_seconds(current_issue) if current_issue else 30
    return f"<b>╔════════════════════════╗</b>\n<b>║   🚀 𝗔𝗨𝗧𝗢 𝗧𝗥𝗔𝗗𝗘 𝗔𝗖𝗧𝗜𝗩𝗘 🚀  ║</b>\n<b>╚════════════════════════╝</b>\n<b>==============================</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁 : ৳ {bnum(f'{target:.2f}')} 𝗽𝗿𝗼𝗳𝗶𝘁</b>\n<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁 : ৳ {bnum(f'{stop_at:.2f}')}</b>\n<b>📋 𝗦𝘁𝗲𝗽𝘀 : {bnum(steps)}</b>\n<b>📊 𝗦𝘁𝗲𝗽 𝗣𝗹𝗮𝗻:</b>\n{build_step_plan_tree(step_amounts)}\n<b>⏱️ 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗣𝗲𝗿𝗶𝗼𝗱 {bnum(current_issue) if current_issue else '----'}</b>\n<b>{build_timer_bar(remaining)}</b>\n<b>🧠 𝗔𝗻𝗮𝗹𝘆𝘀𝗶𝗻𝗴 𝗺𝗮𝗿𝗸𝗲𝘁...</b>"

def build_prediction_animation(percent=75):
    filled = int(percent / 10)
    return f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>🧠 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗜𝗡𝗚 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>∴ 𝗩𝗲𝗿𝗶𝗳𝘆𝗶𝗻𝗴 𝘄𝗮𝗹𝗹𝗲𝘁 & 𝗽𝗲𝗿𝗶𝗼𝗱...</b>\n<b>[{'█' * filled + '░' * (10 - filled)}] {bnum(percent)}%</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>⏳ 𝗥𝘂𝗻𝗻𝗶𝗻𝗴 𝟵 𝗹𝗮𝘆𝗲𝗿𝘀 + 𝗯𝗮𝗰𝗸𝘁𝗲𝘀𝘁...</b>"

def build_new_trade_msg(period, choice, step_num, amount, balance):
    remaining = get_remaining_seconds(period)
    side_icon = "🔵" if choice == "Big" else "🔴"
    return f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>🤖 𝗡𝗘𝗪 𝗧𝗥𝗔𝗗𝗘 𝗣𝗟𝗔𝗖𝗘𝗗</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>⏱️ 𝗣𝗲𝗿𝗶𝗼𝗱    : {bnum(period)}</b>\n<b>⏱️ 𝗧𝗶𝗺𝗲𝗿     : {bnum(remaining)}s 𝗿𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴</b>\n<b>{side_icon} 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡 : {choice.upper()} ❮❮❮</b>\n<b>🚀 𝗦𝘁𝗲𝗽       : 🟢 𝗡𝗼𝗿𝗺𝗮𝗹 — 𝗦𝘁𝗲𝗽 {bnum(step_num)}</b>\n<b>💵 𝗔𝗺𝗼𝘂𝗻𝘁     : ৳ {bnum(f'{amount:.2f}')}</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲    : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>⏳ 𝗪𝗮𝗶𝘁𝗶𝗻𝗴 𝗳𝗼𝗿 𝗿𝗲𝘀𝘂𝗹𝘁...</b>"

def build_result_msg(period, choice, step_num, amount, won, pl, balance, wins, losses, next_step):
    total = wins + losses
    rate = (wins / total * 100) if total > 0 else 0
    result_icon = "𝗪𝗜𝗡 ✅" if won else "𝗟𝗢𝗦𝗦 ❌"
    color = "🟢" if won else "🔴"
    side_icon = "🔵" if choice == "Big" else "🔴"
    pl_str = f"+৳ {bnum(f'{pl:.2f}')}" if pl >= 0 else f"-৳ {bnum(f'{abs(pl):.2f}')}"
    next_msg = "🟢 𝗥𝗲𝗰𝗼𝘃𝗲𝗿𝗲𝗱! 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗦𝘁𝗲𝗽 1." if won else f"🔴 𝗟𝗼𝘀𝘀! 𝗠𝗼𝘃𝗶𝗻𝗴 𝘁𝗼 𝗦𝘁𝗲𝗽 {bnum(next_step)}."
    return f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>{color} 𝗧𝗥𝗔𝗗𝗘 𝗥𝗘𝗦𝗨𝗟𝗧</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>⏰ 𝗣𝗲𝗿𝗶𝗼𝗱 : {bnum(period)}</b>\n<b>{side_icon} 𝗦𝗶𝗱𝗲 : {choice.upper()} ❮❮❮</b>\n<b>🚀 𝗦𝘁𝗲𝗽 : {bnum(step_num)}</b>\n<b>💵 𝗔𝗺𝗼𝘂𝗻𝘁 : ৳ {bnum(f'{amount:.2f}')}</b>\n<b>📊 𝗥𝗲𝘀𝘂𝗹𝘁 : {result_icon}</b>\n<b>💹 𝗣/𝗟 : {pl_str}</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>🏆 𝗪𝗶𝗻𝘀 : {bnum(wins)} 🔴 𝗟𝗼𝘀𝘀𝗲𝘀 : {bnum(losses)} 📈 𝗥𝗮𝘁𝗲 : {bnum(f'{rate:.1f}')}%</b>\n<b>➡️ 𝗡𝗲𝘅𝘁 𝗦𝘁𝗲𝗽 : {bnum(next_step)}</b>\n<b>{next_msg}</b>"

def build_target_reached_msg(start_balance, final_balance, profit, trades, wins, losses):
    rate = (wins / trades * 100) if trades > 0 else 0
    return f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>🎯 𝗧𝗔𝗥𝗚𝗘𝗧 𝗥𝗘𝗔𝗖𝗛𝗘𝗗 🎉</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>💰 𝗦𝘁𝗮𝗿𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{start_balance:.2f}')}</b>\n<b>💳 𝗙𝗶𝗻𝗮𝗹 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{final_balance:.2f}')}</b>\n<b>💹 𝗣𝗿𝗼𝗳𝗶𝘁 𝗠𝗮𝗱𝗲 : +৳ {bnum(f'{profit:.2f}')}</b>\n<b>📊 𝗧𝗿𝗮𝗱𝗲𝘀 : {bnum(trades)} | 🟢 𝗪𝗶𝗻 : {bnum(wins)} | 🔴 𝗟𝗼𝘀𝘀 : {bnum(losses)}</b>\n<b>🏆 𝗪𝗶𝗻 𝗥𝗮𝘁𝗲 : {bnum(f'{rate:.1f}')}%</b>\n<b>✅ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗮𝘂𝘁𝗼-𝗹𝗼𝗴𝗴𝗲𝗱 𝗼𝘂𝘁.</b>\n<b>👇 𝗧𝘆𝗽𝗲 /𝘀𝘁𝗮𝗿𝘁 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻 𝗮𝗴𝗮𝗶𝗻.</b>"

# ───────────────────────────────────────
# ৫. ট্রেড ওয়ার্কার (Smart Wait System)
# ───────────────────────────────────────
async def trade_worker(bot, uid):
    state = get_state(uid)
    session = state["session"]
    token = state["lottery_token"]
    steps = state["step_amounts"]
    start_balance = state["balance"]
    target = state["target"]
    stop_at = start_balance + target
    current_step = 0
    wins = 0
    losses = 0
    total_trades = 0

    while state["trade_running"]:
        try: curr_bal = await asyncio.to_thread(fetch_game_balance, session, token)
        except: curr_bal = state["balance"]

        if curr_bal >= stop_at:
            profit = curr_bal - start_balance
            await bot.send_message(chat_id=uid, text=build_target_reached_msg(start_balance, curr_bal, profit, total_trades, wins, losses), parse_mode="HTML")
            state["trade_running"] = False
            state["lottery_token"] = None
            state["temp_phone"] = ""
            state["temp_password"] = ""
            state["session"] = requests.Session()
            break

        if not token or int(time.time()) >= (state["token_expiry_time"] - 10):
            success, msg, new_token, expiry, _ = await asyncio.to_thread(refresh_token, session, state["temp_phone"], state["temp_password"])
            if success:
                token = new_token
                state["lottery_token"] = new_token
                state["token_expiry_time"] = expiry
            else:
                await bot.send_message(chat_id=uid, text=f"<b>❌ 𝗧𝗼𝗸𝗲𝗻 𝗿𝗲𝗳𝗿𝗲𝘀𝗵 𝗳𝗮𝗶𝗹𝗲𝗱: {msg}</b>", parse_mode="HTML")
                state["trade_running"] = False
                break

        issue, phase = await asyncio.to_thread(get_panel_data, session, token)
        if not issue or phase != "Betting" or issue == state.get("last_betted_issue"):
            await asyncio.sleep(2)
            continue

        if current_step >= len(steps):
            await bot.send_message(chat_id=uid, text=STEP_EXHAUSTED_MSG, parse_mode="HTML")
            state["trade_running"] = False
            break

        amount = steps[current_step]

        if curr_bal < amount:
            await bot.send_message(chat_id=uid, text=f"<b>❌ 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗯𝗮𝗹𝗮𝗻𝗰𝗲!\n𝗡𝗲𝗲𝗱: ৳ {bnum(f'{amount:.2f}')}, 𝗛𝗮𝘃𝗲: ৳ {bnum(f'{curr_bal:.2f}')}.</b>", parse_mode="HTML")
            state["trade_running"] = False
            break

        await bot.send_message(chat_id=uid, text=build_auto_trade_msg(curr_bal, target, stop_at, len(steps), steps, issue), parse_mode="HTML")

        if not state.get("prediction_shown"):
            state["prediction_shown"] = True
            try:
                pred_msg = await bot.send_message(chat_id=uid, text=build_prediction_animation(50), parse_mode="HTML")
                await asyncio.sleep(1)
                try: await pred_msg.edit_text(build_prediction_animation(75), parse_mode="HTML")
                except: pass
                await asyncio.sleep(1)
                try: await pred_msg.edit_text(build_prediction_animation(100), parse_mode="HTML")
                except: pass
                await asyncio.sleep(2)
                try: await pred_msg.delete()
                except: pass
            except Exception as e: logger.error(f"prediction animation error: {e}")

        predicted = get_pattern_prediction(state, issue)

        status_code, res_text = await asyncio.to_thread(place_bet, session, token, issue, amount, predicted)

        if status_code != 200:
            await bot.send_message(chat_id=uid, text=f"<b>❌ 𝗕𝗘𝗧 𝗙𝗔𝗜𝗟𝗘𝗗 (status {status_code})</b>", parse_mode="HTML")
            state["trade_running"] = False
            break
        try:
            rj = json.loads(res_text)
            if rj.get("code") != 0:
                await bot.send_message(chat_id=uid, text=f"<b>❌ 𝗕𝗘𝗧 𝗙𝗔𝗜𝗟𝗘𝗗: {rj.get('msg')}</b>", parse_mode="HTML")
                state["trade_running"] = False
                break
        except: pass

        state["last_betted_issue"] = issue
        await bot.send_message(chat_id=uid, text=build_new_trade_msg(issue, predicted, current_step + 1, amount, curr_bal), parse_mode="HTML")

        await asyncio.sleep(32)

        result = None
        for _ in range(6): 
            result = await asyncio.to_thread(fetch_result, session, issue)
            if result is not None: break
            await asyncio.sleep(3)

        try: new_bal = await asyncio.to_thread(fetch_game_balance, session, token)
        except: new_bal = curr_bal

        state["balance"] = new_bal
        total_trades += 1

        won = (result.lower() == predicted.lower()) if result else False

        if won:
            wins += 1
            step_used = current_step + 1
            current_step = 0
            next_step = 1
        else:
            losses += 1
            step_used = current_step + 1
            current_step += 1
            next_step = current_step + 1

        pl = amount * 0.96 if won else -amount
        await bot.send_message(chat_id=uid, text=build_result_msg(issue, predicted, step_used, amount, won, pl, new_bal, wins, losses, next_step), parse_mode="HTML")

        if not won and current_step >= len(steps):
            await bot.send_message(chat_id=uid, text=STEP_EXHAUSTED_MSG, parse_mode="HTML")
            state["trade_running"] = False
            break

        await asyncio.sleep(2)

    state["trade_running"] = False
    state["trade_task"] = None

# ───────────────────────────────────────
# ৬. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────
async def cmd_getid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(f"<b>🔐 আপনার Telegram ID: `{uid}`</b>\n\n<b>এই আইডিটি কপি করে কোডের `AUTHORIZED_USERS = []` এর ভেতরে বসান।</b>", parse_mode="HTML")

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        await update.message.reply_text("<b>⛔ 𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗</b>", parse_mode="HTML")
        return

    state = get_state(uid)
    state["first_bet"] = True
    state["prediction_shown"] = False
    state["pattern_index"] = 0
    state["last_predicted_issue"] = None

    welcome_text = (
        "<b>🧠 𝗕𝗗=𝗪𝗜𝗡~𝗚𝗢=𝗔𝗨𝗧𝗢~𝗕𝗘𝗧 💥</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🧠 𝗠𝗼𝗱𝗲    : 𝗔𝘂𝘁𝗼 𝗔𝗻𝗮𝗹𝘆𝘀𝗲 & 𝗯𝗲𝘁</b>\n"
        f"<b>👥 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀: {len(state['accounts'])}/6</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>👇 𝗣𝗿𝗲𝘀𝘀 𝘁𝗵𝗲 𝗯𝘂𝘁𝘁𝗼𝗻 𝗯𝗲𝗹𝗼𝘄 𝘁𝗼 𝗟𝗢𝗚𝗜𝗡</b>"
    )
    keyboard = [[InlineKeyboardButton("🔐 𝗟𝗢𝗚𝗜𝗡 𝗧𝗢 𝗔𝗖𝗖𝗢𝗨𝗡𝗧", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid): return

    state = get_state(uid)
    text = update.message.text.strip()

    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"<b>☎️ 𝗡𝘂𝗺𝗯𝗲𝗿 : {bnum(text)}</b>\n\n<b>🔑 𝗡𝗼𝘄 𝗲𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗽𝗮𝘀𝘀𝘄𝗼𝗿𝗱:</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None
        try: await update.message.delete()
        except: pass

        status_msg = await ctx.bot.send_message(chat_id=uid, text="<b>🔄 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗡𝗚...\n[░░░░░░░░░░] 0%</b>", parse_mode="HTML")
        success, msg, real_token, expiry, real_uid = await asyncio.to_thread(refresh_token, state["session"], state["temp_phone"], state["temp_password"])
        if success:
            state["lottery_token"] = real_token
            state["token_expiry_time"] = expiry
            state["real_uid"] = real_uid
            if state["temp_phone"] not in state["accounts"]: state["accounts"].append(state["temp_phone"])
            balance = await asyncio.to_thread(fetch_game_balance, state["session"], real_token)
            state["balance"] = balance
            await status_msg.delete()
            
            dashboard_msg = f"<b>🎉 𝗟𝗢𝗚𝗜𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟 ✅</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>☎️ 𝗣𝗵𝗼𝗻𝗲 : ****{bnum(state['temp_phone'][-4:])}</b>\n<b>👤 𝗨𝗜𝗗 : {bnum(fmt_uid(real_uid))}</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>👇 𝗣𝗿𝗲𝘀𝘀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻</b>"
            reply_keyboard = [[KeyboardButton("🚀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧")], [KeyboardButton("🛑 𝗦𝗧𝗢𝗣 𝗧𝗥𝗔𝗗𝗘"), KeyboardButton("🚪 𝗟𝗢𝗚𝗢𝗨𝗧")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True), parse_mode="HTML")
        else:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"<b>❌ 𝗟𝗢𝗚𝗜𝗡 𝗙𝗔𝗜𝗟𝗘𝗗\n𝗞𝗮𝗿𝗼𝗻: {msg}</b>", parse_mode="HTML")
        return

    if text in ("🚀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧", "🚀 START YOUR TARGET"):
        state["awaiting"] = "target"
        await update.message.reply_text(f"<b>💰 𝗬𝗢𝗨𝗥 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ৳ {bnum(f'{float(state.get(\"balance\", 0.00)):.2f}')}</b>\n\n<b>🎯 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗧𝗔𝗥𝗚𝗘𝗧 𝗽𝗿𝗼𝗳𝗶𝘁 𝗮𝗺𝗼𝘂𝗻𝘁:</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            balance = float(state.get('balance', 0.00))
            state["awaiting"] = "steps"
            await update.message.reply_text(f"<b>🎯 𝗧𝗔𝗥𝗚𝗘𝗧 𝗦𝗘𝗧 🎯</b>\n<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁 : ৳ {bnum(f'{target_amount:.2f}')}</b>\n<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁 : ৳ {bnum(f'{balance+target_amount:.2f}')}</b>\n\n<b>🚀 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗦𝗧𝗘𝗣 𝗖𝗢𝗨𝗡𝗧:</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗩𝗵𝘂𝗹 𝗳𝗼𝗿𝗺𝗮𝘁! শুধু সংখ্যা লিখুন।</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError("Steps 1-50")
            state["steps"] = steps
            state["step_amounts"] = []
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(build_step_amounts_msg(steps), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗩𝗵𝘂𝗹 𝗳𝗼𝗿𝗺𝗮𝘁! ১-৫০ এর মধ্যে দিন।</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            if amount <= 0: raise ValueError("Amount > 0")
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(build_single_step_prompt(state["current_step"]), parse_mode="HTML")
            else:
                state["awaiting"] = None
                current_issue, _ = await asyncio.to_thread(get_panel_data, state["session"], state["lottery_token"])
                combined_msg = build_config_msg(float(state.get('balance', 0)), float(state.get('target', 0)), float(state.get('balance', 0)) + float(state.get('target', 0)), state["steps"], state["step_amounts"], current_issue)
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 𝗦𝗧𝗔𝗥𝗧 𝗧𝗥𝗔𝗗𝗘", callback_data="start_trade_btn"), InlineKeyboardButton("❌ 𝗖𝗔𝗡𝗖𝗘𝗟", callback_data="cancel_trade_btn")]])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb, parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗩𝗵𝘂𝗹 𝗳𝗼𝗿𝗺𝗮𝘁! শুধু সংখ্যা লিখুন।</b>", parse_mode="HTML")
        return

    if text in ("🛑 𝗦𝗧𝗢𝗣 𝗧𝗥𝗔𝗗𝗘", "🛑 STOP TRADE"):
        state["trade_running"] = False
        await update.message.reply_text("<b>🛑 𝗧𝗥𝗔𝗗𝗘 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>", parse_mode="HTML")
        return

    if text in ("🚪 𝗟𝗢𝗚𝗢𝗨𝗧", "🚪 LOGOUT"):
        state["trade_running"] = False
        state["temp_phone"] = ""
        state["temp_password"] = ""
        state["session"] = requests.Session()
        await update.message.reply_text("<b>🚪 𝗟𝗢𝗚𝗚𝗘𝗗 𝗢𝗨𝗧</b>", parse_mode="HTML")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not is_authorized(uid): return

    state = get_state(uid)
    data = query.data

    if data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="<b>🔐 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗟𝗢𝗚𝗜𝗡 🔐</b>\n<b>📱 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗗𝗞 𝗪𝗜𝗡 𝗽𝗵𝗼𝗻𝗲 𝗻𝘂𝗺𝗯𝗲𝗿:</b>", parse_mode="HTML")
    elif data == "start_trade_btn":
        prev_task = state.get("trade_task")
        if state.get("trade_running") or (prev_task and not prev_task.done()):
            await ctx.bot.send_message(chat_id=uid, text="<b>⚠️ 𝗧𝗥𝗔𝗗𝗘 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗥𝗨𝗡𝗡𝗜𝗡𝗚!</b>", parse_mode="HTML")
            return
        state["trade_running"] = True
        state["last_betted_issue"] = None
        state["wins"], state["losses"], state["total_trades"] = 0, 0, 0
        state["prediction_shown"] = False
        state["pattern_index"] = 0
        state["last_predicted_issue"] = None
        state["trade_task"] = asyncio.create_task(trade_worker(ctx.bot, uid))
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await ctx.bot.send_message(chat_id=uid, text="<b>❌ 𝗧𝗥𝗔𝗗𝗘 𝗖𝗔𝗡𝗖𝗘𝗟𝗟𝗘𝗗</b>", parse_mode="HTML")

# ───────────────────────────────────────
# ৭. Render Keep-Alive
# ───────────────────────────────────────
app = Flask('')
@app.route('/')
def home(): return "Bot is running perfectly!"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ───────────────────────────────────────
# ৮. Main
# ───────────────────────────────────────
def main():
    if not BOT_TOKEN or ":" not in BOT_TOKEN: return
    keep_alive() # Render এ সচল রাখার জন্য
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("getid", cmd_getid))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started successfully...")
    
    # 🟢 409 Conflict ফিক্স
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()