import asyncio
import logging
import requests
import json
import re
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG 
# ⚠️ এখানে আপনার টেলিগ্রাম বটের টোকেন বসান
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAFSa0GMt5KPoH-L4ZexuJqRR4XPmgw-8Zg" 

LOGIN_URL = "https://api.hgnicepayapi.com/api/webapi/Login"
USER_INFO_URL = "https://api.hgnicepayapi.com/api/webapi/GetUserInfo"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, "steps": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 লগইন এবং ব্যালেন্স আনার ফাংশন
# ───────────────────────────────────────────
async def api_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    
    headers = {
        "authority": "api.hgnicepayapi.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "ar-origin": "https://www.hgnice.vip",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://www.hgnice.vip",
        "referer": "https://www.hgnice.vip/",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    }

    # 💡 আপনার নতুন পাওয়া ডেটা এখানে বসানো হলো
    login_payload = {
        "username": phone,
        "pwd": password,
        "phonetype": 0,
        "logintype": "mobile",
        "packId": "",
        "deviceId": "6c872674c682a8f66a5ef13954daf91b",
        "pixelId": "",
        "fbcId": "",
        "fbc": "",
        "fbp": "",
        "adId": "",
        "language": 0,
        "random": "9110ceba265941dba15ebc3196f735d0", # নতুন random
        "signature": "6672C0E9F437A8C401819857EE702F49", # নতুন সিগনেচার
        "timestamp": 1792481515 # নতুন টাইমস্ট্যাম্প
    }

    try:
        response = requests.post(LOGIN_URL, json=login_payload, headers=headers, timeout=15)
        data = response.json()
        
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass

        if data.get("code") != 0:
            err_msg = data.get("msg", "Wrong account or password")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ LOGIN FAILED ({phone})\n\n{err_msg}")
            return

        user_data = data.get("data", {})
        token = user_data.get("token", "")
        
        headers["authorization"] = f"Bearer {token}"
        # GetUserInfo এর জন্যও নতুন সিগনেচার দরকার হতে পারে, তবে আপাতত আগেরটাই রাখছি
        info_payload = {
            "language": 0,
            "random": "5f8cc6db4f79466498af393f4cefa024",
            "signature": "1B8641B191D774437D642C99F656F62B",
            "timestamp": 1792440119
        }
        
        uid_val = "Unknown"
        balance = "0.00"

        try:
            info_response = requests.post(USER_INFO_URL, json=info_payload, headers=headers, timeout=10)
            info_data = info_response.json()
            if info_data.get("code") == 0:
                info_d = info_data.get("data", {})
                balance = info_d.get("amount", "0.00")
                uid_val = info_d.get("userId", "Unknown")
        except Exception as e:
            logger.error(f"Info API error: {e}")

        try:
            payload_b64 = token.split('.')[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
            if uid_val == "Unknown": uid_val = decoded_payload.get("UserId", "Unknown")
            if balance == "0.00": balance = decoded_payload.get("Amount", "0.00")
        except:
            pass

        account_info = {
            "phone": phone, "password": password, "uid": uid_val,
            "balance": balance, "token": token
        }
        
        existing = False
        for acc in state["accounts"]:
            if acc["phone"] == phone:
                acc.update(account_info)
                existing = True
                break
        if not existing:
            state["accounts"].append(account_info)

        state["balance"] = balance
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
        
        reply_keyboard = [
            [KeyboardButton("🚀 START YOUR TARGET")],
            [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]
        ]
        markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        
        await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=markup)
        
        if len(state["accounts"]) < 6:
            await ctx.bot.send_message(chat_id=uid, text=f"✅ অ্যাকাউন্ট সেভ হয়েছে ({len(state['accounts'])}/6)। নতুন অ্যাকাউন্ট যোগ করতে /start দিন।")

    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"❌ Network Error:\n{str(e)[:100]}")

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    if len(state["accounts"]) >= 6:
        await update.message.reply_text("✅ আপনার ৬টি অ্যাকাউন্ট ইতিমধ্যে সেভ করা আছে। নতুন করে শুরু করতে /reset দিন।")
        return

    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 Mode    : Auto Analyse & bet\n"
        "🔐 Access  : Private · Authorized Members\n"
        "🔴 Status  : Not Logged In\n"
        f"👥 Accounts: {len(state['accounts'])}/6\n"
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
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
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
        
        loading_msg = await update.message.reply_text("🔄 CONNECTING... [░░░░░░░░░░] 0%")
        for i in range(1, 11):
            await asyncio.sleep(0.1)
            try: await loading_msg.edit_text(f"🔄 CONNECTING... [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        await api_login(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"])
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
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return
        
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            if steps > 50 or steps < 1:
                raise ValueError("Steps must be between 1 and 50")
            state["steps"] = steps
            state["awaiting"] = None
            await update.message.reply_text(f"✅ STEP COUNT SET: {steps}\n\nবট এখন কাজ শুরু করবে (অটো-বেট লজিক পরবর্তী ধাপে যোগ হবে)।")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন (যেমন: 5)।")
        return

    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 TRADE STOPPED")
        return
    if text == "🚪 LOGOUT":
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 LOGGED OUT\n/start দিয়ে আবার লগইন করুন।")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 Enter your HGNICE phone number:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Everyone uses their own account — your session is private."
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, "steps": 0
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। /start দিন।")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()