import asyncio
import logging
import re
import os
import requests
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.vip/#/login"
HOME_URL = "https://www.hgnice.vip/#/"
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
            "first_bet": True
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. API থেকে রেজাল্ট ও প্রেডিকশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
            
        if len(history) == 0: return "BIG", latest_period
        if len(history) < 3:
            return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
            
        if n >= 4:
            l4 = history[n-4]
            if l4 == l3 and l2 == l1 and l4 != l3:
                return l4, latest_period
            if l4 == l2 and l3 == l1 and l4 != l3:
                return l4, latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        fallback_period = datetime.now().strftime("%Y%m%d%H%M%S")
        import random
        return random.choice(["BIG", "SMALL"]), fallback_period

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **HGNICE-এ সংযোগ করা হচ্ছে**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
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
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            await update_loading(30)
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except: pass

            await update_loading(50)
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            await update_loading(70)
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
                await page.wait_for_timeout(400)

            await update_loading(85)
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
                await page.wait_for_timeout(3000) 
            except: pass

            await update_loading(95)
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
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
                await page.wait_for_timeout(500)

            await update_loading(100)
            await asyncio.sleep(0.2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **লগইন ব্যর্থ হয়েছে** ({phone})")
                await browser.close()
                return

            state["balance"] = float(balance)
            masked_phone = f"***{phone[-4:]}"
            
            # 💡 লগইন সফল হলে WinGo পেজে প্রবেশ
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            
            for _ in range(3):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)
                
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if((el.innerText||'').toLowerCase().includes('lottery')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(2000)
            
            try:
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, p')) { if((el.innerText||'').includes('Win Go') && (el.innerText||'').includes('Guess Number')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(3000) 

            await ctx.bot.send_message(chat_id=uid, text="✅ **উইনগো পেজে প্রবেশ করা হয়েছে!**\nবট এখানে অপেক্ষা করছে। শুরু করতে নিচের বাটনে ক্লিক করুন।")

            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 **লগইন সফল হয়েছে** ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ ফোন নম্বর\n{masked_phone}\n\n"
                f"👤 অ্যাকাউন্ট UID\n{uid_val}\n\n"
                f"💰 অ্যাকাউন্ট ব্যালেন্স\n৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 অ্যানালাইসিস ইঞ্জিন:  প্রস্তুত\n"
                "🚀 অটো-ট্রেড সিস্টেম: প্রস্তুত\n\n"
                "👇 শুরু করতে নিচের বাটনে ক্লিক করুন"
            )
            reply_keyboard = [[KeyboardButton("🚀 আপনার টার্গেট শুরু করুন")], [KeyboardButton("🛑 ট্রেড বন্ধ করুন"), KeyboardButton("🚪 লগআউট")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            
            await ctx.bot.send_message(chat_id=uid, text="🚀 **অটো ট্রেড চালু হয়েছে**\nবট বাজি রাখা শুরু করেছে...")

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        profit = current_bal - initial_balance
                        win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                        target_summary = (
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🎯 **টার্গেট পূর্ণ হয়েছে** 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💰 **শুরুর ব্যালেন্স** : ৳ {initial_balance:.2f}\n"
                            f"💵 **শেষ ব্যালেন্স** : ৳ {current_bal:.2f}\n"
                            f"💸 **লাভ**   : +৳ {profit:.2f}\n\n"
                            f"📊 **মোট ট্রেড** : {state['total_trades']} 🟢 **জয়** : {state['wins']} 🔴 **হার** : {state['losses']}\n"
                            f"🏆 **জয়ের হার** : {win_rate:.1f}%\n"
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

                    # 💡 ১. টাইমার ২৫ থেকে ৬ এর মধ্যে হওয়া পর্যন্ত অপেক্ষা করা
                    logger.info("পপআপ চলে যাওয়া এবং টাইমার ৬ থেকে ৩০ এর মধ্যে হওয়া পর্যন্ত অপেক্ষা...")
                    timer_val = "0s"
                    timer_ready = False
                    for _ in range(600): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            
                            # পপআপ চেক (0 0, 0 1 ইত্যাদি)
                            if re.search(r'\b0\s*[0-5]\b', body_text):
                                await asyncio.sleep(0.1)
                                continue
                                
                            match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                            if match:
                                sec = int(match.group(1))
                                # স্ক্রিন স্বাভাবিক হওয়া মাত্রই (২৫ থেকে ৬) ক্লিক করবে
                                if 6 <= sec <= 25: 
                                    timer_val = f"{sec}s"
                                    timer_ready = True
                                    break
                        except: pass
                        await asyncio.sleep(0.1) 

                    if not timer_ready:
                        continue

                    # 💡 ২. বিগ অথবা স্মল ক্লিক (Playwright-এর নিজস্ব Auto-Wait ক্লিক)
                    logger.info(f"{choice} ক্লিক করা হচ্ছে...")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    
                    try:
                        if choice.upper() == "BIG":
                            # Playwright অপেক্ষা করবে পপআপ চলে যাওয়া পর্যন্ত, তারপর ক্লিক করবে
                            await page.locator('div, span, button').filter(has_text=re.compile(r'^BIG$', re.IGNORECASE)).last.click(timeout=10000)
                        else:
                            await page.locator('div, span, button').filter(has_text=re.compile(r'^SMALL$', re.IGNORECASE)).last.click(timeout=10000)
                    except Exception as e:
                        logger.error(f"Click failed: {e}")
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **বিগ/স্মলে ক্লিক করতে ব্যর্থ!**")
                        await asyncio.sleep(5)
                        continue

                    # 💡 ৩. Total amount-এ ক্লিক (যেহেতু বিগ/স্মল ক্লিক সফল হয়েছে, টোটাল অ্যামাউন্ট সাথে সাথেই আসবে)
                    logger.info("Total amount বাটন খোঁজা হচ্ছে...")
                    confirm_success = False
                    
                    # ৩ সেকেন্ড পর্যন্ত অপেক্ষা করবে (যদি UI ল্যাগ হয়)
                    for _ in range(15):
                        try:
                            total_btn = page.locator('text=/Total amount/i').last
                            if await total_btn.count() > 0 and await total_btn.is_visible():
                                await total_btn.click(timeout=1000, force=True)
                                confirm_success = True
                                break
                        except: pass
                        await asyncio.sleep(0.2)

                    # 💡 ৪. মেসেজ লজিক (আপনার দেওয়া)
                    if confirm_success:
                        state['total_trades'] += 1
                        await ctx.bot.send_message(chat_id=uid, text=f"✅ **বাজি সফলভাবে বসানো হয়েছে!**\n\n🎯 প্রেডিকশন: **{choice.upper()}**\n💰 পরিমাণ: ৳ {bet_amount:.2f}", parse_mode="Markdown")
                        
                        await page.wait_for_timeout(2000)
                        proof_path = f"proof_success_{uid}.png"
                        await page.screenshot(path=proof_path)
                        await ctx.bot.send_photo(
                            chat_id=uid, 
                            photo=open(proof_path, 'rb'), 
                            caption=f"📱 স্ক্রিনশটে দেখুন সাইটে কি হয়েছে ↓"
                        )
                        
                    else:
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **{choice.upper()} সিলেক্ট হয়েছে, কিন্তু Total amount বাটনে ক্লিক করা যায়নি!**", parse_mode="Markdown")
                        continue

                    # 💡 ৫. ৩২ সেকেন্ড অপেক্ষা (রেজাল্টের জন্য)
                    await asyncio.sleep(32)

                    # 💡 ৬. রেজাল্ট চেক
                    await page.evaluate("window.scrollTo(0, 0);") 
                    await page.wait_for_timeout(1000)
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            p_l = bet_amount * 0.96
                            win_rate = (state['wins'] / state['total_trades'] * 100)
                            
                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🟢 **ট্রেড রেজাল্ট**\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ পিরিয়ড : {current_period}\n"
                                f"🔵 সাইড : {choice} ❮❮❮\n"
                                f"🚀 স্টেপ : {current_step_idx+1}\n"
                                f"💵 পরিমাণ : ৳ {bet_amount:.2f}\n\n"
                                "📊 ফলাফল : **জয়** ✅\n"
                                f"💹 লাভ/ক্ষতি : +৳ {p_l:.2f}\n"
                                f"💰 ব্যালেন্স : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 জয় : {state['wins']} 🔴 হার : {state['losses']} 📈 রেট :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 মনোবল : 😌 শান্ত ও মনোযোগী\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "➡️ পরবর্তী স্টেপ : ১\n"
                                "🟢 রিকভারি হয়েছে! স্টেপ ১ এ ফিরে যাচ্ছে।"
                            ))
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            p_l = -bet_amount
                            
                            win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_step_txt = f"➡️ পরবর্তী স্টেপ : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                            else:
                                next_step_txt = "🛑 আর কোনো স্টেপ বাকি নেই।"

                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🔴 **ট্রেড রেজাল্ট**\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ পিরিয়ড : {current_period}\n"
                                f"🔵 সাইড : {choice} ❮❮❮\n"
                                f"🚀 স্টেপ : {current_step_idx}\n"
                                f"💵 পরিমাণ : ৳ {bet_amount:.2f}\n\n"
                                "📊 ফলাফল : **হার** ❌\n"
                                f"💹 লাভ/ক্ষতি : -৳ {bet_amount:.2f}\n"
                                f"💰 ব্যালেন্স : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 জয় : {state['wins']} 🔴 হার : {state['losses']} 📈 রেট :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 মনোবল : 😐 মনোযোগী\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"{next_step_txt}"
                            ))

                    # পেজে থাকবে, শুধু স্ক্রল করে নিচে নামবে
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(2000)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await asyncio.sleep(2)
                    
        except Exception as e:
            logger.error(f"Playwright general error: {e}")
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
        "🧠 মোড    : অটো অ্যানালাইসিস ও বেট\n"
        "🔐 অ্যাক্সেস  : প্রাইভেট · অনুমোদিত সদস্য\n"
        "🔴 স্ট্যাটাস  : লগইন করা নেই\n"
        f"👥 অ্যাকাউন্ট: {len(state['accounts'])}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 প্রেডিকশন ইঞ্জিন — ৯ লেয়ার\n"
        "⚡ স্ট্রিক · 🔷 প্যাটার্ন · 📈 ট্রেন্ড\n"
        "🔍 ম্যানিপুলেশন · 🎨 কালার · 🔢 ফ্রিকোয়েন্সি\n"
        "🔄 মার্কভ · ♻️ সাইকেল · 💠 মোমেন্টাম\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 লগইন করতে নিচের বাটনে ক্লিক করুন"
    )
    keyboard = [[InlineKeyboardButton("🔐 অ্যাকাউন্টে লগইন করুন", callback_data="start_login")]]
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
            "║  🔐 অ্যাকাউন্ট লগইন 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"☎️ নম্বর : {text}\n\n"
            "🔑 এখন আপনার পাসওয়ার্ড দিন:\n"
            "নিরাপত্তার জন্য আপনার মেসেজটি সাথে সাথে ডিলিট হয়ে যাবে।"
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 **HGNICE-এ সংযোগ করা হচ্ছে**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 আপনার টার্গেট শুরু করুন" or text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 আপনার টার্গেট শুরু করুন 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 আপনার ব্যালেন্স\n"
            f"৳ {state.get('balance', '0.00')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 আপনার টার্গেট লাভের পরিমাণ লিখুন:\n"
            "আপনি কত টাকা আয় করতে চান? (৳)"
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
                "║   🎯 টার্গেট সেট হয়েছে 🎯   ║\n"
                "╚════════════════════════╝\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 ব্যালেন্স  : ৳ {balance:.2f}\n"
                f"🎯 টার্গেট   : ৳ {target_amount:.2f} লাভ\n"
                f"🏦 থামবে  : ৳ {stop_at:.2f}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 স্টেপ সংখ্যা লিখুন:\n"
                "কতটি স্টেপ নিতে চান? (যেমন: 5, সর্বোচ্চ 50)"
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
                "║   💵 স্টেপ পরিমাণ 💵   ║\n"
                "╚════════════════════════╝\n\n"
                f"আপনি {steps} টি স্টেপ বেছে নিয়েছেন।\n\n"
                f"💵 স্টেপ {state['current_step']} — বাজির পরিমাণ? (৳)"
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
                step_msg = f"💵 স্টেপ {state['current_step']} — বাজির পরিমাণ? (৳)"
                await update.message.reply_text(step_msg)
            else:
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                balance = float(state.get('balance', '0.00'))
                target = float(state.get('target', 0))
                stop_at = balance + target
                step_plan_text = ""
                for i, amt in enumerate(state["step_amounts"]):
                    step_plan_text += f"স্টেপ {i+1:02d} : ৳ {amt:.2f}\n"
                
                combined_msg = (
                    "⚙️ ট্রেড কনফিগারেশন ⚙️\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 ব্যালেন্স  : ৳ {balance:.2f}\n"
                    f"🎯 টার্গেট   : ৳ {target:.2f} লাভ\n"
                    f"🏦 থামবে  : ৳ {stop_at:.2f}\n"
                    f"📋 স্টেপ    : {state['steps']}\n"
                    f"⚠️ মোট ঝুঁকি : ৳ {total_risk:.2f}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📊 স্টেপ প্ল্যান\n"
                    f"{step_plan_text}"
                    "\n"
                    "👇 শুরু করতে START TRADE বাটনে ক্লিক করুন।"
                )
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 ট্রেড শুরু করুন", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 1)।")
        return

    if text == "🛑 ট্রেড বন্ধ করুন" or text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 **ট্রেড বন্ধ করা হয়েছে**")
        return
    if text == "🚪 লগআউট" or text == "🚪 LOGOUT":
        state["trade_running"] = False
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 **লগআউট করা হয়েছে**")
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
            "║  🔐 অ্যাকাউন্ট লগইন 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 আপনার HGNICE ফোন নম্বর দিন:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "প্রত্যেকে নিজের অ্যাকাউন্ট ব্যবহার করুন — আপনার সেশনটি প্রাইভেট।"
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)
    elif data == "start_trade_btn":
        state["trade_running"] = True
        try:
            await query.answer("ট্রেড শুরু হচ্ছে!")
            await query.edit_message_text("🚀 **ট্রেড শুরু হয়েছে...**\nবট উইনগো পেজে প্রবেশ করছে...", parse_mode="Markdown")
        except: pass
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **ট্রেড বাতিল করা হয়েছে**")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["trade_running"] = False
    if state.get("task"): state["task"].cancel()
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, 
        "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False, "task": None,
        "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

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