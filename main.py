import time
import uuid
import hashlib
import requests

def generate_signature(random_str, timestamp, pwd):
    # সাইটের নিয়ম অনুযায়ী সিগনেচার হ্যাশ তৈরি করার লজিক
    raw_str = f"{random_str}{timestamp}{pwd}"
    return hashlib.md5(raw_str.encode()).hexdigest().upper()

def dynamic_login(phone, password):
    url = "https://api.dkwinapi.com/api/webapi/Login"
    
    current_timestamp = int(time.time())
    random_hex = uuid.uuid4().hex
    signature_val = generate_signature(random_hex, current_timestamp, password)
    
    headers = {
        "authority": "api.dkwinapi.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "ar-origin": "https://dkwin8.com",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin8.com",
        "referer": "https://dkwin8.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    payload = {
        "username": phone,          # এখানে ইউজারের দেওয়া সঠিক ফোন নম্বর বসবে
        "pwd": password,            # এখানে ইউজারের দেওয়া সঠিক পাসওয়ার্ড বসবে
        "phonetype": 1,
        "logintype": "mobile",
        "packId": "",
        "deviceId": "78a31db8d2dc8544556f9d82370be707",
        "pixelId": "",
        "fbcId": "",
        "fbc": "",
        "fbp": "",
        "adId": "",
        "language": 0,
        "random": random_hex,
        "signature": signature_val,
        "timestamp": current_timestamp
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}
        