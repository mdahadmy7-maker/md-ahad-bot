import asyncio
import logging
import re
import os
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwwin.com/#/login"
HOME_URL = "https://dkwwin.com/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": 0.0, "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. API থেকে রেজাল্ট ও প্রেডিকশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(HISTORY_API, headers=headers, timeout=10)
        data = res.json()
        
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        reversed_list = list(reversed(list_data))
        
        history = []
        for item in reversed_list:
            num = int(item.get("number", 0))
            history.append("SMALL" if num <= 4 else "BIG")
            
        if len(history) < 3:
            return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
            
        if n >= 4:
            l4 = history[n-4]
            if l4 == l3 and l2 == l1 and l4 != l3: return l4, latest_period
            if l4 == l2 and l3 == l1 and l4 != l3: return l4, latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
    except Exception as e:
        logger.error(f"History API error: {e}")
        return "BIG", datetime.now().strftime("%Y%m%d%H%M%S")

# ───────────────────────────────────────────
# 📸 ৩. ডেবাগ স্ক্রিনশট পাঠানোর হেল্পার
# ───────────────────────────────────────────
async def send_step_screenshot(ctx, uid, page, step_name, status_text):
    path = f"step_{step_name}_{uid}.png"
    try:
        await page.add_style_tag(content="* { animation: none !important; transition: none !important; }")
        await page.screenshot(path=path, full_page=False)
        await ctx.bot.send_photo(
            chat_id=uid, 
            photo=open(path, 'rb'), 
            caption=f"📸 **{step_name}**\n{status_text}"
        )
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
    finally:
        try: os.remove(path)
        except: pass

# ───────────────────────────────────────────
# ৪. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text_status="CONNECTING TO SITE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text_status}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
                "--window-size=400,800"
            ]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800},
            device_scale_factor=1,
            is_mobile=True, has_touch=True
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()
        
        try:
            # ---------------- ধাপ ১: সাইটে প্রবেশ ----------------
            await update_loading(10, "OPENING WEBSITE")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await send_step_screenshot(ctx, uid, page, "ধাপ ১: সাইটে প্রবেশ", "সাইট ওপেন হয়েছে।")

            # ---------------- ধাপ ২: লাল বাটনে ক্লিক ----------------
            await update_loading(25, "CLICKING RED BUTTON")
            
            # আপনার স্ক্রিনশটে লাল বাটনটি স্ক্রিনের ঠিক এই জায়গায় (X: 200, Y: 680) আছে
            await page.mouse.click(200, 680)
            
            await asyncio.sleep(4) 
            await send_step_screenshot(ctx, uid, page, "ধাপ ২: লাল বাটনে ক্লিক", "লাল বাটনে ক্লিক করা হয়েছে।")

            # ---------------- ধাপ ৩: I have an account Login ----------------
            await update_loading(40, "OPENING LOGIN FORM")
            
            # 'I have an account Login' একদম নিচে থাকে (X: 200, Y: 750)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(1)
            await page.mouse.click(200, 750) 
            
            await asyncio.sleep(4) 
            await send_step_screenshot(ctx, uid, page, "ধাপ ৩: 'I have an account' ক্লিক", "লগইন ফর্মে যাওয়া হয়েছে।")

            # ---------------- ধাপ ৪: ফোন এবং পাসওয়ার্ড বসানো ----------------
            await update_loading(55, "ENTERING CREDENTIALS")
            try:
                phone_input = page.locator('input[type="tel"], input[placeholder*="phone" i]').first
                await phone_input.wait_for(state="visible", timeout=5000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(login_phone, delay=100)
                await asyncio.sleep(1)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.type(password, delay=100)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Input error: {e}")
            await send_step_screenshot(ctx, uid, page, "ধাপ ৪: নাম্বার ও পাসওয়ার্ড", "ইনপুট বসানো হয়েছে।")

            # ---------------- ধাপ ৫: Log in বাটনে ক্লিক ----------------
            await update_loading(70, "LOGGING IN")
            
            # লগইন বাটন (X: 200, Y: 650)
            await page.mouse.click(200, 650)
            
            await asyncio.sleep(5)
            await send_step_screenshot(ctx, uid, page, "ধাপ ৫: লগইন ক্লিকের পর", "লগইন প্রসেস শেষ পর্যায়ে।")

            # ---------------- ধাপ ৬: Account পেজে ক্লিক ----------------
            await update_loading(85, "FETCHING ACCOUNT DETAILS")
            try:
                # Account ট্যাব সাধারণত নিচের ডানদিকে থাকে (X: 350, Y: 750)
                await page.mouse.click(350, 750)
                await asyncio.sleep(3) 
            except: pass

            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            # ---------------- ধাপ ৭: UID এবং Balance বের করা ----------------
            for _ in range(5): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text or "incorrect" in page_text.lower():
                    login_status = "failed"
                    break
                
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: 
                        balance = balance_match.group(1)
                    login_status = "success"
                    break
                await asyncio.sleep(1)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            # ---------------- ধাপ ৮: রেজাল্ট পাঠানো ----------------
            if login_status == "failed" or uid_val == "Unknown":
                await send_step_screenshot(ctx, uid, page, "লগইন ব্যর্থ", "পাসওয়ার্ড ভুল অথবা সাইট বটকে ডিটেক্ট করেছে।")
                await browser.close()
                return

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
                "👇 Press START YOUR TARGET to begin"
            )
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown")

            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), [KeyboardButton("🚪 LOGOUT")]]]
            await ctx.bot.send_message(chat_id=uid, text="👇 Press START YOUR TARGET to begin", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৯. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4) 
            
            nav_success = False
            for attempt in range(5):
                body_text = await page.evaluate("() => document.body.innerText")
                if "Time remaining" in body_text:
                    nav_success = True
                    break
                await page.mouse.click(200, 400)
                await asyncio.sleep(2)

            if not nav_success:
                await ctx.bot.send_message(chat_id=uid, text="❌ **গেম পেজে ঢুকতে সমস্যা হচ্ছে!** বট বন্ধ করা হচ্ছে।")
                state["trade_running"] = False
                await browser.close()
                return

            step_plan_str = "┌────────────────────────────────┐\n"
            for i, amt in enumerate(state['step_amounts']):
                step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
            step_plan_str += "└────────────────────────────────┘"

            await ctx.bot.send_message(chat_id=uid, text=(
                "╔════════════════════════════════╗\n"
                "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                "╚════════════════════════════════╝\n\n"
                f"💰 **Balance** : ৳ {state['balance']:.2f}\n"
                f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                f"🏛️ **Stop At** : ৳ {target_balance:.2f}\n"
                f"📋 **Steps**   : {state['steps']}\n\n"
                "📊 **Step Plan:**\n"
                f"{step_plan_str}\n\n"
                "🧠 _Analysing market..._\n"
                "🎬 _Bot is monitoring the timer._"
            ), parse_mode="Markdown")

            # ---------------- ১০. মেইন বেটিং লুপ ----------------
            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        profit = current_bal - initial_balance
                        win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                        target_summary = (
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🎯 **TARGET REACHED** 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💰 **Start Balance** : ৳ {initial_balance:.2f}\n"
                            f"💵 **Final Balance** : ৳ {current_bal:.2f}\n"
                            f"💸 **Profit Made**   : +৳ {profit:.2f}\n\n"
                            f"📊 **Trades** : {state['total_trades']} 🟢 **Win** : {state['wins']} 🔴 **Loss** : {state['losses']}\n"
                            f"🏆 **Win Rate** : {win_rate:.1f}%\n"
                        )
                        await ctx.bot.send_message(chat_id=uid, text=target_summary, parse_mode="Markdown")
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

                    choice, current_period = get_history_and_prediction()

                    timer_val = "0s"
                    for _ in range(300): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if match:
                                sec = int(match.group(1))
                                if 25 <= sec <= 29: 
                                    timer_val = f"{sec}s"
                                    break
                        except: pass
                        await asyncio.sleep(0.1)

                    if choice.upper() == "BIG":
                        await page.mouse.click(100, 700)
                    else:
                        await page.mouse.click(300, 700)

                    await asyncio.sleep(1)

                    await page.evaluate("""
                        (() => {
                            for(let el of document.querySelectorAll('span, div, label')) {
                                if(el.innerText && el.innerText.includes('I agree')) {
                                    let cb = el.parentElement.querySelector('input[type="checkbox"]');
                                    if(cb && !cb.checked) cb.click();
                                    else el.click();
                                }
                            }
                            let btns = document.querySelectorAll('div, button, span');
                            for(let el of btns) {
                                let txt = (el.innerText || '').toLowerCase();
                                if(txt.includes('total amount')) {
                                    el.click();
                                    return true;
                                }
                            }
                        })()
                    """)
                    
                    await asyncio.sleep(2)
                    proof_path = f"proof_success_{uid}.png"
                    await page.screenshot(path=proof_path, full_page=False)
                    
                    await ctx.bot.send_photo(
                        chat_id=uid, 
                        photo=open(proof_path, 'rb'), 
                        caption=f"✅ **BET PLACED!**\n\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}"
                    )
                    try: os.remove(proof_path)
                    except: pass

                    await asyncio.sleep(30) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!** Balance: ৳ {new_balance:.2f}")
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!** Next Step: {current_step_idx+1}")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# হ্যান্ডলারগুলো
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
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
        await update.message.reply_text(f"☎️ Number : {text}\n\n🔑 Now enter your password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        
        loading_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **CONNECTING TO SITE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 START YOUR TARGET 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 YOUR BALANCE: ৳ {state.get('balance', '0.00')}\n"
            "🎯 Enter your TARGET profit amount (in ৳):"
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
                f"💰 Balance  : ৳ {balance:.2f}\n"
                f"🎯 Target   : ৳ {target_amount:.2f} profit\n"
                f"🏦 Stop At  : ৳ {stop_at:.2f}\n\n"
                "🚀 Enter your STEP COUNT:\n(How many steps? e.g. 5, max 50)"
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
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                balance = float(state.get('balance', '0.00'))
                target = float(state.get('target', 0))
                stop_at = balance + target
                step_plan_text = ""
                for i, amt in enumerate(state["step_amounts"]):
                    step_plan_text += f"Step {i+1:02d} : ৳ {amt:.2f}\n"
                
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
                    "👇 Press START TRADE to begin."
                )
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 1)।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
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
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your DKWIN phone number:")
    elif data == "start_trade_btn":
        state["trade_running"] = True
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()