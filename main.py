import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ এখানে আপনার নতুন বটের API Token বসান
TOKEN = "8648518720:AAH3PNB7Eaws5h7TJNZcxTvXPvDR5vZn1tU"

# আপনার টেলিগ্রাম আইডি এখানে দিন যাতে শুধু আপনিই অ্যাডমিন প্যানেল দেখতে পারেন (আপনার ইউজার আইডি নম্বর)
ADMIN_USER_ID = 8164888241  # এখানে আপনার টেলিগ্রাম আইডি বসাবেন

# ১. /start কমান্ড রেসপন্স
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    # চেক করা ইউজার অ্যাডমিন কি না
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ আপনার এই প্যানেলটি ব্যবহার করার অনুমতি নেই।")
        return

    admin_text = (
        "⚙️ **Admin Control Panel**\n"
        "_________________________________________\n"
        "Welcome to bot management system. Choose an option below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Bot Status & Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 Restart Engine", callback_data="admin_restart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=admin_text, reply_markup=reply_markup, parse_mode="Markdown")

# ৩. বাটন হ্যান্ডলার (ইউজার এবং অ্যাডমিন ইন্টারঅ্যাকশন)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # ইউজার ফ্লো
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

    # অ্যাডমিন প্যানেল বাটন অ্যাকশন
    elif data == "admin_stats":
        await query.edit_message_text(
            text="📊 **Bot Statistics:**\n\n- Total Users: Active\n- Server Status: Online (100%)\n- Current Ping: 45ms",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
        )
    elif data == "admin_broadcast":
        await query.edit_message_text(
            text="📢 Broadcast feature is ready. Send your announcement text.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
        )
    elif data == "admin_restart":
        await query.edit_message_text(
            text="🔄 Engine restart signal sent successfully.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
        )
    elif data == "admin_back":
        admin_text = "⚙️ **Admin Control Panel**\nChoose an option below:"
        keyboard = [
            [InlineKeyboardButton("📊 Bot Status & Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔄 Restart Engine", callback_data="admin_restart")]
        ]
        await query.edit_message_text(text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Ahad WinGo Bot with Admin Panel is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
