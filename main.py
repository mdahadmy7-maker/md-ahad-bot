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
# 📸 ৩. ডেবাগ স্ক্রিনশট পাঠানোর হেল্পার
# ───────────────────────────────────────────
async def send_step_screenshot(ctx, uid, page, step_name, status_text):
    path = f"step_{step_name}_{uid}.png"
    try:
        # কালো স্ক্রিন ফিক্স
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 0);")
        await asyncio.sleep(1.5) 

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
            await page.goto(SITE_URL, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5) 
            await send_step_screenshot(ctx, uid, page, "ধাপ ১: সাইটে প্রবেশ", "সাইট ওপেন হয়েছে।")

            # ---------------- ধাপ ২: লাল বাটনে ক্লিক ----------------
            await update_loading(25, "CLICKING RED BUTTON")
            red_clicked = False
            
            try:
                # ১. লাল বাটন খোঁজা (Dk Win Login)
                red_btn = page.locator('text="Dk Win Login"').first
                if await red_btn.count() > 0:
                    await red_btn.click(force=True, timeout=5000)
                    red_clicked = True
                else:
                    # ২. জাভাস্ক্রিপ্ট দিয়ে জোর করে ক্লিক
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
                await asyncio.sleep(4) 
            except Exception as e:
                logger.warning(f"Red button error: {e}")
            
            await send_step_screenshot(ctx, uid, page, "ধাপ ২: লাল বাটনে ক্লিক", f"বাটন ক্লিক: {'সফল' if red_clicked else 'ব্যর্থ'}")

            # ---------------- ধাপ ৩: I have an account Login ----------------
            await update_loading(40, "OPENING LOGIN FORM")
            acc_clicked = False
            try:
                # ১. Playwright দিয়ে খোঁজা
                acc_btn = page.locator('text="I have an account"').first
                if await acc_btn.count() > 0 and await acc_btn.is_visible():
                    await acc_btn.click(force=True, timeout=5000)
                    acc_clicked = True
                else:
                    # ২. জাভাস্ক্রিপ্ট দিয়ে খোঁজা
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
                    # ৩. যদি কিছুতেই না হয়, তবে নিচের দিকে ক্লিক করা (মোবাইল ভিউ এর জন্য)
                    await page.mouse.click(200, 750)
                    acc_clicked = True

                await asyncio.sleep(4) 
            except Exception as e:
                logger.warning(f"Acc button error: {e}")
            
            await send_step_screenshot(ctx, uid, page, "ধাপ ৩: 'I have an account' ক্লিক", f"লগইন ফর্মে যাওয়া: {'সফল' if acc_clicked else 'ব্যর্থ'}")

            # ---------------- ধাপ ৪: ফোন এবং পাসওয়ার্ড বসানো ----------------
            await update_loading(55, "ENTERING CREDENTIALS")
            try:
                # প্লেসহোল্ডার বা ইনপুট টাইপ দিয়ে খোঁজা
                phone_input = page.locator('input[placeholder*="phone" i]').first
                if await phone_input.count() == 0:
                    phone_input = page.locator('input[type="tel"]').first
                
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(login_phone, delay=150)
                await asyncio.sleep(1)
                
                # পাসওয়ার্ড বক্স
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
                # হলুদ রঙের Log in বাটন
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

            # এখানে আপনার বেটিং লজিক বসবে...

        except Exception as e:
            logger.error(f"Main error: {e}")
            try:
                await send_step_screenshot(ctx, uid, page, "মেইন এরর", f"Error: {str(e)[:100]}")
            except: pass
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