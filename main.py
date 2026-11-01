import asyncio
import logging
import os
import re
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = "আপনার_টেলিগ্রাম_বট_টোকেন_এখানে_দিবেন" 
SITE_URL = "https://dkwin1.com/#/login"
HOME_URL = "https://dkwin1.com/#/"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ইউজার স্টেট ম্যানেজমেন্ট
user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None,        # কি ইনপুট নিচ্ছে (target, phone, pass)
            "phone": "",
            "password": "",
            "target": 0.0,           # টার্গেট কত টাকা লাভ করবে
            "target_balance": 0.0,   # মোট কত ব্যালেন্স হলে থামবে
            "initial_balance": 0.0,  # শুরুতে কত টাকা ছিল
            "current_balance": 0.0,  # বর্তমান ব্যালেন্স
            "steps": [1, 3, 7, 15, 31], # বাজি ধরার স্টেপ (আপনার ইচ্ছেমতো বদলাতে পারেন)
            "current_step": 0,       # বর্তমানে কোন স্টেপে আছে
            "trade_running": False,  # ট্রেড চলছে কিনা
            "task": None,
            "wins": 0, "losses": 0,
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. টেলিগ্রাম কিবোর্ড এবং মেসেজ
# ═══════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    welcome_msg = (
        "👋 **DKWIN1 অটো-বটে আপনাকে স্বাগতম!**\n\n"
        "🤖 এই বটটি Playwright প্রযুক্তি ব্যবহার করে সম্পূর্ণ অটোমেটিক Big/Small বাজি ধরবে।\n"
        "📌 শুরু করতে নিচের বাটনে ক্লিক করুন।"
    )
    keyboard = [[InlineKeyboardButton("⚙️ অ্যাকাউন্ট সেটআপ", callback_data="setup_account")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode="Markdown")

async def setup_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    state = get_state(uid)
    state["awaiting"] = "phone"
    
    await query.edit_message_text("📱 অনুগ্রহ করে আপনার **ফোন নাম্বার** দিন (যেমন: 017XXXXXXXX):", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text

    if state["awaiting"] == "phone":
        state["phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔒 এখন আপনার **পাসওয়ার্ড** দিন:")
    
    elif state["awaiting"] == "password":
        state["password"] = text
        state["awaiting"] = "target"
        await update.message.reply_text("🎯 দুর্দান্ত! এখন আপনার **টার্গেট (লাভ)** কত টাকা, তা লিখুন (যেমন: 500):")
    
    elif state["awaiting"] == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            state["awaiting"] = None
            
            reply_keyboard = [[KeyboardButton("🚀 ট্রেডিং শুরু করুন")], [KeyboardButton("🛑 ট্রেডিং বন্ধ করুন")]]
            await update.message.reply_text(
                f"✅ সেটআপ সম্পন্ন!\n🎯 টার্গেট: {target_amount} টাকা লাভ।\n\nএখন 'ট্রেডিং শুরু করুন' বাটনে ক্লিক করুন।",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )
        except ValueError:
            await update.message.reply_text("❌ ভুল ইনপুট! শুধু সংখ্যা লিখুন (যেমন: 500)।")

# ═══════════════════════════════════════════
# ৩. Playwright অটোমেশন (আসল ম্যাজিক)
# ═══════════════════════════════════════════
async def run_playwright_trade(uid, ctx):
    state = get_state(uid)
    
    async with async_playwright() as p:
        # ব্রাউজার ওপেন (স্ক্রিন না দেখতে চাইলে headless=True দিন)
        browser = await p.chromium.launch(headless=True) 
        page = await browser.new_page()
        
        try:
            # ১. লগইন
            await ctx.bot.send_message(chat_id=uid, text="🔄 সাইটে লগইন করা হচ্ছে...")
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(3000)
            
            # --- [সতর্কতা: সাইটের ইনপুট ফিল্ডের সঠিক লোকেটর দরকার হতে পারে] ---
            await page.locator('input[type="text"]').first.fill(state["phone"]) # ফোন নাম্বার
            await page.locator('input[type="password"]').first.fill(state["password"]) # পাসওয়ার্ড
            await page.get_by_text("Log in", exact=False).last.click() # লগইন বাটন
            await page.wait_for_timeout(5000)
            
            # ২. গেম পেজে যাওয়া (WinGo 30S)
            await ctx.bot.send_message(chat_id=uid, text="🎮 WinGo 30S গেমে ঢোকা হচ্ছে...")
            await page.goto(HOME_URL, timeout=60000)
            await page.wait_for_timeout(3000)
            
            # গেম সিলেক্ট করার লজিক (আপনার সাইটের লেআউট অনুযায়ী এটি এডজাস্ট করতে হতে পারে)
            try:
                await page.get_by_text("WinGo 30sec", exact=False).first.click(timeout=5000)
            except:
                pass # যদি সরাসরি গেম পেজ ওপেন হয়
            
            await page.wait_for_timeout(3000)
            await ctx.bot.send_message(chat_id=uid, text="✅ গেম পেজে সফলভাবে ঢোকা হয়েছে। ট্রেডিং শুরু হচ্ছে...")

            # ৩. ট্রেডিং লুপ
            while state["trade_running"]:
                current_bet_amount = state["steps"][state["current_step"]]
                
                # এখানে আপনার প্রেডিকশন লজিক বসবে (Big নাকি Small)
                prediction = random.choice(["Big", "Small"]) # উদাহরণস্বরূপ র‍্যান্ডম
                
                await ctx.bot.send_message(
                    chat_id=uid, 
                    text=f"⏳ স্টেপ {state['current_step']+1}: {prediction} এ {current_bet_amount} টাকা বাজি ধরা হচ্ছে..."
                )

                # --- [সতর্কতা: সাইটের বাজি ধরার বাটনের সঠিক লোকেটর দরকার হতে পারে] ---
                try:
                    # পরিমাণ সেট করা
                    amount_input = page.locator('input[type="number"]').first
                    await amount_input.fill(str(current_bet_amount))
                    await page.wait_for_timeout(500)
                    
                    # Big বা Small এ ক্লিক
                    await page.get_by_text(prediction, exact=True).last.click()
                    await page.wait_for_timeout(1000)
                    
                    # কনফার্ম বাটনে ক্লিক
                    await page.get_by_text("Confirm", exact=True).last.click()
                    
                    await ctx.bot.send_message(chat_id=uid, text="✅ বাজি সফলভাবে ধরা হয়েছে!")
                    
                except Exception as e:
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ ক্লিক করতে সমস্যা হয়েছে: {e}")
                    state["trade_running"] = False
                    break

                # ৪. রেজাল্ট আসার জন্য অপেক্ষা (৩০ সেকেন্ড)
                await ctx.bot.send_message(chat_id=uid, text="⏳ রেজাল্টের জন্য অপেক্ষা করা হচ্ছে (৩০ সেকেন্ড)...")
                await page.wait_for_timeout(35000)
                
                # --- [এখানে Win/Loss চেক করার লজিক বসাতে হবে] ---
                # উদাহরণস্বরূপ, ধরলাম বাজি জিতেছে
                is_win = random.choice([True, False]) 
                
                if is_win:
                    state["wins"] += 1
                    state["current_step"] = 0 # জিতলে আবার ১ম স্টেপে ফিরে যাবে
                    await ctx.bot.send_message(chat_id=uid, text="🎉 অভিনন্দন! আপনি জিতেছেন। স্টেপ রিসেট হয়েছে।")
                else:
                    state["losses"] += 1
                    if state["current_step"] < len(state["steps"]) - 1:
                        state["current_step"] += 1 # হারলে পরবর্তী স্টেপে যাবে
                        await ctx.bot.send_message(chat_id=uid, text="😔 আপনি হেরেছেন। পরবর্তী স্টেপে যাওয়া হচ্ছে...")
                    else:
                        state["trade_running"] = False
                        await ctx.bot.send_message(chat_id=uid, text="❌ আপনি সব স্টেপে হেরেছেন। ট্রেডিং বন্ধ করা হলো।")
                        break

                await page.wait_for_timeout(3000) # পরবর্তী রাউন্ডের আগে একটু অপেক্ষা

        except Exception as e:
            await ctx.bot.send_message(chat_id=uid, text=f"❌ সিস্টেম এরর: {str(e)}")
        finally:
            state["trade_running"] = False
            await browser.close()
            await ctx.bot.send_message(chat_id=uid, text="🛑 ব্রাউজার বন্ধ করা হয়েছে। ট্রেডিং শেষ।")

# ═══════════════════════════════════════════
# ৪. কমান্ড হ্যান্ডলার (বাটন প্রেস)
# ═══════════════════════════════════════════
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text

    if text == "🚀 ট্রেডিং শুরু করুন":
        if not state["phone"] or not state["password"]:
            await update.message.reply_text("⚠️ আগে অ্যাকাউন্ট সেটআপ করুন (/start দিয়ে)।")
            return
            
        if state["trade_running"]:
            await update.message.reply_text("⚠️ ট্রেডিং ইতিমধ্যে চলছে!")
            return
            
        state["trade_running"] = True
        state["current_step"] = 0
        await update.message.reply_text("🚀 অটো-ট্রেডিং চালু হচ্ছে, ব্রাউজার ওপেন হচ্ছে...")
        
        # Playwright টাস্ক ব্যাকগ্রাউন্ডে চালু করা
        state["task"] = asyncio.create_task(run_playwright_trade(uid, context))

    elif text == "🛑 ট্রেডিং বন্ধ করুন":
        if state["trade_running"]:
            state["trade_running"] = False
            await update.message.reply_text("🛑 ট্রেডিং বন্ধ করার নির্দেশ দেওয়া হয়েছে...")
        else:
            await update.message.reply_text("⚠️ এখন কোনো ট্রেডিং চলছে না।")

# ═══════════════════════════════════════════
# ৫. মেইন ফাংশন
# ═══════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(setup_account, pattern="setup_account"))
    app.add_handler(MessageHandler(filters.Regex("^(🚀 ট্রেডিং শুরু করুন|🛑 ট্রেডিং বন্ধ করুন)$"), handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()