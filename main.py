import asyncio
import logging
import re
import os
import requests
import json
import random
import time
from datetime import datetime, timezone
from enum import Enum
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন ও স্টেট
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.vip/#/login"
HOME_URL = "https://www.hgnice.vip/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

# আপনার দেওয়া Enum থেকে স্টেট নেওয়া হলো
class BotState(str, Enum):
    NOT_LOGGED_IN    = "NOT_LOGGED_IN"
    LOGIN_NUMBER     = "LOGIN_NUMBER"
    LOGIN_PASSWORD   = "LOGIN_PASSWORD"
    LOGGED_IN        = "LOGGED_IN"
    TARGET_INPUT     = "TARGET_INPUT"
    STEP_COUNT_INPUT = "STEP_COUNT_INPUT"
    STEP_AMOUNT_INPUT= "STEP_AMOUNT_INPUT"
    READY            = "READY"
    TRADING          = "TRADING"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "state": BotState.NOT_LOGGED_IN,
            "temp_phone": "", "temp_password": "",
            "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0,
            "first_bet": True
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# 💡 ২. টাইম সিঙ্ক (Time Sync) লজিক
# ═══════════════════════════════════════════
def get_seconds_left():
    now = datetime.now(timezone.utc)
    return 30 - (now.second % 30)

# ───────────────────────────────────────────
# 💡 ৩. API থেকে প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API + f"?t={int(time.time()*1000)}", timeout=10)
        data = res.json()
        
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            return "SMALL"
            
        reversed_list = list(reversed(list_data))
        history = []
        for item in reversed_list:
            num = int(item.get("number", 0))
            history.append("SMALL" if num <= 4 else "BIG")
            
        if len(history) < 3: return "BIG"
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return "SMALL" if l1 == 'BIG' else "BIG"
                
        return "SMALL" if l1 == 'BIG' else "BIG"
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        return "SMALL"

def check_win_loss_fast(period, choice):
    try:
        res = requests.get(HISTORY_API + f"?t={int(time.time()*1000)}", timeout=5)
        data = res.json()
        for item in data.get("data", {}).get("list", []):
            if str(item.get("issueNumber")) == str(period):
                num = int(item.get("number", 0))
                actual_result = "SMALL" if num <= 4 else "BIG"
                return (actual_result == choice), actual_result
    except: pass
    return None, None

# ───────────────────────────────────────────
# ৪. Playwright অটো-বেট ফাংশন
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
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
            await page.locator('input[type="password"]').first.fill(password)
            await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            
            await update_loading(50)
            await page.wait_for_timeout(4000)
            
            # পপআপ ক্লোজ
            await page.evaluate("""
                (function() {
                    let elements = document.querySelectorAll('button, div, span, a');
                    for (let el of elements) {
                        let text = (el.innerText || '').trim().toLowerCase();
                        if (['confirm', 'close', 'ok'].includes(text)) el.click();
                    }
                })();
            """)

            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if (el.innerText && el.innerText.trim().toLowerCase() === 'account') { el.click(); return true; } } }""")
            await page.wait_for_timeout(3000) 
            
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            if not uid_match:
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**")
                await browser.close()
                return

            balance = balance_match.group(1) if balance_match else "0.00"
            state["balance"] = float(balance)
            
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            await ctx.bot.send_message(chat_id=uid, text=f"🎉 **LOGIN SUCCESSFUL**\nBalance: ৳ {balance}", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 START YOUR TARGET")]], resize_keyboard=True))
            state["state"] = BotState.LOGGED_IN

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ট্রেডিং লুপ ----------------
            state["state"] = BotState.TRADING
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
            await page.wait_for_timeout(2000)
            await page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last.click(timeout=5000, force=True)
            await page.wait_for_timeout(3000) 

            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance or current_step_idx >= len(state['step_amounts']):
                        state["trade_running"] = False
                        await ctx.bot.send_message(chat_id=uid, text="🎯 **টার্গেট শেষ অথবা স্টেপ শেষ! বট বন্ধ হচ্ছে।**")
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice = get_history_and_prediction()

                    # 💡 ১. UTC টাইম দিয়ে অপেক্ষা করা
                    sec_left = get_seconds_left()
                    if sec_left <= 3:
                        await asyncio.sleep(sec_left + 1.5) 
                    else:
                        await asyncio.sleep(sec_left - 28)

                    # 💡 ২. Big / Small ক্লিক
                    clicked = await page.evaluate(f"""
                        (function() {{
                            // '00' ওভারলে রিমুভ করা
                            for (let el of document.querySelectorAll('div, span')) {{
                                if ((el.innerText || '').trim() === '00') {{
                                    let p = el.closest('div');
                                    while(p) {{ p.style.display = 'none'; p = p.parentElement; }}
                                }}
                            }}
                            let target = '{choice}'.toUpperCase();
                            for (let el of document.querySelectorAll('div, span, button, p, a')) {{
                                if ((el.innerText || '').trim().toUpperCase() === target) {{
                                    let rect = el.getBoundingClientRect();
                                    if (rect.width > 0) {{
                                        el.closest('button, div[role="button"]').dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
                                        return true;
                                    }}
                                }}
                            }}
                            return false;
                        }})();
                    """)

                    # 💡 ৩. Total amount বাটনে ক্লিক
                    if clicked:
                        try:
                            popup = page.locator('text="Total amount"').last
                            await popup.wait_for(state="visible", timeout=5000)
                            await popup.click(force=True)
                        except:
                            pass

                    await ctx.bot.send_message(chat_id=uid, text=f"✅ **{choice}** তে ক্লিক করা হয়েছে।")
                    
                    # 💡 ৪. রেজাল্ট চেক
                    await asyncio.sleep(32)
                    is_win, _ = check_win_loss_fast("latest", choice) # আপাতত ডেমো
                    
                    # WinGo পেজে ফিরে যাওয়া
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1000)
                    await page.locator('text="Lottery"').first.click(force=True)
                    await page.wait_for_timeout(1000)
                    await page.locator('div:has-text("Win Go")').last.click(force=True)

                except Exception as e:
                    logger.error(f"Loop Error: {e}")
                    state["trade_running"] = False
                    break
                    
        finally:
            await browser.close()

# ═══════════════════════════════════════════
# ৫. টেলিগ্রাম হ্যান্ডলার
# ═══════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["state"] = BotState.NOT_LOGGED_IN
    
    await update.message.reply_text("Welcome! Press Login:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔐 LOGIN", callback_data="start_login")]]))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    if text == "🚀 START YOUR TARGET":
        state["state"] = BotState.TARGET_INPUT
        await update.message.reply_text("Enter Target Profit (৳):")
        return

    if state["state"] == BotState.TARGET_INPUT:
        state["target"] = float(text)
        state["state"] = BotState.STEP_COUNT_INPUT
        await update.message.reply_text("Enter Step Count:")
        return

    if state["state"] == BotState.STEP_COUNT_INPUT:
        state["steps"] = int(text)
        state["step_amounts"] = []
        state["current_step"] = 1
        state["state"] = BotState.STEP_AMOUNT_INPUT
        await update.message.reply_text("Enter Step 1 Amount:")
        return

    if state["state"] == BotState.STEP_AMOUNT_INPUT:
        state["step_amounts"].append(float(text))
        state["current_step"] += 1
        if state["current_step"] <= state["steps"]:
            await update.message.reply_text(f"Enter Step {state['current_step']} Amount:")
        else:
            state["state"] = BotState.READY
            await update.message.reply_text("Press START TRADE to begin", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade")]]))

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["state"] = BotState.LOGIN_NUMBER
        await query.edit_message_text("Enter Phone Number:")
    elif query.data == "start_trade":
        state["trade_running"] = True

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()