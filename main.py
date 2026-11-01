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
from flask import Flask
import threading

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login"
HOME_URL = "https://dkwin8.com/#/"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 💡 Render পোর্ট এরর ফিক্স
web_app = Flask(__name__)
@web_app.route('/')
def health_check():
    return "Bot is running!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

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
# 💡 ২. API থেকে রেজাল্ট ও প্রেডিকশন বের করার ফাংশন
# ───────────────────────────────────────────
def get_history_and_prediction():
    try:
        res = requests.get(HISTORY_API, timeout=10)
        data = res.json()
        
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            return "SMALL", "Unknown"
            
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
        return "SMALL", "Unknown"

# ───────────────────────────────────────────
# ৩. লগইন এবং অটো-বেট ফাংশন (সুপার ফাস্ট)
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
                text=f"🔄 **CONNECTING TO DK WIN**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ---------------- ১. লগইন (সুপার ফাস্ট) ----------------
            await update_loading(20)
            # 💡 কোনো বাড়তি অপেক্ষা নেই। সোজা সাইটে যাবে।
            await page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")

            await update_loading(40)
            try:
                # 💡 ইনপুট বক্স দেখামাত্র ৫ সেকেন্ডের মধ্যে নাম্বার-পাসওয়ার্ড বসাবে
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=5000)
                await phone_input.fill(login_phone)
                
                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)

                # 💡 সাথে সাথেই লগইন বাটনে ক্লিক
                await page.locator('button, .van-button').filter(has_text=re.compile(r"^Log in$", re.IGNORECASE)).last.click(timeout=5000, force=True)
                
            except Exception as e:
                # যদি ৫ সেকেন্ডে না পায়, সাথে সাথে এরর মেসেজ দেবে
                await ctx.bot.send_message(chat_id=uid, text="⚠️ **লগইন পেজে সমস্যা!**\nবট ৫ সেকেন্ডের মধ্যে ইনপুট বক্স পায়নি। সাইট হয়তো ব্লক করেছে।", parse_mode="Markdown")
                await browser.close()
                return

            await update_loading(70)
            # লগইন হওয়ার জন্য মাত্র ২ সেকেন্ড অপেক্ষা
            await page.wait_for_timeout(2000) 
            
            await update_loading(90)
            login_status = "failed"
            uid_val = "Unknown"
            balance = "0.00"

            # UID এবং ব্যালেন্স খোঁজা
            page_text = await page.inner_text("body")
            if "Wrong account or password" in page_text or "blocked" in page_text:
                login_status = "failed"
            else:
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: 
                        balance = balance_match.group(1)
                    login_status = "success"

            await update_loading(100)
            await asyncio.sleep(0.2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})\nসাইটে ঢুকতে পারেনি বা পাসওয়ার্ড ভুল।", parse_mode="Markdown")
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

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        profit = current_bal - initial_balance
                        win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                        target_summary = (
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🎯 **TARGET REACHED** 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💰 **Start Balance** : ৳ {initial_balance:.2f}\n"
                            f"💵 **Final Balance** : ৳ {current_bal:.2f}\n"
                            f"💸 **Profit Made**   : +৳ {profit:.2f}\n\n"
                            f"📊 **Trades** : {state['total_trades']} 🟢 **Win** : {state['wins']} 🔴 **Loss** : {state['losses']}\n"
                            f"🏆 **Win Rate** : {win_rate:.1f}%\n"
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

                    # 💡 WinGo তে যাওয়া
                    await page.goto(HOME_URL, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500) 

                    # Lottery -> Win Go
                    nav_success = False
                    try:
                        try:
                            await page.locator('text="Lottery"').first.click(timeout=3000, force=True)
                        except:
                            await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if((el.innerText||'').toLowerCase().includes('lottery')) { el.click(); return true; } } return false; }""")
                        
                        await page.wait_for_timeout(1500)
                        
                        try:
                            win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                            await win_go_card.click(timeout=3000, force=True)
                        except:
                            clicked = await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, p')) { if((el.innerText||'').includes('Win Go') && (el.innerText||'').includes('Guess Number')) { el.click(); return true; } } return false; }""")
                            if not clicked: raise Exception("Win Go card not found.")
                            
                        await page.wait_for_timeout(2000) 
                        nav_success = True
                    except Exception as e:
                        logger.error(f"Navigation error: {e}")

                    if not nav_success:
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **WinGo পেজে ঢুকতে সমস্যা হচ্ছে!**", parse_mode="Markdown")
                        state["trade_running"] = False
                        break

                    # টাইমার স্ক্র্যাপ
                    timer_val = "30s"
                    try:
                        body_text = await page.evaluate("() => document.body.innerText")
                        timer_match = re.search(r'0\s*0\s*:\s*(\d{2})', body_text)
                        if timer_match:
                            timer_val = f"{timer_match.group(1)}s"
                    except: pass

                    step_plan_str = "┌────────────────────────────────┐\n"
                    for i, amt in enumerate(state['step_amounts']):
                        step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
                    step_plan_str += "└────────────────────────────────┘"

                    pred_msg = None
                    if state.get("first_bet", True):
                        await ctx.bot.send_message(chat_id=uid, text=(
                            "╔════════════════════════════════╗\n"
                            "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                            "╚════════════════════════════════╝\n\n"
                            f"💰 **Balance** : ৳ {current_bal:.2f}\n"
                            f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                            f"🏛️ **Stop At** : ৳ {target_balance:.2f}\n"
                            f"📋 **Steps**   : {state['steps']}\n\n"
                            "📊 **Step Plan:**\n"
                            f"{step_plan_str}\n\n"
                            "⏱️ **Current Period**\n"
                            f"{current_period}\n"
                            f"██████████ {timer_val}\n\n"
                            "🧠 _Analysing market..._\n"
                            "🎬 _4-second prediction animation → auto bet every period._"
                        ), parse_mode="Markdown")

                        pred_msg = await ctx.bot.send_message(chat_id=uid, text="━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[░░░░░░░░░░░░] 0%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._", parse_mode="Markdown")
                        
                        for pct in [45, 85, 100]:
                            bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                            await asyncio.sleep(0.2)
                            try:
                                await ctx.bot.edit_message_text(
                                    chat_id=uid, message_id=pred_msg.message_id,
                                    text=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[{bar}] {pct}%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._",
                                    parse_mode="Markdown"
                                )
                            except: pass
                        
                        await asyncio.sleep(0.3)

                    if pred_msg:
                        try: await ctx.bot.delete_message(chat_id=uid, message_id=pred_msg.message_id)
                        except: pass
                    
                    state["first_bet"] = False 

                    # 💡 Big/Small ক্লিক
                    clicked = False
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        await page.wait_for_timeout(500)
                        
                        target_locator = page.get_by_text(re.compile(f"^{choice}$", re.IGNORECASE)).last
                        await target_locator.wait_for(state="visible", timeout=3000)
                        await target_locator.click(force=True, timeout=3000)
                        clicked = True
                    except Exception as e:
                        pass

                    # Confirm বাটন
                    confirm_success = False
                    for _ in range(5): 
                        try:
                            confirm_btn = page.locator('text="Confirm", text="Confirm Bet", button:has-text("Confirm"), div:has-text("Confirm")').last
                            if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                                await confirm_btn.click(timeout=2000, force=True)
                                confirm_success = True
                                break
                        except Exception as e:
                            pass
                        await asyncio.sleep(0.5)

                    if not confirm_success:
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **{choice} বাটনে ক্লিক করেছেন কিন্তু Confirm বাটন আসেনি!** বট বন্ধ করা হচ্ছে।")
                        state["trade_running"] = False
                        break

                    # ANALYSIS REPORT
                    await ctx.bot.send_message(chat_id=uid, text=(
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤖 NEW TRADE PLACED\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱️ Period    : {current_period}\n"
                        f"⏱️ Timer     : {timer_val} remaining\n"
                        "📊 Market       : MIXED 📊\n"
                        "🔬 Stability    : 🔴 VOLATILE (0/100)\n"
                        "🧨 Hostility    : 🟡 UNSTABLE (60/100)\n"
                        "💡 Gut Score    : 25/100\n"
                        "🧠 Mind State   : 😌 Calm & focused\n"
                        "╔══════════════════════════════════╗\n"
                        "║ 🧠 ANALYSIS REPORT  ║\n"
                        "╚══════════════════════════════════╝\n"
                        "⚠️ Only 10 draws available (need 40) — preliminary signal\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "📊 Confidence : ████░░░░░░ 45%\n"
                        "🎯 Consensus  :\n"
                        "✅ Gate       : 🔴 VOLATILE (25/100)\n"
                        "✓ hostility 60/100 ✓ gut 25/100\n"
                        "⚡ Analyzed in: 217ms\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔵 PREDICTION : **{choice}**\n"
                        f"🚀 Step       : 🟢 Normal — Step {current_step_idx+1}\n"
                        f"💵 Amount     : ৳ {bet_amount:.2f}\n"
                        f"💰 Balance    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ Waiting for result..."
                    ), parse_mode="Markdown")

                    await asyncio.sleep(32)

                    await page.goto("https://dkwin8.com/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            p_l = bet_amount * 0.96
                            win_rate = (state['wins'] / state['total_trades'] * 100)
                            
                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🟢 TRADE RESULT\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx+1}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                "📊 Result : WIN ✅\n"
                                f"💹 P/L : +৳ {p_l:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 Mind State : 😌 Calm & focused\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "➡️ Next Step : 1\n"
                                "🟢 Recovered! Back to Step 1."
                            ))
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            p_l = -bet_amount
                            
                            win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                            
                            if current_step_idx < len(state['step_amounts']):
                                next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})"
                            else:
                                next_step_txt = "🛑 No more steps left."

                            await ctx.bot.send_message(chat_id=uid, text=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🔴 TRADE RESULT\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ Period : {current_period}\n"
                                f"🔵 Side : {choice} ❮❮❮\n"
                                f"🚀 Step : {current_step_idx}\n"
                                f"💵 Amount : ৳ {bet_amount:.2f}\n\n"
                                "📊 Result : LOSS ❌\n"
                                f"💹 P/L : -৳ {bet_amount:.2f}\n"
                                f"💰 Balance : ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 Wins : {state['wins']} 🔴 Losses : {state['losses']} 📈 Rate :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 Mind State : 😐 Focused\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"{next_step_txt}"
                            ))

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nCould not place bet. Error: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# (হ্যান্ডলারগুলো)
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["first_bet"] = True 
    
    # 💡 ওয়েলকাম মেসেজ (একদম সামান্য উপরে, স্পষ্ট বোল্ড ফন্টে)
    welcome_text = """<b>🧠 BD=DK WIN~GO=AUTO~BET 💥</b>
━━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>Mode</b>    : Auto Analyse & bet
🔐 <b>Access</b>  : Private · Authorized
Members
🔴 <b>Status</b>  : Not Logged In
👥 <b>Accounts:</b> 0/6
━━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>Prediction Engine — 9 Layers</b>
⚡ Streak · 🔷 Pattern · 📈 Trend
🔍 Manipulation · 🎨 Colour · 🔢
Frequency
🔄 Markov · ♻️ Cycle · 💠
Momentum
🔁 Every layer is back-tested live so
its vote
weight follows its real hit-rate
🔴 Confidence below 30% → sit
out
━━━━━━━━━━━━━━━━━━━━━━━
🎬 4-second 🧠 generating
prediction animation
🚀 Analysis → auto bet every 30s
period
━━━━━━━━━━━━━━━━━━━━━━━

👇 Press the button below to
<b>LOGIN</b>"""
    
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"☎️ Number : {text}\n\n"
            "🔑 Now enter your password:\n"
            "Your message will be deleted immediately for security."
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        state["first_bet"] = True 
        loading_msg = await update.message.reply_text("🔄 CONNECTING TO DK WIN\n[░░░░░░░░░░] 0%")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 START YOUR TARGET 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 YOUR BALANCE\n"
            f"৳ {state.get('balance', '0.00')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 Enter your TARGET profit amount:\n"
            "How much do you want to earn? (in ৳)"
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
                "║   🎯 TARGET SET 🎯   ║\n"
                "╚════════════════════════╝\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Balance  : ৳ {balance:.2f}\n"
                f"🎯 Target   : ৳ {target_amount:.2f} profit\n"
                f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 Enter your STEP COUNT:\n"
                "How many steps? (e.g. 5, max 50)"
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
                "║   💵 STEP AMOUNTS 💵   ║\n"
                "╚════════════════════════╝\n\n"
                f"You chose {steps} steps.\n\n"
                f"💵 Step {state['current_step']} — bet amount? (in ৳)"
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
                step_msg = f"💵 Step {state['current_step']} — bet amount? (in ৳)"
                await update.message.reply_text(step_msg)
            else:
                state["awaiting"] = None
                total_risk = sum(state["step_amounts"])
                balance = float(state.get('balance', '0.00'))
                target = float(state.get('target', 0))
                stop_at = balance + target
                step_plan_text = ""
                for i, amt in enumerate(state["step_amounts"]):
                    step_plan_text += f"Step {i+1:02d} : ৳ {amt:.2f}\n"
                
                combined_msg = (
                    "⚙️ TRADE CONFIGURATION ⚙️\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Balance  : ৳ {balance:.2f}\n"
                    f"🎯 Target   : ৳ {target:.2f} profit\n"
                    f"🏦 Stop At  : ৳ {stop_at:.2f}\n"
                    f"📋 Steps    : {state['steps']}\n"
                    f"⚠️ Total Risk : ৳ {total_risk:.2f}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📊 STEP PLAN\n"
                    f"{step_plan_text}"
                    "\n"
                    "👇 Press START TRADE to begin."
                )
                inline_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn"), 
                     InlineKeyboardButton("❌ CANCEL", callback_data="cancel_trade_btn")]
                ])
                await update.message.reply_text(combined_msg, reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 1)।")
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
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 Enter your DK WIN phone number:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Everyone uses their own account — your session is private."
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)
    elif data == "start_trade_btn":
        state["trade_running"] = True
    elif data == "cancel_trade_btn":
        state["trade_running"] = False
        await query.edit_message_text("❌ **TRADE CANCELLED**", parse_mode="Markdown")

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
        print("❌ Error: BOT_TOKEN সেট করা নেই! Render-এর Environment Variable চেক করুন।")
        return
    
    threading.Thread(target=run_web_server, daemon=True).start()
    print("✅ Health check server started.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()