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
            "wins": 0, "losses": 0, "total_trades": 0, "first_bet": True,
            "bearer_token": None
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. API থেকে প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(HISTORY_API, headers=headers, timeout=5)
        data = res.json()
        list_data = data.get("data", {}).get("list", [])
        if not list_data: raise Exception("No data")
            
        latest_period = str(list_data[0].get("issueNumber", "Unknown"))
        reversed_list = list(reversed(list_data))
        
        history = ["SMALL" if int(item.get("number", 0)) <= 4 else "BIG" for item in reversed_list]
            
        if len(history) < 3:
            return ("SMALL" if history[-1] == 'BIG' else "BIG"), latest_period
            
        n = len(history)
        l1, l2, l3 = history[n-1], history[n-2], history[n-3]
        
        if l1 == l2 == l3:
            return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
            
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        import random
        return random.choice(["BIG", "SMALL"]), datetime.now().strftime("%Y%m%d%H%M%S")

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট (সুপার ফাস্ট)
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text="CONNECTING TO HGNICE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        # ==========================================
        # 💡 এপিআই ক্যাপচার (শুধু WinGoBet ধরবে)
        # ==========================================
        async def log_bet_api(request):
            if request.method == "POST":
                # ১. Bearer টোকেন খোঁজা (যেকোনো এপিআই হিট হলেই টোকেন সেভ করবে)
                auth_header = request.headers.get("authorization", "")
                if "Bearer" in auth_header:
                    state["bearer_token"] = auth_header.replace("Bearer ", "")

                # ২. শুধুমাত্র WinGoBet এপিআই ক্যাপচার করা
                if "WinGoBet" in request.url:
                    try:
                        api_msg = (
                            "🚨 <b>REAL BET API CAPTURED!</b> 🚨\n\n"
                            f"🔗 <b>URL:</b>\n<code>{request.url}</code>\n\n"
                            f"📦 <b>Payload:</b>\n<pre>{request.post_data}</pre>\n\n"
                            f"🔑 <b>Bearer Token:</b>\n<code>{state.get('bearer_token', 'Not Found')}</code>"
                        )
                        await ctx.bot.send_message(chat_id=uid, text=api_msg, parse_mode="HTML")
                        logger.info("WinGoBet API Captured Successfully!")
                    except Exception as e:
                        logger.error(f"Telegram capture failed: {e}")

        page.on("request", log_bet_api)
        # ==========================================

        try:
            # ---------------- লগইন ----------------
            await update_loading(20)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except: pass
            
            await update_loading(50)
            await page.wait_for_timeout(5000)

            # পপআপ ক্লোজ
            for _ in range(5):
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }")
                await page.wait_for_timeout(300)

            # ব্যালেন্স চেক
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            if not uid_match:
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED**")
                await browser.close()
                return

            state["balance"] = float(balance_match.group(1)) if balance_match else 0.0
            
            await update_loading(80, "OPENING WIN GO GAME")
            
            # ---------------- WinGo পেজে যাওয়া (একবারই) ----------------
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                await page.wait_for_timeout(1000)
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except: pass
            await page.wait_for_timeout(3000) 

            await update_loading(100, "READY TO TRADE")
            if loading_msg_id: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)

            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(
                chat_id=uid, 
                text=f"🎉 **LOGIN SUCCESSFUL** ✅\n💰 Balance: ৳ {state['balance']:.2f}\n👇 Press START YOUR TARGET to begin", 
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ (সুপার ফাস্ট) ----------------
            initial_balance = state["balance"]
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳ {current_bal - initial_balance:.2f}\nবট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!**")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**")
                        state["trade_running"] = False
                        break

                    choice, current_period = get_history_and_prediction()

                    # 💡 টাইমার ২৮-২৯ সেকেন্ড হওয়া পর্যন্ত অপেক্ষা করবে
                    logger.info("Waiting for 28s or 29s phase...")
                    timer_found = False
                    for _ in range(700): # ৩৫ সেকেন্ড পর্যন্ত অপেক্ষা করবে (0.05 * 700)
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            # ২৮ বা ২৯ সেকেন্ড খোঁজা
                            if re.search(r'0\s*0\s*[:.]?\s*(28|29)', body_text):
                                timer_found = True
                                break
                        except: pass
                        await asyncio.sleep(0.05) # সুপার ফাস্ট চেক

                    if not timer_found:
                        logger.info("Timer missed, retrying...")
                        continue

                    # 💡 Big/Small ক্লিক
                    js_click = f"""
                    (() => {{
                        let els = document.querySelectorAll('div, span, button');
                        for (let el of els) {{
                            if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                if (el.getBoundingClientRect().width > 0) {{ el.click(); return true; }}
                            }}
                        }}
                        return false;
                    }})()
                    """
                    await page.evaluate(js_click)
                    
                    # 💡 Amount বসানো এবং Confirm ক্লিক (সঠিকভাবে অপেক্ষা করে)
                    try:
                        # ১. Amount ফিল্ড আসার জন্য অপেক্ষা
                        inp = page.locator('input[type="text"], input[type="number"]').first
                        await inp.wait_for(state="visible", timeout=5000)
                        await inp.fill(str(int(bet_amount)))

                        # ২. I agree
                        agree = page.locator('text="I agree"').first
                        if await agree.is_visible(): 
                            await agree.click(force=True)

                        # ৩. Total amount বাটন
                        confirm_btn = page.locator("text=/Total amount/i").last
                        await confirm_btn.wait_for(state="visible", timeout=5000)
                        await confirm_btn.click(force=True)
                        logger.info("Bet placed successfully!")
                    except Exception as e:
                        logger.error(f"Bet click error: {e}")
                        continue # ক্লিক না হলে পরের রাউন্ডে যাবে

                    # 💡 রেজাল্ট চেক (ব্রাউজার রিলোড না করেই)
                    await asyncio.sleep(32) # রেজাল্টের জন্য ৩২ সেকেন্ড অপেক্ষা

                    # ব্যালেন্স চেক করা
                    body_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', body_text)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: 1")
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})" if current_step_idx < len(state['step_amounts']) else "🛑 No more steps left."
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n{next_step_txt}")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
        finally:
            await browser.close()

# হ্যান্ডলারগুলো
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    welcome_text = "🧠 **BD=WIN~GO=AUTO~BET 💥**\n👇 Press the button below to LOGIN"
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number : {text}\n🔑 Now enter your password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = f"💰 YOUR BALANCE\n৳ {state.get('balance', '0.00')}\n\n🎯 Enter your TARGET profit amount:"
        await update.message.reply_text(target_msg)
        return
        
    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            balance = float(state.get('balance', '0.00'))
            stop_at = balance + target_amount
            target_set_msg = f"🎯 Target: ৳ {target_amount:.2f}\n🏦 Stop At: ৳ {stop_at:.2f}\n\n🚀 Enter your STEP COUNT (max 50):"
            state["awaiting"] = "steps"
            await update.message.reply_text(target_set_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1: raise ValueError("Invalid")
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — bet amount?")
        except ValueError:
            await update.message.reply_text("❌ ১ থেকে ৫০ এর মধ্যে সংখ্যা দিন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount?")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text("⚙️ CONFIGURATION DONE.\n👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! সংখ্যা লিখুন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
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
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your HGNICE phone number:")
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