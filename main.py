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
# ৩. লগইন এবং অটো-বেট (সুপার ফাস্ট লজিক)
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
        
        # এপিআই ক্যাপচার (শুধু বেট এপিআই ধরার জন্য)
        async def log_bet_api(request):
            if request.method == "POST" and "WinGoBet" in request.url:
                logger.info(f"🎯 BET API HIT: {request.post_data}")
                
                # Bearer টোকেন বের করা (যদি থাকে)
                auth_header = request.headers.get("authorization", "")
                if "Bearer" in auth_header:
                    state["bearer_token"] = auth_header.replace("Bearer ", "")
        page.on("request", log_bet_api)

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

                    # 💡 টাইমার ২৮-২৯ সেকেন্ড হওয়া পর্যন্ত অপেক্ষা করবে (ফাস্ট লজিক)
                    logger.info("Waiting for 28s phase...")
                    for _ in range(350): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            # ২৮ বা ২৯ সেকেন্ড খোঁজা
                            if re.search(r'0\s*0\s*[:.]?\s*(28|29)', body_text):
                                break
                        except: pass
                        await asyncio.sleep(0.05) # সুপার ফাস্ট চেক

                    # 💡 Big/Small ক্লিক (সরাসরি জাভাস্ক্রিপ্ট দিয়ে, যা ১ মিলিসেকেন্ডে কাজ করে)
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
                    await page.wait_for_timeout(800) # মডাল ওপেন হওয়ার জন্য ০.৮ সেকেন্ড

                    # 💡 Amount বসানো এবং Confirm ক্লিক
                    try:
                        # ১. Amount
                        inp = page.locator('input[type="text"], input[type="number"]').first
                        await inp.wait_for(state="visible", timeout=3000)
                        await inp.fill(str(int(bet_amount)))

                        # ২. I agree
                        agree = page.locator('text="I agree"').first
                        if await agree.is_visible(): await agree.click(force=True)

                        # ৩. Total amount বাটন
                        confirm_btn = page.locator("text=/Total amount/i").last
                        await confirm_btn.wait_for(state="visible", timeout=3000)
                        await confirm_btn.click(force=True)
                    except Exception as e:
                        logger.error(f"Click error: {e}")

                    # 💡 রেজাল্ট চেক (ব্রাউজার রিলোড না করেই)
                    await asyncio.sleep(32) # রেজাল্টের জন্য ৩২ সেকেন্ড অপেক্ষা

                    # আমরা পেজ রিলোড না করে, শুধু ব্যালেন্সের টেক্সট চেক করব
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
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: {current_step_idx+1}")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
        finally:
            await browser.close()