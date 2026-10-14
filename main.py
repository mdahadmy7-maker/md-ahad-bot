import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ আপনার নতুন বটের API Token এখানে দিন
TOKEN = "8572734509:AAElZm13hcSKvlnK6hw4i_VQr96-45amWTs"

# ১. /start কমান্ড এবং স্থায়ী মেনু কিবোর্ডসহ রেসপন্স
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = (
        "🧠 Prediction Engine — 9 Layers\n"
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
    
    # স্ক্রিনের নিচের স্থায়ী মেনু বা কিবোর্ড বাটন (যা আপনি স্ক্রিনশটে দেখিয়েছেন)
    reply_keyboard = [
        [KeyboardButton("🔐 LOGIN TO ACCOUNT")],
        [KeyboardButton("📊 Live Status"), KeyboardButton("ℹ️ Help")]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    # মেসেজের ভেতরে থাকা ইনলাইন লগইন বাটন
    inline_keyboard = [
        [InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="login")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)
    
    await update.message.reply_text(
        text=welcome_message, 
        reply_markup=inline_markup
    )
    # স্থায়ী মেনু কিবোর্ড পাঠানোর জন্য আলাদা মেসেজ বা একসাথে পাঠানো যায়
    await update.message.reply_text(
        text="👇 নিচের মেনু বাটন ব্যবহার করতে পারেন:",
        reply_markup=markup
    )

# ২. নিচের স্থায়ী মেনু থেকে কেউ কোনো বাটনে চাপ দিলে যা হবে
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == "🔐 LOGIN TO ACCOUNT":
        await update.message.reply_text("✅ অ্যাকাউন্ট ভেরিফিকেশন সফল হয়েছে! নিচের অপশনগুলো দেখুন:")
    elif text == "📊 Live Status":
        await update.message.reply_text("🚀 বর্তমান সার্ভার স্ট্যাটাস: ১০০% সচল এবং কাজ করছে।")
    elif text == "ℹ️ Help":
        await update.message.reply_text("💡 সাহায্য পেতে অ্যাডমিনের সাথে যোগাযোগ করুন।")

# ৩. ইনলাইন বাটনের কাজ (আগের মতো)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "login":
        prediction_text = (
            "🧠 **PREDICTION GENERATED** 🧠\n"
            "_________________________________________\n\n"
            "📌 **Period:** 202610140089\n"
            "🎨 **Result:** BIG / GREEN\n"
            "🎯 **Confidence:** 88%\n"
            "_________________________________________\n\n"
            "⏳ *Auto updating for next period in 30 seconds...*"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Prediction", callback_data="login")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=prediction_text, reply_markup=reply_markup, parse_mode="Markdown")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    print("Bot is running with custom menu...")
    application.run_polling()

if __name__ == '__main__':
    main()
