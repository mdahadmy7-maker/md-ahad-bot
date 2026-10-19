import asyncio
import logging
import random
import os
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
# ২. হেল্পার: লগইন সফল হয়েছে কিনা চেক করা (রিয়েল-টাইম)
# ───────────────────────────────────────────
async def check_login_success(page):
    try:
        # ১৫ সেকেন্ড পর্যন্ত অপেক্ষা করবে, কিন্তু প্রতি ০.৫ সেকেন্ড পর পর চেক করবে
        for _ in range(30): 
            await page.wait_for_timeout(500)
            
            # ১. ভুল পাসওয়ার্ড চেক (Error 147)
            error_popup = page.locator('text="Wrong account or password"').first
            if await error_popup.is_visible():
                return False, "Wrong account or password (Error: 147)"
                
            # ২. সফল লগইন চেক (ড্যাশবোর্ডে UID আছে কি না)
            uid_locator = page.locator('text="UID"').first
            if await uid_locator.is_visible():
                return True, "Success"
                
        # ১৫ সেকেন্ড পরেও কিছু না পেলে
        return False, "Timeout: Website did not respond within 15 seconds."
        
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

# ───────────────────────────────────────────
# ৩. হেল্পার: ব্যালেন্স ও UID বের করা
# ───────────────────────────────────────────
async def get_account_info(page):
    try:
        await page.wait_for_timeout(2000)
        balance = "0.00"
        uid = "Unknown"
        try:
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*\|\s*(\d+)', page_text, re.IGNORECASE)
            if uid_match:
                uid = uid_match.group(1)
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if balance_match:
                balance = balance_match.group(1)
        except Exception:
            pass
        return balance, uid
    except Exception:
        return "0.00", "Unknown"

# ───────────────────────────────────────────
# ৪. মূল অটো-বেট লুপ (লগইন লজিক)
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx, loading_msg_id):
    state = get_state(uid)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        page = await browser.new_page()
        
        try:
            # ১. সাইটে যাওয়া
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(3000) 
            
            # ২. লগইন পেজে যাওয়া
            try:
                await page.locator('text="Log in"').first.click(timeout=3000)
                await page.wait_for_timeout(1000)
            except:
                pass 

            # ৮৮০ বাদ দেওয়া
            login_phone = state["phone"]
            if login_phone.startswith("880"):
                login_phone = login_phone[3:]
            elif login_phone.startswith("88"):
                login_phone = login_phone[2:]

            # ৩. জাভাস্ক্রিপ্ট দিয়ে ফর্ম ফিলাপ করা
            js_fill_script = f"""
            (function() {{
                let inputs = document.querySelectorAll('input');
                for (let i = 0; i < inputs.length; i++) {{
                    let input = inputs[i];
                    if (input.type === 'text' || input.type === 'tel' || input.type === 'number') {{
                        input.value = '{login_phone}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }} else if (input.type === 'password') {{
                        input.value = '{state["password"]}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            }})();
            """
            await page.evaluate(js_fill_script)
            await page.wait_for_timeout(500)
            
            # ৪. জাভাস্ক্রিপ্ট দিয়ে লগইন বাটনে ক্লিক করা
            js_click_script = """
            (function() {
                let btns = document.querySelectorAll('button, div, span, a');
                for (let i = 0; i < btns.length; i++) {
                    let text = btns[i].innerText.toLowerCase();
                    if (text.includes('log in') || text.includes('login') || text.includes('sign in')) {
                        btns[i].click();
                        return;
                    }
                }
            })();
            """
            await page.evaluate(js_click_script)
            
            # --- লগইন রেজাল্ট চেক (রিয়েল-টাইম) ---
            login_success, login_msg = await check_login_success(page)
            
            # 💡 লোডিং মেসেজ ডিলিট করা (যেই মাত্র রেসপন্স পাবে)
            if loading_msg_id:
                try:
                    await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except:
                    pass
            
            if not login_success:
                await ctx.bot.send_message(
                    chat_id=uid, 
                    text=f"❌ **LOGIN FAILED**\n\n{login_msg}\n\n_দয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।_",
                    parse_mode="Markdown"
                )
                state["running"] = False
                await browser.close()
                return
            
            # সফল লগইন হলে UID এবং ব্যালেন্স বের করা
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
                "☎️ **Phone Number**\n"
                f"{masked_phone}\n\n"
                "👤 **Account UID**\n"
                f"{state['account_uid']}\n\n"
                "💰 **Account Balance**\n"
                f"৳ {state['balance']}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")],
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await ctx.bot.send_message(chat_id=uid, text=login_msg_text, parse_mode="Markdown", reply_markup=markup)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Playwright error: {e}")
            if loading_msg_id:
                try:
                    await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except:
                    pass
            await ctx.bot.send_message(
                chat_id=uid, 
                text=f"⚠️ **BOT ERROR:**\n`{str(e)[:150]}`\n\n_সাইটে ঢুকতে সমস্যা হচ্ছে।_", 
                parse_mode="Markdown"
            )
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৫. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 Access  : Private\n"
        "🔴 Status  : Not Logged In\n"
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
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            f"📱 Number: {text}\n\n🔑 **Now enter your password:**",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: 
            await update.message.delete()
        except: 
            pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        # দ্রুত লোডিং অ্যানিমেশন (১.৫ সেকেন্ড)
        for i in range(1, 11):
            await asyncio.sleep(0.15)
            filled = "█" * i
            empty = "░" * (10 - i)
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {i*10}%", parse_mode="Markdown")
            except:
                pass
        
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx, loading_msg.message_id))
        return

    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 **LOGGED OUT**", parse_mode="Markdown")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data
    
    if data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(
            chat_id=uid,
            text="📱 **Enter your HGNICE phone number:**\n_Example: 8801884495095_",
            parse_mode="Markdown"
        )

def main():
    if not BOT_TOKEN or BOT_TOKEN == "এখানে_আপনার_টেলিগ্রাম_বটের_টোকেন_বসান":
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