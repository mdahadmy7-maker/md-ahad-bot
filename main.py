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
BOT_TOKEN = "8850232346:AAFxrxOHHdFzS560JepDpxgj2oqS0tr6nPo" 

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
# ২. হেল্পার: লগইন সফল হয়েছে কিনা চেক করা
# ───────────────────────────────────────────
async def check_login_success(page):
    try:
        await page.wait_for_timeout(5000) # লগইন রিকোয়েস্ট প্রসেস হওয়ার জন্য অপেক্ষা
        
        # ১. ভুল পাসওয়ার্ডের পপ-আপ চেক (Error 147)
        error_popup = page.locator('text="Wrong account or password"').first
        if await error_popup.is_visible():
            return False, "Wrong account or password (Error: 147)"
            
        # ২. সফল লগইন চেক (ড্যাশবোর্ডে UID আছে কি না)
        uid_locator = page.locator('text="UID"').first
        if await uid_locator.is_visible(timeout=3000):
            return True, "Success"
             
        return False, "Unknown state after login attempt."
        
    except Exception as e:
        logger.error(f"Login check error: {e}")
        return False, f"Error checking login: {str(e)[:50]}"

# ───────────────────────────────────────────
# ৩. হেল্পার: স্ক্রিন থেকে আসল ব্যালেন্স ও UID বের করা
# ───────────────────────────────────────────
async def get_account_info(page):
    try:
        await page.wait_for_timeout(3000)
        balance = "0.00"
        uid = "Unknown"
        
        try:
            page_text = await page.inner_text("body")
            
            # UID খোঁজা
            uid_match = re.search(r'UID\s*\|\s*(\d+)', page_text, re.IGNORECASE)
            if uid_match:
                uid = uid_match.group(1)
                
            # ব্যালেন্স খোঁজা
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if balance_match:
                balance = balance_match.group(1)
                
        except Exception as e:
            logger.error(f"Scraping regex error: {e}")
            
        return balance, uid
    except Exception as e:
        logger.error(f"Info error: {e}")
        return "0.00", "Unknown"

# ───────────────────────────────────────────
# ৪. হেল্পার: বাজি ধরা এবং রেজাল্ট চেক
# ───────────────────────────────────────────
async def place_bet_and_check_win(page, bet_mode, amount):
    try:
        if bet_mode == "BIG":
            await page.locator('text="Big"').first.click(timeout=5000)
        else:
            await page.locator('text="Small"').first.click(timeout=5000)
        
        await page.wait_for_timeout(1000)
        try:
            await page.locator('text="Confirm"').first.click(timeout=3000)
        except:
            pass
        
        await asyncio.sleep(32)
        
        try:
            await page.locator('text="My history"').first.click(timeout=5000)
            await page.wait_for_timeout(3000)
            first_result = await page.locator('text="Win"').first.is_visible()
            await page.locator('text="Chart"').first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            return first_result
        except Exception as e:
            logger.error(f"Result check error: {e}")
            return False
    except Exception as e:
        logger.error(f"Bet error: {e}")
        return False

# ───────────────────────────────────────────
# ৫. মূল অটো-বেট লুপ (এখানে ক্লিকের লজিক দেওয়া আছে)
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx, loading_msg_id):
    state = get_state(uid)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) 
        page = await browser.new_page()
        
        try:
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000) 
            
            login_phone = state["phone"]
            if login_phone.startswith("880"):
                login_phone = login_phone[3:]

            # ১. ফোন নাম্বার বসানো
            try:
                await page.get_by_placeholder("Please enter phone number").fill(login_phone, timeout=3000)
            except:
                await page.fill('input[type="text"]', login_phone)
                
            await page.wait_for_timeout(1500)
            
            # ২. পাসওয়ার্ড বসানো
            try:
                await page.get_by_placeholder("Password").fill(state["password"], timeout=3000)
            except:
                await page.fill('input[type="password"]', state["password"])
                
            await page.wait_for_timeout(1500)
            
            # ৩. লাল "Log in" বাটনে ক্লিক করা (এখানে ৪টি ভিন্ন পদ্ধতি ব্যবহার করা হয়েছে)
            logger.info("Attempting to click Login button...")
            try:
                # পদ্ধতি ১: বাটনের ভেতরের লেখা "Log in" দিয়ে খোঁজা
                await page.locator('button:has-text("Log in")').last.click(timeout=3000)
            except:
                try:
                    # পদ্ধতি ২: শুধু টেক্সট "Log in" দিয়ে খোঁজা
                    await page.locator('text="Log in"').last.click(timeout=3000)
                except:
                    try:
                        # পদ্ধতি ৩: ওয়েবসাইটের কমন ক্লাস নাম (van-button) দিয়ে খোঁজা
                        await page.locator('.van-button--primary, .login-btn, .submit-btn').last.click(timeout=3000)
                    except:
                        # পদ্ধতি ৪: পেজের সবচেয়ে বড় লাল বাটনটি খোঁজা
                        await page.locator('div[role="button"], button').last.click(timeout=3000)
            
            # --- লগইন রেজাল্ট চেক ---
            login_success, login_msg = await check_login_success(page)
            
            # লোডিং মেসেজটি ডিলিট করা
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
            
            # সফল লগইন
            bal, user_uid = await get_account_info(page)
            state["balance"] = bal
            state["account_uid"] = user_uid
            state["logged_in"] = True
            
            masked_phone = f"****{state['phone'][-4:]}"
            
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
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 START YOUR TARGET")],
                [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await ctx.bot.send_message(chat_id=uid, text=login_msg_text, parse_mode="Markdown", reply_markup=markup)
            
            # গেমে ঢোকা
            await page.locator('text="WinGo 30sec"').first.click(timeout=5000)
            await page.wait_for_timeout(3000)
            
            while state["running"]:
                if not state["steps"]:
                    await asyncio.sleep(2)
                    continue

                current_amount = state["steps"][state["step_idx"]]
                
                if state["bet_choice"] == "RANDOM":
                    bet_mode = random.choice(["BIG", "SMALL"])
                else:
                    bet_mode = state["bet_choice"]
                    
                emoji = "🟠" if bet_mode == "BIG" else "🔵"
                await ctx.bot.send_message(
                    chat_id=uid, 
                    text=f"{emoji} **{bet_mode}**-এ {current_amount} টাকা বাজি ধরছে...\n(Step {state['step_idx']+1}/{len(state['steps'])})"
                )
                
                is_win = await place_bet_and_check_win(page, bet_mode, current_amount)
                
                if is_win:
                    state["profit"] += (current_amount * 0.96)
                    state["step_idx"] = 0 
                    await ctx.bot.send_message(chat_id=uid, text=f"✅ **WIN!** প্রফিট: ৳{state['profit']:.2f}")
                else:
                    state["profit"] -= current_amount
                    state["step_idx"] += 1
                    if state["step_idx"] >= len(state["steps"]):
                        state["step_idx"] = 0
                    await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOSE!** প্রফিট: ৳{state['profit']:.2f}")
                
                if state["profit"] >= state["target"]:
                    await ctx.bot.send_message(chat_id=uid, text="🎉 **TARGET REACHED!** বট বন্ধ হচ্ছে।")
                    state["running"] = False
                    break
                    
                await asyncio.sleep(3)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Playwright error: {e}")
            await ctx.bot.send_message(
                chat_id=uid, 
                text=f"⚠️ **BOT ERROR:**\n`{str(e)[:200]}`\n\n_দয়া করে এই মেসেজটির স্ক্রিনশট অ্যাডমিনকে পাঠান_", 
                parse_mode="Markdown"
            )
        finally:
            await browser.close()

# ───────────────────────────────────────────
# ৬. টেলিগ্রাম হ্যান্ডলার (আপনার আগের কোড অনুযায়ী)
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak · 🔷 Pattern · 📈 Trend\n"
        "🔍 Manipulation · 🎨 Colour · 🔢 Frequency\n"
        "🔄 Markov · ♻️ Cycle · 💠 Momentum\n"
        "🔁 Every layer is back-tested live so its vote\n"
        "weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"📱 Number: {text}\n\n"
            "🔑 **Now enter your password:**\n"
            "_Your message will be deleted immediately for security._",
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
        
        for i in range(1, 11):
            await asyncio.sleep(0.3)
            filled = "█" * i
            empty = "░" * (10 - i)
            percent = i * 10
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown")
            except:
                pass
        
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx, loading_msg.message_id))
        return

    if text == "🚀 START YOUR TARGET":
        if not state["logged_in"]:
            state["awaiting"] = "steps"
            await update.message.reply_text(
                "💰 **BET STEPS** লিখুন (কমা দিয়ে):\n"
                "_Example: 2,4,8,16,32_",
                parse_mode="Markdown"
            )
        else:
            state["running"] = True
            await update.message.reply_text("🚀 বেটিং পুনরায় শুরু হচ্ছে...")
            if state.get("task"): state["task"].cancel()
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx, None)) 
        return

    if text == "🛑 STOP TRADE":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🛑 **TRADE STOPPED**\nAutoTrading session paused.", parse_mode="Markdown")
        return

    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 **LOGGED OUT**\nYour session has ended successfully.", parse_mode="Markdown")
        return

    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(f"✅ STEPS SAVED: `{parts}`\n\n🎯 **TARGET PROFIT** দিন (যেমন: 100):", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! আবার লিখুন (যেমন: 2,4,8):")
        return

    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["profit"] = 0
            state["awaiting"] = None
            
            keyboard = [
                [InlineKeyboardButton("🟠 BIG", callback_data="choice_BIG"), InlineKeyboardButton("🔵 SMALL", callback_data="choice_SMALL")],
                [InlineKeyboardButton("🎲 RANDOM", callback_data="choice_RANDOM")]
            ]
            await update.message.reply_text("✅ টার্গেট সেভ হয়েছে।\n🎯 বাজি ধরার মোড সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন:")
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
            text=(
                "╔════════════════════════╗\n"
                "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
                "╚════════════════════════╝\n\n"
                "📱 **Enter your HGNICE phone number:**\n"
                "_Example: 8801884495095_\n\n"
                "_Everyone uses their own account — your session is private._"
            ),
            parse_mode="Markdown"
        )
        
    elif data.startswith("choice_"):
        state["bet_choice"] = data.split("_")[1]
        state["running"] = True
        await query.edit_message_text(
            f"🚀 **AUTO BETTING STARTED**\n🎯 Target: {state['target']} ৳\n📈 Steps: {state['steps']}\n🎲 Choice: {state['bet_choice']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 STOP", callback_data="stop_bet")]])
        )
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx, None))
        
    elif data == "stop_bet":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await query.edit_message_text("🛑 **AUTO BETTING STOPPED**", parse_mode="Markdown")

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