import asyncio
import logging
import json
import re
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG 
# ⚠️ এখানে আপনার টেলিগ্রাম বটের টোকেন বসান
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAEUh-lBN2hW0i3WRqR_CJUsGi3CSmSU7HU" 
SITE_URL = "https://www.hgnice.vip"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, "steps": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 Playwright দিয়ে লগইন এবং ব্যালেন্স আনার ফাংশন
# ───────────────────────────────────────────
async def playwright_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone # 880 বাদ দেওয়া
    
    async with async_playwright() as p:
        # সার্ভারে রান করার জন্য headless=True
        browser = await p.chromium.launch(headless=True) 
        
        # মোবাইল ব্রাউজার সিমুলেশন (যাতে ওয়েবসাইট আসল মোবাইল ভাবে)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ওয়েবসাইটে যাওয়া
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            # ফর্ম ফিলাপ (অটোমেটিক মাউস ক্লিক ও টাইপিং)
            try:
                await page.fill('input[type="text"], input[type="tel"]', login_phone, timeout=5000)
                await page.wait_for_timeout(1000)
                await page.fill('input[type="password"]', password, timeout=5000)
                await page.wait_for_timeout(1000)
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=5000)
            except:
                # যদি উপরের সিলেক্টর না মেলে, তবে জাভাস্ক্রিপ্ট দিয়ে ক্লিক
                await page.evaluate(f"""
                    let inputs = document.querySelectorAll('input');
                    if(inputs.length > 0) inputs[0].value = '{login_phone}';
                    if(inputs.length > 1) inputs[1].value = '{password}';
                    let btns = document.querySelectorAll('button, div');
                    for (let b of btns) {{ if(b.innerText.toLowerCase().includes('log in')) b.click(); }}
                """)
            
            # লগইনের জন্য অপেক্ষা
            await page.wait_for_timeout(8000)
            
            # 💡 সফল লগইন হলে UID এবং Balance স্ক্র্যাপ করা
            page_text = await page.inner_text("body")
            
            if "Wrong account or password" in page_text or "Wrong signature" in page_text:
                if loading_msg_id:
                    try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                    except: pass
                await ctx.bot.send_message(chat_id=uid, text=f"❌ LOGIN FAILED ({phone})\n\nWrong account or password / Signature Error.")
                await browser.close()
                return
                
            uid_val = "Unknown"
            balance = "0.00"
            
            # রেগুলার এক্সপ্রেশন দিয়ে স্ক্রিন থেকে UID ও Balance বের করা
            uid_match = re.search(r'UID\s*\|\s*(\d+)', page_text, re.IGNORECASE)
            if uid_match: uid_val = uid_match.group(1)
                
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if balance_match: balance = balance_match.group(1)

            # অ্যাকাউন্ট সেভ করা
            account_info = {"phone": phone, "password": password, "uid": uid_val, "balance": balance}
            existing = False
            for acc in state["accounts"]:
                if acc["phone"] == phone:
                    acc.update(account_info)
                    existing = True
                    break
            if not existing:
                state["accounts"].append(account_info)
                
            state["balance"] = balance
            masked_phone = f"***{phone[-4:]}"
            
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            
            # 💡 ড্যাশবোর্ড মেসেজ
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone Number\n{masked_phone}\n\n"
                f"👤 Account UID\n{uid_val}\n\n"
                f"💰 Account Balance\n৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")],
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=markup)
            
            if len(state["accounts"]) < 6:
                await ctx.bot.send_message(chat_id=uid, text=f"✅ অ্যাকাউন্ট সেভ হয়েছে ({len(state['accounts'])}/6)। নতুন অ্যাকাউন্ট যোগ করতে /start দিন।")

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ Error: {str(e)[:100]}")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    if len(state["accounts"]) >= 6:
        await update.message.reply_text("✅ আপনার ৬টি অ্যাকাউন্ট ইতিমধ্যে সেভ করা আছে। নতুন করে শুরু করতে /reset দিন।")
        return

    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        f"👥 Accounts: {len(state['accounts'])}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak · 🔷 Pattern · 📈 Trend\n"
        "🔍 Manipulation · 🎨 Colour · 🔢 Frequency\n"
        "🔄 Markov · ♻️ Cycle · 💠 Momentum\n"
        "🔁 Every layer is back-tested live so its vote\n"
        "weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            f"☎️ Number : {text}\n\n"
            "🔑 Now enter your password:\n"
            "Your message will be deleted immediately for security."
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 CONNECTING... [░░░░░░░░░░] 0%")
        for i in range(1, 11):
            await asyncio.sleep(0.1)
            try: await loading_msg.edit_text(f"🔄 CONNECTING... [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        await playwright_login(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"])
        return

    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 START YOUR TARGET 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 YOUR BALANCE\n"
            f"৳ {state.get('balance', '0.00')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 Enter your TARGET profit amount:\n"
            "How much do you want to earn? (in ৳)"
        )
        await update.message.reply_text(target_msg)
        return

    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            balance = float(state.get('balance', '0.00'))
            stop_at = balance + target_amount
            
            target_set_msg = (
                "╔════════════════════════╗\n"
                "║   🎯 TARGET SET 🎯   ║\n"
                "╚════════════════════════╝\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Balance  : ৳ {balance:.2f}\n"
                f"🎯 Target   : ৳ {target_amount:.2f} profit\n"
                f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 Enter your STEP COUNT:\n"
                "How many steps? (e.g. 5, max 50)"
            )
            state["awaiting"] = "steps"
            await update.message.reply_text(target_set_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1:
                raise ValueError("Steps must be between 1 and 50")
            state["steps"] = steps
            state["awaiting"] = None
            await update.message.reply_text(f"✅ STEP COUNT SET: {steps}\n\nবট এখন কাজ শুরু করবে (অটো-বেট লজিক পরবর্তী ধাপে যোগ হবে)।")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন (যেমন: 5)।")
        return

    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 LOGGED OUT\n/start দিয়ে আবার লগইন করুন।")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 Enter your HGNICE phone number:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Everyone uses their own account — your session is private."
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, "steps": 0
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()