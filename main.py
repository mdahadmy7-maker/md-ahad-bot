import asyncio
import logging
import re
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.vip/#/login"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "balance": "0.00", "target": 0, "steps": 0, "step_amounts": [], 
            "trade_running": False, "task": None, "current_step": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_prediction():
    try:
        res = requests.get(HISTORY_API, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            return "SMALL", "Unknown"
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        history = ["SMALL" if int(item.get("number", 0)) <= 4 else "BIG" for item in reversed(list_data)]
        
        if len(history) == 0: return "BIG", latest_period
        if len(history) < 3: return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
        
        return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
    except:
        return "SMALL", "Unknown"

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট (সরল কিন্তু শক্তিশালী)
# ───────────────────────────────────────────
async def run_bot(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(text):
        if not loading_msg_id: return
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text=text, parse_mode="Markdown")
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        
        try:
            await update_loading("🔄 **OPENING WEBSITE...**")
            # ওয়েবসাইট লোড হওয়ার জন্য অপেক্ষা
            await page.goto(SITE_URL, timeout=60000, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # পপআপ থাকলে বন্ধ করা
            await update_loading("🔄 **CLOSING POPUPS...**")
            for _ in range(3):
                try:
                    await page.evaluate("""
                        (function() {
                            let els = document.querySelectorAll('button, div, span');
                            for (let el of els) {
                                let txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (txt === 'confirm' || txt === 'ok' || txt === 'close') { el.click(); return; }
                            }
                        })();
                    """)
                    await page.wait_for_timeout(500)
                except: pass

            # ফোন নাম্বার এবং পাসওয়ার্ড বসানো
            await update_loading("🔄 **ENTERING DETAILS...**")
            try:
                # ইনপুট বক্সগুলো লোড হওয়া পর্যন্ত অপেক্ষা করবে
                await page.wait_for_selector('input[type="password"]', timeout=15000)
                
                # প্রথম টেক্সট বক্সে নাম্বার
                await page.locator('input[type="text"]').first.fill(login_phone)
                await page.wait_for_timeout(500)
                # পাসওয়ার্ড বক্সে পাসওয়ার্ড
                await page.locator('input[type="password"]').first.fill(password)
                await page.wait_for_timeout(500)
            except Exception as e:
                logger.error(f"Input Error: {e}")

            # লগইন ক্লিক
            await update_loading("🔄 **LOGGING IN...**")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=5000)
            except:
                try:
                    await page.locator('text="Log in"').last.click(timeout=5000)
                except:
                    await page.keyboard.press("Enter") # ব্যাকআপ

            # লগইন রেজাল্ট চেক (৫ সেকেন্ড অপেক্ষা)
            await page.wait_for_timeout(5000)
            page_text = await page.inner_text("body")

            if "Wrong account or password" in page_text or "Error: 147" in page_text:
                await update_loading("❌ **LOGIN FAILED: WRONG PASSWORD**")
                await browser.close()
                return

            # Account পেজে গিয়ে ডেটা নেওয়া
            try:
                await page.evaluate("""
                    (function() {
                        let els = document.querySelectorAll('div, span, a');
                        for (let el of els) {
                            if (el.innerText && el.innerText.trim().toLowerCase() === 'account') { el.click(); return; }
                        }
                    })();
                """)
                await page.wait_for_timeout(3000)
                page_text = await page.inner_text("body")
            except: pass

            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)

            if uid_match:
                uid_val = uid_match.group(1)
                balance = balance_match.group(1) if balance_match else "0.00"
                state["balance"] = float(balance)
                
                # 💡 আপনার পছন্দের ড্যাশবোর্ড ডিজাইন
                msg = (
                    "╔════════════════════════╗\n"
                    "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                    "╚════════════════════════╝\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"☎️ Phone Number\n***{phone[-4:]}\n\n"
                    f"👤 Account UID\n{uid_val}\n\n"
                    f"💰 Account Balance\n৳ {balance}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🧠 Analysis Engine:  READY\n"
                    "🚀 AutoTrade System: READY\n\n"
                    "👇 Press START YOUR TARGET to begin"
                )
                reply_kb = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
                await ctx.bot.send_message(chat_id=uid, text=msg, reply_markup=ReplyKeyboardMarkup(reply_kb, resize_keyboard=True))
            else:
                # 💡 যদি UID না পায়, তবে স্ক্রিনশট পাঠাবে
                await page.screenshot(path=f"err_{uid}.png")
                await ctx.bot.send_photo(chat_id=uid, photo=open(f"err_{uid}.png", 'rb'), caption="⚠️ **LOGIN ERROR!**\nUID পাওয়া যায়নি। পেজে কী আছে স্ক্রিনশটে দেখুন।")
                await browser.close()
                return

            # --- অটো-বেট লুপ ---
            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            initial_bal = state["balance"]
            target_bal = initial_bal + float(state["target"])
            
            while state["trade_running"]:
                if state["current_step"] >= len(state["step_amounts"]):
                    await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!**")
                    state["trade_running"] = False
                    break

                bet_amt = state["step_amounts"][state["current_step"]]
                choice, period = get_prediction()

                await page.goto("https://www.hgnice.vip/#/WinGo", wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)

                # পপআপ ক্লোজ
                try:
                    await page.evaluate("""
                        (function() {
                            let els = document.querySelectorAll('button, div, span');
                            for (let el of els) {
                                let txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (txt === 'confirm' || txt === 'ok' || txt === 'close') { el.click(); return; }
                            }
                        })();
                    """)
                    await page.wait_for_timeout(1000)
                except: pass

                # Big/Small ক্লিক
                clicked = False
                try:
                    await page.get_by_text(choice, exact=True).last.click(timeout=10000, force=True)
                    clicked = True
                except: pass

                if not clicked:
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **{choice} বাটন পাওয়া যায়নি!**")
                    state["trade_running"] = False
                    break

                await page.wait_for_timeout(1000)
                try: await page.locator('text="Confirm"').last.click(timeout=3000)
                except: pass

                await ctx.bot.send_message(chat_id=uid, text=f"🤖 **BET PLACED:** {choice}\nAmount: ৳ {bet_amt}\nWaiting for result...")
                await asyncio.sleep(32)

                # রেজাল্ট চেক
                await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                new_text = await page.inner_text("body")
                new_bal_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', new_text, re.IGNORECASE)
                
                if new_bal_match:
                    new_bal = float(new_bal_match.group(1))
                    if new_bal > state["balance"]:
                        state["balance"] = new_bal
                        state["current_step"] = 0
                        await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nBalance: ৳ {new_bal}")
                    else:
                        state["balance"] = new_bal
                        state["current_step"] += 1
                        await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nBalance: ৳ {new_bal}\nNext Step: {state['current_step']+1}")

        except Exception as e:
            logger.error(f"Main Error: {e}")
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **BOT ERROR:**\n`{str(e)[:150]}`")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)
    await update.message.reply_text("👇 **Press the button below to LOGIN**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="login")]]))

async def msg_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state["awaiting"] == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter password:")
        return

    if state["awaiting"] == "password":
        state["temp_password"] = text
        state["awaiting"] = None
        # পাসওয়ার্ড মেসেজ ডিলিট
        try: await update.message.delete()
        except: pass
        
        msg = await update.message.reply_text("🔄 **CONNECTING...**")
        state["task"] = asyncio.create_task(run_bot(uid, ctx, msg.message_id, state["temp_phone"], text))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit amount:")
        return
        
    if state["awaiting"] == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("🚀 Enter STEP COUNT (e.g. 5):")
        except: await update.message.reply_text("❌ Number only!")
        return
        
    if state["awaiting"] == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = []
            state["current_step"] = 0
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — amount?")
        except: await update.message.reply_text("❌ Number only!")
        return

    if state["awaiting"] == "step_amount":
        try:
            state["step_amounts"].append(float(text))
            state["current_step"] += 1
            if state["current_step"] < state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']+1} — amount?")
            else:
                state["awaiting"] = None
                await update.message.reply_text("✅ Steps saved!\n👇 Press START TRADE to begin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="trade")]]))
        except: await update.message.reply_text("❌ Number only!")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 STOPPED")
        return

async def btn_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your HGNICE phone number:")
    elif query.data == "trade":
        await query.message.delete()
        state["trade_running"] = True

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()