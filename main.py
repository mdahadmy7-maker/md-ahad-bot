import asyncio
import logging
import re
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
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
# ২. লগইন ফাংশন (শুধু টেক্সট রেসপন্স, কোনো ছবি নেই)
# ───────────────────────────────────────────
async def execute_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    try:
        p = await async_playwright().start()
        # Termux বা Render এর জন্য
        browser = await p.chromium.launch(
            headless=True, 
            # Termux এর জন্য পাথ:
            executable_path="/data/data/com.termux/files/usr/bin/chromium-browser", 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}, is_mobile=True, has_touch=True
        )
        page = await context.new_page()
        
        state["playwright"] = p
        state["browser"] = browser
        state["page"] = page

        await ctx.bot.send_message(chat_id=uid, text="🔄 **সাইটে ঢোকা হচ্ছে...**")
        await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # "I have an account" বাটনে ক্লিক
        try:
            acc_btn = page.locator('text="I have an account"').first
            if await acc_btn.count() > 0:
                await acc_btn.click(force=True, timeout=5000)
                await asyncio.sleep(3)
        except: pass

        # নাম্বার ও পাসওয়ার্ড বসানো
        try:
            await page.locator('input[type="text"], input[type="tel"]').first.fill(login_phone)
            await asyncio.sleep(1)
            await page.locator('input[type="password"]').first.fill(password)
            await asyncio.sleep(1)
        except: pass

        # Log in বাটনে ক্লিক
        try:
            await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=5000)
        except:
            await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, a')) { if((el.innerText||'').toLowerCase()==='log in') el.click(); } }")
        
        await ctx.bot.send_message(chat_id=uid, text="🔄 **লগইন প্রসেস হচ্ছে...**")
        await asyncio.sleep(6) 

        # পপআপ ক্লোজ
        for _ in range(5):
            await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { let t=(el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close') el.click(); } }")
            await asyncio.sleep(0.5)

        # Account পেজে ক্লিক
        try:
            await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
            await asyncio.sleep(4) 
        except: pass

        # UID এবং Balance বের করা
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
            await asyncio.sleep(0.5)

        if uid_val != "Unknown":
            state["balance"] = float(balance)
            state["uid_val"] = uid_val
            # এখানে কোনো ছবি পাঠানো হচ্ছে না, শুধু টেক্সট
            await ctx.bot.send_message(chat_id=uid, text=f"✅ **LOGIN SUCCESSFUL**\n\n👤 **UID:** `{uid_val}`\n💰 **Balance:** ৳ {balance}")
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE")]]
            await ctx.bot.send_message(chat_id=uid, text="👇 এখন আপনার টার্গেট সেট করুন।", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        else:
            await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**\n\nপাসওয়ার্ড ভুল অথবা সাইট বটকে ডিটেক্ট করেছে।")

    except Exception as e:
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সিস্টেম এরর:** `{str(e)[:100]}`")
    finally:
        pass # ব্রাউজার খোলা রাখব যাতে বাজি ধরা যায়

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await close_browser(uid)
    user_state[uid] = get_state(uid) 
    
    welcome_text = (
        "🧠 **DK WIN AUTO BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔴 Status  : Not Logged In\n"
        "👇 Press the button below to LOGIN"
    )
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 **এখন আপনার পাসওয়ার্ড দিন:**")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(execute_login(uid, ctx, state["temp_phone"], state["temp_password"]))
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    
    if data == "start_login":
        state["awaiting"] = "phone"
        await query.edit_message_text("📱 **আপনার DK WIN ফোন নাম্বার দিন:**")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await close_browser(uid)
    user_state[uid] = get_state(uid) 
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()