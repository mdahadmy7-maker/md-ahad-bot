import requests
import json
import time
import uuid
import hashlib

# ==========================================
# 🔴 এখানে আপনার লগইনের তথ্য দিন
# ==========================================
USERNAME = "8801745701676"
PASSWORD = "1234"
DEVICE_ID = "4aa593880f5c671907b460252b022635" # এটি আপনি চাইলে পরিবর্তন করতে পারেন

LOGIN_URL = "https://api.dkwinapi.com/api/webapi/Login"

# ==========================================
# ⚙️ সিগনেচার জেনারেটর ফাংশন
# ==========================================
def generate_signature(payload_data):
    # ১. ডাটাগুলো A-Z অনুযায়ী সাজানো
    sorted_keys = sorted(payload_data.keys())
    
    # ২. নতুন অবজেক্ট তৈরি (খালি ডাটা বাদ দিয়ে)
    filtered_data = {}
    for key in sorted_keys:
        val = payload_data[key]
        if val is not None and val != "":
            filtered_data[key] = val
            
    # ৩. JSON স্ট্রিং তৈরি করা (একদম কম্প্যাক্ট, কোনো স্পেস ছাড়া)
    json_string = json.dumps(filtered_data, separators=(',', ':'))
    
    # ৪. MD5 হ্যাশ তৈরি (Wz ফাংশনের কাজ)
    # 💡 মনে রাখবেন: যদি সিগনেচার না মেলে, তবে এখানে একটি SECRET_KEY যোগ করতে হতে পারে
    # যেমন: raw_string = json_string + "secret_key"
    raw_string = json_string 
    
    signature = hashlib.md5(raw_string.encode('utf-8')).hexdigest().upper()
    
    return signature

# ==========================================
# 🚀 মেইন লগইন প্রসেস
# ==========================================
def attempt_login():
    current_timestamp = int(time.time())
    random_str = uuid.uuid4().hex # ৩২ অক্ষরের র‍্যান্ডম স্ট্রিং
    
    # প্রাথমিক পে-লোড (সিগনেচার ছাড়া)
    payload = {
        "username": USERNAME,
        "pwd": PASSWORD,
        "phonetype": 1,
        "logintype": "mobile",
        "packId": "",
        "deviceId": DEVICE_ID,
        "pixelId": "",
        "fbcId": "",
        "fbc": "",
        "fbp": "",
        "adId": "",
        "language": 0,
        "random": random_str,
        "timestamp": current_timestamp
    }

    # সিগনেচার বের করা
    signature = generate_signature(payload)
    
    # ফাইনাল পে-লোডে সিগনেচার যুক্ত করা
    payload["signature"] = signature

    # HTTP হেডার্স
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "ar-origin": "https://dkwin0.com",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin0.com",
        "referer": "https://dkwin0.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    print(f"[*] Attempting login for {USERNAME}...")
    print(f"[*] Generated Signature: {signature}")
    print(f"[*] Timestamp: {current_timestamp}")

    try:
        response = requests.post(LOGIN_URL, json=payload, headers=headers)
        res_data = response.json()
        
        if res_data.get("code") == 0:
            print("\n✅ LOGIN SUCCESSFUL!")
            token = res_data["data"]["token"]
            print(f"🔑 TOKEN: {token[:50]}...")
            
            # টোকেনটি একটি ফাইলে সেভ করে রাখা (বটে ব্যবহারের জন্য)
            with open("token.txt", "w") as f:
                f.write(token)
            print("💾 Token saved to token.txt")
            
        else:
            print("\n❌ LOGIN FAILED!")
            print(f"Error Message: {res_data.get('msg')}")
            print(f"Full Response: {json.dumps(res_data, indent=2)}")
            
    except Exception as e:
        print(f"\n⚠️ Request Error: {e}")

if __name__ == "__main__":
    attempt_login()