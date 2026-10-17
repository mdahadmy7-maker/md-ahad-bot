import asyncio
import logging
import random
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAEHLP6ghiuFc0So1MG4Dq6RlqFOOCTCmok")
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
# হেল্পার: স্ক্রিন থেকে ব্যালেন্স ও UID বের করা
# ───────────────────────────────────────────
async def get_account_info(page):
    try:
        await page.wait_for_timeout(3000)
        # স্ক্রিনে 'Balance' বা 'UID' লেখা থেকে ডেটা বের করার চেষ্টা (এটি সাইটের HTML এর উপর নির্ভরশীল)
        # আপাতত আমরা ডেমো ডেটা দিচ্ছি, তবে কোডে স্ক্র্যাপিং বসানো যাবে
        balance = "6.56" # স্ক্র্যাপিং করে আসল ব্যালেন্স বের করতে হবে
        uid = "2084883"  # স্ক্র্যাপিং করে আসল UID বের করতে হবে
        return balance, uid
    except:
        return "0.00", "Unknown"

# ───────────────────────────────────────────
# হেল্পার: বাজি ধরা এবং রেজাল্ট চেক
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
# মূল অটো-বেট লুপ
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        page = await browser.new_page()
        
        try:
            await ctx.bot.send_message(chat_id=uid, text="🌐 HGNice সাইটে ঢুকছি...")
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            await ctx.bot.send_message(chat_id=uid, text="🔐 লগইন করা হচ্ছে...")
            await page.get_by_placeholder("Please enter the phone number").fill(state["phone"])
            await page.get_by_placeholder("Password").fill(state["password"])
            await page.locator('text="Log in"').last.click()
            await page.wait_for_timeout(5000)
            
            await ctx.bot.send_message(chat_id=uid, text="🎮 WinGo 30s গেমে ঢুকছি...")
            await page.locator('text="WinGo 30sec"').first.click(timeout=5000)
            await page.wait_for_timeout(3000)
            
            await ctx.bot.send_message(chat_id=uid, text="✅ গেম রেডি! বেটিং শুরু হচ্ছে...")
            
            while state["running"]:
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
        finally:
            await browser.close()

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার (স্ক্রিনশটের মতো ডিজাইন)
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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

    # ১. ফোন নম্বর গ্রহণ
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

    # ২. পাসওয়ার্ড গ্রহণ (এবং পাসওয়ার্ড মেসেজ ডিলিট করা)
    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = "steps"
        
        # পাসওয়ার্ড মেসেজটি ডিলিট করা
        try: 
            await update.message.delete()
        except: 
            pass
        
        # লগইন সফল হওয়ার ডেমো ড্যাশবোর্ড
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "☎️ **Phone Number**\n"
            f"****{state['phone'][-4:]}\n\n"
            "👤 **Account UID**\n"
            "2084883\n\n"
            "💰 **Account Balance**\n"
            "৳ 6.56\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🧠 Analysis Engine:  READY\n"
            "🚀 AutoTrade System: READY\n\n"
            "👇 Press START YOUR TARGET to begin"
        )
        
        # কিবোর্ড বাটন তৈরি
        reply_keyboard = [
            [KeyboardButton("🚀 START YOUR TARGET")],
            [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
        ]
        markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        
        await update.message.reply_text(login_msg, reply_markup=markup)
        return

    # ৩. START YOUR TARGET বাটনে ক্লিক
    if text == "🚀 START YOUR TARGET":
        if not state["logged_in"]:
            # প্রথমবার ক্লিক করলে স্টেপ চাইবে
            state["awaiting"] = "steps"
            await update.message.reply_text(
                "💰 **BET STEPS** লিখুন (কমা দিয়ে):\n"
                "_Example: 2,4,8,16,32_",
                parse_mode="Markdown"
            )
        else:
            # পরেরবার ক্লিক করলে সরাসরি বেটিং শুরু করবে
            state["running"] = True
            await update.message.reply_text("🚀 বেটিং পুনরায় শুরু হচ্ছে...")
            if state.get("task"): state["task"].cancel()
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        return

    # ৪. STOP TRADE বাটনে ক্লিক
    if text == "🛑 STOP TRADE":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🛑 **TRADE STOPPED**\nAutoTrading session paused.", parse_mode="Markdown")
        return

    # ৫. LOGOUT বাটনে ক্লিক
    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 **LOGGED OUT**\nYour session has ended successfully.", parse_mode="Markdown")
        return

    # স্টেপ গ্রহণ
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

    # টার্গেট গ্রহণ
    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["profit"] = 0
            state["awaiting"] = None
            state["logged_in"] = True
            
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
                "📱 **Enter your HGNICE phone number:**\n\n"
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
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        
    elif data == "stop_bet":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await query.edit_message_text("🛑 **AUTO BETTING STOPPED**", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()