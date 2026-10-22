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
            "trade_running": False, "task": None, "current_step": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 ২. API থেকে প্রেডিকশন বের করার ফাংশন
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
            
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        return "SMALL", "Unknown"

# ───────────────────────────────────────────
# ৩. মূল লগইন এবং বেটিং ফাংশন
# ───────────────────────────────────────────
async def run_bot(uid, ctx, loading_msg_id, phone, password):
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
        try:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
                viewport={"width": 412, "height": 915}
            )
            page = await context.new_page()
            page.set_default_timeout(60000) # গ্লোবাল টাইমআউট
            
            # ---------------- ১. লগইন ----------------
            await update_loading(10)
            await page.goto(SITE_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            await update_loading(30)
            try:
                # মানুষের মতো টাইপিং
                await page.locator('input[placeholder="Please enter the phone number"]').click()
                await page.keyboard.type(login_phone, delay=100)
                await page.wait_for_timeout(500)
                
                await page.locator('input[type="password"]').first.click()
                await page.keyboard.type(password, delay=100)
                await page.wait_for_timeout(1000)
            except Exception as e:
                logger.error(f"Input fill error: {e}")

            await update_loading(50)
            # লগইন ক্লিক
            try:
                await page.locator('button:has-text("Log in")').last.click(force=True, timeout=10000)
            except:
                await page.get_by_text("Log in", exact=True).last.click(force=True, timeout=10000)
            
            await update_loading(70)
            await page.wait_for_timeout(5000) # লগইন প্রসেস হওয়ার জন্য অপেক্ষা
            
            # পপআপ থাকলে বন্ধ করা
            for _ in range(5):
                try:
                    await page.evaluate("""
                        (function() {
                            let els = document.querySelectorAll('button, div, span, a');
                            for (let el of els) {
                                let text = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (text === 'confirm' || text === 'ok' || text === 'close') {
                                    el.click(); return;
                                }
                            }
                        })();
                    """)
                    await page.wait_for_timeout(1000)
                except: pass

            await update_loading(85)
            # Account পেজে গিয়ে ডেটা নেওয়া
            try:
                await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
            except: pass

            await update_loading(95)
            login_status = "failed"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text or "Error: 147" in page_text:
                    login_status = "failed"
                    break
                
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(1000)

            await update_loading(100)
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED ({phone})**\n\nসঠিক নাম্বার/পাসওয়ার্ড দিন অথবা স্ক্রিনশটে দেখুন কী সমস্যা।")
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

            # অপেক্ষা করা হচ্ছে ইউজার বাটন চাপার জন্য
            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. বেটিং লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳ {current_bal - initial_balance:.2f}")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text="⚠️ **সব স্টেপ শেষ!**")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    choice, current_period = get_history_and_prediction()

                    # 💡 WinGo তে যাওয়া
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                    try:
                        # Lottery ক্লিক
                        await page.locator('text="Lottery"').first.click(force=True, timeout=10000)
                        await page.wait_for_timeout(2000)
                        
                        # Win Go ক্লিক
                        await page.locator('text="Win Go"').first.click(force=True, timeout=10000)
                        await page.wait_for_timeout(4000)
                    except Exception as e:
                        logger.error(f"Navigation error: {e}")

                    # Big/Small ক্লিক
                    try:
                        target_locator = page.get_by_text(choice, exact=True).last
                        await target_locator.click(force=True, timeout=10000)
                        await page.wait_for_timeout(1000)
                    except:
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **{choice} বাটনে ক্লিক করা যায়নি!**")
                        raise Exception("Button not found")

                    # Confirm
                    try:
                        await page.locator('text="Confirm"').last.click(force=True, timeout=3000)
                    except: pass

                    await ctx.bot.send_message(chat_id=uid, text=f"🤖 **BET PLACED:** {choice}\nAmount: ৳ {bet_amount}\nWaiting for result...")
                    
                    await asyncio.sleep(32)

                    # রেজাল্ট চেক
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000) 
                    new_text = await page.inner_text("body")
                    new_bal_match = re.search(r'Total\s*balance\s*[৳:]?\s*([\d.]+)', new_text, re.IGNORECASE)
                    
                    if new_bal_match:
                        new_bal = float(new_bal_match.group(1))
                        if new_bal > current_bal:
                            state["balance"] = new_bal
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nBalance: ৳ {new_bal:.2f}")
                        else:
                            state["balance"] = new_bal
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nBalance: ৳ {new_bal:.2f}\nNext Step: {current_step_idx+1}")

                except Exception as e:
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)
    welcome_text = "👇 **Press the button below to LOGIN**"
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter your password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        if state.get("task"): state["task"].cancel()
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**\n[░░░░░░░░░░] 0%")
        state["task"] = asyncio.create_task(run_bot(uid, ctx, loading_msg.message_id, state["temp_phone"], text))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter your TARGET profit amount:")
        return
        
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["awaiting"] = "steps"
            await update.message.reply_text("🚀 Enter your STEP COUNT (e.g. 5):")
        except: await update.message.reply_text("❌ Number only!")
        return
        
    if state.get("awaiting") == "steps":
        try:
            state["steps"] = int(text)
            state["step_amounts"] = []
            state["current_step"] = 0
            state["awaiting"] = "step_amount"
            await update.message.reply_text(f"💵 Step 1 — amount?")
        except: await update.message.reply_text("❌ Number only!")
        return

    if state.get("awaiting") == "step_amount":
        try:
            state["step_amounts"].append(float(text))
            state["current_step"] += 1
            if state["current_step"] < state["steps"]:
                await update.message.reply_text(f"💵 Step {state['current_step']+1} — amount?")
            else:
                state["awaiting"] = None
                inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="trade")]])
                await update.message.reply_text("✅ Steps saved!\n👇 Press START TRADE to begin.", reply_markup=inline_kb)
        except: await update.message.reply_text("❌ Number only!")
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 STOPPED")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 Enter your phone number:")
    elif query.data == "trade":
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