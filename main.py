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
BOT_TOKEN = "8850232346:AAGBBUhSwIaIGc0uiCMM7qO3MAbAR62_mZI" 
SITE_URL = "https://www.hgnice.vip/#/login"
WINGO_URL = "https://www.hgnice.vip/#/WinGo" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
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
            # ---------------- ১. লগইন ----------------
            await update_loading(20, "সাইটে ঢুকছে...")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            await update_loading(40, "লগইন তথ্য দেওয়া হচ্ছে...")
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except: pass

            await update_loading(60, "লগইন করা হচ্ছে...")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except: pass
            
            await update_loading(80, "পপ-আপ বন্ধ করা হচ্ছে...")
            for _ in range(10):
                await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('button, div, span, a, input[type="button"]');
                        for (let el of elements) {
                            let text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                            if (text === 'confirm' || text === 'receive' || text === 'close' || text === 'ok') {
                                let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                el.dispatchEvent(event);
                            }
                        }
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
                                el.click(); return true;
                            }
                        }
                    })();
                """)
                await page.wait_for_timeout(2000)
            except: pass

            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
                    login_status = "failed"; break
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"; break
                await page.wait_for_timeout(500)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
                await browser.close(); return

            state["balance"] = float(balance)
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
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            # ---------------- ২. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            last_choice = None
            last_result = None 

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nব্যালেন্স ৳{current_bal:.2f} হয়েছে। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** ব্যালেন্স: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])

                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**\nপ্রয়োজন: ৳{bet_amount}, আছে: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    # WinGo পেজে যাওয়া
                    await page.goto(WINGO_URL, timeout=60000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)

                    # 💡 পিরিয়ড নাম্বার স্ক্র্যাপ করা
                    current_period = "Unknown"
                    try:
                        # "Time remaining" এর নিচে থাকা লম্বা নাম্বারটি খোঁজা (১৭-২০ ডিজিট)
                        body_text = await page.inner_text("body")
                        period_match = re.search(r'\b\d{17,20}\b', body_text)
                        if period_match:
                            current_period = period_match.group(0)
                    except: pass

                    # --- গেম হিস্ট্রি রিড করা ---
                    history = []
                    try:
                        hist_elements = await page.locator('text=/^Big$|^Small$/').all_inner_texts()
                        if hist_elements:
                            history = [h.strip() for h in hist_elements if h.strip() in ['Big', 'Small']]
                            history = history[:5]
                    except: pass

                    # --- প্রেডিকশন লজিক ---
                    choice = "Small"
                    if len(history) >= 5:
                        if history.count('Big') == 5:
                            choice = "Small" 
                        elif history.count('Small') == 5:
                            choice = "Big"
                        elif all(history[i] != history[i+1] for i in range(4)):
                            choice = "Small"
                        else:
                            if last_result == "Win":
                                choice = "Big" if history[0] == "Small" else "Small"
                            elif last_result == "Loss":
                                choice = "Big" if last_choice == "Small" else "Small"
                    else:
                        if last_result == "Win" and history:
                            choice = "Big" if history[0] == "Small" else "Small"
                        elif last_result == "Loss" and last_choice:
                            choice = "Big" if last_choice == "Small" else "Small"

                    # বেট অ্যামাউন্ট বসানো
                    try:
                        input_box = page.locator('input[type="number"], input[type="text"]').last
                        await input_box.fill(str(bet_amount))
                    except: pass

                    # Big বা Small ক্লিক
                    if choice == "Big":
                        await page.locator('text="Big"').last.click(timeout=5000)
                    else:
                        await page.locator('text="Small"').last.click(timeout=5000)
                        
                    await page.wait_for_timeout(1500)

                    # কনফার্ম ক্লিক
                    try:
                        await page.locator('text="Confirm"').last.click(timeout=3000)
                    except: pass

                    # 💡 ড্যাশবোর্ডে পিরিয়ড এবং বাজির তথ্য শো করা
                    bet_msg = (
                        f"🎯 **BET PLACED**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📄 **Period:** `{current_period}`\n"
                        f"🚀 **Prediction:** **{choice}**\n"
                        f"💰 **Amount:** ৳ {bet_amount:.2f}\n"
                        f"⏳ Waiting for result..."
                    )
                    await ctx.bot.send_message(chat_id=uid, text=bet_msg, parse_mode="Markdown")

                    # রেজাল্টের জন্য অপেক্ষা
                    await asyncio.sleep(32)

                    # --- Win/Loss চেক ---
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    new_page_text = await page.inner_text("body")
                    new_balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        if new_balance > current_bal:
                            # WIN
                            state["balance"] = new_balance
                            last_result = "Win"
                            last_choice = choice
                            current_step_idx = 0
                            
                            win_msg = (
                                "╔════════════════════════╗\n"
                                "║  🎉 YOU WIN! ✅       ║\n"
                                "╚════════════════════════╝\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                f"📈 Target  : ৳ {target_balance:.2f}\n"
                                f"🚀 Next Bet: Step 1 (৳ {state['step_amounts'][0]})\n"
                            )
                            await ctx.bot.send_message(chat_id=uid, text=win_msg)
                        else:
                            # LOSS
                            state["balance"] = new_balance
                            last_result = "Loss"
                            last_choice = choice
                            current_step_idx += 1
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_amount = state['step_amounts'][current_step_idx]
                                loss_msg = (
                                    "╔════════════════════════╗\n"
                                    "║  ❌ YOU LOSS!         ║\n"
                                    "╚════════════════════════╝\n"
                                    f"💰 Balance : ৳ {new_balance:.2f}\n"
                                    f"📉 Next Bet: Step {current_step_idx+1} (৳ {next_amount})\n"
                                )
                            else:
                                loss_msg = "❌ YOU LOSS! সব স্টেপ শেষ। বট বন্ধ হচ্ছে।"
                                state["trade_running"] = False
                                
                            await ctx.bot.send_message(chat_id=uid, text=loss_msg)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ Error: {str(e)[:50]}")
                    await asyncio.sleep(5)

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার (আগের মতোই)
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
        
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, None, state["temp_phone"], state["temp_password"]))
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
  