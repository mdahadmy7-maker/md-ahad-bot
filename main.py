import asyncio
import logging
import re
import os
import requests
import random
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
            "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            # HTML প্রেডিকশন স্টেট
            "last3": [], "reverseMode": False, "reverseCount": 0, "reverseTarget": 1,
            "streakCount": 0, "streakType": None, "streakReversePending": False,
            "displayedResult": "--", "last_period": ""
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. HTML থেকে নেওয়া প্রেডিকশন লজিক
# ───────────────────────────────────────────
def get_prediction(state):
    try:
        res = requests.get(HISTORY_API, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: return state["displayedResult"]
        
        latest = list_data[0]
        latest_period = str(latest.get("issueNumber", ""))
        latest_num = int(latest.get("number", 0))
        
        if not latest_period or latest_period == state["last_period"]:
            return state["displayedResult"] 
            
        state["last_period"] = latest_period
        currentResultSize = 'SMALL' if latest_num <= 4 else 'BIG'

        if currentResultSize == state["streakType"]:
            state["streakCount"] += 1
        else:
            state["streakType"] = currentResultSize
            state["streakCount"] = 1

        if not state["reverseMode"]:
            state["last3"].append(currentResultSize)
            if len(state["last3"]) > 3: state["last3"].pop(0)

        if state["streakReversePending"]:
            state["streakReversePending"] = False
            patternDetected = False
            if len(state["last3"]) == 3:
                a, b, c = state["last3"]
                if a != b and b != c and a == c:
                    patternDetected = True

            if patternDetected:
                state["reverseMode"] = True
                state["reverseCount"] = 1
                state["reverseTarget"] = 1 if random.random() < 0.5 else 2
                state["displayedResult"] = 'SMALL' if currentResultSize == 'BIG' else 'BIG'
            else:
                state["displayedResult"] = currentResultSize

        elif state["streakCount"] >= 6 and not state["reverseMode"]:
            state["streakReversePending"] = True
            state["displayedResult"] = 'SMALL' if currentResultSize == 'BIG' else 'BIG'

        elif state["reverseMode"]:
            state["displayedResult"] = 'SMALL' if currentResultSize == 'BIG' else 'BIG'
            state["reverseCount"] += 1
            if state["reverseCount"] >= state["reverseTarget"]:
                state["reverseMode"] = False
                state["reverseCount"] = 0
                state["last3"] = []

        else:
            patternDetected = False
            if len(state["last3"]) == 3:
                a, b, c = state["last3"]
                if a != b and b != c and a == c:
                    patternDetected = True

            if patternDetected:
                state["reverseMode"] = True
                state["reverseCount"] = 1
                state["reverseTarget"] = 1 if random.random() < 0.5 else 2
                state["displayedResult"] = 'SMALL' if currentResultSize == 'BIG' else 'BIG'
            else:
                state["displayedResult"] = currentResultSize

        return state["displayedResult"]
    except Exception as e:
        logger.error(f"Prediction Error: {e}")
        return random.choice(["BIG", "SMALL"])

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
                text=f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
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
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
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
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            # ট্রেড রানিং এর জন্য অপেক্ষা
            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. WinGo পেজে ঢোকা এবং মেসেজ পাঠানো ----------------
            logger.info("Navigating to WinGo page...")
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

            initial_balance = state["balance"]
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            # 💡 WinGo পেজে ঢোকার সাথে সাথে ওয়েলকাম মেসেজ পাঠানো
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

            # ---------------- ৫. মেইন বেটিং লুপ ----------------
            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text="🎯 **TARGET REACHED!**")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!** বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])

                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**")
                        state["trade_running"] = False
                        break

                    choice = get_prediction(state)
                    
                    # 💡 ১. স্ক্রিনে 5,4,3,2,1,0,0 আছে কিনা চেক (আপনার স্ক্রিনশটের মতো)
                    logger.info(f"Prediction: {choice}. Checking for overlay...")
                    is_cleared = False
                    for _ in range(600): 
                        try:
                            blocked = await page.evaluate("""
                                () => {
                                    let elements = document.querySelectorAll('div, span, p');
                                    for (let el of elements) {
                                        let txt = (el.innerText || el.textContent || '').trim();
                                        let cleanTxt = txt.replace(/\\s+/g, ''); // সব স্পেস মুছে ফেলা হচ্ছে
                                        
                                        if (['5', '4', '3', '2', '1', '0', '00'].includes(cleanTxt)) {
                                            let rect = el.getBoundingClientRect();
                                            // স্ক্রিনে বড় করে দেখা যাচ্ছে কিনা
                                            if (rect.width > 40 && rect.height > 40) return true;
                                        }
                                    }
                                    return false;
                                }
                            """)
                            
                            if not blocked:
                                is_cleared = True
                                break 
                        except: pass
                        await asyncio.sleep(0.1)

                    if not is_cleared:
                        continue

                    # 💡 ২. বিগ অথবা স্মলে ক্লিক 
                    logger.info(f"Screen clear. Clicking {choice}...")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    
                    clicked = await page.evaluate(f"""
                        (() => {{
                            let els = document.querySelectorAll('div, span, button');
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
                    
                    if not clicked:
                        continue

                    # 💡 ৩. Total amount এ ক্লিক
                    logger.info("Clicking Total amount...")
                    await page.wait_for_timeout(800) 
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
                        return false;
                    })()
                    """)

                    await page.wait_for_timeout(1500)
                    
                    # 💡 ৪. স্ক্রিনশট 
                    proof_path = f"proof_success_{uid}.png"
                    await page.screenshot(path=proof_path)
                    await ctx.bot.send_photo(chat_id=uid, photo=open(proof_path, 'rb'), caption=f"✅ **BET PLACED!**\nPrediction: **{choice}**\nAmount: ৳ {bet_amount:.2f}")

                    # 💡 ৫. রেজাল্টের জন্য অপেক্ষা
                    await asyncio.sleep(32)

                    # 💡 ৬. উপরে স্ক্রল করে Wallet balance চেক করা (একই পেজে থাকবে)
                    logger.info("Checking result...")
                    await page.evaluate("window.scrollTo(0, 0);")
                    await page.wait_for_timeout(1500) 
                    
                    body_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', body_text)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}")
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}")

                    # আবার নিচে স্ক্রল করে গেমে ফিরে আসা
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(1000)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ═══════════════════════════════════════════
# ৪. টেলিগ্রাম হ্যান্ডলার
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private\n"
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
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter Password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...** 0%")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit (৳):")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("📊 Enter STEP COUNT:")
        except: pass
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 amount (৳):")
        except: pass
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} amount (৳):")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
                await update.message.reply_text("👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except: pass
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        if state.get("task"): state["task"].cancel()
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
        # 💡 এখানে কোনো edit_message_text নেই, তাই আপনার মেসেজটি আগের মতোই থাকবে
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**")

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