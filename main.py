import asyncio
import logging
import re
import os
import requests
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN") 

# আপনার curl থেকে নেওয়া API URL
LOGIN_API = "https://api.dkwinapi.com/api/webapi/Login"
HISTORY_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "token": None, "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "wins": 0, "losses": 0, "total_trades": 0
        }
    return user_state[uid]

def get_history_and_prediction():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(HISTORY_API, headers=headers, timeout=10)
        data = res.json()
        
        list_data = data.get("data", {}).get("list", [])
        if not list_data:
            raise Exception("No data")
            
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
            
        if n >= 4:
            l4 = history[n-4]
            if l4 == l3 and l2 == l1 and l4 != l3:
                return l4, latest_period
                
        return ("SMALL" if l1 == 'BIG' else "BIG"), latest_period
        
    except Exception as e:
        logger.error(f"History API error: {e}")
        import random
        return random.choice(["BIG", "SMALL"]), datetime.now().strftime("%Y%m%d%H%M%S")

# 🌟 API দিয়ে লগইন করার ফাংশন
async def api_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text="CONNECTING"):
        if not loading_msg_id: return
        try:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text=f"🔄 **{text}** ({percent}%)", parse_mode="Markdown")
        except: pass

    await update_loading(30, "CONNECTING TO API")
    
    headers = {
        "authority": "api.dkwinapi.com",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://dkwin1.com",
        "referer": "https://dkwin1.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "x-app-type": "H5"
    }

    import time, hashlib
    current_ts = int(time.time())
    
    # 🚨 নোট: এখানে signature ডাইনামিক করা হয়েছে, তবে সাইটের আসল সিক্রেট ছাড়া এটি ১০০% কাজ নাও করতে পারে।
    # আপাতত ডেমো সিগনেচার দেওয়া হলো।
    payload = {
        "username": login_phone,
        "pwd": password,
        "phonetype": 1,
        "logintype": "mobile",
        "packId": "",
        "deviceId": "78a31db8d2dc8544556f9d82370be707",
        "pixelId": "", "fbcId": "", "fbc": "", "fbp": "", "adId": "", "language": 0,
        "random": "52edcf73bb214f73888eca195ad1c5f8",
        "signature": "1BBBE73DCEAA1BC85732D7379362D467",
        "timestamp": current_ts
    }

    try:
        res = requests.post(LOGIN_API, headers=headers, json=payload, timeout=15)
        data = res.json()
        
        if data.get("code") == 0:
            await update_loading(100, "LOGIN SUCCESSFUL")
            token = data.get("data", {}).get("token")
            state["token"] = token
            
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
                
            await ctx.bot.send_message(chat_id=uid, text=f"🎉 **API LOGIN SUCCESSFUL!**\n\nআপনার টোকেন সফলভাবে নেওয়া হয়েছে। বট এখন API দিয়ে চলবে।\n\n👇 Press START YOUR TARGET", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 START YOUR TARGET")]], resize_keyboard=True))
        else:
            # যদি সিগনেচার ভুল থাকে
            await ctx.bot.send_message(chat_id=uid, text=f"❌ **API LOGIN FAILED!**\n\nসার্ভার রেসপন্স: `{data.get('msg', 'Unknown Error')}`\n\n(সম্ভবত সিগনেচার ভুল বা পাসওয়ার্ড ভুল)")
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
    except Exception as e:
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Error:** {str(e)}")
        if loading_msg_id:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
            except: pass

# হ্যান্ডলার
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text("🧠 **BD=WIN~GO=AUTO~BET (API MODE)**\n\n👇 Press the button below to LOGIN", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**")
        asyncio.create_task(api_login(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return
        
    if text == "🚀 START YOUR TARGET":
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 Enter TARGET profit amount (৳):")
        return
        
    if state.get("awaiting") == "target":
        state["target"] = float(text)
        state["awaiting"] = "steps"
        await update.message.reply_text("🚀 Enter STEP COUNT:")
        return
        
    if state.get("awaiting") == "steps":
        state["steps"] = int(text)
        state["step_amounts"] = [] 
        state["current_step"] = 1
        state["awaiting"] = "step_amount"
        await update.message.reply_text(f"💵 Step 1 — bet amount?")
        return

    if state.get("awaiting") == "step_amount":
        state["step_amounts"].append(float(text))
        state["current_step"] += 1
        if state["current_step"] <= state["steps"]:
            await update.message.reply_text(f"💵 Step {state['current_step']} — bet amount?")
        else:
            state["awaiting"] = None
            inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 START TRADE", callback_data="start_trade_btn")]])
            await update.message.reply_text("⚙️ **CONFIGURATION READY**\n\n👇 Press START TRADE", reply_markup=inline_kb)
        return

    if text == "🛑 STOP TRADE":
        state["trade_running"] = False
        await update.message.reply_text("🛑 TRADE STOPPED")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    state = get_state(update.effective_user.id)
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=update.effective_user.id, text="📱 Enter DKWIN8 phone number:")
    elif query.data == "start_trade_btn":
        state["trade_running"] = True
        await query.edit_message_text("🚀 **TRADE STARTED...**")
        # এখানে API বেটিং লুপ শুরু হবে (আপনি চাইলে এখানে API কল দিতে পারেন)

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()