import requests
import time
import json

def direct_api_login(phone, password):
    # আপনার curl থেকে নেওয়া URL
    url = "https://api.dkwinapi.com/api/webapi/Login"
    
    # আপনার curl থেকে নেওয়া Headers
    headers = {
        "authority": "api.dkwinapi.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "ar-origin": "https://dkwin1.com",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin1.com",
        "referer": "https://dkwin1.com/",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    # বর্তমান টাইমস্ট্যাম্প (সেকেন্ডে)
    current_timestamp = int(time.time())

    # আপনার curl থেকে নেওয়া Payload
    payload = {
        "username": phone,
        "pwd": password,
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
        # 🚨 এখানে আপনার আগের ওই সিগনেচার বসানো হলো (এটি সাধারণত কাজ করবে না)
        "random": "52edcf73bb214f73888eca195ad1c5f8",
        "signature": "1BBBE73DCEAA1BC85732D7379362D467",
        "timestamp": current_timestamp
    }

    print("Sending Request...")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        print("Status Code:", response.status_code)
        print("Response JSON:", json.dumps(response.json(), indent=4))
    except Exception as e:
        print("Error:", e)

# টেস্ট করার জন্য (পাসওয়ার্ড দিন)
direct_api_login("8801745701676", "your_password_here")