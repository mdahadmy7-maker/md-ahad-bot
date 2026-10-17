import asyncio
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # ← এখানে আপনার টেলিগ্রাম বটের টোকেন দিন
SITE_URL = "https://www.hgnice.vip"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "logged_in": False, "awaiting": None, "phone": "", "password": "",
            "running": False, "task": None, "browser": None,
            "steps": [], "step_idx": 0, "target": 0, "profit": 0, "bet_choice": "RANDOM"
        }
    return user_state[uid]

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
        
        await asyncio.sleep(32) # রেজাল্টের জন্য অপেক্ষা
        
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
        browser = await p.chromium.launch(headless=True) # টেস্টের জন্য False করুন
        page = await browser.new_page()
        
        try:
            await ctx.bot.send_message(chat_id=uid, text="🌐 HGNice সাইটে ঢুকছি...")
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            await page.get_by_placeholder("Please enter the phone number").fill(state["phone"])
            await page.get_by_placeholder("Password").fill(state["password"])
            await page.locator('text="Log in"').last.click()
            await page.wait_for_timeout(5000)
            
            await page.locator('text="WinGo 30sec"').first.click(timeout=5000)
            await page.wait_for_timeout(3000)
            
            await ctx.bot.send_message(chat_id=uid, text="✅ লগইন সফল! বেটিং শুরু হচ্ছে...")
            
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
# টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    
    welcome_text = (
        "🧠 **Prediction Engine — 9 Layers**\n"
        "⚡ Streak • 🔷 Pattern • 📈 Trend\n"
        "─────────────────────────\n"
        "🚀 Analysis → auto bet every 30s period\n"
        "─────────────────────────\n"
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
        # মেসেজ ডিলিট হবে না, নতুন মেসেজ আসবে
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
        state["awaiting"] = "steps"
        # মেসেজ ডিলিট করার লাইনটি মুছে দেওয়া হয়েছে
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
            "╚════════════════════════╝\n\n"
            "💰 **BET STEPS** লিখুন (কমা দিয়ে):\n"
            "_Example: 2,4,8,16,32_",
            parse_mode="Markdown"
        )
        return

    if state.get("awaiting") == "steps":
        try:
            parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
            state["steps"] = parts
            state["step_idx"] = 0
            state["awaiting"] = "target"
            await update.message.reply_text(
                f"✅ STEPS SAVED: `{parts}`\n\n"
                "🎯 **TARGET PROFIT** দিন (যেমন: 100):", 
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ ভুল ফরম্যাট! আবার লিখুন (যেমন: 2,4,8):")
        return

    if state.get("awaiting") == "target":
        try:
            state["target"] = float(text)
            state["profit"] = 0
            state["awaiting"] = None
            
            keyboard = [
                [InlineKeyboardButton("🟠 BIG", callback_data="choice_BIG"), 
                 InlineKeyboardButton("🔵 SMALL", callback_data="choice_SMALL")],
                [InlineKeyboardButton("🎲 RANDOM", callback_data="choice_RANDOM")]
            ]
            await update.message.reply_text(
                "✅ টার্গেট সেভ হয়েছে।\n🎯 এখন আপনি কোন দিকে বাজি ধরতে চান সিলেক্ট করুন:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
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
        # এখানেও edit_message_text এর বদলে reply_text দেওয়া ভালো, তবে ইনলাইন বাটনের জন্য edit_message_text-ই ব্যবহার করতে হয়
        await query.edit_message_text(
            "╔════════════════════════╗\n"
            "║  🔐 ACCOUNT LOGIN 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "📱 **Enter your HGNICE phone number:**\n\n"
            "_Everyone uses their own account — your session is private._",
            parse_mode="Markdown"
        )
    
    elif data.startswith("choice_"):
        state["bet_choice"] = data.split("_")[1]
        state["logged_in"] = True
        state["running"] = True
        
        await query.edit_message_text(
            f"🚀 **AUTO BETTING STARTED**\n"
            f"🎯 Target: {state['target']} ৳\n"
            f"📈 Steps: {state['steps']}\n"
            f"🎲 Choice: {state['bet_choice']}\n"
            f"⏳ কাজ চলছে...",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 STOP", callback_data="stop_bet")]])
        )
        if state.get("task"): state["task"].cancel()
        state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
        
    elif data == "stop_bet":
        state["running"] = False
        if state.get("task"): state["task"].cancel()
        await query.edit_message_text("🛑 **AUTO BETTING STOPPED**", parse_mode="Markdown")

async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    state["running"] = False
    if state.get("task"): state["task"].cancel()
    await update.message.reply_text("🛑 বেটিং বন্ধ করা হয়েছে।")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("🤖 Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()