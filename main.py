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
SITE_URL = "https://dkwwin.com"
HOME_URL = "https://dkwwin.com/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True,
            "browser": None, "page": None, "playwright": None
        }
    return user_state[uid]

# ব্রাউজার বন্ধ করার ফাংশন
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
# 💡 ২. API থেকে রেজাল্ট ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(HISTORY_API, headers=headers, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        reversed_list = list(reversed(list_data))
        
        history = []
        for item in reversed_list:
            num = int(item.get("number", 0))
            history.append("SMALL" if num <= 4 else "BIG")
            
        if len(history) < 3: return "BIG", latest_period
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
# ৩. লাইভ ব্রাউজার ওপেন করে লগইন ফর্মে যাওয়া
# ───────────────────────────────────────────
async def start_browser_login(uid, ctx):
    state = get_state(uid)
    await close_browser(uid) 
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await context.new_page()
        
        state["playwright"] = p
        state["browser"] = browser
        state["page"] = page
        
        msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **সাইটে ঢোকা হচ্ছে...**")
        await page.goto(SITE_URL, timeout=60000, wait_until="networkidle")
        await page.wait_for_timeout(5000) 

        # ১. প্রথম স্ক্রিনশটের লাল বাটনে ক্লিক (Dk Win Login)
        try:
            red_btn = page.locator('text="Dk Win Login"').first
            if await red_btn.count() > 0:
                await red_btn.click(force=True, timeout=10000)
                await page.wait_for_timeout(5000) 
        except Exception as e:
            logger.error(f"Red button error: {e}")

        # ২. দ্বিতীয় স্ক্রিনশটের 'I have an account Login' বাটনে ক্লিক
        try:
            acc_btn = page.locator('text="I have an account"').first
            if await acc_btn.count() > 0 and await acc_btn.is_visible():
                await acc_btn.click(force=True, timeout=10000)
                await page.wait_for_timeout(5000) 
        except Exception as e:
            logger.error(f"Account btn error: {e}")

        state["awaiting"] = "phone"
        await ctx.bot.edit_message_text(chat_id=uid, message_id=msg.message_id, text="📱 **আপনার DKWIN ফোন নাম্বার দিন:**")
        
    except Exception as e:
        await ctx.bot.send_message(chat_id=uid, text=f"❌ ব্রাউজার চালু করতে সমস্যা: {e}")
        await close_browser(uid)

# ───────────────────────────────────────────
# ৪. বেটিং লুপ (ব্যাকগ্রাউন্ডে চলবে)
# ───────────────────────────────────────────
async def betting_loop(uid, ctx):
    state = get_state(uid)
    page = state["page"]
    if not page:
        await ctx.bot.send_message(chat_id=uid, text="❌ ব্রাউজার সেশন পাওয়া যায়নি।")
        return

    initial_balance = float(state['balance'])
    target_balance = initial_balance + float(state['target'])
    current_step_idx = 0
    
    await ctx.bot.send_message(chat_id=uid, text="🔄 **WinGo গেম পেজে যাওয়া হচ্ছে...**")
    await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000) 
    
    nav_success = False
    for _ in range(15):
        body_text = await page.evaluate("() => document.body.innerText")
        if "Time remaining" in body_text:
            nav_success = True
            break
        await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='close'||t==='ok') el.click(); } }""")
        await page.wait_for_timeout(500)
        try: await page.get_by_text("WinGo 30sec", exact=True).first.click(timeout=2000, force=True)
        except: pass
        await page.wait_for_timeout(2000)

    if not nav_success:
        await ctx.bot.send_message(chat_id=uid, text="❌ **গেম পেজে ঢুকতে সমস্যা হচ্ছে!**")
        state["trade_running"] = False
        return

    await ctx.bot.send_message(chat_id=uid, text="🚀 **AUTO TRADE ACTIVE**\nবট এখন কাজ শুরু করেছে।")

    while state["trade_running"]:
        try:
            current_bal = state["balance"]
            if current_bal >= target_balance:
                profit = current_bal - initial_balance
                await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳{profit:.2f}")
                state["trade_running"] = False
                break

            if current_step_idx >= len(state['step_amounts']):
                await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** ব্যালেন্স: ৳{current_bal:.2f}।")
                state["trade_running"] = False
                break
                
            bet_amount = float(state['step_amounts'][current_step_idx])
            if current_bal < bet_amount:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **ব্যালেন্স নেই!** প্রয়োজন: ৳{bet_amount}")
                state["trade_running"] = False
                break

            choice, current_period = get_history_and_prediction()
            timer_val = "0s"
            for _ in range(600): 
                try:
                    body_text = await page.evaluate("() => document.body.innerText")
                    if "0 0" in body_text:
                        await asyncio.sleep(0.1)
                        continue
                    match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                    if match:
                        sec = int(match.group(1))
                        if 25 <= sec <= 29: 
                            timer_val = f"{sec}s"
                            break
                except: pass
                await asyncio.sleep(0.1)

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(200)
            
            try:
                await page.evaluate(f"""
                    (() => {{
                        let els = document.querySelectorAll('div, span, button, p');
                        for (let el of els) {{
                            let txt = (el.innerText || el.textContent || '').trim().toUpperCase();
                            if (txt === '{choice.upper()}') {{
                                let rect = el.getBoundingClientRect();
                                if (rect.top > 500) {{ el.click(); return true; }}
                            }}
                        }}
                        return false;
                    }})()
                """)
            except: pass

            await page.wait_for_timeout(1000)
            js_confirm_bet = """
            (() => {
                for(let el of document.querySelectorAll('span, div, label')) {
                    if(el.innerText && el.innerText.includes('I agree')) {
                        let cb = el.parentElement.querySelector('input[type="checkbox"]');
                        if(cb && !cb.checked) cb.click();
                        else el.click();
                    }
                }
                for(let el of document.querySelectorAll('div, button, span')) {
                    if((el.innerText || '').toLowerCase().includes('total amount')) {
                        el.click(); return true;
                    }
                }
                return false;
            })()
            """
            await page.evaluate(js_confirm_bet)

            await page.wait_for_timeout(2000)
            proof_path = f"proof_success_{uid}.png"
            await page.screenshot(path=proof_path)
            await ctx.bot.send_photo(
                chat_id=uid, photo=open(proof_path, 'rb'), 
                caption=f"✅ **BET PLACED!**\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}"
            )
            try: os.remove(proof_path)
            except: pass

            for _ in range(350):
                body_text = await page.evaluate("() => document.body.innerText")
                if "0 0" in body_text: break
                await asyncio.sleep(0.2)

            await page.wait_for_timeout(2000)
            await page.evaluate("window.scrollTo(0, 0);")
            await page.wait_for_timeout(1500) 
            
            new_page_text = await page.evaluate("() => document.body.innerText")
            new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
            if not new_balance_match: new_balance_match = re.search(r'[৳]\s*([\d.]+)', new_page_text)
            
            if new_balance_match:
                new_balance = float(new_balance_match.group(1))
                state['total_trades'] += 1
                
                if new_balance > current_bal:
                    state["balance"] = new_balance
                    state["wins"] += 1
                    current_step_idx = 0
                    p_l = bet_amount * 0.96
                    await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\n💹 P/L: +৳{p_l:.2f}\n💰 Balance: ৳{new_balance:.2f}")
                else:
                    state["balance"] = new_balance
                    state["losses"] += 1
                    current_step_idx += 1
                    await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\n💹 P/L: -৳{bet_amount:.2f}\n💰 Balance: ৳{new_balance:.2f}\n➡️ Next Step: {current_step_idx+1}")

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(1500)

        except Exception as e:
            logger.error(f"Betting error: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nএরর: {str(e)[:50]}")
            state["trade_running"] = False
            break

# ───────────────────────────────────────────
# ৫. টেলিগ্রাম হ্যান্ডলার
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
    page = state.get("page")
    
    # ১. ফোন নাম্বার নেওয়া
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        if page:
            try:
                await ctx.bot.send_message(chat_id=uid, text="🔄 **নাম্বার বসানো হচ্ছে...**")
                # ফোন নাম্বার বসানো
                phone_input = page.locator('input[type="tel"], input[type="text"]').first
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.fill(text)
                await page.wait_for_timeout(1000)
            except Exception as e:
                await update.message.reply_text(f"⚠️ নাম্বার বসাতে সমস্যা: {e}")
                return
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 **এখন আপনার পাসওয়ার্ড দিন:**")
        return

    # ২. পাসওয়ার্ড নেওয়া
    if state.get("awaiting") == "password":
        state["temp_password"] = text
        try: await update.message.delete()
        except: pass
        
        if page:
            try:
                await ctx.bot.send_message(chat_id=uid, text="🔄 **পাসওয়ার্ড বসিয়ে লগইন করা হচ্ছে...**")
                # পাসওয়ার্ড বসানো
                pass_input = page.locator('input[type="password"]').first
                await pass_input.wait_for(state="visible", timeout=10000)
                await pass_input.fill(text)
                await page.wait_for_timeout(1000)
                
                # লগইন বাটনে ক্লিক
                try:
                    await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000, force=True)
                except:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, a')) { if((el.innerText||'').toLowerCase()==='log in') el.click(); } }")
                
                await page.wait_for_timeout(8000)
                
                # পপআপ ক্লোজ
                for _ in range(10):
                    await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { let t=(el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }")
                    await page.wait_for_timeout(500)
                
                # Account পেজে যাওয়া
                await ctx.bot.send_message(chat_id=uid, text="🔄 **একাউন্ট পেজে যাওয়া হচ্ছে...**")
                try:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
                    await page.wait_for_timeout(6000)
                except: pass
                
                # UID এবং Balance বের করা
                page_text = await page.inner_text("body")
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                if not balance_match: balance_match = re.search(r'৳\s*([\d.]+)', page_text)
                
                uid_val = uid_match.group(1) if uid_match else "Unknown"
                balance = balance_match.group(1) if balance_match else "0.00"
                
                if uid_val != "Unknown":
                    state["balance"] = float(balance)
                    
                    # স্ক্রিনশট নেওয়া
                    ss_path = f"dash_{uid}.png"
                    await page.screenshot(path=ss_path)
                    await ctx.bot.send_photo(
                        chat_id=uid, photo=open(ss_path, 'rb'), 
                        caption=f"✅ **LOGIN SUCCESSFUL**\n\n👤 UID: `{uid_val}`\n💰 Balance: ৳ {balance}\n\n👇 আপনার পরবর্তী নির্দেশনার জন্য অপেক্ষা করছি।"
                    )
                    try: os.remove(ss_path)
                    except: pass
                    
                    reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
                    await ctx.bot.send_message(chat_id=uid, text="👇 Press START YOUR TARGET to begin", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
                else:
                    ss_path = f"fail_{uid}.png"
                    await page.screenshot(path=ss_path)
                    await ctx.bot.send_photo(
                        chat_id=uid, photo=open(ss_path, 'rb'),
                        caption="❌ **LOGIN FAILED**\n\nUID খুঁজে পাওয়া যায়নি। স্ক্রিনশটে দেখুন সাইটে কী লেখা আছে।"
                    )
                    try: os.remove(ss_path)
                    except: pass
                    
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text=f"⚠️ লগইন প্রসেসে সমস্যা: {e}")
        
        state["awaiting"] = None
        return

    # ৩. টার্গেট সেট করা
    if text == "🚀 START YOUR TARGET":
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
        await query.edit_message_text("🔄 **ব্রাউজার ওপেন হচ্ছে এবং সাইটে ঢোকা হচ্ছে...**")
        await start_browser_login(uid, ctx)
        
    elif data == "start_trade_btn":
        state["trade_running"] = True
        await query.edit_message_text("🚀 **TRADE STARTING...**")
        asyncio.create_task(betting_loop(uid, ctx))
        
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
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