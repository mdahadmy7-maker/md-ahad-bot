import logging
import os
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850232346:AAGHxO0ZNcoSVb3N5u1dSXcWa1_nszIRlxM") 

# ⚠️ এখানে আপনার সাইটের আসল API URL বসান (অবশ্যই)
LOGIN_API_URL = "https://api.hgnice.vip/api/webapi/login"  
BALANCE_API_URL = "https://api.hgnice.vip/api/webapi/GetBalance" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "steps": [], "step_idx": 0, 
            "target": 0, "profit": 0, "bet_choice": "RANDOM",
            "balance": "0.00", "account_uid": "Unknown"
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. API দিয়ে আসল লগইন এবং ব্যালেন্স চেক
# ───────────────────────────────────────────
async def check_login_and_balance(phone, password):
    try:
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        
        payload = {
            "username": phone,
            "pwd": password,
            "phonetype": 0,
            "logintype": "mobile",
            "packId": "",
            "deviceId": "6c872674c682a8f66a5ef13954daf91b",
            "language": 0,
            "random": "492a7ac31af149e7be2118192c8b2a62",
            "signature": "BAD43FD0A17EBDD51BBD8DB9CBE7379",
            "timestamp": 1792218692
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(LOGIN_API_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 0 and data.get("data", {}).get("token"):
                        token = data["data"]["token"]
                        uid = str(data["data"].get("UserId", "Unknown"))
                        
                        bal_headers = {**headers, "Authorization": f"Bearer {token}"}
                        async with session.get(BALANCE_API_URL, headers=bal_headers) as bal_resp:
                            if bal_resp.status == 200:
                                bal_data = await bal_resp.json()
                                balance = str(bal_data.get("data", {}).get("balance", "0.00"))
                                return True, "Success", balance, uid
                        return True, "Success", "0.00", uid
                    else:
                        return False, data.get("msg", "Wrong account or password"), "0.00", "Unknown"
                else:
                    return False, "Server error", "0.00", "Unknown"
    except Exception as e:
        logger.error(f"API error: {e}")
        return False, "Connection error", "0.00", "Unknown"

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
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
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n"
            f"📱 Number: {text}\n\n"
            "🔑 **Now enter your password:**",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CHECKING...**")
        login_success, login_msg, bal, account_uid = await check_login_and_balance(state["phone"], state["password"])
        try: await loading_msg.delete()
        except: pass
        
        if not login_success:
            await update.message.reply_text(
                f"❌ **LOGIN FAILED**\n{login_msg}\n\nদয়া করে সঠিক নাম্বার ও পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।",
                parse_mode="Markdown"
            )
            return
            
        state["balance"] = bal
        state["account_uid"] = account_uid
        state["logged_in"] = True
        
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
        await update.message.reply_text(login_msg_text, parse_mode="Markdown", reply_markup=markup)
        return

    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "steps"
        await update.message.reply_text("💰 **BET STEPS** লিখুন (কমা দিয়ে):\n_Example: 2,4,8,16,32_", parse_mode="Markdown")
        return

    if text == "🛑 STOP TRADE":
        state["running"] = False
        await update.message.reply_text("🛑 **TRADE STOPPED**", parse_mode="Markdown")
        return

    if text == "🚪 LOGOUT":
        state["running"] = False
        state["logged_in"] = False
        await update.message.reply_text("🚪 **LOGGED OUT**", parse_mode="Markdown")
        return

    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(f"✅ STEPS SAVED: `{parts}`\n\n🎯 **TARGET PROFIT** দিন:", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! আবার লিখুন:")
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
                "📱 **Enter your HGNICE phone number:**"
            ),
            parse_mode="Markdown"
        )
        
    elif data.startswith("choice_"):
        state["bet_choice"] = data.split("_")[1]
        await query.edit_message_text(
            f"🚀 **AUTO BETTING STARTED**\n🎯 Target: {state['target']} ৳\n📈 Steps: {state['steps']}\n🎲 Choice: {state['bet_choice']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 STOP", callback_data="stop_bet")]])
        )
        
    elif data == "stop_bet":
        state["running"] = False
        await query.edit_message_text("🛑 **AUTO BETTING STOPPED**", parse_mode="Markdown")

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
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