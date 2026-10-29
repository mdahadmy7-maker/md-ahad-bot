import requests
import hashlib
import uuid
import time
import json
import sys
from datetime import datetime

# ═══════════════════════════════════════════════════════════
# HGNICE AUTO BET BOT — WinGo 30S (FINAL API v6)
# Login + ARGame Balance + Auto Bet + Martingale + Target
# ═══════════════════════════════════════════════════════════

# ───────────── আপনার তথ্য এখানে বসান ─────────────
PHONE    = "8801351539676"          # ← আপনার ফোন (দেশের কোড সহ)
PASSWORD = "your_password"          # ← আপনার আসল পাসওয়ার্ড
STEPS    = [1, 2, 4, 8, 16, 32]     # ← আপনার স্টেপ (ইচ্ছামত)
TARGET   = 6                        # ← টার্গেট প্রফিট (৳6)

# ───────────── API এন্ডপয়েন্ট ─────────────
API_BASE     = "https://api.hgnicepayapi.com/api/webapi"
API_RESULT   = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
GAME_CODE    = "WinGo_30S"
LANG_VAL     = 0

# ───────────── TypeId ম্যাপ (আপনার রঙ অনুযায়ী) ─────────────
TYPE_BIG   = 1     # 💛 হলুদ
TYPE_SMALL = 2     # 🔵 নীল

# ───────────── স্টেট ─────────────
token = ""
token_hdr = "Bearer "
step_idx = 0
wins = 0
losses = 0
last_period = ""
balance = 0.0
start_balance = 0.0
profit = 0.0

# ═══════════════════════════════════════════════════════════
# Helpers (আপনার দেওয়া সিগনেচার জেনারেটর)
# ═══════════════════════════════════════════════════════════
def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def uuidv4():
    return str(uuid.uuid4()).replace("-", "")

def build_sig(data):
    t = dict(data)
    t.pop("signature", None)
    t.pop("timestamp", None)
    t["language"] = LANG_VAL
    t["random"] = uuidv4()
    clean = {k: v for k, v in t.items() if v is not None and v != ""}
    sorted_json = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    t["signature"] = md5(sorted_json).upper()[:32]
    t["timestamp"] = int(time.time())
    return t

def api_call(endpoint, data, with_token=True):
    body = build_sig(data)
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    if with_token and token:
        headers["Authorization"] = token_hdr + token
    url = API_BASE + endpoint
    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  ❌ Network error: {e}")
        return None
    if j.get("code") not in (0, None) and j.get("msgCode") not in (0, None):
        print(f"  ❌ API error: {j.get('msg') or j.get('msgCode') or j.get('code')}")
        return None
    return j

# ═══════════════════════════════════════════════════════════
# LOGIN & BALANCE
# ═══════════════════════════════════════════════════════════
def api_login(phone, pwd):
    global token, token_hdr
    data = {
        "username": phone, "pwd": pwd, "phonetype": 1,
        "logintype": "mobile", "packId": "",
        "deviceId": uuidv4(), "pixelId": "", "fbcId": "",
        "fbc": "", "fbp": "", "adId": "", "language": LANG_VAL,
    }
    j = api_call("/Login", data, with_token=False)
    if not j:
        return False
    d = j.get("data") or {}
    token = d.get("token", "")
    token_hdr = d.get("tokenHeader", "Bearer ")
    return bool(token)

def api_balance():
    global balance
    try:
        j = api_call("/GetAllwallets", {})
        if not j: return balance
        d = j.get("data") or {}
        lst = d.get("thidGameBalanceList", [])
        for item in lst:
            if item.get("vendorCode") == "ARGame":
                balance = float(item.get("balance", 0) or 0)
                return balance
    except: pass
    return balance

# ═══════════════════════════════════════════════════════════
# RESULT & PREDICTION
# ═══════════════════════════════════════════════════════════
def get_latest_result():
    try:
        res = requests.get(API_RESULT, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if list_data:
            return str(list_data[0].get("issueNumber", "")), int(list_data[0].get("number", 0))
    except Exception as e:
        print(f"History API error: {e}")
    return None, None

def get_prediction():
    _, last_num = get_latest_result()
    if last_num is not None:
        # প্রেডিকশন লজিক (আপনি চাইলে পরিবর্তন করতে পারেন)
        # আপাতত: ৫ বা তার বেশি হলে SMALL, ৪ বা কম হলে BIG
        return "SMALL" if last_num >= 5 else "BIG"
    return "BIG"

# ═══════════════════════════════════════════════════════════
# PLACE BET
# ═══════════════════════════════════════════════════════════
def place_bet(issue_number, amount, prediction):
    bet_content = "BigSmall_Big" if prediction == "BIG" else "BigSmall_Small"
    
    data = {
        "gameCode": GAME_CODE,
        "issueNumber": issue_number,
        "amount": int(amount),
        "betMultiple": 1,
        "betContent": bet_content
    }
    
    # বেট এপিআই এন্ডপয়েন্ট
    j = api_call("/Lottery/WinGoBet", data)
    if j and j.get("code") == 0:
        return True
    return False

# ═══════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════
def main():
    global step_idx, wins, losses, balance, start_balance, profit, last_period
    
    print("🔄 Logging in...")
    if not api_login(PHONE, PASSWORD):
        print("❌ Login failed! Please check your phone and password.")
        return
    print("✅ Login successful!")
    
    balance = api_balance()
    start_balance = balance
    print(f"💰 Start Balance: ৳ {balance:.2f}")
    
    if balance <= 0:
        print("❌ No balance to trade.")
        return

    print(f"🚀 Starting Auto-Bet | Target Profit: ৳ {TARGET}")
    print(f"📋 Martingale Steps: {STEPS}\n")
    
    last_seen_issue = ""
    
    while True:
        try:
            # ১. বর্তমান issue নাম্বার চেক করা
            current_issue, _ = get_latest_result()
            if not current_issue:
                time.sleep(1)
                continue
                
            # ২. নতুন রাউন্ড শুরু হলে বিট করা
            # যদি issue নাম্বার পরিবর্তন হয়ে যায় (অর্থাৎ নতুন রাউন্ড আসে)
            if current_issue != last_seen_issue:
                print(f"\n⏳ New Round Detected: {current_issue}")
                
                # প্রেডিকশন নেওয়া
                pred = get_prediction()
                bet_amount = STEPS[step_idx]
                
                # ব্যালেন্স চেক
                balance = api_balance()
                if balance < bet_amount:
                    print(f"❌ Insufficient balance (৳{balance:.2f}). Stopping.")
                    break
                    
                print(f"🎯 Placing bet: {pred} | ৳{bet_amount} | Step {step_idx+1}/{len(STEPS)}")
                
                success = place_bet(current_issue, bet_amount, pred)
                
                if success:
                    print(f"✅ Bet placed successfully for {current_issue}!")
                    last_seen_issue = current_issue
                    
                    # ৩. রেজাল্টের জন্য ৩০ সেকেন্ড অপেক্ষা
                    print("⏳ Waiting 32 seconds for result...")
                    time.sleep(32)
                    
                    # ৪. ব্যালেন্স চেক করে জয়/পরাজয় নির্ধারণ
                    new_balance = api_balance()
                    p_l = new_balance - balance
                    
                    if p_l > 0:
                        wins += 1
                        profit += p_l
                        print(f"🟢 WIN! (+৳{p_l:.2f}) | Balance: ৳{new_balance:.2f}")
                        step_idx = 0 # জিতলে স্টেপ ১ এ ফিরে যাবে
                    else:
                        losses += 1
                        profit += p_l
                        print(f"🔴 LOSS! (৳{p_l:.2f}) | Balance: ৳{new_balance:.2f}")
                        step_idx += 1 # হারলে পরের স্টেপে যাবে
                        
                    # ৫. টার্গেট পূরণ হলে স্টপ
                    if profit >= TARGET:
                        print(f"\n🎯 TARGET REACHED! Profit: ৳{profit:.2f}")
                        print(f"🏆 Total Wins: {wins} | Losses: {losses}")
                        break
                        
                    if step_idx >= len(STEPS):
                        print("\n⚠️ All steps finished! Stopping.")
                        break
                else:
                    print("❌ Failed to place bet. Retrying next round.")
                    time.sleep(5)
            else:
                # নতুন issue না আসা পর্যন্ত অপেক্ষা
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            break
        except Exception as e:
            print(f"⚠️ Error in loop: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()