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
BOT_TOKEN = "8850232346:AAEUh-lBN2hW0i3WRqR_CJUsGi3CSmSU7HU" 

LOGIN_URL = "https://api.hgnicepayapi.com/api/webapi/Login"
USER_INFO_URL = "https://api.hgnicepayapi.com/api/webapi/GetUserInfo"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "phone": "", "password": "", 
            "balance": "0.00", "target": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 লগইন এবং ব্যালেন্স আনার ফাংশন
# ───────────────────────────────────────────
async def api_login(uid, ctx, loading_msg_id):
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

    login_payload = {
        "username": state["phone"],
        "pwd": state["password"],
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
        "random": "f6dd624a23b343ee9d7e53fd01b8cc66",
        "signature": "F9FF4A78B3914639BB25FCD184E650C8", 
        "timestamp": 1792437970 
    }

    try:
        response = requests.post(LOGIN_URL, json=login_payload, headers=headers, timeout=15)
        data = response.json()
        
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass

        if data.get("code") != 0:
            err_msg = data.get("msg", "Wrong account or password")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\n\n{err_msg}", parse_mode="Markdown")
            return

        user_data = data.get("data", {})
        token = user_data.get("token", "")
        
        headers["authorization"] = f"Bearer {token}"
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
                balance = info_d.get("amount", info_d.get("Amount", "0.00"))
                uid_val = info_d.get("userId", info_d.get("UserId", "Unknown"))
        except:
            pass

        try:
            payload_b64 = token.split('.')[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
            if uid_val == "Unknown": uid_val = decoded_payload.get("UserId", "Unknown")
            if balance == "0.00": balance = decoded_payload.get("Amount", "0.00")
        except Exception as e:
            logger.error(f"Token decode error: {e}")

        state["balance"] = balance
        masked_phone = f"***{state['phone'][-4:]}" # আপনার ডিজাইন অনুযায়ী ***5095
        
        # 💡 আপনার দেওয়া ১ম ডিজাইন
        dashboard_msg = (
            "╔════════════════════════╗\n"
            "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"☎️ Phone Number\n"
            f"{masked_phone}\n\n"
            f"👤 Account UID\n"
            f"{uid_val}\n\n"
            f"💰 Account Balance\n"
            f"৳ {balance}\n"
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
        
        await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, parse_mode="Markdown", reply_markup=markup)

    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"❌ **Network Error:**\n`{str(e)[:100]}`", parse_mode="Markdown")

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_state(uid)
    
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
            "╚════════════════════════╝\n\n"
            f"☎️ **Number :** {text}\n\n"
            "🔑 **Now enter your password:**\n"
            "_Your message will be deleted immediately for security._",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "password":
        state["password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...** [░░░░░░░░░░] 0%")
        for i in range(1, 11):
            await asyncio.sleep(0.1)
            try: await loading_msg.edit_text(f"🔄 **CONNECTING...** [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        await api_login(uid, ctx, loading_msg.message_id)
        return

    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        # 💡 আপনার দেওয়া ২য় ডিজাইন
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
        await update.message.reply_text(target_msg, parse_mode="Markdown")
        return

    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            state["awaiting"] = None
            await update.message.reply_text(f"✅ **TARGET SET: ৳ {target_amount}**\n\nবট এখন কাজ শুরু করবে (লজিক পরবর্তীতে যোগ হবে)।")
        except ValueError:
            await update.message.reply_text("❌ **ভুল ফরম্যাট!** দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return

    if text == "🛑 STOP TRADE":
        await update.message.reply_text("🛑 **TRADE STOPPED**", parse_mode="Markdown")
        return
    if text == "🚪 LOGOUT":
        state["phone"] = ""
        state["password"] = ""
        await update.message.reply_text("🚪 **LOGGED OUT**\n/start দিয়ে আবার লগইন করুন।", parse_mode="Markdown")
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
            "📱 **Enter your HGNICE phone number:**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "_Everyone uses their own account — your session is private._"
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg, parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()