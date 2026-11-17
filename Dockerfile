# বেস ইমেজ হিসেবে পাইথন ব্যবহার করা হচ্ছে
FROM python:3.10-slim

# cURL ইনস্টল করা হচ্ছে (বেট প্লেস করার জন্য জরুরি)
RUN apt-get update && apt-get install -y curl

# ওয়ার্কিং ডিরেক্টরি সেট করা হচ্ছে
WORKDIR /app

# requirements.txt কপি করে লাইব্রেরি ইনস্টল করা হচ্ছে
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# বাকি সব ফাইল কপি করা হচ্ছে
COPY . .

# বট রান করার কমান্ড (আপনার ফাইলের নাম main.py হলে এটাই থাকবে)
CMD ["python", "main.py"]