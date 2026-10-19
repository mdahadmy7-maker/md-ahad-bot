import asyncio
import logging
import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG 
# ⚠️ এখানে আপনার টেলিগ্রাম বটের টোকেন বসান
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAHdpHDCFqCJkku3JcfnjNmU3PylHiY5FwY" 
SITE_URL = "https://www.hgnice.vip" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "task": None, "steps": [], "step_idx": 0, 
            "target": 0, "profit": 0, "bet_choice": "RANDOM",
            "balance": "0.00", "account_uid": "Unknown"
        }
    return user_state[uid]

# ───────────────────────────────────────────
# হেল্পার: লগইন সফল হয়েছে কিনা চেক করা
# ───────────────────────────────────────────
async def check_login_success(page):
    try:
        for _ in range(20): # ১০ সেকেন্ড অপেক্ষা করবে
            await page.wait_for_timeout(500)
            
            # ১. ভুল পাসওয়ার্ড চেক
            if await page.locator('text="Wrong account or password"').first.is_visible():
                return False, "Wrong account or password (Error: 147)"
                
            # ২. সফল লগইন চেক
            if await page.locator('text="UID"').first.is_visible():
                return True, "Success"
                
        return False, "Timeout: Website dashboard did not load. Maybe Number is wrong."
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

async def get_account_info(page):
    try:
        await page.wait_for_timeout(2000)
        page_text = await page.inner_text("body")
        
        uid = "Unknown"
        uid_match = re.search(r'UID\s*\|\s*(\d+)', page_text, re.IGNORECASE)
        if uid_match: uid = uid_match.group(1)
            
        balance = "0.00"
        balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
        if balance_match: balance = balance_match.group(1)
                
        return balance, uid
    except Exception:
        return "0.00", "Unknown"

# ───────────────────────────────────────────
# মূল অটো-বেট লুপ (রিয়েল ক্লিক ও টাইপিং)
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx, loading_msg_id):
    state = get_state(uid)
    
    async with async_playwright() as p:
        # পিসিতে টেস্ট করতে False করুন, সার্ভারে True রাখুন
        browser = await p.chromium.launch(headless=True) 
        
        # ব্রাউজারকে মোবাইল হিসেবে সাজানো (যাতে ওয়েবসাইট মোবাইল ভার্সন লোড করে)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000) 
            
            try:
                await page.locator('text="Log in"').first.click(timeout=3000)
                await page.wait_for_timeout(2000)
            except:
                pass 

            login_phone = state["phone"]
            if login_phone.startswith("880"): login_phone = login_phone[3:]
            elif login_phone.startswith("88"): login_phone = login_phone[2:]

            # 💡 ১. ফোন নাম্বার বক্সে মাউস ক্লিক করে টাইপ করা
            try:
                # প্রথম ইনপুট বক্সটি খুঁজে সেখানে ক্লিক করবে এবং টাইপ করবে
                phone_input = page.locator('input[type="text"], input[type="tel"], input[type="number"]').first
                await phone_input.click(timeout=5000)
                await phone_input.fill(login_phone) # সরাসরি ভ্যালু বসানো
                await page.keyboard.press("Enter") # কীবোর্ডের এন্টার চাপা
                await page.wait_for_timeout(1000)
            except Exception as e:
                logger.error(f"Phone fill error: {e}")

            # 💡 ২. পাসওয়ার্ড বক্সে মাউস ক্লিক করে টাইপ করা
            try:
                # পাসওয়ার্ড ইনপুট বক্সটি খুঁজে সেখানে ক্লিক করবে এবং টাইপ করবে
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click(timeout=5000)
                await pass_input.fill(state["password"])
                await page.wait_for_timeout(1000)
            except Exception as e:
                logger.error(f"Password fill error: {e}")
            
            # 💡 ৩. লগইন বাটনে ক্লিক করা (আসল মাউস ক্লিক)
            try:
                # বাটনের লেখা 'Log in' বা 'Login' খুঁজে সেখানে ক্লিক করবে
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=5000)
            except:
                try:
                    await page.locator('text="Log in"').last.click(timeout=5000)
                except:
                    await page.locator('div[class*="btn"]').last.click(timeout=5000) # ব্যাকআপ বাটন
            
            # --- লগইন রেজাল্ট চেক ---
            login_success, login_msg = await check_login_success(page)
            
            # লোডিং মেসেজ ডিলিট করা
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            
            if not login_success:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\n\n{login_msg}", parse_mode="Markdown")
                state["running"] = False
                await browser.close()
                return
            
            # সফল লগইন
            bal, user_uid = await get_account_info(page)
            state["balance"] = bal
            state["account_uid"] = user_uid
            state["logged_in"] = True
            masked_phone = f"****{login_phone[-4:]}"
            
            login_msg_text = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ **Phone:** {masked_phone}\n"
                f"👤 **UID:** {state['account_uid']}\n"
                f"💰 **Balance:** ৳ {state['balance']}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=login_msg_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
            
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **BOT ERROR:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    get_state(update.effective_user.id)["running"] = False
    await update.message.reply_text("🔐 **LOGIN TO ACCOUNT**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔐 LOGIN", callback_data="start_login")]]))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"📱 Number: {text}\n\n🔑 **Now enter your password:**")
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...** [░░░░░░░░░░] 0%")
        for i in range(1, 11):
            await asyncio.sleep(0.15)
            try: await loading_msg.edit_text(f"🔄 **CONNECTING...** [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx, loading_msg.message_id))
        return

    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        await update.message.reply_text("🚪 **LOGGED OUT**")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=uid, text="📱 **Enter your phone number:**\n_Example: 8801884495095_")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()