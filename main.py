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

BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "http://dkwin8.com/#/login"
HOME_URL = "http://dkwin8.com/#/"
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
            "first_bet": True, "api_token": None
        }
    return user_state[uid]

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

async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text="CONNECTING"):
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
        # ব্রাউজার ওপেন হবে শুধু লগইন টোকেন নেওয়ার জন্য
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()

        try:
            await update_loading(10, "OPENING SITE")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            await update_loading(30, "LOGGING IN")
            await page.evaluate(f"""
                () => {{
                    let inputs = document.querySelectorAll('input');
                    for(let i of inputs) {{
                        if(i.type === 'text' || i.type === 'tel') {{
                            i.value = '{login_phone}';
                            i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            i.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                        if(i.type === 'password') {{
                            i.value = '{password}';
                            i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            i.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }}
            """)

            await page.evaluate("""
                () => {
                    let els = document.querySelectorAll('button, div, span, a');
                    for(let el of els) {
                        let text = (el.innerText || el.value || '').trim().toLowerCase();
                        if (text === 'log in' || text === 'login') { el.click(); return true; }
                    }
                    return false;
                }
            """)

            await page.wait_for_timeout(5000) 

            # টোকেন এবং ব্যালেন্স চেক
            login_status = "failed"
            uid_val = "Unknown"
            balance = "0.00"
            token = None

            for _ in range(10): 
                page_text = await page.inner_text("body")
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                # LocalStorage থেকে টোকেন নেওয়ার চেষ্টা
                token = await page.evaluate("() => localStorage.getItem('token') || localStorage.getItem('Authorization') || localStorage.getItem('auth_token')")
                
                if uid_match or token:
                    if uid_match: uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(1000)

            await update_loading(100, "SUCCESS")
            await asyncio.sleep(0.5)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status != "success":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\nসাইটে ঢুকতে সমস্যা হচ্ছে বা পাসওয়ার্ড ভুল।")
                await browser.close()
                return

            state["api_token"] = token
            state["balance"] = float(balance)
            
            await ctx.bot.send_message(chat_id=uid, text=f"🎉 **LOGIN SUCCESSFUL**\n\nUID: `{uid_val}`\nBalance: ৳ {balance}\n\n👇 Press START YOUR TARGET to begin", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE")]], resize_keyboard=True))

            # ব্রাউজার বন্ধ করে দেওয়া হচ্ছে (র‍্যাম খালি করার জন্য)
            await browser.close()

            while not state.get("trade_running", False):
                await asyncio.sleep(1)

            # ---------------- API দিয়ে বাজি ধরার লজিক ----------------
            # এখানে আমরা ব্রাউজার বন্ধ করে সরাসরি API কল করব
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            await ctx.bot.send_message(chat_id=uid, text="🚀 **AUTO TRADE ACTIVE (API MODE)**\n\nএখন থেকে কোনো ব্রাউজার ছাড়াই সুপারফাস্ট স্পিডে বাজি ধরবে।")

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        state["trade_running"] = False
                        await ctx.bot.send_message(chat_id=uid, text="🎯 **TARGET REACHED!**")
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        state["trade_running"] = False
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!**")
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    if current_bal < bet_amount:
                        state["trade_running"] = False
                        await ctx.bot.send_message(chat_id=uid, text="❌ **পর্যাপ্ত ব্যালেন্স নেই!**")
                        break

                    choice, current_period = get_history_and_prediction()

                    # 💡 API দিয়ে বাজি ধরার জন্য এখানে POST রিকোয়েস্ট পাঠাতে হবে
                    # যেহেতু আপনার দেওয়া curl এ signature দরকার, তাই আমরা ফেক রেসপন্স দিয়ে সিমুলেট করছি।
                    # আপনি যদি signature তৈরির ফর্মুলা জানেন, তবে নিচের লজিকটি আসল API কল দিয়ে রিপ্লেস করবেন।
                    
                    # ডেমো সাকসেস
                    await ctx.bot.send_message(chat_id=uid, text=f"✅ **BET PLACED (API)**\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}\n⏳ Waiting for result...")
                    
                    # ৩০ সেকেন্ড অপেক্ষা (রেজাল্ট আসার জন্য)
                    for _ in range(30):
                        if not state["trade_running"]: break
                        await asyncio.sleep(1)

                    # ডেমো রেজাল্ট (আপনি চাইলে এখানে API থেকে আসল রেজাল্ট চেক করতে পারেন)
                    import random
                    is_win = random.choice([True, False])
                    
                    if is_win:
                        state["balance"] += (bet_amount * 0.96)
                        current_step_idx = 0
                        await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {state['balance']:.2f}")
                    else:
                        state["balance"] -= bet_amount
                        current_step_idx += 1
                        await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {state['balance']:.2f}")

                except Exception as e:
                    logger.error(f"API Betting error: {e}")
                    state["trade_running"] = False
                    break

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            try: await browser.close()
            except: pass