import asyncio
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন (এখানে টোকেন বসান)
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAGBBUhSwIaIGc0uiCMM7qO3MAbAR62_mZI" 
SITE_URL = "https://www.hgnice.vip/#/login"

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
# ২. লগইন করার ফাংশন
# ───────────────────────────────────────────
async def playwright_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ১. ওয়েবসাইটে ঢোকা
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000) 

            # ২. নাম্বার ও পাসওয়ার্ড বসানো
            try:
                phone_input = page.get_by_placeholder("Please enter the phone number")
                await phone_input.click(timeout=10000)
                await page.keyboard.type(login_phone, delay=50)
                await page.wait_for_timeout(500)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click(timeout=10000)
                await pass_input.fill(password)
                await page.evaluate(f"""
                    let passInput = document.querySelector('input[type="password"]');
                    if (passInput) {{
                        passInput.value = '{password}';
                        passInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                """)
                await page.wait_for_timeout(1000)
            except:
                pass

            # ৩. লগইন বাটনে ক্লিক
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            # 💡 ৪. পপ-আপ আসার জন্য ৫ সেকেন্ড অপেক্ষা
            await page.wait_for_timeout(5000) 

            # 💡 ৫. 'Confirm' বাটনে ক্লিক করা
            try:
                confirm_btn = page.locator('text="Confirm"').first
                if await confirm_btn.is_visible(timeout=5000):
                    await confirm_btn.click()
                    await page.wait_for_timeout(2000) # পপ-আপ বন্ধ হওয়ার জন্য অপেক্ষা
            except:
                pass # পপ-আপ না থাকলে স্কিপ করবে

            # 💡 ৬. নিচের ডান কোণে থাকা 'Account' বাটনে ক্লিক করা
            try:
                # আমরা 'Account' লেখাটি খুঁজব এবং একদম শেষেরটি (নিচের নেভিগেশন বারে) ক্লিক করব
                account_btn = page.locator('text="Account"').last
                if await account_btn.is_visible(timeout=5000):
                    await account_btn.click()
                    await page.wait_for_timeout(3000) # অ্যাকাউন্ট পেজ লোড হওয়ার জন্য অপেক্ষা
            except:
                pass

            # ৭. ড্যাশবোর্ড থেকে UID এবং Balance খোঁজা
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(15): 
                page_text = await page.inner_text("body")
                
                if "Wrong account or password" in page_text or "Wrong signature" in page_text:
                    login_status = "failed"
                    break
                    
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match:
                        balance = balance_match.group(1)
                    login_status = "success"
                    break
                    
                await page.wait_for_timeout(1000)

            # লোডিং মেসেজ ডিলিট করা
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            # ৮. রেজাল্ট চেক
            if login_status == "failed":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\n\nWrong account or password.", parse_mode="Markdown")
                await browser.close()
                return
                
            elif login_status == "unknown" or uid_val == "Unknown":
                screenshot_path = f"error_{uid}.png"
                await page.screenshot(path=screenshot_path)
                with open(screenshot_path, "rb") as photo:
                    await ctx.bot.send_photo(chat_id=uid, photo=photo, caption="⚠️ লগইন হয়েছে কিনা বা UID পাওয়া যায়নি। স্ক্রিনশটে পপ-আপ বা এরর দেখুন।")
                await browser.close()
                return

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
            
            # 💡 ৯. ড্যাশবোর্ড মেসেজ
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
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
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
        
        # ১০০% লোডিং
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...** [░░░░░░░░░░] 0%", parse_mode="Markdown")
        for i in range(1, 101):
            if i % 10 == 0: 
                filled = "█" * (i//10)
                empty = "░" * (10 - (i//10))
                try: await loading_msg.edit_text(f"🔄 **CONNECTING...** [{filled}{empty}] {i}%", parse_mode="Markdown")
                except: pass
            await asyncio.sleep(0.05) 
        
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
            state["steps"] = steps
            state["awaiting"] = None
            await update.message.reply_text(f"✅ STEP COUNT SET: {steps}\n\nবট এখন কাজ শুরু করবে।")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return

    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 LOGGED OUT")
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
    if not BOT_TOKEN or BOT_TOKEN == "এখানে_আপনার_টেলিগ্রাম_বটের_টোকেন_বসান":
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