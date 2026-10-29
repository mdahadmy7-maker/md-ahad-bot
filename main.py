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
            "balance": "0.00", "target": 0, "steps": 0, "step_amounts": [], 
            "current_step": 0, "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. এপিআই থেকে প্রেডিকশন নেওয়া
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        history = [int(item.get("number", 0)) for item in list_data[:15]]
        
        if not history: return "BIG", latest_period
        
        last_num = history[0]
        sizes = ['B' if x >= 5 else 'S' for x in history]
        
        trend = "BIG"
        if len(sizes) >= 3 and sizes[0] == 'S' and sizes[1] == 'B' and sizes[2] == 'B':
            trend = "BIG"
        elif len(sizes) >= 3 and sizes[0] == 'B' and sizes[1] == 'S' and sizes[2] == 'S':
            trend = "SMALL"
        elif last_num == 4 or last_num == 6:
            trend = "SMALL"
        else:
            trend = "SMALL" if sizes[0] == 'B' else "BIG"
            
        return trend, latest_period
    except Exception as e:
        logger.error(f"API Error: {e}")
        return "BIG", "Unknown"

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone # ৮৮০ সহ যাবে
    
    async def update_msg(text):
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text=text, parse_mode="Markdown")
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        # ==========================================
        # 💡 WinGoBet API ক্যাপচার (আপনার মূল লক্ষ্য)
        # ==========================================
        async def log_bet_api(request):
            if request.method == "POST" and "WinGoBet" in request.url:
                try:
                    api_msg = (
                        "🚨 **REAL BET API CAPTURED!** 🚨\n\n"
                        f"🔗 **URL:**\n`{request.url}`\n\n"
                        f"📦 **Payload:**\n`{request.post_data}`"
                    )
                    await ctx.bot.send_message(chat_id=uid, text=api_msg, parse_mode="Markdown")
                except: pass
        page.on("request", log_bet_api)
        # ==========================================

        try:
            # লগইন
            await update_msg("🔄 **Logging in...**")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except: pass
            
            for _ in range(5):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)

            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            if not uid_match:
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**")
                await browser.close()
                return

            state["balance"] = float(balance_match.group(1)) if balance_match else 0.0
            if loading_msg_id: 
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE")]]
            await ctx.bot.send_message(chat_id=uid, text=f"🎉 **LOGIN SUCCESSFUL** ✅\n💰 Balance: ৳ {state['balance']:.2f}", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # WinGo পেজে যাওয়া (সহজ লজিক)
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            try:
                await page.get_by_text("Lottery", exact=True).first.click(timeout=5000, force=True)
                await page.wait_for_timeout(1000)
                await page.get_by_text("WinGo 30sec", exact=True).first.click(timeout=5000, force=True)
            except: pass
            await page.wait_for_timeout(3000) 

            # বেটিং লুপ
            current_step_idx = 0
            while state["trade_running"]:
                try:
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = get_history_and_prediction()

                    # ২৯ সেকেন্ডের জন্য অপেক্ষা
                    timer_found = False
                    for _ in range(400): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            clean_text = body_text.replace(" ", "")
                            if re.search(r'00:(30|29)', clean_text):
                                timer_found = True
                                break
                        except: pass
                        await asyncio.sleep(0.1)

                    if not timer_found: continue 

                    # Big/Small ক্লিক
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    js_click_big_small = f"""
                    (() => {{
                        let els = document.querySelectorAll('div, span, button');
                        for (let el of els) {{
                            if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                el.click(); return true;
                            }}
                        }}
                        return false;
                    }})()
                    """
                    await page.evaluate(js_click_big_small)
                    await page.wait_for_timeout(1500)

                    # Amount বসানো
                    try:
                        inp = page.locator('input[type="text"], input[type="number"]').first
                        if await inp.is_visible():
                            await inp.click(force=True)
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await inp.type(str(int(bet_amount)), delay=20)
                    except: pass

                    # Total Amount ক্লিক
                    js_confirm_bet = """
                    (() => {
                        for(let el of document.querySelectorAll('button, div, span')) {
                            if(el.innerText && el.innerText.toLowerCase().includes('total amount')) {
                                el.click(); return true;
                            }
                        }
                        return false;
                    })()
                    """
                    for _ in range(10):
                        if await page.evaluate(js_confirm_bet): break
                        await page.wait_for_timeout(500)

                    await page.wait_for_timeout(2000)
                    
                    # স্ক্রিনশট নেওয়া
                    await ctx.bot.send_message(chat_id=uid, text=f"✅ **BET PLACED!**\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}")

                    # রেজাল্ট চেক
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
                        if new_balance > state["balance"]:
                            state["balance"] = new_balance
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}")
                        else:
                            state["balance"] = new_balance
                            current_step_idx += 1
                            if current_step_idx >= len(state['step_amounts']):
                                await ctx.bot.send_message(chat_id=uid, text="🛑 **সব স্টেপ শেষ!**")
                                state["trade_running"] = False
                                break
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: {current_step_idx+1}")

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(1500)

                except Exception as e:
                    logger.error(f"Bet error: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
        finally:
            await browser.close()

# হ্যান্ডলারগুলো
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