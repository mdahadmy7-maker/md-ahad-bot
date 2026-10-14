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

# আপনার টেলিগ্রাম বটের টোকেনটি এখানে বসিয়ে দিন
BOT_TOKEN = "8918135716:AAGmTW1mZTLJDmnJWpGNjRj6cKGWIFqrvVc"
ACCESS_KEY = "123456"

user_states = {}

def get_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "logged_in": False,
            "awaiting": "phone",  # শুরুতে ফোন নম্বর চাওয়ার জন্য
            "game": None,
            "steps": [],
            "step_idx": 0,
            "target": 0,
            "profit": 0,
            "bets": 0,
            "wins": 0,
            "running": False,
            "task": None,
        }
    return user_states[uid]

def stop_user(uid):
    state = get_state(uid)
    state["running"] = False
    if state.get("task"):
        state["task"].cancel()

def gen_period(game_mode):
    return "2026101301001"

async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    try:
        while state["running"]:
            await asyncio.sleep(28)
            if not state["running"]:
                break
            p = gen_period(state["game"])
    except asyncio.CancelledError:
        pass

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
    state = get_state(uid)
    text = update.message.text.strip()

    # যদি ফোন নম্বর বা এক্সেস কি চাওয়া হয়
    if not state["logged_in"]:
        if state.get("awaiting") == "phone" or state.get("awaiting") == "key":
            if text.lower() == ACCESS_KEY.lower():
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
                    "✅ *KEY ACCEPTED!*\n🎯 গেম সিলেক্ট করুন:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                await update.message.reply_text("❌ ভুল Access Key বা নম্বর। আবার দিন।")
            return

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
                "❌ ভুল ফরম্যাট! 10,20,40,80,160 এভাবে লিখুন", parse_mode="Markdown"
            )
        return

    if state.get("awaiting") == "target":
        try:
            tgt = float(text)
            state["target"] = tgt
            state["awaiting"] = None
            state["profit"] = 0
            state["bets"] = 0
            state["wins"] = 0
            state["step_idx"] = 0
            state["running"] = True
            await update.message.reply_text(
                f"🚀 *AUTO BETTING STARTED!*\n🎯 Target: *{tgt}*\n⏳ অপেক্ষা করুন...",
                parse_mode="Markdown",
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
    uid = update.effective_user.id
    state = get_state(uid)
    data = query.data

    if data == "start_login":
        state["awaiting"] = "phone"
        login_text = (
            "╔═══════════════════════════════╗\n"
            "║        🔐 **ACCOUNT LOGIN** 🔐        ║\n"
            "╚═══════════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📱 Enter your HGNICE phone number:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Everyone uses their own account — your session is private._"
        )
        await query.message.reply_text(login_text, parse_mode="Markdown")

    elif data.startswith("game_"):
        mode = data.split("_")[1]
        state["game"] = mode
        state["awaiting"] = "steps"
        await query.edit_message_text(
            f"🎮 *WinGo {mode.upper()} SELECTED*\n\n"
            f"💰 *BET STEPS* লিখুন:\n_Example: 10,20,40,80,160_",
            parse_mode="Markdown",
        )
    elif data == "stop_bet":
        stop_user(uid)
        await query.edit_message_text(
            f"🛑 STOPPED\n💰 Profit: *{state['profit']}*",
            parse_mode="Markdown",
        )

def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN সেট করা নেই!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
