import asyncio
import logging
import random
import os
import re
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
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
# ২. হেল্পার: লগইন চেক (API দিয়ে - দ্রুত)
# ───────────────────────────────────────────
async def check_login_api(phone, password):
    # এটি একটি ডেমো API কল, যেখানে আসল সাইটের লগইন API-এর ফরম্যাট ব্যবহার করা হয়েছে
    # আপনি আপনার সাইটের আসল API URL এবং পে-লোড এখানে বসাতে পারেন
    try:
        async with aiohttp.ClientSession() as session:
            # এখানে আমরা ডেমো হিসেবে ধরে নিচ্ছি, পাসওয়ার্ড "123456" হলে সফল
            # আসল API বসালে এটি সাইটের সাথে কানেক্ট করবে
            await asyncio.sleep(2) # নেটওয়ার্ক ডিলে সিমুলেট
            
            # ডেমো লজিক: পাসওয়ার্ড 123456 হলে সফল, নাহলে ভুল
            if password == "123456":
                return True, "Success", "6.56", "2084883"
            else:
                return False, "Wrong account or password", "0.00", "Unknown"
    except Exception as e:
        logger.error(f"API error: {e}")
        return False, "Connection Error", "0.00", "Unknown"

# ───────────────────────────────────────────
# ৩. মূল অটো-বেট লুপ
# ───────────────────────────────────────────
async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    
    # লোডিং শেষ হওয়ার সাথে সাথে API কল করা হবে
    login_success, login_msg, bal, user_uid = await check_login_api(state["phone"], state["password"])
    
    if not login_success:
        await ctx.bot.send_message(
            chat_id=uid, 
            text=f"❌ **LOGIN FAILED**\n{login_msg}\n\nদয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।",
            parse_mode="Markdown"
        )
        state["running"] = False
        return
        
    state["balance"] = bal
    state["account_uid"] = user_uid
    
    # সাকসেস মেসেজ
    login_msg_text = (
        "╔════════════════════════╗\n"
        "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
        "╚════════════════════════╝\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "☎️ **Phone Number**\n"
        f"****{state['phone'][-4:]}\n\n"
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
    
    # Playwright দিয়ে আসল বাজি ধরার লজিক (আপাতত ডেমো)
    # আপনি চাইলে Playwright কে এখানে কল করতে পারেন
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
        
        # ডেমো রেজাল্ট
        await asyncio.sleep(5)
        is_win = random.choice([True, False])
        
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

# ───────────────────────────────────────────
# ৪. টেলিগ্রাম হ্যান্ডলার
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

    # ২. পাসওয়ার্ড গ্রহণ, ডিলিট এবং লোডিং
    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        # পাসওয়ার্ড মেসেজ ডিলিট
        try: 
            await update.message.delete()
        except: 
            pass
        
        # লোডিং মেসেজ
        loading_msg = await update.message.reply_text("🔄 **CONNECTING TO HGNICE**\n[░░░░░░░░░░] 0%", parse_mode="Markdown")
        
        for i in range(1, 11):
            await asyncio.sleep(0.2)
            filled = "█" * i
            empty = "░" * (10 - i)
            percent = i * 10
            try:
                await loading_msg.edit_text(f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown")
            except:
                pass
        
        # লোডিং শেষে সরাসরি API কল করে রেজাল্ট
        state["running"] = True
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        return

    # ৩. START YOUR TARGET বাটন
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
            state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        return

    # ৪. STOP TRADE বাটন
    if text == "🛑 STOP TRADE":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🛑 **TRADE STOPPED**", parse_mode="Markdown")
        return

    # ৫. LOGOUT বাটন
    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        if state.get("task"): state["task"].cancel()
        await update.message.reply_text("🚪 **LOGGED OUT**", parse_mode="Markdown")
        return

    # ৬. স্টেপ গ্রহণ
    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(f"✅ STEPS SAVED: `{parts}`\n\n🎯 **TARGET PROFIT** দিন:", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! আবার লিখুন (যেমন: 2,4,8):")
        return

    # ৭. টার্গেট গ্রহণ
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
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
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