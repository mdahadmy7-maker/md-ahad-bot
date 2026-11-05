# অফিসিয়াল Playwright ইমেজ ব্যবহার করা হলো
FROM mcr.microsoft.com/playwright/python:v1.41.2-jammy

WORKDIR /app

COPY requirements.txt .

# পাইথন ডিপেন্ডেন্সি ইনস্টল
RUN pip install --no-cache-dir -r requirements.txt

# 💡 সবচেয়ে গুরুত্বপূর্ণ ধাপ: ব্রাউজার এবং সিস্টেম ডিপেন্ডেন্সি ইনস্টল করা
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

CMD ["python", "main.py"]