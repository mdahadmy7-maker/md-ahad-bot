import asyncio
import logging
import re
import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. Flask সার্ভার (Render এর জন্য)
# ═══════════════════════════════════════════
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# ═══════════════════════════════════════════
# ২. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "balance": "0.00", "uid_val": "Unknown", "browser": None, "page": None, "playwright": None
        }
    return user_state[uid]

async def close_browser(uid):
    state = get_state(uid)
    if state.get("browser"):
        try: await state["browser"].close()
        except: pass
    if state.get("playwright"):
        try: await state["playwright"].stop()
        except: pass
    state["browser"] = None
    state["page"] = None
    state["playwright"] = None

# ───────────────────────────────────────────
# ৩. লগইন ফাংশন (লগ ও স্ক্রিনশট সহ)
# ───────────────────────────────────────────
async def execute_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    try:
        print(">>> [LOG] Playwright starting...")
        p = await async_playwright().start()
        
        print(">>> [LOG] Launching Chromium browser...")
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}
        )
        page = await context.new_page()
        
        state["playwright"] = p
        state["browser"] = browser
        state["page"] = page

        await ctx.bot.send_message(chat_id=uid, text="🔄 **সাইটে ঢোকা হচ্ছে...**")
        print(">>> [LOG] Navigating to URL...")
        await page.goto(SITE_URL, timeout=90000, wait_until="domcontentloaded")
        print(">>> [LOG] URL loaded successfully.")
        
        await page.wait_for_timeout(5000)

        # লগইন ফর্ম পূরণ
        print(">>> [LOG] Filling credentials...")
        try:
            await page.locator('input[type="text"], input[type="tel"]').first.fill(login_phone)
            await page.wait_for_timeout(1000)
            await page.locator('input[type="password"]').first.fill(password)
            await page.wait_for_timeout(1000)
            print(">>> [LOG] Clicking Login button...")
            await page.get_by_text("Log in", exact=False).last.click()
        except Exception as e:
            print(f">>> [LOG] Input Error: {e}")

        await ctx.bot.send_message(chat_id=uid, text="🔄 **লগইন প্রসেস হচ্ছে...**")
        await page.wait_for_timeout(6000) 

        # পপআপ ক্লোজ
        print(">>> [LOG] Closing popups...")
        for _ in range(5):
            await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { let t=(el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close') el.click(); } }")
            await page.wait_for_timeout(500)

        # Account পেজ
        print(">>> [LOG] Navigating to Account page...")
        try:
            await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
            await page.wait_for_timeout(4000) 
        except: pass

        # UID ও Balance বের করা
        print(">>> [LOG] Extracting UID and Balance...")
        uid_val = "Unknown"
        balance = "0.00"
        for _ in range(10): 
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if not balance_match: balance_match = re.search(r'৳\s*([\d.]+)', page_text)
            
            if uid_match:
                uid_val = uid_match.group(1)
                if balance_match: balance = balance_match.group(1)
                break
            await page.wait_for_timeout(500)

        if uid_val != "Unknown":
            state["balance"] = float(balance)
            state["uid_val"] = uid_val
            print(f">>> [LOG] SUCCESS: UID {uid_val}, Balance {balance}")
            await ctx.bot.send_message(chat_id=uid, text=f"✅ **LOGIN SUCCESSFUL**\n\n👤 **UID:** `{uid_val}`\n💰 **Balance:** ৳ {balance}")
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")]]
            await ctx.bot.send_message(chat_id=uid, text="👇 এখন আপনার টার্গেট সেট করুন।", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        else:
            print(">>> [LOG] FAILED: UID not found in text.")
            # 💡 লগইন ব্যর্থ হলে স্ক্রিনশট নেওয়া
            ss_path = f"fail_{uid}.jpg"
            try:
                await page.screenshot(path=ss_path, type="jpeg", quality=80)
                await ctx.bot.send_photo(
                    chat_id=uid, 
                    photo=open(ss_path, 'rb'), 
                    caption="❌ **LOGIN FAILED**\n\nপাসওয়ার্ড ভুল অথবা সাইট বটকে ডিটেক্ট করেছে। নিচের স্ক্রিনশটে দেখুন সাইটে কী অবস্থা।"
                )
                os.remove(ss_path)
            except Exception as e:
                print(f">>> [LOG] Screenshot failed: {e}")
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**\n\nপাসওয়ার্ড ভুল অথবা সাইট বটকে ডিটেক্ট করেছে।")

    except Exception as e:
        print(f">>> [LOG] CRITICAL ERROR: {e}")
        logger.error(f"Login Error: {e}")
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সিস্টেম এরর:** `{str(e)[:150]}`")

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await close_browser(uid)
    user_state[uid] = get_state(uid) 
    await update.message.reply_text("🧠 **DK WIN AUTO BET**\n\n👇 Press the button to LOGIN", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔐 LOGIN", callback_data="start_login")]]))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 **পাসওয়ার্ড দিন:**")
    elif state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(execute_login(uid, ctx, state["temp_phone"], state["temp_password"]))

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if query.data == "start_login":
        get_state(uid)["awaiting"] = "phone"
        await query.edit_message_text("📱 **ফোন নাম্বার দিন:**")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return

    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()