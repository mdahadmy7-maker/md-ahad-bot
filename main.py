import asyncio
import logging
import requests
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG 
# ⚠️ এখানে আপনার টেলিগ্রাম বটের টোকেন বসান
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAEUh-lBN2hW0i3WRqR_CJUsGi3CSmSU7HU" 
API_URL = "https://api.hgnicepayapi.com/api/webapi/Login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "phone": "", "password": ""}
    return user_state[uid]

# ───────────────────────────────────────────
# 💡 লগইন ফাংশন (আপনার সফল curl ডেটা দিয়ে)
# ───────────────────────────────────────────
async def api_login(uid, ctx, loading_msg_id):
    state = get_state(uid)
    
    # আপনার সফল curl থেকে নেওয়া হেডার
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

    # আপনার সফল পেলোড
    payload = {
        "username": state["phone"], # অথবা সরাসরি "8801884495095"
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
        "signature": "F9FF4A78B3914639BB25FCD184E650C8", # আপনার সফল সিগনেচার
        "timestamp": 1792437970 # আপনার সফল টাইমস্ট্যাম্প
    }

    try:
        # রিকোয়েস্ট পাঠানো
        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        data = response.json()
        
        # লোডিং মেসেজ ডিলিট
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass

        if data.get("code") == 0:
            # লগইন সফল হলে ডেটা বের করা
            user_data = data.get("data", {})
            
            # টোকেন বের করা
            token = user_data.get("token", "")
            
            # UID বের করা (webSocketChannels এর ভেতর থেকে)
            uid_val = "Unknown"
            channels = user_data.get("webSocketChannels", [])
            if channels:
                match = re.search(r'userid/(\d+)', channels[0])
                if match:
                    uid_val = match.group(1)
            
            # ব্যালেন্স (রেসপন্সে সরাসরি না থাকলে 0.00 দেখাবে, পরে প্রোফাইল API থেকে আনতে হবে)
            balance = user_data.get("balance", "0.00") 
            
            masked_phone = f"****{state['phone'][-4:]}"
            
            success_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ **Phone:** {masked_phone}\n"
                f"👤 **Account UID:** {uid_val}\n"
                f"💰 **Balance:** ৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            await ctx.bot.send_message(chat_id=uid, text=success_msg, parse_mode="Markdown")
            
        else:
            # এরর মেসেজ
            err_msg = data.get("msg", "Wrong account or password")
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\n\n{err_msg}", parse_mode="Markdown")
            
    except Exception as e:
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass
        await ctx.bot.send_message(chat_id=uid, text=f"❌ **Network Error:**\n`{str(e)[:100]}`", parse_mode="Markdown")

# ───────────────────────────────────────────
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    get_state(update.effective_user.id)
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
            await asyncio.sleep(0.1)
            try: await loading_msg.edit_text(f"🔄 **CONNECTING...** [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        await api_login(uid, ctx, loading_msg.message_id)
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