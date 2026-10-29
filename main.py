import asyncio
import logging
import re
import os
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://www.hgnice.vip/#/login"
HOME_URL = "https://www.hgnice.vip/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "temp_phone": "", "temp_password": "", "balance": "0.00", "target": 0, "steps": 0, "step_amounts": [], "current_step": 0, "trade_running": False, "task": None, "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True}
    return user_state[uid]

def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API, timeout=10)
        list_data = res.json().get("data", {}).get("list", [])
        if not list_data: raise Exception("No data")
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        history = ["SMALL" if int(item.get("number", 0)) <= 4 else "BIG" for item in reversed(list_data)]
        if len(history) < 3: return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
        l1, l2, l3 = history[-1], history[-2], history[-3]
        if l1 == l2 == l3: return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
    except:
        import random
        return random.choice(["BIG", "SMALL"]), datetime.now().strftime("%Y%m%d%H%M%S")

async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent):
        if not loading_msg_id: return
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text=f"🔄 **CONNECTING...** {percent}%", parse_mode="Markdown")
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36", viewport={"width": 412, "height": 915})
        page = await context.new_page()
        
        # এপিআই ক্যাপচার
        async def log_bet_api(request):
            if request.method == "POST" and "WinGoBet" in request.url:
                try:
                    await ctx.bot.send_message(chat_id=uid, text=f"🚨 **BET API CAPTURED!**\n\nURL: `{request.url}`\n\nPayload: `{request.post_data}`", parse_mode="Markdown")
                except: pass
        page.on("request", log_bet_api)

        try:
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            await update_loading(30)
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except: pass
            
            await update_loading(60)
            for _ in range(5):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)

            await update_loading(80)
            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if(el.innerText && el.innerText.trim().toLowerCase()==='account') { el.click(); return true; } } }""")
            await page.wait_for_timeout(3000) 

            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            if not uid_match:
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**")
                await browser.close()
                return

            state["balance"] = float(balance_match.group(1)) if balance_match else 0.0
            await update_loading(100)
            if loading_msg_id: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)

            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE")]]
            await ctx.bot.send_message(chat_id=uid, text=f"🎉 **LOGIN SUCCESSFUL** ✅\n💰 Balance: ৳ {state['balance']:.2f}", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # WinGo পেজে যাওয়া
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                await page.wait_for_timeout(1000)
                await page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last.click(timeout=5000, force=True)
            except: pass
            await page.wait_for_timeout(3000) 

            initial_balance = state["balance"]
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    if current_bal >= target_balance or current_step_idx >= len(state['step_amounts']) or current_bal < float(state['step_amounts'][current_step_idx]):
                        await ctx.bot.send_message(chat_id=uid, text="🛑 **TARGET REACHED OR NO BALANCE!**")
                        state["trade_running"] = False
                        break

                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = get_history_and_prediction()

                    # ২৮-২৯ সেকেন্ডের জন্য অপেক্ষা
                    timer_found = False
                    for _ in range(700): 
                        try:
                            if re.search(r'0\s*0\s*[:.]?\s*(28|29)', await page.evaluate("() => document.body.innerText")):
                                timer_found = True
                                break
                        except: pass
                        await asyncio.sleep(0.05) 

                    if not timer_found: continue

                    # Big/Small ক্লিক
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.get_by_text(choice.upper(), exact=True).first.click(force=True, timeout=5000)
                    
                    # Total Amount ক্লিক (এটাই মূল ফিক্স)
                    await page.locator("text=Total amount").last.wait_for(state="visible", timeout=10000)
                    await page.locator("text=Total amount").last.click(force=True)
                    
                    await page.wait_for_timeout(2000)
                    await asyncio.sleep(32) # রেজাল্টের জন্য অপেক্ষা

                    # ব্যালেন্স আপডেট
                    body_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', body_text)
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}")
                        else:
                            state["balance"] = new_balance
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
        finally:
            await browser.close()

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text("🧠 **BD=WIN~GO=AUTO~BET 💥**", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 Now enter your password:")
    elif state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        if state.get("task"): state["task"].cancel()
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
    elif text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit:")
    elif state.get("awaiting") == "target":
        state["target"] = float(text)
        state["awaiting"] = "steps"
        await update.message.reply_text("🚀 Enter STEP COUNT:")
    elif state.get("awaiting") == "steps":
        state["steps"] = int(text)
        state["step_amounts"] = []
        state["current_step"] = 1
        state["awaiting"] = "step_amount"
        await update.message.reply_text("💵 Step 1 amount:")
    elif state.get("awaiting") == "step_amount":
        state["step_amounts"].append(float(text))
        state["current_step"] += 1
        if state["current_step"] <= state["steps"]:
            await update.message.reply_text(f"💵 Step {state['current_step']} amount:")
        else:
            state["awaiting"] = None
            inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
            await update.message.reply_text("👇 Press START TRADE.", reply_markup=inline_kb)
    elif text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 STOPPED")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter phone number:")
    elif query.data == "start_trade_btn":
        state["trade_running"] = True

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()