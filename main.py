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
# ৩. স্ক্রিনশট পাঠানোর হেল্পার
# ───────────────────────────────────────────
async def send_debug_screenshot(ctx, uid, page, caption, tag):
    """প্রতিটি ধাপে স্ক্রিনশট পাঠায় — বট কোথায় আটকেছে বুঝতে"""
    path = f"debug_{tag}_{uid}.png"
    try:
        await page.screenshot(path=path, full_page=False)
        await ctx.bot.send_photo(
            chat_id=uid,
            photo=open(path, 'rb'),
            caption=f"📸 **DEBUG — {tag}**\n{caption}"
        )
    except Exception as e:
        logger.error(f"Screenshot error ({tag}): {e}")
    finally:
        try: os.remove(path)
        except: pass


# ───────────────────────────────────────────
# ৪. লগইন + অটো-বেট (প্রতিটি ধাপে স্ক্রিনশট)
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
                text=f"🔄 **{text_status}**\n[{filled}{empty}] {percent}%",
                parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--window-size=400,800"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800},
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        try:
            # ---------------- ধাপ ১: সাইটে প্রবেশ ----------------
            await update_loading(10, "OPENING WEBSITE")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await send_debug_screenshot(ctx, uid, page, "সাইট খোলার পর এই অবস্থা", "step1_open")

            # ---------------- ধাপ ২: লাল বাটন ----------------
            await update_loading(25, "NAVIGATING TO LOGIN")
            try:
                red_btn = page.locator('text="Dk Win Login"').first
                if await red_btn.count() > 0 and await red_btn.is_visible():
                    await red_btn.click(force=True, timeout=10000)
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Red button skip: {e}")
            await send_debug_screenshot(ctx, uid, page, "Dk Win Login বাটনে ক্লিকের পর", "step2_red")

            # ---------------- ধাপ ৩: I have an account ----------------
            await update_loading(40, "OPENING LOGIN FORM")
            try:
                acc_btn = page.locator('text="I have an account"').first
                if await acc_btn.count() > 0 and await acc_btn.is_visible():
                    await acc_btn.click(force=True, timeout=10000)
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Account btn skip: {e}")
            await send_debug_screenshot(ctx, uid, page, "Login form খোলার পর", "step3_form")

            # ---------------- ধাপ ৪: ফোন ও পাসওয়ার্ড ----------------
            await update_loading(55, "ENTERING CREDENTIALS")
            phone_ok = False
            pass_ok = False
            try:
                # প্লেসহোল্ডার/টাইপ দিয়ে নির্ভরযোগ্য সিলেক্টর
                phone_input = page.locator(
                    'input[placeholder*="phone" i], input[placeholder*="number" i], '
                    'input[placeholder*="mobile" i], input[type="tel"]'
                ).first
                if await phone_input.count() == 0:
                    phone_input = page.locator('input[type="text"]').first
                await phone_input.wait_for(state="visible", timeout=15000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(login_phone, delay=random.randint(80, 150))
                await asyncio.sleep(0.5)
                phone_ok = True
            except Exception as e:
                logger.error(f"Phone input error: {e}")

            try:
                pass_input = page.locator('input[type="password"]').first
                await pass_input.wait_for(state="visible", timeout=10000)
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.type(password, delay=random.randint(80, 150))
                await asyncio.sleep(0.5)
                pass_ok = True
            except Exception as e:
                logger.error(f"Password input error: {e}")

            await send_debug_screenshot(
                ctx, uid, page,
                f"ফোন বসানো: {'✅' if phone_ok else '❌'} | পাসওয়ার্ড বসানো: {'✅' if pass_ok else '❌'}",
                "step4_credentials"
            )

            # ---------------- ধাপ ৫: Log in বাটন ----------------
            await update_loading(70, "LOGGING IN")
            clicked_login = False
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000, force=True)
                clicked_login = True
            except:
                try:
                    clicked_login = await page.evaluate("""
                        (() => {
                            for(let el of document.querySelectorAll('button, div, span, a')) {
                                let t = (el.innerText||'').trim().toLowerCase();
                                if(t === 'log in' || t === 'login') { el.click(); return true; }
                            }
                            return false;
                        })()
                    """)
                except: pass
            logger.info(f"Login button clicked: {clicked_login}")

            await asyncio.sleep(5)

            # পপআপ ক্লোজ
            for _ in range(10):
                await page.evaluate("""
                    (() => {
                        for(let el of document.querySelectorAll('button, div, span')) {
                            let t = (el.innerText||'').toLowerCase();
                            if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click();
                        }
                    })()
                """)
                await asyncio.sleep(0.5)

            await send_debug_screenshot(ctx, uid, page, "Login ক্লিকের পর (পপআপ ক্লোজ সহ)", "step5_after_login")

            # ---------------- ধাপ ৬: Account পেজ ----------------
            await update_loading(85, "FETCHING ACCOUNT DETAILS")
            try:
                account_tab = page.get_by_text("Account", exact=True).last
                if await account_tab.count() > 0 and await account_tab.is_visible():
                    await account_tab.click(force=True, timeout=10000)
                else:
                    await page.evaluate("""
                        (() => {
                            for(let el of document.querySelectorAll('div, span, a, p')) {
                                if((el.innerText||'').trim().toLowerCase()==='account') el.click();
                            }
                        })()
                    """)
                await asyncio.sleep(4)
            except Exception as e:
                logger.warning(f"Account tab: {e}")

            await send_debug_screenshot(ctx, uid, page, "Account পেজে ঢোকার পর", "step6_account")

            # ---------------- ধাপ ৭: UID ও Balance ----------------
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(15):
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
                await asyncio.sleep(0.5)

            logger.info(f"Login status: {login_status}, UID: {uid_val}, Balance: {balance}")

            # ফাইনাল স্ক্রিনশট (ব্ল্যাক স্ক্রিন ফিক্স)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollTo(0, 0);")
            await asyncio.sleep(2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            ss_path = f"dash_{uid}.png"
            await page.screenshot(path=ss_path, full_page=False)

            # ---------------- ধাপ ৮: রেজাল্ট ----------------
            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_photo(
                    chat_id=uid,
                    photo=open(ss_path, 'rb'),
                    caption=f"❌ **LOGIN FAILED** ({phone})\n\nসম্ভবত পাসওয়ার্ড ভুল অথবা সাইট বটকে ডিটেক্ট করেছে। স্ক্রিনশটে দেখুন সাইটে কী লেখা আছে।"
                )
                await browser.close()
                try: os.remove(ss_path)
                except: pass
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
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )

            await ctx.bot.send_photo(
                chat_id=uid,
                photo=open(ss_path, 'rb'),
                caption=dashboard_msg,
                parse_mode="Markdown"
            )
            try: os.remove(ss_path)
            except: pass

            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(
                chat_id=uid,
                text="👇 Press START YOUR TARGET to begin",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )

            # ট্রেড স্টার্টের অপেক্ষা
            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ধাপ ৯: অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            nav_success = False
            for attempt in range(15):
                body_text = await page.evaluate("() => document.body.innerText")
                if "Time remaining" in body_text or re.search(r'0\s*0\s*:\s*\d{2}', body_text):
                    nav_success = True
                    break

                await page.evaluate("""
                    (() => {
                        for(let el of document.querySelectorAll('button, div, span, a')) {
                            let t = (el.innerText||'').toLowerCase();
                            if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click();
                        }
                    })()
                """)
                await asyncio.sleep(0.5)

                try:
                    await page.get_by_text("WinGo 30sec", exact=True).first.click(timeout=2000, force=True)
                except:
                    try:
                        await page.get_by_text("Win Go", exact=False).first.click(timeout=2000, force=True)
                    except: pass
                await asyncio.sleep(2)

            await send_debug_screenshot(ctx, uid, page, f"গেম পেজে ঢোকার পর (nav_success={nav_success})", "step9_game")

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

            # ---------------- ধাপ ১০: মেইন বেটিং লুপ ----------------
            while state["trade_running"]:
                try:
                    current_bal = float(state["balance"])

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

                    # টাইমার অপেক্ষা (25-29 সেকেন্ডের মধ্যে বেট)
                    timer_val = "0s"
                    for _ in range(600):
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if not match:
                                match = re.search(r'\b(\d{2})\s*s\b', body_text)
                            if match:
                                sec = int(match.group(1))
                                timer_val = f"{sec}s"
                                if 25 <= sec <= 29:
                                    break
                        except: pass
                        await asyncio.sleep(0.2)

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(0.3)

                    # BIG/SMALL ক্লিক — তিন স্তরের ব্যাকআপ
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
                                            if (rect.width > 0 && rect.height > 0 && rect.top > 400) {{
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
                        # bounding_box দিয়ে নির্ভুল ক্লিক
                        try:
                            target = page.locator(f'text="{choice.capitalize()}"').last
                            box = await target.bounding_box()
                            if box:
                                await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                clicked = True
                        except: pass

                    if not clicked:
                        # শেষ ব্যাকআপ: হার্ডকোড কোঅর্ডিনেট
                        try:
                            if choice.upper() == "BIG":
                                await page.mouse.click(103, 890)
                            else:
                                await page.mouse.click(309, 890)
                            clicked = True
                        except: pass

                    logger.info(f"BIG/SMALL clicked: {clicked} (choice={choice}, timer={timer_val})")

                    await asyncio.sleep(1)

                    # বেট নিশ্চিতকরণ
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

                    await asyncio.sleep(2)

                    # বেট প্লেসের প্রুফ স্ক্রিনশট
                    proof_path = f"proof_success_{uid}.png"
                    await page.evaluate("window.scrollTo(0, 0);")
                    await asyncio.sleep(1)
                    await page.screenshot(path=proof_path, full_page=False)

                    await ctx.bot.send_photo(
                        chat_id=uid,
                        photo=open(proof_path, 'rb'),
                        caption=f"✅ **BET PLACED**\n\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}\n⏱️ Timer: {timer_val}"
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
                        f"🚀 Step       : Step {current_step_idx+1}\n"
                        f"💵 Amount     : ৳ {bet_amount:.2f}\n"
                        f"💰 Balance    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ Waiting for result..."
                    ), parse_mode="Markdown")

                    # রেজাল্টের অপেক্ষা
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
                                f"🔵 Side : {choice}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n"
                                f"💹 P/L : +৳ {p_l:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate : {win_rate:.1f}%\n"
                                "➡️ Next Step : 1"
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
                                f"🔵 Side : {choice}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n"
                                f"💹 P/L : -৳ {bet_amount:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate : {win_rate:.1f}%\n"
                                f"{next_step_txt}"
                            ))

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1.5)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    # বেট লুপে এরর হলে স্ক্রিনশট পাঠান
                    await send_debug_screenshot(ctx, uid, page, f"বেট লুপে এরর: {str(e)[:100]}", "error_betloop")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: `{str(e)[:100]}`", parse_mode="Markdown")
                    state["trade_running"] = False
                    break

        except Exception as e:
            logger.error(f"Main error: {e}")
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            # মেইন এররেও স্ক্রিনশট পাঠান
            try:
                await send_debug_screenshot(ctx, uid, page, f"মেইন এরর: {str(e)[:100]}", "error_main")
            except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()


# ───────────────────────────────────────────
# হ্যান্ডলার
# ───────────────────────────────────────────
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
        f"👥 Accounts: {len(state['accounts'])}/6\n"
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
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
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
        state["first_bet"] = True

        # ctx.bot.send_message ব্যবহার (মেসেজ ডিলিটের পর নিরাপদ)
        loading_msg = await ctx.bot.send_message(
            chat_id=uid,
            text="🔄 **CONNECTING TO SITE**\n[░░░░░░░░░░] 0%",
            parse_mode="Markdown"
        )
        state["task"] = asyncio.create_task(
            playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"])
        )
        return

    if text == "🚀 START YOUR TARGET":