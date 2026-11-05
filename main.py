import asyncio
import logging
import re
import os
import random
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login"
HOME_URL = "https://dkwin8.com/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "balance": "0.00", "uid_val": "Unknown", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "browser": None, "page": None, "playwright": None
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. ব্রাউজার বন্ধ করার ফাংশন
# ───────────────────────────────────────────
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
# ৩. লগইন এবং ব্যালেন্স বের করার ফাংশন (হাইব্রিড)
# ───────────────────────────────────────────
async def execute_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    try:
        # ব্রাউজার ওপেন করা (হেডলেস, কোনো স্ক্রিনশট নেওয়া হবে না)
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True, 
            executable_path="/data/data/com.termux/files/usr/bin/chromium-browser", # Termux এর জন্য
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}, is_mobile=True, has_touch=True
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await context.new_page()
        
        state["playwright"] = p
        state["browser"] = browser
        state["page"] = page

        # ১. সাইটে ঢোকা
        await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # ২. "I have an account" বাটনে ক্লিক
        try:
            acc_btn = page.locator('text="I have an account"').first
            if await acc_btn.count() > 0 and await acc_btn.is_visible():
                await acc_btn.click(force=True, timeout=10000)
                await asyncio.sleep(3)
        except: pass

        # ৩. ফোন এবং পাসওয়ার্ড বসানো
        try:
            phone_input = page.locator('input[type="text"], input[type="tel"]').first
            await phone_input.wait_for(state="visible", timeout=15000)
            await phone_input.fill(login_phone)
            await asyncio.sleep(1)
            
            pass_input = page.locator('input[type="password"]').first
            await pass_input.fill(password)
            await asyncio.sleep(1)
        except Exception as e:
            await ctx.bot.send_message(chat_id=uid, text=f"❌ ইনপুট ফিল্ডে সমস্যা: {e}")
            return

        # ৪. Log in বাটনে ক্লিক
        try:
            await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000, force=True)
        except:
            await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, a')) { if((el.innerText||'').toLowerCase()==='log in') el.click(); } }")
        
        await ctx.bot.send_message(chat_id=uid, text="🔄 **লগইন করা হচ্ছে...**")
        await asyncio.sleep(6) # লগইন হতে সময় দিন

        # ৫. পপআপ ক্লোজ
        for _ in range(10):
            await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { let t=(el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }")
            await asyncio.sleep(0.5)

        # ৬. Account পেজে ক্লিক
        try:
            account_tab = page.get_by_text("Account", exact=True).last
            if await account_tab.count() > 0 and await account_tab.is_visible():
                await account_tab.click(force=True, timeout=10000)
            else:
                await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
            await asyncio.sleep(4) 
        except: pass

        # ৭. UID এবং Balance বের করা
        uid_val = "Unknown"
        balance = "0.00"
        for _ in range(15): 
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
            
            # সফল লগইন মেসেজ
            await ctx.bot.send_message(chat_id=uid, text=f"✅ **LOGIN SUCCESSFUL**\n\n👤 UID: `{uid_val}`\n💰 Balance: ৳ {balance}\n\n👇 এখন আপনার টার্গেট সেট করুন।")
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text="👇 Press START YOUR TARGET", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        else:
            await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**\n\nসম্ভবত পাসওয়ার্ড ভুল অথবা সাইট লোড হতে সমস্যা হয়েছে।")
            await close_browser(uid)

    except Exception as e:
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সিস্টেম এরর:** `{str(e)[:100]}`")
        await close_browser(uid)

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await close_browser(uid)
    user_state[uid] = get_state(uid) 
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
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
    
    # ১. ফোন নাম্বার নেওয়া
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 **এখন আপনার পাসওয়ার্ড দিন:**")
        return

    # ২. পাসওয়ার্ড নেওয়া এবং সাথে সাথে লগইন শুরু করা
    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        # এখানে লগইন প্রসেস শুরু হবে (কোনো বাড়তি মেসেজ ছাড়া)
        state["task"] = asyncio.create_task(execute_login(uid, ctx, state["temp_phone"], state["temp_password"]))
        return

    # ৩. টার্গেট সেট করা (লগইন সফল হওয়ার পর)
    if text == "🚀 START YOUR TARGET":
        if state.get("uid_val") == "Unknown":
            await update.message.reply_text("❌ আগে লগইন করুন। /start দিন।")
            return
        state["awaiting"] = "target"
        await update.message.reply_text(f"💰 YOUR BALANCE: ৳ {state.get('balance', '0.00')}\n\n🎯 Enter your TARGET profit amount (in ৳):")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("🚀 Enter your STEP COUNT (e.g. 5, max 50):")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError()
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
            else:
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                step_plan_text = "".join([f"Step {i+1:02d} : ৳ {amt:.2f}\n" for i, amt in enumerate(state["step_amounts"])])
                
                msg = (
                    f"⚙️ TRADE CONFIGURATION ⚙️\n"
                    f"💰 Balance : ৳ {state['balance']:.2f}\n"
                    f"🎯 Target  : ৳ {state['target']:.2f}\n"
                    f"📋 Steps   : {state['steps']}\n"
                    f"⚠️ Risk    : ৳ {total_risk:.2f}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📊 STEP PLAN\n{step_plan_text}\n"
                    f"👇 Press START TRADE to begin."
                )
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]])
                await update.message.reply_text(msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু সংখ্যা লিখুন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
        
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        await close_browser(uid)
        await update.message.reply_text("🚪 LOGGED OUT এবং ব্রাউজার বন্ধ করা হয়েছে। /start দিন।")
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
    elif data == "start_trade_btn":
        await query.edit_message_text("🚀 **ট্রেডিং শুরু হচ্ছে...**")
        # এখানে আমরা পরবর্তী ধাপে বাজি ধরার ফাংশনটি কল করব
        await ctx.bot.send_message(chat_id=uid, text="বাজি ধরার লজিক পরবর্তী ধাপে যুক্ত করা হবে।")
    elif data == "cancel_trade_btn":
        await query.edit_message_text("❌ **TRADE CANCELLED**")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["trade_running"] = False
    if state.get("task"): state["task"].cancel()
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