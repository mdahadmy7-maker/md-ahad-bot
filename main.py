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
# 📸 ৩. ডেবাগ স্ক্রিনশট পাঠানোর হেল্পার (ব্ল্যাক স্ক্রিন ফিক্স)
# ───────────────────────────────────────────
async def send_step_screenshot(ctx, uid, page, step_name, status_text):
    path = f"step_{step_name}_{uid}.png"
    try:
        # কালো স্ক্রিন ফিক্স: স্ক্রল করে পেজ ফোর্স রেন্ডার করা এবং মাউস মুভ করা
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, 0);")
        await asyncio.sleep(1.5) 
        await page.mouse.move(200, 400)

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
        # 💡 এখানে headless=False দেওয়া হলো। এটি আপনার পিসিতে ব্রাউজার ওপেন করবে।
        # যদি আপনার পিসিতে গুগল ক্রোম ইনস্টল থাকে, তবে ব্রাউজারটি আরও ভালো কাজ করবে।
        browser = await p.chromium.launch(
            headless=False, # ব্রাউজার সরাসরি ওপেন হবে
            slow_mo=500,    # প্রতিটি কাজে আধা সেকেন্ড বিরতি দেবে
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
                "--start-maximized" # ব্রাউজার ফুল স্ক্রিনে ওপেন হবে
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
            await page.goto(SITE_URL, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5) 
            await send_step_screenshot(ctx, uid, page, "ধাপ ১: সাইটে প্রবেশ", "সাইট ওপেন হয়েছে।")

            # ---------------- ধাপ ২: লাল বাটনে ক্লিক ----------------
            await update_loading(25, "CLICKING RED BUTTON")
            red_clicked = False
            try:
                red_btn = page.locator('text="Dk Win Login"').first
                if await red_btn.count() > 0:
                    await red_btn.click(force=True, timeout=5000)
                    red_clicked = True
                else:
                    red_clicked = await page.evaluate("""
                        (() => {
                            let els = document.querySelectorAll('button, a, div, span');
                            for (let el of els) {
                                let text = (el.innerText || el.textContent || '').toLowerCase();
                                if (text.includes('dk win login') || text.includes('quick sign-in')) {
                                    el.click(); return true;
                                }
                            }
                            return false;
                        })()
                    """)
                await asyncio.sleep(7) 
            except Exception as e:
                logger.warning(f"Red button error: {e}")
            
            await send_step_screenshot(ctx, uid, page, "ধাপ ২: লাল বাটনে ক্লিক", f"বাটন ক্লিক: {'সফল' if red_clicked else 'ব্যর্থ'}")

            # ---------------- ধাপ ৩: I have an account Login ----------------
            await update_loading(40, "OPENING LOGIN FORM")
            acc_clicked = False
            try:
                acc_btn = page.locator('text="I have an account"').first
                if await acc_btn.count() > 0 and await acc_btn.is_visible():
                    await acc_btn.click(force=True, timeout=5000)
                    acc_clicked = True
                else:
                    acc_clicked = await page.evaluate("""
                        (() => {
                            let els = document.querySelectorAll('button, a, div, span');
                            for (let el of els) {
                                let text = (el.innerText || el.textContent || '').toLowerCase();
                                if (text.includes('i have an account') || text === 'login') {
                                    el.click(); return true;
                                }
                            }
                            return false;
                        })()
                    """)
                
                if not acc_clicked:
                    await page.mouse.click(200, 750)
                    acc_clicked = True

                await asyncio.sleep(7) 
            except Exception as e:
                logger.warning(f"Acc button error: {e}")
            
            await send_step_screenshot(ctx, uid, page, "ধাপ ৩: 'I have an account' ক্লিক", f"লগইন ফর্মে যাওয়া: {'সফল' if acc_clicked else 'ব্যর্থ'}")

            # ---------------- ধাপ ৪: ফোন এবং পাসওয়ার্ড বসানো ----------------
            await update_loading(55, "ENTERING CREDENTIALS")
            try:
                phone_input = page.locator('input[placeholder*="phone" i]').first
                if await phone_input.count() == 0:
                    phone_input = page.locator('input[type="tel"]').first
                
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(login_phone, delay=150)
                await asyncio.sleep(1)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.type(password, delay=150)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Input error: {e}")
            
            await send_step_screenshot(ctx, uid, page, "ধাপ ৪: নাম্বার ও পাসওয়ার্ড", "ইনপুট বসানো হয়েছে।")

            # ---------------- ধাপ ৫: Log in বাটনে ক্লিক ----------------
            await update_loading(70, "LOGGING IN")
            try:
                login_btn = page.locator('button:has-text("Log in")').last
                if await login_btn.count() == 0:
                    login_btn = page.locator('text="Log in"').last
                
                if await login_btn.count() > 0 and await login_btn.is_visible():
                    await login_btn.click(force=True, timeout=5000)
                else:
                    await page.evaluate("""
                        (() => {
                            for(let el of document.querySelectorAll('button, div, span')) {
                                if((el.innerText||'').trim().toLowerCase() === 'log in') {
                                    el.click(); return;
                                }
                            }
                        })()
                    """)
            except Exception as e:
                logger.error(f"Login btn error: {e}")
            
            await asyncio.sleep(6)

            # পপআপ ক্লোজ
            for _ in range(5):
                await page.evaluate("""
                    (() => {
                        for(let el of document.querySelectorAll('button, div, span')) {
                            let t=(el.innerText||'').toLowerCase();
                            if(t==='confirm'||t==='ok'||t==='close') el.click();
                        }
                    })()
                """)
                await asyncio.sleep(1)

            await send_step_screenshot(ctx, uid, page, "ধাপ ৫: লগইন ক্লিকের পর", "লগইন প্রসেস শেষ পর্যায়ে।")

            # ---------------- ধাপ ৬: Account পেজে ক্লিক ----------------
            await update_loading(85, "FETCHING ACCOUNT DETAILS")
            try:
                account_tab = page.get_by_text("Account", exact=True).last
                if await account_tab.count() > 0 and await account_tab.is_visible():
                    await account_tab.click(force=True, timeout=5000)
                await asyncio.sleep(4) 
            except: pass

            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            # ---------------- ধাপ ৭: UID এবং Balance বের করা ----------------
            for _ in range(10): 
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
            await asyncio.sleep(5) 
            
            nav_success = False
            for attempt in range(15):
                body_text = await page.evaluate("() => document.body.innerText")
                if "Time remaining" in body_text:
                    nav_success = True
                    break
                
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }")
                await asyncio.sleep(1)
                
                try:
                    await page.get_by_text("WinGo 30sec", exact=True).first.click(timeout=3000, force=True)
                except:
                    try:
                        await page.get_by_text("Win Go", exact=False).first.click(timeout=3000, force=True)
                    except: pass
                await asyncio.sleep(3)

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
                    await asyncio.sleep(0.5)
                    
                    clicked = False
                    try:
                        locator = page.locator(f'text="{choice.capitalize()}"').last
                        if await locator.count() > 0 and await locator.is_visible():
                            await locator.click(force=True, timeout=2000)
                            clicked = True
                    except: pass
                        
                    if not clicked:
                        try:
                            clicked = await page.evaluate(f"""
                                (() => {{
                                    let els = document.querySelectorAll('div, span, button, p');
                                    for (let el of els) {{
                                        let txt = (el.innerText || el.textContent || '').trim().toUpperCase();
                                        if (txt === '{choice.upper()}') {{
                                            let rect = el.getBoundingClientRect();
                                            if (rect.width > 0 && rect.height > 0 && rect.top > 500) {{
                                                el.click();
                                                return true;
                                            }}
                                        }}
                                    }}
                                    return false;
                                }})()
                            """)
                        except: pass
                            
                    if not clicked:
                        try:
                            if choice.upper() == "BIG":
                                await page.mouse.click(103, 890)
                            else:
                                await page.mouse.click(309, 890)
                        except: pass

                    await asyncio.sleep(1.5)

                    js_confirm_bet = """
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
                        return false;
                    })()
                    """
                    bet_result = await page.evaluate(js_confirm_bet)
                    
                    if not bet_result:
                        try:
                            agree_box = page.locator('text="I agree"').last
                            if await agree_box.count() > 0 and await agree_box.is_visible():
                                await agree_box.click(force=True, timeout=1000)
                            confirm_btn = page.locator('text=/Total amount/i').last
                            if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                                await confirm_btn.click(timeout=2000, force=True)
                        except: pass

                    await asyncio.sleep(2.5)
                    proof_path = f"proof_success_{uid}.png"
                    
                    await page.evaluate("window.scrollTo(0, 0);")
                    await asyncio.sleep(1.5)
                    await page.screenshot(path=proof_path, full_page=False)
                    
                    await ctx.bot.send_photo(
                        chat_id=uid, 
                        photo=open(proof_path, 'rb'), 
                        caption=f"✅ **BET PLACED SUCCESSFULLY!**\n\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}"
                    )
                    
                    try: os.remove(proof_path)
                    except: pass

                    await ctx.bot.send_message(chat_id=uid, text=(
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤖 NEW TRADE PLACED\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱️ Period    : {current_period}\n"
                        f"⏱️ Timer     : {timer_val} remaining\n"
                        f"🔵 PREDICTION : **{choice}**\n"
                        f"🚀 Step       : 🟢 Normal — Step {current_step_idx+1}\n"
                        f"💵 Amount     : ৳ {bet_amount:.2f}\n"
                        f"💰 Balance    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ Waiting for result..."
                    ), parse_mode="Markdown")

                    for _ in range(350):
                        body_text = await page.evaluate("() => document.body.innerText")
                        if "0 0" in body_text:
                            break
                        await asyncio.sleep(0.2)

                    await asyncio.sleep(2)

                    await page.evaluate("window.scrollTo(0, 0);")
                    await asyncio.sleep(1.5) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    if not new_balance_match:
                        new_balance_match = re.search(r'[৳]\s*([\d.]+)', new_page_text)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            p_l = bet_amount * 0.96
                            win_rate = (state['wins'] / state['total_trades'] * 100)
                            
                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "🟢 TRADE RESULT (WIN)\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx+1}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                f"💹 P/L : +৳ {p_l:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate : {win_rate:.1f}%\n"
                                "➡️ Next Step : 1\n"
                            ))
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            
                            win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                            else:
                                next_step_txt = "🛑 No more steps left."

                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "🔴 TRADE RESULT (LOSS)\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                f"💹 P/L : -৳ {bet_amount:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate : {win_rate:.1f}%\n"
                                f"{next_step_txt}"
                            ))

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1.5)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nCould not place bet. Error: {str(e)[:50]}")
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
                f"💰 Balance  : ৳ {balance:.2