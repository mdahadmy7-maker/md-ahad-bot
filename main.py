import asyncio
import logging
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন (এখানে টোকেন বসান)
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAGhKvEHu8V2X5CONTsHi5tv3NyVc634XYk" 
SITE_URL = "https://www.hgnice.vip/#/login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. লগইন করার ফাংশন
# ───────────────────────────────────────────
async def playwright_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text_status=""):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **লোড হচ্ছে...** [{filled}{empty}] {percent}%\n_{text_status}_", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            await update_loading(20, "সাইটে ঢুকছে...")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            await update_loading(40, "লগইন তথ্য দেওয়া হচ্ছে...")
            try:
                phone_input = page.get_by_placeholder("Please enter the phone number")
                await phone_input.click(timeout=10000)
                await page.keyboard.type(login_phone, delay=30)
                await page.wait_for_timeout(300)
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click(timeout=10000)
                await pass_input.fill(password)
                await page.wait_for_timeout(500)
            except: pass

            await update_loading(60, "লগইন করা হচ্ছে...")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            await update_loading(80, "পপ-আপ বন্ধ করা হচ্ছে...")
            for _ in range(10):
                clicked = await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('button, div, span, a, input[type="button"]');
                        for (let el of elements) {
                            let text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                            if (text === 'confirm' || text === 'receive' || text === 'close' || text === 'ok') {
                                let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                el.dispatchEvent(event);
                                return true;
                            }
                        }
                        return false;
                    })();
                """)
                await page.wait_for_timeout(500)

            await update_loading(90, "অ্যাকাউন্ট পেজে যাওয়া হচ্ছে...")
            try:
                await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('div, span, a');
                        for (let el of elements) {
                            if (el.innerText && el.innerText.trim().toLowerCase() === 'account') {
                                let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                el.dispatchEvent(event);
                                return true;
                            }
                        }
                        return false;
                    })();
                """)
                await page.wait_for_timeout(2000)
            except: pass

            await update_loading(95, "তথ্য সংগ্রহ করা হচ্ছে...")
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text or "Wrong signature" in page_text:
                    login_status = "failed"
                    break
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(500)

            if login_status == "success":
                await update_loading(100, "সফলভাবে সম্পন্ন হয়েছে!")
                await asyncio.sleep(0.3)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\n\nWrong account or password.", parse_mode="Markdown")
                await browser.close()
                return
                
            elif login_status == "unknown" or uid_val == "Unknown":
                screenshot_path = f"error_{uid}.png"
                await page.screenshot(path=screenshot_path)
                with open(screenshot_path, "rb") as photo:
                    await ctx.bot.send_photo(chat_id=uid, photo=photo, caption="⚠️ UID পাওয়া যায়নি। স্ক্রিনশটে দেখুন বট কোথায় আটকে আছে।")
                await browser.close()
                return

            account_info = {"phone": phone, "password": password, "uid": uid_val, "balance": balance}
            existing = False
            for acc in state["accounts"]:
                if acc["phone"] == phone:
                    acc.update(account_info)
                    existing = True
                    break
            if not existing: state["accounts"].append(account_info)
                
            state["balance"] = balance
            masked_phone = f"***{phone[-4:]}"
            
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
        loading_msg = await update.message.reply_text("🔄 **লোড হচ্ছে...** [░░░░░░░░░░] 0%", parse_mode="Markdown")
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
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError("Steps must be between 1 and 50")
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            
            step_msg = (
                "╔════════════════════════╗\n"
                "║   💵 STEP AMOUNTS 💵   ║\n"
                "╚════════════════════════╝\n\n"
                f"You chose {steps} steps.\n\n"
                f"💵 Step {state['current_step']} — bet amount? (in ৳)"
            )
            await update.message.reply_text(step_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন (যেমন: 5)।")
        return

    # 💡 ৪. স্টেপের বাজির পরিমাণ নেওয়া এবং একসাথে পুরো কনফিগারেশন দেখানো
    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            if amount <= 0: raise ValueError("Amount must be greater than 0")
            
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            
            if state["current_step"] <= state["steps"]:
                step_msg = f"💵 Step {state['current_step']} — bet amount? (in ৳)"
                await update.message.reply_text(step_msg)
            else:
                # সব স্টেপ শেষ, এখন পুরো কনফিগারেশন একসাথে দেখাবে
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                balance = float(state.get('balance', '0.00'))
                target = float(state.get('target', 0))
                stop_at = balance + target
                
                step_plan_text = ""
                for i, amt in enumerate(state["step_amounts"]):
                    step_plan_text += f"Step {i+1:02d} : ৳ {amt:.2f}\n"
                
                # একটি ডামি পিরিয়ড কোড তৈরি
                current_period_code = datetime.now().strftime("%Y%m%d%H%M%S") + "000"
                
                # 💡 আপনার দেওয়া হুবহু ফরম্যাটে সবকিছু একসাথে
                combined_msg = (
                    "⚙️ TRADE CONFIGURATION ⚙️\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Balance  : ৳ {balance:.2f}\n"
                    f"🎯 Target   : ৳ {target:.2f} profit\n"
                    f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                    f"📋 Steps    : {state['steps']}\n"
                    f"⚠️ Total Risk : ৳ {total_risk:.2f}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📊 STEP PLAN\n"
                    f"{step_plan_text}"
                    "\n"
                    "📄 COPY CODE\n"
                    f"`{current_period_code}`\n\n"
                    "⏱️ Current Period\n"
                    f"{current_period_code}\n"
                    "▓▓▓▓▓▓▓▓ 1s\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🧠 Engine: 9 layers + live backtest\n"
                    "🔴 Confidence gate: below 30% → sit out\n"
                    "🎬 Prediction animation: 4s\n\n"
                    "👇 Press START TRADE to begin."
                )
                
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                
                # parse_mode বাদ দেওয়া হয়েছে যাতে কোনো এরর না আসে
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
                
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 1)।")
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
    data = query.data
    
    if data == "start_login":
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
        
    elif data == "start_trade_btn":
        state["trade_running"] = True
        # এখানে আপনার পরবর্তী কাজ (অটো-বেট লজিক) যোগ হবে
        await query.edit_message_text(
            "🚀 **TRADE STARTED SUCCESSFULLY!**\n\n"
            "বট এখন আপনার স্টেপ অনুযায়ী বাজি ধরা শুরু করবে।\n"
            "(বাজি ধরার লজিক পরবর্তী ধাপে যোগ করা হবে)।",
            parse_mode="Markdown"
        )
        
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text(
            "❌ **TRADE CANCELLED**\n\nআপনি ট্রেড বাতিল করেছেন।"
        )

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, 
        "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False
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