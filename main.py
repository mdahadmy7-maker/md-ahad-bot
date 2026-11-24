import asyncio
import logging
import os
import time
import uuid
import hashlib
import json
import base64
import random
import httpx
from urllib.parse import urlparse, parse_qs
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.request import HTTPXRequest
from flask import Flask
from threading import Thread

# ═══════════════════════════════════════════
# ১. কনফিগারেশন এবং কঠোর সিকিউরিটি
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing! Please set it in Render.")

AUTHORIZED_USERS = [7083673844]

def is_authorized(uid: int) -> bool:
    if not AUTHORIZED_USERS:
        return True
    return uid in AUTHORIZED_USERS

LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"
PANEL_URL = "https://api.ar-lottery01.com/api/Energy/GetPanel"
BET_URL = "https://api.ar-lottery01.com/api/Lottery/WinGoBet"
BALANCE_URL = "https://api.ar-lottery01.com/api/Lottery/GetBalance"
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

def get_resilient_session():
    session = requests.Session()
    retry = Retry(connect=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

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
            "session": get_resilient_session()
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
            return False, data.get("msg"), None, None, None
        lottery_url = data["data"].get("lotteryLoginUrl", "")
        sso_ticket = parse_qs(urlparse(lottery_url).query).get("Token", [""])[0]
        panel_rnd = random.randint(100000000000, 999999999999)
        panel_ts = int(time.time())
        panel_sig = generate_dynamic_sig({"gameCode": "WinGo_30S", "language": "en", "random": panel_rnd})
        panel_url = f"{PANEL_URL}?gameCode=WinGo_30S&language=en&random={panel_rnd}&signature={panel_sig}&timestamp={panel_ts}"
        panel_headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {sso_ticket}",
            "origin": "https://dkwin8.com", "referer": "https://dkwin8.com/",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }
        panel_res = session.get(panel_url, headers=panel_headers, timeout=10)
        auth_header = panel_res.headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            real_token = auth_header[7:]
            expiry = decode_jwt_expiry(real_token)
            real_uid = decode_jwt(real_token).get("UserId", "Unknown")
            return True, "Success", real_token, expiry, real_uid
        else:
            return False, "No token in header", None, None, None
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
        "origin": "https://dkwin8.com", "referer": "https://dkwin8.com/",
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

def fetch_game_balance(session, real_token, retries=3):
    for attempt in range(1, retries + 1):
        try:
            bal_rnd = random.randint(100000000000, 999999999999)
            bal_ts = int(time.time())
            bal_sig = generate_dynamic_sig({"language": "en", "random": bal_rnd})
            bal_url = f"{BALANCE_URL}?language=en&random={bal_rnd}&signature={bal_sig}&timestamp={bal_ts}"
            bal_headers = {
                "accept": "application/json, text/plain, */*",
                "authorization": f"Bearer {real_token}",
                "origin": "https://dkwin8.com",
                "referer": "https://dkwin8.com/",
                "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
            }
            bal_res = session.get(bal_url, headers=bal_headers, timeout=15)
            try:
                bal_data = bal_res.json()
            except Exception:
                if attempt < retries: time.sleep(1)
                continue

            code_raw = bal_data.get("code")
            if code_raw == 0 or str(code_raw) == "0":
                data = bal_data.get("data")
                if isinstance(data, dict):
                    for key in ("balance", "Balance", "money", "amount", "userBalance", "availableBalance", "totalAmount"):
                        if key in data and data[key] is not None:
                            try:
                                return float(data[key])
                            except (TypeError, ValueError):
                                continue
                elif isinstance(data, (int, float)):
                    return float(data)
                elif isinstance(data, str):
                    try:
                        return float(data)
                    except ValueError:
                        pass
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1)
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
            "origin": "https://dkwin8.com", "referer": "https://dkwin8.com/",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        }
        bet_res = session.post(BET_URL, data=json_string, headers=bet_headers, timeout=15)
        return bet_res.status_code, bet_res.text
    except Exception as e:
        return 500, str(e)

def fetch_win_loss(session, real_token, issue_number):
    try:
        rnd = random.randint(100000000000, 999999999999)
        ts = int(time.time())
        sig = generate_dynamic_sig({
            "issueNumber": str(issue_number),
            "language": "en",
            "random": rnd
        })
        url = f"{WIN_LOSS_URL}?issueNumber={issue_number}&language=en&random={rnd}&signature={sig}&timestamp={ts}"
        headers = {
            "accept": "application/json, text/plain, */*",
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
        "<b>╚════════════════════════╝</b>\n\n"
        f"<b>𝗬𝗼𝘂 𝗰𝗵𝗼𝘀𝗲 {bnum(steps)} 𝘀𝘁𝗲𝗽𝘀.</b>\n\n"
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
        "<b>🎬 𝗣𝗿𝗲𝗱𝗶𝗰𝘁𝗶𝗼𝗻 𝗮𝗻𝗶𝗺𝗮𝘁𝗶𝗼𝗻: 𝟰𝘀</b>\n\n"
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
        "<b>📊 𝗦𝘁𝗲𝗽 𝗣𝗹𝗮𝗻:</b>\n\n"
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
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        "<b>∴ 𝗩𝗲𝗿𝗶𝗳𝘆𝗶𝗻𝗴 𝘄𝗮𝗹𝗹𝗲𝘁 & 𝗽𝗲𝗿𝗶𝗼𝗱...</b>\n\n"
        f"<b>[{bar}] {bnum(percent)}%</b>\n\n"
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
        f"<b>{side_icon} 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡 : {str(choice).upper()} ❮❮❮</b>\n\n"
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
        f"<b>💵 𝗔𝗺𝗼𝘂𝗻𝘁 : ৳ {bnum(f'{amount:.2f}')}</b>\n\n"
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
        f"<b>💰 𝗦𝘁𝗮𝗿𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{start_balance:.2f}')}</b>\n\n"
        f"<b>💳 𝗙𝗶𝗻𝗮𝗹 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ৳ {bnum(f'{final_balance:.2f}')}</b>\n\n"
        f"<b>💹 𝗣𝗿𝗼𝗳𝗶𝘁 𝗠𝗮𝗱𝗲 : +৳ {bnum(f'{profit:.2f}')}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📊 𝗧𝗿𝗮𝗱𝗲𝘀 : {bnum(trades)}</b>\n\n"
        f"<b>🟢 𝗪𝗶𝗻 : {bnum(wins)}</b>\n\n"
        f"<b>🔴 𝗟𝗼𝘀𝘀 : {bnum(losses)}</b>\n\n"
        f"<b>🏆 𝗪𝗶𝗻 𝗥𝗮𝘁𝗲 : {bnum(f'{rate:.1f}')}%</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>✅ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗮𝘂𝘁𝗼-𝗹𝗼𝗴𝗴𝗲𝗱 𝗼𝘂𝘁.</b>\n\n"
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
        except:
            curr_bal = state["balance"]

        if curr_bal >= stop_at:
            profit = curr_bal - start_balance
            await bot.send_message(chat_id=uid, text=build_target_reached_msg(start_balance, curr_bal, profit, total_trades, wins, losses), parse_mode="HTML")
            state["trade_running"] = False
            state["lottery_token"] = None
            state["temp_phone"] = ""
            state["temp_password"] = ""
            state["session"] = get_resilient_session()
            break

        if not token or int(time.time()) >= (state["token_expiry_time"] - 10):
            success, msg, new_token, expiry, _ = await asyncio.to_thread(refresh_token, session, state["temp_phone"], state["temp_password"])
            if success:
                token = new_token
                state["lottery_token"] = new_token
                state["token_expiry_time"] = expiry
            else:
                await asyncio.sleep(2)
                continue

        issue, phase = await asyncio.to_thread(get_panel_data, session, token)
        if not issue or phase != "Betting" or issue == state.get("last_betted_issue"):
            await asyncio.sleep(0.5)
            continue

        remaining = get_remaining_seconds(issue)
        if remaining < 7:
            await asyncio.sleep(0.5)
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
        bet_failed = False
        if status_code != 200:
            bet_failed = True
        else:
            try:
                rj = json.loads(res_text)
                if rj.get("code") != 0:
                    bet_failed = True
            except:
                pass

        if bet_failed:
            if not state.get("fail_retry_shown"):
                state["fail_retry_shown"] = True
                await asyncio.sleep(1)
                continue
            else:
                state["last_betted_issue"] = issue
                await asyncio.sleep(1)
                continue

        state["last_betted_issue"] = issue
        await bot.send_message(chat_id=uid, text=build_new_trade_msg(issue, predicted, current_step + 1, amount, curr_bal), parse_mode="HTML")

        for _ in range(16):
            if not state["trade_running"]:
                break
            await asyncio.sleep(1)
            
        if not state["trade_running"]:
            break

        won = None
        win_amount = 0.0
        for _ in range(15):
            won, win_amount = await asyncio.to_thread(fetch_win_loss, session, token, issue)
            if won is not None:
                break
            if not state["trade_running"]:
                break
            await asyncio.sleep(1)

        if won is None:
            hist_res = await asyncio.to_thread(fetch_result, session, issue)
            if hist_res is not None:
                actual_res_fb = hist_res.capitalize()
                won = (actual_res_fb.lower() == predicted.lower())
            else:
                continue

        try:
            new_bal = await asyncio.to_thread(fetch_game_balance, session, token)
        except:
            new_bal = curr_bal

        state["balance"] = new_bal
        total_trades += 1
        actual_res = predicted if won else ("Small" if predicted.upper() == "BIG" else "Big")
        update_prediction_logic(state, actual_res.upper())

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

        await asyncio.sleep(0.5)

    state["trade_running"] = False
    state["trade_task"] = None

# ───────────────────────────────────────
# ৭. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────
async def cmd_getid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"<b>🔐 আপনার Telegram ID: `{uid}`</b>\n\n"
        f"<b>এই আইডিটি কপি করে কোডের `AUTHORIZED_USERS = []` এর ভেতরে বসান, </b>"
        f"<b>যেমন: `AUTHORIZED_USERS = [{uid}]`</b>\n"
        f"<b>এরপর বট রিস্টার্ট করলে অন্য কেউ আপনার বট ব্যবহার করতে পারবে না।</b>",
        parse_mode="HTML"
    )

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        await update.message.reply_text(
            "<b>⛔ 𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗\n\n𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗯𝗼𝘁.</b>",
            parse_mode="HTML"
        )
        return

    state = get_state(uid)
    state["first_bet"] = True
    state["prediction_shown"] = False
    state["auto_trade_shown"] = False
    state["fail_retry_shown"] = False
    state["last3"] = []
    state["reverseMode"] = False
    state["reverseCount"] = 0
    state["reverseTarget"] = 1
    state["streakCount"] = 0
    state["streakType"] = None
    state["streakReversePending"] = False
    state["displayedResult"] = "--"

    welcome_text = (
        "<b>🧠 𝐁𝐃=𝐖𝐈𝐍~𝐆𝐎=𝐀𝐔𝐓𝐎~𝐁𝐄𝐓 💥</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🧠 𝐌𝐨𝐝𝐞    : 𝐀𝐮𝐭𝐨 𝐀𝐧𝐚𝐥𝐲𝐬𝐞 &amp; 𝐁𝐞𝐭</b>\n"
        "<b>🔐 𝐀𝐜𝐜𝐞𝐬𝐬  : 𝐏𝐫𝐢𝐯𝐚𝐭𝐞 · 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝 𝐌𝐞𝐦𝐛𝐞𝐫𝐬</b>\n"
        "<b>🔴 𝐒𝐭𝐚𝐭𝐮𝐬  : 𝐍𝐨𝐭 𝐋𝐨𝐠𝐠𝐞𝐝 𝐈𝐧</b>\n"
        f"<b>👥 𝐀𝐜𝐜𝐨𝐮𝐧𝐭𝐬: {bnum(len(state['accounts']))}/𝟔</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🧠 𝐏𝐫𝐞𝐝𝐢𝐜𝐭𝐢𝐨𝐧 𝐄𝐧𝐠𝐢𝐧𝐞 — 𝟗 𝐋𝐚𝐲𝐞𝐫𝐬</b>\n"
        "\n"
        "<b>⚡ 𝐒𝐭𝐫𝐞𝐚𝐤 · 🔷 𝐏𝐚𝐭𝐭𝐞𝐫𝐧 · 📈 𝐓𝐫𝐞𝐧𝐝</b>\n"
        "<b>🔍 𝐌𝐚𝐧𝐢𝐩𝐮𝐥𝐚𝐭𝐢𝐨𝐧 · 🎨 𝐂𝐨𝐥𝐨𝐮𝐫 · 🔢 𝐅𝐫𝐞𝐪𝐮𝐞𝐧𝐜𝐲</b>\n"
        "<b>🔄 𝐌𝐚𝐫𝐤𝐨𝐯 · ♻️ 𝐂𝐲𝐜𝐥𝐞 · 💠 𝐌𝐨𝐦𝐞𝐧𝐭𝐮𝐦</b>\n"
        "\n"
        "<b>🔁 𝐄𝐯𝐞𝐫𝐲 𝐥𝐚𝐲𝐞𝐫 𝐢𝐬 𝐛𝐚𝐜𝐤-𝐭𝐞𝐬𝐭𝐞𝐝 𝐥𝐢𝐯𝐞 𝐬𝐨 𝐢𝐭𝐬 𝐯𝐨𝐭𝐞</b>\n"
        "<b>𝐰𝐞𝐢𝐠𝐡𝐭 𝐟𝐨𝐥𝐥𝐨𝐰𝐬 𝐢𝐭𝐬 𝐫𝐞𝐚𝐥 𝐡𝐢𝐭-𝐫𝐚𝐭𝐞</b>\n"
        "\n"
        "<b>🔴 𝐂𝐨𝐧𝐟𝐢𝐝𝐞𝐧𝐜𝐞 𝐛𝐞𝐥𝐨𝐰 𝟑𝟎% → 𝐒𝐢𝐭 𝐎𝐮𝐭</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>🎬 𝟒-𝐬𝐞𝐜𝐨𝐧𝐝 🧠 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐢𝐧𝐠 𝐏𝐫𝐞𝐝𝐢𝐜𝐭𝐢𝐨𝐧 𝐀𝐧𝐢𝐦𝐚𝐭𝐢𝐨𝐧</b>\n"
        "<b>🚀 𝐀𝐧𝐚𝐥𝐲𝐬𝐢𝐬 → 𝐀𝐮𝐭𝐨 𝐁𝐞𝐭 𝐄𝐯𝐞𝐫𝐲 𝟑𝟎𝐬 𝐏𝐞𝐫𝐢𝐨𝐝</b>\n"
        "\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>👇 𝐏𝐫𝐞𝐬𝐬 𝐓𝐡𝐞 𝐁𝐮𝐭𝐭𝐨𝐧 𝐁𝐞𝐥𝐨𝐰 𝐓𝐨 𝐋𝐎𝐆𝐈𝐍</b>"
    )
    keyboard = [[InlineKeyboardButton("🔐 𝗟𝗢𝗚𝗜𝗡 𝗧𝗢 𝗔𝗖𝗖𝗢𝗨𝗡𝗧", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        await update.message.reply_text("<b>⛔ 𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗</b>", parse_mode="HTML")
        return

    state = get_state(uid)
    text = update.message.text.strip()

    if text in ("🛑 𝗦𝗧𝗢𝗣 𝗧𝗥𝗔𝗗𝗘", "🛑 STOP TRADE"):
        state["trade_running"] = False
        await update.message.reply_text("<b>🛑 𝗧𝗿𝗮𝗱𝗲 𝘀𝘁𝗼𝗽𝗽𝗲𝗱.</b>", parse_mode="HTML")
        return

    if text in ("🚪 𝗟𝗢𝗚𝗢𝗨𝗧", "🚪 LOGOUT"):
        state["trade_running"] = False
        state["lottery_token"] = None
        state["temp_phone"] = ""
        state["temp_password"] = ""
        state["accounts"] = []
        state["balance"] = 0.0
        state["session"] = get_resilient_session()
        await update.message.reply_text(
            "<b>🚪 𝗟𝗼𝗴𝗴𝗲𝗱 𝗼𝘂𝘁 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆.</b>\n<b>👇 𝗧𝘆𝗽𝗲 /start 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻 𝗮𝗴𝗮𝗶𝗻.</b>",
            parse_mode="HTML"
        )
        return

    if text in ("🚀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧", "🚀 START YOUR TARGET"):
        if not state.get("lottery_token"):
            await update.message.reply_text("<b>❌ Please login first. Type /start</b>", parse_mode="HTML")
            return
        state["awaiting"] = "target"
        balance_val = float(state.get('balance', 0.00))
        target_msg = (
            "<b>╔════════════════════════╗</b>\n"
            "<b>║   🚀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧 🚀  ║</b>\n"
            "<b>╚════════════════════════╝</b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>💰 𝗬𝗢𝗨𝗥 𝗕𝗔𝗟𝗔𝗡𝗖𝗘</b>\n"
            f"<b>৳ {bnum(f'{balance_val:.2f}')}</b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>🎯 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗧𝗔𝗥𝗚𝗘𝗧 𝗽𝗿𝗼𝗳𝗶𝘁 𝗮𝗺𝗼𝘂𝗻𝘁:</b>\n"
            "<b>𝗛𝗼𝘄 𝗺𝘂𝗰𝗵 𝗱𝗼 𝘆𝗼𝘂 𝘄𝗮𝗻𝘁 𝘁𝗼 𝗲𝗮𝗿𝗻? (𝗶𝗻 ৳)</b>"
        )
        await update.message.reply_text(target_msg, parse_mode="HTML")
        return

    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "<b>╔════════════════════════╗</b>\n"
            "<b>║  🔐 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗟𝗢𝗚𝗜𝗡 🔐  ║</b>\n"
            "<b>╚════════════════════════╝</b>\n"
            f"<b>☎️ 𝗡𝘂𝗺𝗯𝗲𝗿 : {bnum(text)}</b>\n\n"
            "<b>🔑 𝗡𝗼𝘄 𝗲𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗽𝗮𝘀𝘀𝘄𝗼𝗿𝗱:</b>\n"
            "<b>𝗬𝗼𝘂𝗿 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗱𝗲𝗹𝗲𝘁𝗲𝗱 𝗶𝗺𝗺𝗲𝗱𝗶𝗮𝘁𝗲𝗹𝘆 𝗳𝗼𝗿 𝘀𝗲𝗰𝘂𝗿𝗶𝘁𝘆.</b>",
            parse_mode="HTML"
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None
        try: await update.message.delete()
        except: pass

        status_msg = await ctx.bot.send_message(chat_id=uid, text="<b>🔄 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗡𝗚 𝗧𝗢 𝗦𝗜𝗧𝗘...\n[░░░░░░░░░░] 0%</b>", parse_mode="HTML")
        success, msg, real_token, expiry, real_uid = await asyncio.to_thread(refresh_token, state["session"], state["temp_phone"], state["temp_password"])
        if success:
            state["lottery_token"] = real_token
            state["token_expiry_time"] = expiry
            state["real_uid"] = real_uid
            if state["temp_phone"] not in state["accounts"]:
                state["accounts"].append(state["temp_phone"])
            await asyncio.sleep(1)
            balance = await asyncio.to_thread(fetch_game_balance, state["session"], real_token)
            state["balance"] = balance
            await status_msg.delete()
            masked_phone = "****" + bnum(state["temp_phone"][-4:])
            display_uid = fmt_uid(real_uid)
            dashboard_msg = (
                "<b>╔═══════════════════════╗</b>\n"
                "<b>║  🎉 𝗟𝗢𝗚𝗜𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟 ✅ ║</b>\n"
                "<b>╚═══════════════════════╝</b>\n"
                "\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                "<b>☎️ 𝗣𝗵𝗼𝗻𝗲 𝗡𝘂𝗺𝗯𝗲𝗿</b>\n"
                f"<b>{masked_phone}</b>\n"
                "\n"
                "<b>👤 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗨𝗜𝗗</b>\n"
                f"<b>{bnum(display_uid)}</b>\n"
                "\n"
                "<b>💰 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲</b>\n"
                f"<b>৳ {bnum(f'{balance:.2f}')}</b>\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                "\n"
                "<b>🧠 𝗔𝗻𝗮𝗹𝘆𝘀𝗶𝘀 𝗘𝗻𝗴𝗶𝗻𝗲:  𝗥𝗘𝗔𝗗𝗬</b>\n"
                "<b>🚀 𝗔𝘂𝘁𝗼𝗧𝗿𝗮𝗱𝗲 𝗦𝘆𝘀𝘁𝗲𝗺: 𝗥𝗘𝗔𝗗𝗬</b>\n"
                "\n"
                "<b>👇 𝗣𝗿𝗲𝘀𝘀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧 𝘁𝗼 𝗯𝗲𝗴𝗶𝗻</b>"
            )
            reply_keyboard = [[KeyboardButton("🚀 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗧𝗔𝗥𝗚𝗘𝗧")], [KeyboardButton("🛑 𝗦𝗧𝗢𝗣 𝗧𝗥𝗔𝗗𝗘"), KeyboardButton("🚪 𝗟𝗢𝗚𝗢𝗨𝗧")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True), parse_mode="HTML")
        else:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"<b>❌ 𝗟𝗢𝗚𝗜𝗡 𝗙𝗔𝗜𝗟𝗘𝗗\n𝗞𝗮𝗿𝗼𝗻: {msg}</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            if target_amount <= 0:
                raise ValueError()
            state["target"] = target_amount
            balance = float(state.get('balance', 0.00))
            stop_at = balance + target_amount
            # 🔧 আপনার দেওয়া নতুন মেসেজটি এখানে বসানো হলো
            target_set_msg = (
                "<b>╔════════════════════════╗</b>\n"
                "<b>║   🎯 𝗧𝗔𝗥𝗚𝗘𝗧 𝗦𝗘𝗧 🎯    ║</b>\n"
                "<b>╚════════════════════════╝</b>\n"
                f"<b>💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲  : ৳ {bnum(f'{balance:.2f}')}</b>\n"
                f"<b>🎯 𝗧𝗮𝗿𝗴𝗲𝘁   : ৳ {bnum(f'{target_amount:.2f}')} 𝗽𝗿𝗼𝗳𝗶𝘁</b>\n"
                f"<b>🏦 𝗦𝘁𝗼𝗽 𝗔𝘁  : ৳ {bnum(f'{stop_at:.2f}')}</b>\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                "<b>🚀 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗦𝗧𝗘𝗣 𝗖𝗢𝗨𝗡𝗧: 𝗛𝗼𝘄 𝗺𝗮𝗻𝘆 𝘀𝘁𝗲𝗽𝘀? (𝗲.𝗴. 𝟱, {𝟭,𝟮,𝟰} 𝟱𝟬)</b>"
            )
            state["awaiting"] = "steps"
            await update.message.reply_text(target_set_msg, parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗮𝗺𝗼𝘂𝗻𝘁. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝗮 𝗽𝗼𝘀𝗶𝘁𝗶𝘃𝗲 𝗻𝘂𝗺𝗯𝗲𝗿 (𝗶𝗻 ৳).</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "steps":
        try:
            steps_n = int(text)
            if steps_n < 1 or steps_n > 20:
                raise ValueError()
            state["steps"] = steps_n
            state["step_amounts"] = []
            state["current_step"] = 0
            state["awaiting"] = "step_amount"
            await update.message.reply_text(build_step_amounts_msg(steps_n), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱. 𝗘𝗻𝘁𝗲𝗿 𝗮 𝗻𝘂𝗺𝗯𝗲𝗿 𝗯𝗲𝘁𝘄𝗲𝗲𝗻 𝟭-𝟮𝟬.</b>", parse_mode="HTML")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amt = float(text)
            if amt <= 0:
                raise ValueError()
            state["step_amounts"].append(amt)
            state["current_step"] += 1

            if state["current_step"] < state["steps"]:
                await update.message.reply_text(build_single_step_prompt(state["current_step"] + 1), parse_mode="HTML")
            else:
                state["awaiting"] = None
                issue, phase = await asyncio.to_thread(get_panel_data, state["session"], state["lottery_token"])
                cfg_msg = build_config_msg(
                    state["balance"], state["target"], state["balance"] + state["target"],
                    state["steps"], state["step_amounts"], issue
                )
                kb = [[
                    InlineKeyboardButton("🚀 𝗦𝗧𝗔𝗥𝗧 𝗧𝗥𝗔𝗗𝗘", callback_data="start_trade"),
                    InlineKeyboardButton("❌ 𝗖𝗔𝗡𝗖𝗘𝗟", callback_data="cancel_trade")
                ]]
                await update.message.reply_text(cfg_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗮𝗺𝗼𝘂𝗻𝘁. 𝗘𝗻𝘁𝗲𝗿 𝗮 𝗽𝗼𝘀𝗶𝘁𝗶𝘃𝗲 𝗻𝘂𝗺𝗯𝗲𝗿.</b>", parse_mode="HTML")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_authorized(uid):
        return
    state = get_state(uid)

    if query.data == "start_login":
        state["awaiting"] = "phone"
        await query.message.reply_text(
            "<b>╔═════════════════════════╗</b>\n"
            "<b>║   🔐 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗟𝗢𝗚𝗜𝗡 🔐   ║</b>\n"
            "<b>╚═════════════════════════╝</b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>📱 𝗘𝗻𝘁𝗲𝗿 𝘆𝗼𝘂𝗿 𝗗𝗞 𝗪𝗜𝗡 𝗽𝗵𝗼𝗻𝗲 𝗻𝘂𝗺𝗯𝗲𝗿:</b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>𝗘𝘃𝗲𝗿𝘆𝗼𝗻𝗲 𝘂𝘀𝗲𝘀 𝘁𝗵𝗲𝗶𝗿 𝗼𝘄𝗻 𝗮𝗰𝗰𝗼𝘂𝗻𝘁 —</b>\n"
            "<b>𝘆𝗼𝘂𝗿 𝘀𝗲𝘀𝘀𝗶𝗼𝗻 𝗶𝘀 𝗽𝗿𝗶𝘃𝗮𝘁𝗲.</b>",
            parse_mode="HTML"
        )
        return

    if query.data == "cancel_trade":
        state["trade_running"] = False
        state["step_amounts"] = []
        try:
            await query.message.edit_text("<b>❌ 𝗧𝗿𝗮𝗱𝗲 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱.</b>", parse_mode="HTML")
        except:
            await query.message.reply_text("<b>❌ 𝗧𝗿𝗮𝗱𝗲 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱.</b>", parse_mode="HTML")
        return

    if query.data == "start_trade":
        if state.get("trade_running"):
            await query.message.reply_text("<b>⚠️ 𝗧𝗿𝗮𝗱𝗲 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗿𝘂𝗻𝗻𝗶𝗻𝗴.</b>", parse_mode="HTML")
            return
        if not state.get("lottery_token") or not state.get("step_amounts"):
            await query.message.reply_text("<b>❌ 𝗦𝗲𝘁𝘂𝗽 𝗶𝗻𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲. 𝗣𝗹𝗲𝗮𝘀𝗲 /start 𝗮𝗴𝗮𝗶𝗻.</b>", parse_mode="HTML")
            return
        
        state["trade_running"] = True
        state["auto_trade_shown"] = True 
        state["prediction_shown"] = False
        state["fail_retry_shown"] = False
        state["last_betted_issue"] = None
        
        # চাপ দেওয়ার সাথে সাথে অটো ট্রেড মেসেজটি চলে আসবে
        issue, phase = await asyncio.to_thread(get_panel_data, state["session"], state["lottery_token"])
        await query.message.reply_text(
            text=build_auto_trade_msg(
                state["balance"], state["target"], state["balance"] + state["target"],
                len(state["step_amounts"]), state["step_amounts"], issue
            ), 
            parse_mode="HTML"
        )
        
        task = asyncio.create_task(trade_worker(ctx.bot, uid))
        state["trade_task"] = task
        
        await query.answer("🚀 Trade Started!", show_alert=False)
        # ❌ বাটন ডিলিট করার লাইনটি রিমুভ করা হয়েছে যাতে বাটন থেকে যায়
        return

# ───────────────────────────────────────
# ৮. Render Keep-Alive (Web Service-এর জন্য)
# ───────────────────────────────────────
app = Flask('')

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ───────────────────────────────────────
# ৯. Main (নেটওয়ার্ক ইস্যু ফিক্স করা হলো)
# ───────────────────────────────────────
def main():
    keep_alive()

    request = HTTPXRequest(connect_timeout=20.0, read_timeout=30.0, write_timeout=30.0, pool_timeout=30.0)
    
    application = Application.builder().token(BOT_TOKEN).request(request).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("getid", cmd_getid))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()