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
WINGO_URL = "https://www.hgnice.vip/#/WinGo"
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
            "wins": 0, "losses": 0, "total_trades": 0
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
# ৩. লগইন এবং অটো-বেট (রিয়েল-টাইম লোডিং ও শক্তিশালী পপআপ কিলার)
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    # 💡 রিয়েল-টাইম লোডিং আপডেট করার ফাংশন
    async def update_loading(percent, status_text):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{status_text}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        await update_loading(10, "OPENING BROWSER...")
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ---------------- ১. সাইটে প্রবেশ ----------------
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_selector('input[type="text"]', timeout=15000)
            
            # পপআপ বন্ধ করা (যদি থাকে)
            for _ in range(3):
                try:
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
                    await page.wait_for_timeout(500)
                except: pass

            # ---------------- ২. ইনফরমেশন বসানো ----------------
            await update_loading(30, "ENTERING CREDENTIALS...")
            await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
            await page.wait_for_timeout(500)
            await page.locator('input[type="password"]').first.fill(password)
            await page.wait_for_timeout(500)

            # ---------------- ৩. লগইন ক্লিক ----------------
            await update_loading(50, "CLICKING LOGIN...")
            try:
                # একাধিক পদ্ধতিতে লগইন বাটনে ক্লিক করা হবে
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=5000)
            except:
                try:
                    await page.locator('button:has-text("Log in")').last.click(timeout=5000)
                except:
                    await page.evaluate("""
                        (function() {
                            let elements = document.querySelectorAll('button, div, span');
                            for (let el of elements) {
                                let text = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (text === 'log in' || text === 'login') { el.click(); return true; }
                            }
                        })();
                    """)

            # ---------------- ৪. ড্যাশবোর্ড লোড হওয়ার অপেক্ষা ----------------
            await update_loading(70, "VERIFYING ACCOUNT...")
            
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"
            
            # ১৫ সেকেন্ড পর্যন্ত অপেক্ষা করবে
            for i in range(15):
                await update_loading(70 + (i * 1.5), "WAITING FOR DASHBOARD...")
                
                # পপআপ (Announcement) আবার আসলে বন্ধ করা
                try:
                    popup_btn = page.locator('button:has-text("Confirm"), div:has-text("Confirm"), span:has-text("Confirm")').last
                    if await popup_btn.is_visible(timeout=500):
                        await popup_btn.click(force=True, timeout=1000)
                except: pass

                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
                    login_status = "failed"
                    break
                
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: 
                        balance = balance_match.group(1)
                    login_status = "success"
                    break
                
                await page.wait_for_timeout(1000)

            await update_loading(100, "COMPLETED!")

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            # ---------------- ৫. রেজাল্ট চেক ----------------
            if login_status == "failed":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\nWrong account or password.")
                await browser.close()
                return
                
            if uid_val == "Unknown":
                # লগইন না হলে স্ক্রিনশট নিয়ে টেলিগ্রামে পাঠাবে
                screenshot_path = f"login_error_{uid}.png"
                await page.screenshot(path=screenshot_path)
                await ctx.bot.send_photo(
                    chat_id=uid, 
                    photo=open(screenshot_path, 'rb'), 
                    caption="⚠️ **LOGIN TIMEOUT!**\nDashboard load hoyni. Ki error hoyeche screenshot e dekhen."
                )
                await browser.close()
                return

            # সফল লগইন
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

            # ---------------- ৬. বেটিং লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 TARGET REACHED!\nProfit: ৳ {current_bal - initial_balance:.2f}")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** ব্যালেন্স: ৳{current_bal:.2f}।")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = get_history_and_prediction()

                    await page.goto(WINGO_URL, timeout=60000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000) 

                    # WinGo পেজের পপআপ বন্ধ
                    for _ in range(3):
                        try:
                            await page.evaluate("""
                                (function() {
                                    let elements = document.querySelectorAll('button, div, span');
                                    for (let el of elements) {
                                        let text = (el.innerText || el.textContent || '').trim().toLowerCase();
                                        if (text === 'confirm' || text === 'ok' || text === 'close') { el.click(); return true; }
                                    }
                                })();
                            """)
                            await page.wait_for_timeout(1000)
                        except: pass

                    # Big / Small ক্লিক
                    clicked = False
                    try:
                        target_locator = page.locator(f'div:text-is("{choice}"), span:text-is("{choice}")').last
                        await target_locator.wait_for(state="visible", timeout=10000)
                        await target_locator.click(force=True, timeout=5000)
                        clicked = True
                    except:
                        pass

                    if not clicked:
                        raise Exception(f"{choice} button not found.")

                    await page.wait_for_timeout(1000) 
                    try:
                        await page.locator('text="Confirm"').last.click(force=True, timeout=3000)
                    except: pass

                    await ctx.bot.send_message(chat_id=uid, text=f"🤖 **BET PLACED:** {choice}\nAmount: ৳ {bet_amount}\nWaiting 32s for result...")

                    await asyncio.sleep(32)

                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!** Balance: ৳ {new_balance:.2f}")
                        else:
                            state["balance"] = new_balance
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!** Balance: ৳ {new_balance:.2f}\nMoving to Step {current_step_idx+1}")

                except Exception as e:
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
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
        await update.message.reply_text(
            f"☎️ Number: {text}\n\n"
            "🔑 Now enter your password:"
        )
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        
        # পাসওয়ার্ড মেসেজ ডিলিট
        try: 
            await update.message.delete()
        except: 
            pass
        
        if state.get("task"): state["task"].cancel()
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        state["task"] = asyncio.create_task(playwright_login_and_bet(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        target_msg = (
            "🚀 **START YOUR TARGET** 🚀\n"
            f"💰 YOUR BALANCE: ৳ {state.get('balance', '0.00')}\n"
            "🎯 Enter your TARGET profit amount:"
        )
        await update.message.reply_text(target_msg)
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text(f"✅ Target: ৳ {text}\n\n🚀 Enter your STEP COUNT (e.g. 5):")
        except ValueError:
            await update.message.reply_text("❌ শুধু সংখ্যা লিখুন।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            state["steps"] = steps
            state["step_amounts"] = [] 
            state["current_step"] = 1
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — bet amount? (in ৳)")
        except ValueError:
            await update.message.reply_text("❌ শুধু সংখ্যা লিখুন।")
        return

    if state.get("awaiting") == "step_amount":
        try:
            amount = float(text)
            state["step_amounts"].append(amount)
            state["current_step"] += 1
            if state["current_step"] <= state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount? (in ৳)")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
                await update.message.reply_text("✅ Steps saved!\n👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except ValueError:
            await update.message.reply_text("❌ শুধু সংখ্যা লিখুন।")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["trade_running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 LOGGED OUT")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your HGNICE phone number:")
    elif query.data == "start_trade_btn":
        await query.message.delete()
        state["trade_running"] = True

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