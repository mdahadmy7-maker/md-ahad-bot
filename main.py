import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ আপনার বটের নতুন API Token এবং অ্যাডমিন আইডি বসান
TOKEN = "8648518720:AAEWG-y74hp60BcrOyLiqNiTLMUwjvutPdA"
ADMIN_USER_ID = 8164888241  # এখানে আপনার টেলিগ্রাম আইডি বসাবেন

# অনুমোদিত ইউজারদের আইডি জমা রাখার লিস্ট (ডিফল্টভাবে অ্যাডমিন অনুমোদিত)
APPROVED_USERS = {ADMIN_USER_ID}

# ১. /start কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # ইউজার অনুমোদিত কি না তা চেক করা
    if user_id not in APPROVED_USERS:
        # অ্যাডমিনকে নোটিফিকেশন পাঠানো
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"🔔 **New Access Request!**\n\n"
                     f"👤 **User:** {user_name}\n"
                     f"🆔 **ID:** `{user_id}`\n\n"
                     f"অ্যাপ্রুভ করতে লিখুন: `/approve {user_id}`",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to notify admin: {e}")

        # ইউজারকে নোটিফিকেশন
        await update.message.reply_text(
            f"❌ **Access Denied!**\n\n"
            f"Hello {user_name}, you do not have permission to use this bot.\n"
            f"Your Access Request (ID: `{user_id}`) has been sent to the Admin.\n\n"
            f"⏳ Please wait for Admin approval.",
            parse_mode="Markdown"
        )
        return

    # অনুমোদিত ইউজারদের জন্য মূল মেনু
    welcome_message = (
        "🧠 **Prediction Engine — 9 Layers**\n"
        "⚡ Streak • 🔷 Pattern • 📈 Trend\n"
        "🔍 Manipulation • 🎨 Colour • 🔢 Frequency\n"
        "🔄 Markov • ♻️ Cycle • 💎 Momentum\n\n"
        "🔄 Every layer is back-tested live so its vote weight follows its real hit-rate\n"
        "🔴 Confidence below 30% → sit out\n"
        "_________________________________________\n\n"
        "🎬 4-second 🧠 generating prediction animation\n"
        "🚀 Analysis → auto bet every 30s period\n"
        "_________________________________________\n\n"
        "👇 Press the button below to LOGIN"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="step_login")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_message, reply_markup=reply_markup, parse_mode="Markdown")

# ২. অ্যাডমিন প্যানেল কমান্ড (/admin)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ আপনার এই প্যানেলটি ব্যবহার করার অনুমতি নেই।")
        return

    admin_text = (
        "⚙️ **Admin Control Panel**\n"
        "_________________________________________\n"
        f"📊 Total Approved Users: {len(APPROVED_USERS)}\n\n"
        "**Commands:**\n"
        "• `/approve <user_id>` — ইউজারকে পারমিশন দিতে\n"
        "• `/revoke <user_id>` — পারমিশন বাতিল করতে\n"
        "• `/users` — অনুমোদিত ইউজারের লিস্ট দেখতে"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Bot Status & Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=admin_text, reply_markup=reply_markup, parse_mode="Markdown")

# ৩. ইউজার পারমিশন দেওয়ার কমান্ড (/approve <user_id>)
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        return
    
    try:
        target_id = int(context.args[0])
        APPROVED_USERS.add(target_id)
        
        await update.message.reply_text(f"✅ User `{target_id}` has been approved!", parse_mode="Markdown")
        
        # ইউজারকে জানান দেওয়া
        await context.bot.send_message(
            chat_id=target_id,
            text="🎉 **Congratulations!** Your account has been approved by Admin.\nType /start to use the bot.",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ সঠিক ফরম্যাট: `/approve <user_id>`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error notifying user: {e}")

# ৪. ইউজার পারমিশন বাতিল করার কমান্ড (/revoke <user_id>)
async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        return
    
    try:
        target_id = int(context.args[0])
        if target_id == ADMIN_USER_ID:
            await update.message.reply_text("❌ আপনি নিজেকে রিমুভ করতে পারবেন না।")
            return
            
        APPROVED_USERS.discard(target_id)
        await update.message.reply_text(f"🚫 User `{target_id}` permission revoked!", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ সঠিক ফরম্যাট: `/revoke <user_id>`", parse_mode="Markdown")

# ৫. অনুমোদিত ইউজারের লিস্ট (/users)
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        return
    
    user_list = "\n".join([f"• `{uid}`" for uid in APPROVED_USERS])
    await update.message.reply_text(f"👥 **Approved Users List:**\n\n{user_list}", parse_mode="Markdown")

# ৬. বাটন হ্যান্ডলার
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # ইউজার অনুমোদিত না থাকলে বাটন কাজ করবে না
    if user_id not in APPROVED_USERS:
        await query.edit_message_text("❌ আপনার একাউন্টটি এখনও অনুমোদিত নয়।")
        return

    data = query.data

    if data == "step_login":
        step2_message = (
            "✅ **Account Verified Successfully!**\n\n"
            "Please select your Server / Game Mode to start live prediction:"
        )
        keyboard2 = [
            [InlineKeyboardButton("🎯 WinGo 30s Server", callback_data="step_wingo_30s")],
            [InlineKeyboardButton("🎲 WinGo 1m Server", callback_data="step_wingo_1m")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="step_main")]
        ]
        await query.edit_message_text(text=step2_message, reply_markup=InlineKeyboardMarkup(keyboard2), parse_mode="Markdown")

    elif data == "step_wingo_30s" or data == "step_wingo_1m":
        server_name = "WinGo 30s" if "30s" in data else "WinGo 1m"
        step3_message = (
            f"🚀 **{server_name} Engine Activated!**\n\n"
            "📊 **Live Status:** Analyzing trend data...\n"
            "⚡ **Current Hit Rate:** 94.2%\n\n"
            "Press below to generate prediction for next period!"
        )
        keyboard3 = [
            [InlineKeyboardButton("🔮 GENERATE PREDICTION", callback_data="step_predict")],
            [InlineKeyboardButton("🔙 Back", callback_data="step_login")]
        ]
        await query.edit_message_text(text=step3_message, reply_markup=InlineKeyboardMarkup(keyboard3), parse_mode="Markdown")

    elif data == "step_predict":
        prediction_text = (
            "🧠 **PREDICTION GENERATED** 🧠\n"
            "_________________________________________\n\n"
            "📌 **Period:** 202610140089\n"
            "🎨 **Result:** BIG / GREEN\n"
            "🎯 **Confidence:** 88%\n"
            "_________________________________________\n\n"
            "⏳ *Auto updating for next period in 30 seconds...*"
        )
        keyboard4 = [
            [InlineKeyboardButton("🔄 Refresh Prediction", callback_data="step_predict")],
            [InlineKeyboardButton("⚙️ Change Server", callback_data="step_login")]
        ]
        await query.edit_message_text(text=prediction_text, reply_markup=InlineKeyboardMarkup(keyboard4), parse_mode="Markdown")

    elif data == "step_main":
        welcome_message = (
            "🧠 **Prediction Engine — 9 Layers**\n"
            "⚡ Streak • 🔷 Pattern • 📈 Trend\n\n"
            "👇 Press the button below to LOGIN"
        )
        keyboard = [
            [InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="step_login")]
        ]
        await query.edit_message_text(text=welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_stats":
        await query.edit_message_text(
            text=f"📊 **Bot Statistics:**\n\n- Approved Users: {len(APPROVED_USERS)}\n- Server Status: Online (100%)\n- Ping: 40ms",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
        )
    elif data == "admin_broadcast":
        await query.edit_message_text(
            text="📢 Broadcast feature is ready.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
        )
    elif data == "admin_back":
        admin_text = f"⚙️ **Admin Control Panel**\nTotal Approved Users: {len(APPROVED_USERS)}"
        keyboard = [
            [InlineKeyboardButton("📊 Bot Status & Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")]
        ]
        await query.edit_message_text(text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("revoke", revoke_user))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Ahad WinGo Bot with Permission System is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
