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

# Render Web Service-এর জন্য Flask (Keep-Alive)
from flask import Flask
from threading import Thread

# ═══════════════════════════════════════════
# ১. কনফিগারেশন এবং কঠোর সিকিউরিটি
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing! Please set it in Render.")

AUTHORIZED_USERS = [7083673844] # আপনার টেলিগ্রাম আইডি

def is_authorized(uid: int) -> bool:
    if not AUTHORIZED_USERS:
        return True
    return uid in AUTHORIZED_USERS

LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"
PANEL_URL = "https://api.ar-lottery01.com/api/Energy/GetPanel"
BET_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
HISTORY_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
WIN_LOSS_URL = "https://api.ar-lottery01.com/api/Lottery/GetWinLossResult"
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

STEP_EXHAUSTED_MSG = (
    "<b>╔════════════════════════════╗</b>\n"
    "<b>║    ✨ 🔔 নতুন আপডেট! 🔔 ✨     ║</b>\n"
    "<b>╠════════════════════════════╣</b>\n"
    "<b>║  💫 আপনার ধাপ অনুযায়ী সব কাজ সফলভাবে শেষ হয়েছে। ✅</b>\n"
    "<b>║  🎊 স্বপ্ন পূরণের পথে এগিয়ে চলুন, সাফল্যের নতুন দিগন্ত ছুঁয়ে চলুন। 🌸</b>\n"
    "<b>║  ✨ আজকের পরিশ্রম, আগামী দিনের জয়, সাহস নিয়ে এগিয়ে যান, সাফল্য হবেই নিশ্চয়! 💖</b>\n"
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
            "last3": [], "reverseMode": False, "reverseCount": 0, "reverseTarget": 1,
            "streakCount": 0, "streakType": None, "streakReversePending": False, "displayedResult": "--",
            "auto_trade_shown": False,
            "fail_retry_shown": False,
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

def generate_balance_sig(random_val, timestamp_val):
    payload = {"language": "en", "random": int(random_val)}
    sorted_dict = {k: payload[k] for k in sorted(payload.keys())}
    json_string = json.dumps(sorted_dict, separators=(',', ':'))
    return hashlib.md5(json_string.encode('utf-8')).hexdigest().upper()

def generate_bet_sig(gameCode, issueNumber, amount, betMultiple, betContent, language, rnd):
    payload_to_sign = {
        "gameCode": gameCode, "issueNumber": str(issueNumber), "amount": int(amount),
        "betMultiple": int(betMultiple), "betContent": betContent, "language": language, "random": int(rnd)
    }
    sorted_dict = {k: payload_to_sign[k] for k in sorted(payload_to_sign.keys())}
    json_string = json.dumps(sorted_dict, separators=(',', ':'))
    return hashlib.md5(json_string.encode('utf-8')).hexdigest().upper()

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

def get_remaining_seconds(issue_number=None):
    return max(0, 30 - int(time.time()) % 30)

def build_timer_bar(seconds):
    filled = min(10, max(0, int(10 * seconds / 30)))
    bar = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {bnum(seconds)}𝘀"

# ───────────────────────────────────────
# ৩. প্রেডিকশন লজিক
# ───────────────────────────────────────
def update_prediction_logic(state, current_result_size):
    current_result_size = current_result_size.upper()
    if current_result_size == state["streakType"]:
        state["streakCount"] += 1
    else:
        state["streakType"] = current_result_size
        state["streakCount"] = 1

    if not state["reverseMode"]:
        state["last3"].append(current_result_size)
        if len(state["last3"]) > 3:
            state["last3"].pop(0)

    if state["streakReversePending"]:
        state["streakReversePending"] = False
        pattern_detected = False
        if len(state["last3"]) == 3:
            a, b, c = state["last3"]
            if a != b and b != c and a == c:
                pattern_detected = True
        if pattern_detected:
            state["reverseMode"] = True
            state["reverseCount"] = 1
            state["reverseTarget"] = random.choice([1, 2])
            state["displayedResult"] = "SMALL" if current_result_size == "BIG" else "BIG"
        else:
            state["displayedResult"] = current_result_size
    elif state["streakCount"] >= 6 and not state["reverseMode"]:
        state["streakReversePending"] = True
        state["displayedResult"] = "SMALL" if current_result_size == "BIG" else "BIG"
    elif state["reverseMode"]:
        state["displayedResult"] = "SMALL" if current_result_size == "BIG" else "BIG"
        state["reverseCount"] += 1
        if state["reverseCount"] >= state["reverseTarget"]:
            state["reverseMode"] = False
            state["reverseCount"] = 0
            state["last3"] = []
    else:
        pattern_detected = False
        if len(state["last3"]) == 3:
            a, b, c = state["last3"]
            if a != b and b != c and a == c:
                pattern_detected = True
        if pattern_detected:
            state["reverseMode"] = True
            state["reverseCount"] = 1
            state["reverseTarget"] = random.choice([1, 2])
            state["displayedResult"] = "SMALL" if current_result_size == "BIG" else "BIG"
        else:
            state["displayedResult"] = current_result_size
    return state["displayedResult"]

# ───────────────────────────────────────
# ৪. API কল
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
            return False, data.get("msg"), None, None, None, 0.0
        
        token = data["data"]["token"]
        lottery_url = data["data"].get("lotteryLoginUrl", "")
        lottery_token = parse_qs(urlparse(lottery_url).query).get("Token", [""])[0]
        
        jwt_data = decode_jwt(token)
        real_uid = jwt_data.get("UserId", "Unknown")
        expiry = decode_jwt_expiry(token)
        login_balance = float(data["data"].get("balance", 0.0))

        if expiry == 0:
            expiry = int(time.time()) + 7200
            
        return True, "Success", lottery_token, expiry, real_uid, login_balance
    except Exception as e:
        logger.error(f"Login Exception: {e}")
        return False, str(e), None, None, None, 0.0

def get_panel_data(session, real_token):
    panel_rnd = random.randint(100000000000, 999999999999)
    panel_ts = int(time.time())
    payload = {"gameCode": "WinGo_30S", "language": "en", "random": int(panel_rnd)}
    sorted_dict = {k: payload[k] for k in sorted(payload.keys())}
    panel_sig = hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode('utf-8')).hexdigest().upper()
    
    panel_url = f"{PANEL_URL}?gameCode=WinGo_30S&language=en&random={panel_rnd}&signature={panel_sig}&timestamp={panel_ts}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"Bearer {real_token}",
        "origin": "https://dkwin8.com", "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        res = session.get(panel_url, headers=headers, timeout=5)
        data = res.json()
        if data.get("code") == 0:
            return data["data"]["currentIssueNumber"], data["data"]["phase"]
    except:
        pass
        
    try:
        res = session.get(HISTORY_URL, timeout=5)
        data = res.json()
        if data.get("code") == 0:
            latest_period = int(data['data']['list'][0]['issueNumber'])
            next_issue = str(latest_period + 1)
            return next_issue, "Betting"
    except:
        pass
        
    return None, None

# ⬇️⬇️⬇️ এখানে আপনার ওয়ার্কিং স্ক্রিপ্টের হুবহু হেডার ব্যবহার করা হয়েছে ⬇️⬇️⬇️
def fetch_game_balance(session, real_token):
    bal_rnd = random.randint(100000000000, 999999999999)
    bal_ts = int(time.time())
    bal_sig = generate_balance_sig(bal_rnd, bal_ts)
    bal_url = f"https://api.ar-lottery01.com/api/Lottery/GetBalance?language=en&random={bal_rnd}&signature={bal_sig}&timestamp={bal_ts}"
    
    bal_headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {real_token}",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    }
    try:
        bal_res = session.get(bal_url, headers=bal_headers, timeout=15)
        bal_data = bal_res.json()
        if bal_data.get("code") == 0:
            return float(bal_data['data']['balance'])
        else:
            logger.error(f"Balance Fetch API Error: {bal_data}")
            return None 
    except Exception as e:
        logger.error(f"Balance Fetch Exception: {e}")
    return None

def place_bet(session, real_token, issue_number, amount, choice):
    try:
        bet_content = f"BigSmall_{choice}"
        c_ts = int(time.time())
        c_rnd = random.randint(100000000000, 999999999999)
        
        sig = generate_bet_sig("WinGo_30S", issue_number, amount, 1, bet_content, "en", c_rnd)
        
        bet_payload = {
            "gameCode": "WinGo_30S", "issueNumber": str(issue_number), "amount": int(amount),
            "betMultiple": 1, "betContent": bet_content, "language": "en",
            "random": c_rnd, "signature": sig, "timestamp": c_ts
        }
        bet_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {real_token}",
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
        bet_res = session.post(BET_URL, json=bet_payload, headers=bet_headers, timeout=15)
        return bet_res.status_code, bet_res.text
    except Exception as e:
        return 500, str(e)

def fetch_win_loss(session, real_token, issue_number):
    try:
        rnd = random.randint(100000000000, 999999999999)
        ts = int(time.time())
        
        payload_to_sign = {"issueNumber": str(issue_number), "language": "en", "random": int(rnd)}
        sorted_dict = {k: payload_to_sign[k] for k in sorted(payload_to_sign.keys())}
        sig = hashlib.md5(json.dumps(sorted_dict, separators=(',', ':')).encode('utf-8')).hexdigest().upper()

        url = (
            f"{WIN_LOSS_URL}?issueNumber={issue_number}"
            f"&language=en&random={rnd}&signature={sig}&timestamp={ts}"
        )
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {real_token}",
            "origin": "https://dkwin8.com", "referer": "https://dkwin8.com/",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }
        res = session.get(url, headers=headers, timeout=15)
        data = res.json()
        if data.get("code") == 0:
            d = data.get("data") or {}
            if "status" not in d:
                return None, 0.0
            status = bool(d.get("status"))
            win_amt = float(d.get("winAmount") or 0)
            return status, win_amt
    except Exception as e:
        logger.error(f"fetch_win_loss error: {e}")
    return None, 0.0

def fetch_result(session, issue_number):
    try:
        res = session.get(HISTORY_URL, timeout=10)
        data = res.json()
        for item in data.get('data', {}).get('list', []):
            if str(item.get('issueNumber')) == str(issue_number):
                premium = str(item.get('premium', '')).upper()
                if premium in ('B', 'BIG'):
                    return "Big"
                elif premium in ('S', 'SMALL'):
                    return "Small"
                if 'sum' in item:
                    total = int(item['sum'])
                    return "Big" if total >= 23 else "Small"
                nums = item.get('number', '')
                if nums:
                    total = sum(int(x) for x in str(nums).split(','))
                    return "Big" if total >= 23 else "Small"
    except Exception as e:
        logger.error(f"fetch_result error: {e}")
    return None

# ───────────────────────────────────────
# ৫. মেসেজ বিল্ডার
# ───────────────────────────────────────
def build_step_amounts_msg(steps):
    return (
        "<b>╔════════════════════════╗</b>\n"
        "<b>║   💵 𝗦𝗧𝗘𝗣 𝗔𝗠𝗢𝗨𝗡𝗧𝗦 💵   ║</b>\n"
        "<b>╚════════════════════════╝</b>\n"
        "\n"
        f"<b>𝗬𝗼𝘂 𝗰𝗵𝗼𝘀𝗲 {bnum(steps)} 𝘀𝘁𝗲𝗽𝘀.</b>\n"
        "\n"
        "<b>💵 𝗦𝘁𝗲𝗽 𝟭 — 𝗯𝗲𝘁 𝗮𝗺𝗼𝘂𝗻𝘁? (𝗶𝗻 ৳)</b>"
    )

def build_single_step_prompt(step_num):
    return f"<b>💵 𝗦𝘁𝗲𝗽 {bnum(step_num)} — 𝗯𝗲𝘁 𝗮𝗺𝗼𝘂𝗻𝘁? (𝗶𝗻 ৳)</b>"

def build_step_plan_bars(step_amounts):
    lines = []
    for i, amt in enumerate(step_amounts):
        bars = "▰" * min(i + 1, 10)
        lines.append(f"<b>𝗦𝘁𝗲𝗽 {bnum(f'{i+1:02d}')} {bars} ৳ {bnum(f'{amt:.2f}')}</b>")
    return "\n".join(lines)

def build_step_plan_tree(step_amounts):
    lines = []
    n = len(step_amounts)
    for i, amt in enumerate(step_amounts):
        prefix = "└─" if i == n - 1 else "├─"
        lines.append(f"<b>{prefix} 𝗦𝘁𝗲𝗽 {bnum(f'{i+1:02d}')} ➤ ৳ {bnum(f'{amt:.2f}')}</b>")
    return "\n".join(lines)

def build_config_msg(balance, target, stop_at, steps, step_amounts, current_issue):
    remaining = get_remaining_seconds(current_issue)
    timer_bar = build_timer_bar(remaining)
    total_risk = sum(step_amounts)
    return (
        "<b>╔════════════════════════╗</b>\n"
        "<b>║  ⚙️ 𝗧𝗥𝗔𝗗𝗘 𝗖𝗢𝗡𝗙𝗜𝗚𝗨𝗥𝗔𝗧𝗜𝗢𝗡 ⚙️   ║</b>\n"
        "<b>╚════════════════════════╝</b>\n"
        f"<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲  : ৳ {bnum(f'{balance:.2f}')}</b>\n"
        f"<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁   : ৳ {bnum(f'{target:.2f}')} 𝗽𝗿𝗼𝗳𝗶𝘁</b>\n"
        f"<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁  : ৳ {bnum(f'{stop_at:.2f}')}</b>\n"
        f"<b>📋 𝗦𝘁𝗲𝗽𝘀    : {bnum(steps)}</b>\n"
        f"<b>⚠️ 𝗧𝗼𝘁𝗮𝗹 𝗥𝗶𝘀𝗸 : ৳ {bnum(f'{total_risk:.2f}')}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>📊 𝗦𝗧𝗘𝗣 𝗣𝗟𝗔𝗡</b>\n"
        f"{build_step_plan_bars(step_amounts)}\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>⏱️ 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗣𝗲𝗿𝗶𝗼𝗱 {bnum(current_issue) if current_issue else '----'} </b>\n"
        f"<b>{timer_bar}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🧠 𝗘𝗻𝗴𝗶𝗻𝗲: 𝟵 𝗹𝗮𝘆𝗲𝗿𝘀 + 𝗹𝗶𝘃𝗲 𝗯𝗮𝗰𝗸𝘁𝗲𝘀𝘁</b>\n"
        "<b>🔴 𝗖𝗼𝗻𝗳𝗶𝗱𝗲𝗻𝗰𝗲 𝗴𝗮𝘁𝗲: 𝗯𝗲𝗹𝗼𝘄 𝟯𝟬% → 𝘀𝗶𝘁 𝗼𝘂𝘁</b>\n"
        "<b>🎬 𝗣𝗿𝗲𝗱𝗶𝗰𝘁𝗶𝗼𝗻 𝗮𝗻𝗶𝗺𝗮𝘁𝗶𝗼𝗻: 𝟰𝘀</b>\n"
        "\n"
        "<b>👇 𝗣𝗿𝗲𝘀𝘀 𝗦𝗧𝗔𝗥𝗧 𝗧𝗥𝗔𝗗𝗘 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻.</b>"
    )

def build_auto_trade_msg(balance, target, stop_at, steps, step_amounts, current_issue):
    remaining = get_remaining_seconds(current_issue)
    timer_bar = build_timer_bar(remaining)
    return (
        "<b>╔════════════════════════╗</b>\n"
        "<b>║   🚀 𝗔𝗨𝗧𝗢 𝗧𝗥𝗔𝗗𝗘 𝗔𝗖𝗧𝗜𝗩𝗘 🚀  ║</b>\n"
        "<b>╚════════════════════════╝</b>\n"
        "<b>==============================</b>\n"
        f"<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n"
        f"<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁 : ৳ {bnum(f'{target:.2f}')} 𝗽𝗿𝗼𝗳𝗶𝘁</b>\n"
        f"<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁 : ৳ {bnum(f'{stop_at:.2f}')}</b>\n"
        f"<b>📋 𝗦𝘁𝗲𝗽𝘀 : {bnum(steps)}</b>\n"
        "<b>----------------------------------------</b>\n"
        "<b>📊 𝗦𝘁𝗲𝗽 𝗣𝗹𝗮𝗻:</b>\n"
        "\n"
        f"{build_step_plan_tree(step_amounts)}\n"
        "<b>----------------------------------------</b>\n"
        f"<b>⏱️ 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗣𝗲𝗿𝗶𝗼𝗱 {bnum(current_issue) if current_issue else '----'}</b>\n"
        f"<b>{timer_bar}</b>\n"
        "<b>----------------------------------------</b>\n"
        "<b>🧠 𝗔𝗻𝗮𝗹𝘆𝘀𝗶𝗻𝗴 𝗺𝗮𝗿𝗸𝗲𝘁...</b>\n"
        "<b>🎬 𝟰-𝘀𝗲𝗰𝗼𝗻𝗱 𝗽𝗿𝗲𝗱𝗶𝗰𝘁𝗶𝗼𝗻 𝗮𝗻𝗶𝗺𝗮𝘁𝗶𝗼𝗻 → 𝗮𝘂𝘁𝗼 𝗯𝗲𝘁 𝗲𝘃𝗲𝗿𝘆 𝗽𝗲𝗿𝗶𝗼𝗱.</b>"
    )

def build_prediction_animation(percent=75):
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🧠 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗜𝗡𝗚 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "\n"
        "<b>∴ 𝗩𝗲𝗿𝗶𝗳𝘆𝗶𝗻𝗴 𝘄𝗮𝗹𝗹𝗲𝘁 & 𝗽𝗲𝗿𝗶𝗼𝗱...</b>\n"
        "\n"
        f"<b>[{bar}] {bnum(percent)}%</b>\n"
        "\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>⏳ 𝗥𝘂𝗻𝗻𝗶𝗻𝗴 𝟵 𝗹𝗮𝘆𝗲𝗿𝘀 + 𝗯𝗮𝗰𝗸𝘁𝗲𝘀𝘁...</b>"
    )

def build_new_trade_msg(period, choice, step_num, amount, balance):
    remaining = get_remaining_seconds(period)
    side_icon = "🔵" if str(choice).upper() == "BIG" else "🔴"
    return (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🤖 𝗡𝗘𝗪 𝗧𝗥𝗔𝗗𝗘 𝗣𝗟𝗔𝗖𝗘𝗗</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>⏱️ 𝗣𝗲𝗿𝗶𝗼𝗱    : {bnum(period)}</b>\n"
        f"<b>⏱️ 𝗧𝗶𝗺𝗲𝗿     : {bnum(remaining)}s 𝗿𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴</b>\n"
        "<b>📊 𝗠𝗮𝗿𝗸𝗲𝘁       : 𝗠𝗜𝗫𝗘𝗗 📊</b>\n"
        "<b>🔬 𝗦𝘁𝗮𝗯𝗶𝗹𝗶𝘁𝘆    : 🔴 𝗩𝗢𝗟𝗔𝗧𝗜𝗟𝗘 (0/100)</b>\n"
        "<b>🧨 𝗛𝗼𝘀𝘁𝗶𝗹𝗶𝘁𝘆    : 🟡 𝗨𝗡𝗦𝗧𝗔𝗕𝗟𝗘 (60/100)</b>\n"
        "<b>💡 𝗚𝘂𝘁 𝗦𝗰𝗼𝗿𝗲    : 25/100</b>\n"
        "<b>🧠 𝗠𝗶𝗻𝗱 𝗦𝘁𝗮𝘁𝗲   : 😌 𝗖𝗮𝗹𝗺 & 𝗳𝗼𝗰𝘂𝘀𝗲𝗱</b>\n"
        "<b>╔══════════════════════════════════╗</b>\n"
        "<b>║ 🧠 𝗔𝗡𝗔𝗟𝗬𝗦𝗜𝗦 𝗥𝗘𝗣𝗢𝗥𝗧             ║</b>\n"
        "<b>╚══════════════════════════════════╝</b>\n"
        "<b>⚠️ 𝗢𝗻𝗹𝘆 10 𝗱𝗿𝗮𝘄𝘀 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 (𝗻𝗲𝗲𝗱 40) — 𝗽𝗿𝗲𝗹𝗶𝗺𝗶𝗻𝗮𝗿𝘆 𝘀𝗶𝗴𝗻𝗮𝗹</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>📊 𝗖𝗼𝗻𝗳𝗶𝗱𝗲𝗻𝗰𝗲 : ████░░░░░░ 45%</b>\n"
        "<b>🎯 𝗖𝗼𝗻𝘀𝗲𝗻𝘀𝘂𝘀  :</b>\n"
        "<b>✅ 𝗚𝗮𝘁𝗲       : 🔴 𝗩𝗢𝗟𝗔𝗧𝗜𝗟𝗘 (25/100)</b>\n"
        "<b>✓ 𝗵𝗼𝘀𝘁𝗶𝗹𝗶𝘁𝘆 60/100 ✓ 𝗴𝘂𝘁 25/100</b>\n"
        "<b>⚡ 𝗔𝗻𝗮𝗹𝘆𝘇𝗲𝗱 𝗶𝗻: 217ms</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>{side_icon} 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡 : {str(choice).upper()} ❮❮❮</b>\n"
        "\n"
        f"<b>🚀 𝗦𝘁𝗲𝗽       : 🟢 𝗡𝗼𝗿𝗺𝗮𝗹 — 𝗦𝘁𝗲𝗽 {bnum(step_num)}</b>\n"
        f"<b>💵 𝗔𝗺𝗼𝘂𝗻𝘁     : ৳ {bnum(f'{amount:.2f}')}</b>\n"
        f"<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲    : ৳ {bnum(f'{balance:.2f}')}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>⏳ 𝗪𝗮𝗶𝘁𝗶𝗻𝗴 𝗳𝗼𝗿 𝗿𝗲𝘀𝘂𝗹𝘁...</b>"
    )

def build_result_msg(period, choice, step_num, amount, won, pl, balance, wins, losses, next_step):
    total = wins + losses
    rate = (wins / total * 100) if total > 0 else 0
    result_icon = "𝗪𝗜𝗡 ✅" if won else "𝗟𝗢𝗦𝗦 ❌"
    color = "🟢" if won else "🔴"
    side_icon = "🔵" if str(choice).upper() == "BIG" else "🔴"
    if pl >= 0:
        pl_str = f"+৳ {bnum(f'{pl:.2f}')}"
    else:
        pl_str = f"-৳ {bnum(f'{abs(pl):.2f}')}"
    next_msg = "🟢 𝗥𝗲𝗰𝗼𝘃𝗲𝗿𝗲𝗱! 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗦𝘁𝗲𝗽 1." if won else f"🔴 𝗟𝗼𝘀𝘀! 𝗠𝗼𝘃𝗶𝗻𝗴 𝘁𝗼 𝗦𝘁𝗲𝗽 {bnum(next_step)}."
    return (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>—</b>\n"
        f"<b>{color} 𝗧𝗥𝗔𝗗𝗘 𝗥𝗘𝗦𝗨𝗟𝗧</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>—</b>\n"
        f"<b>⏰ 𝗣𝗲𝗿𝗶𝗼𝗱 : {bnum(period)}</b>\n"
        f"<b>{side_icon} 𝗦𝗶𝗱𝗲 : {str(choice).upper()} ❮❮❮</b>\n"
        f"<b>🚀 𝗦𝘁𝗲𝗽 : {bnum(step_num)}</b>\n"
        f"<b>💵 𝗔𝗺𝗼𝘂𝗻𝘁 : ৳ {bnum(f'{amount:.2f}')}</b>\n"
        "\n"
        f"<b>📊 𝗥𝗲𝘀𝘂𝗹𝘁 : {result_icon}</b>\n"
        f"<b>💹 𝗣/𝗟 : {pl_str}</b>\n"
        f"<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{balance:.2f}')}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>—</b>\n"
        f"<b>🏆 𝗪𝗶𝗻𝘀 : {bnum(wins)} 🔴 𝗟𝗼𝘀𝘀𝗲𝘀 : {bnum(losses)} 📈 𝗥𝗮𝘁𝗲 :</b>\n"
        f"<b>{bnum(f'{rate:.1f}')}%</b>\n"
        "<b>🧠 𝗠𝗶𝗻𝗱 𝗦𝘁𝗮𝘁𝗲 : 😌 𝗖𝗮𝗹𝗺 & 𝗳𝗼𝗰𝘂𝘀𝗲𝗱</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>—</b>\n"
        f"<b>➡️ 𝗡𝗲𝘅𝘁 𝗦𝘁𝗲𝗽 : {bnum(next_step)}</b>\n"
        f"<b>{next_msg}</b>"
    )

def build_target_reached_msg(start_balance, final_balance, profit, trades, wins, losses):
    rate = (wins / trades * 100) if trades > 0 else 0
    return (
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🎯 𝗧𝗔𝗥𝗚𝗘𝗧 𝗥𝗘𝗔𝗖𝗛𝗘𝗗 🎉</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>╔══════════════════════════╗</b>\n"
        "<b>║ 💎 𝗦𝗘𝗦𝗦𝗜𝗢𝗡 𝗦𝗨𝗠𝗠𝗔𝗥𝗬 ║</b>\n"
        "<b>╚══════════════════════════╝</b>\n"
        f"<b>💰 𝗦𝘁𝗮𝗿𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{start_balance:.2f}')}</b>\n"
        "\n"
        f"<b>💳 𝗙𝗶𝗻𝗮𝗹 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{final_balance:.2f}')}</b>\n"
        "\n"
        f"<b>💹 𝗣𝗿𝗼𝗳𝗶𝘁 𝗠𝗮𝗱𝗲 : +৳ {bnum(f'{profit:.2f}')}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📊 𝗧𝗿𝗮𝗱𝗲𝘀 : {bnum(trades)}</b>\n"
        "\n"
        f"<b>🟢 𝗪𝗶𝗻 : {bnum(wins)}</b>\n"
        "\n"
        f"<b>🔴 𝗟𝗼𝘀𝘀 : {bnum(losses)}</b>\n"
        "\n"
        f"<b>🏆 𝗪𝗶𝗻 𝗥𝗮𝘁𝗲 : {bnum(f'{rate:.1f}')}%</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>✅ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗮𝘂𝘁𝗼-𝗹𝗼𝗴𝗴𝗲𝗱 𝗼𝘂𝘁.</b>\n"
        "\n"
        "<b>👇 𝗧𝘆𝗽𝗲 /𝘀𝘁𝗮𝗿𝘁 𝗮𝗻𝗱 𝗽𝗿𝗲𝘀𝘀 𝗟𝗢𝗚𝗜𝗡 𝗧𝗢 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻 𝗮𝗴𝗮𝗶𝗻.</b>"
    )

# ───────────────────────────────────────
# ৬. ট্রেড ওয়ার্কার
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
        try:
            curr_bal = await asyncio.to_thread(fetch_game_balance, session, token)
            if curr_bal is None:
                curr_bal = state["balance"] 
        except:
            curr_bal = state["balance"]

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
            success, msg, new_token, expiry, _, _ = await asyncio.to_thread(refresh_token, session, state["temp_phone"], state["temp_password"])
            if success:
                token = new_token
                state["lottery_token"] = new_token
                state["token_expiry_time"] = expiry
            else:
                await asyncio.sleep(2)
                continue

        issue, phase = await asyncio.to_thread(get_panel_data, session, token)
        
        if not state.get("auto_trade_shown"):
            state["auto_trade_shown"] = True
            display_issue = issue if issue else "----"
            await bot.send_message(chat_id=uid, text=build_auto_trade_msg(curr_bal, target, stop_at, len(steps), steps, display_issue), parse_mode="HTML")

        if not issue or phase != "Betting" or issue == state.get("last_betted_issue"):
            await asyncio.sleep(1)
            continue

        remaining = get_remaining_seconds(issue)
        if remaining < 7:
            await asyncio.sleep(1)
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
            except Exception as e:
                logger.error(f"prediction animation error: {e}")

        remaining = get_remaining_seconds(issue)
        if remaining < 2:
            state["last_betted_issue"] = issue
            continue

        predicted = state.get("displayedResult", "--")
        if predicted == "--" or str(predicted).upper() not in ("BIG", "SMALL"):
            predicted = random.choice(["Big", "Small"])
        else:
            predicted = str(predicted).capitalize()
        state["displayedResult"] = predicted

        status_code, res_text = await asyncio.to_thread(place_bet, session, token, issue, amount, predicted)
        
        if status_code == 401:
            logger.warning("401 Unauthorized detected during bet. Refreshing token...")
            success, msg, new_token, expiry, _, _ = await asyncio.to_thread(refresh_token, session, state["temp_phone"], state["temp_password"])
            if success:
                token = new_token
                state["lottery_token"] = new_token
                state["token_expiry_time