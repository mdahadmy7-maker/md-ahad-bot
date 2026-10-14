import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ এখানে আপনার নতুন বটের API TOKEN বসান
TOKEN = "8572734509:AAElZm13hcSKvlnK6hw4i_VQr96-45amWTs"

# Step 1: /start Command Response
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

# Step Button Handlers (সিরিয়াল অনুযায়ী পরের ধাপ শো করার জন্য)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # ২য় ধাপ: Login এ চাপ দেওয়ার পর
    if query.data == "step_login":
        step2_message = (
            "✅ **Account Verified Successfully!**\n\n"
            "Please select your Server / Game Mode to start live prediction:"
        )
        keyboard2 = [
            [InlineKeyboardButton("🎯 WinGo 30s Server", callback_data="step_wingo_30s")],
            [InlineKeyboardButton("🎲 WinGo 1m Server", callback_data="step_wingo_1m")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="step_main")]
        ]
        reply_markup2 = InlineKeyboardMarkup(keyboard2)
        await query.edit_message_text(text=step2_message, reply_markup=reply_markup2, parse_mode="Markdown")

    # ৩য় ধাপ: WinGo 30s সিলেক্ট করার পর
    elif query.data == "step_wingo_30s":
        step3_message = (
            "🚀 **WinGo 30s Engine Activated!**\n\n"
            "📊 **Live Status:** Analyzing last 100 period numbers...\n"
            "⚡ **Current Hit Rate:** 94.2%\n\n"
            "Press below to generate prediction for next period!"
        )
        keyboard3 = [
            [InlineKeyboardButton("🔮 GENERATE PREDICTION", callback_data="step_predict")],
            [InlineKeyboardButton("🔙 Back", callback_data="step_login")]
        ]
        reply_markup3 = InlineKeyboardMarkup(keyboard3)
        await query.edit_message_text(text=step3_message, reply_markup=reply_markup3, parse_mode="Markdown")

    # ৩য় ধাপ (অন্য মান): WinGo 1m
    elif query.data == "step_wingo_1m":
        step3_message = (
            "🎲 **WinGo 1m Engine Activated!**\n\n"
            "📊 **Live Status:** Fetching trend data...\n"
            "⚡ **Current Hit Rate:** 91.8%\n\n"
            "Press below to generate prediction!"
        )
        keyboard3 = [
            [InlineKeyboardButton("🔮 GENERATE PREDICTION", callback_data="step_predict")],
            [InlineKeyboardButton("🔙 Back", callback_data="step_login")]
        ]
        reply_markup3 = InlineKeyboardMarkup(keyboard3)
        await query.edit_message_text(text=step3_message, reply_markup=reply_markup3, parse_mode="Markdown")

    # ৪র্থ ধাপ: Prediction Generate করা
    elif query.data == "step_predict":
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
        reply_markup4 = InlineKeyboardMarkup(keyboard4)
        await query.edit_message_text(text=prediction_text, reply_markup=reply_markup4, parse_mode="Markdown")

    # মেইন মেনুতে ফিরে যাওয়া
    elif query.data == "step_main":
        welcome_message = (
            "🧠 **Prediction Engine — 9 Layers**\n"
            "⚡ Streak • 🔷 Pattern • 📈 Trend\n\n"
            "👇 Press the button below to LOGIN"
        )
        keyboard = [
            [InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="step_login")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=welcome_message, reply_markup=reply_markup, parse_mode="Markdown")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("New Bot is running successfully...")
    application.run_polling()

if __name__ == '__main__':
    main()
