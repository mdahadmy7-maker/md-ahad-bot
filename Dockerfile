FROM python:3.10-slim

# Playwright ব্রাউজারের জন্য প্রয়োজনীয় লাইব্রেরি ইনস্টল
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright ব্রাউজার ইনস্টল
RUN playwright install chromium

COPY . .

CMD ["python", "main.py"]