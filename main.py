import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Your Bot Token
TOKEN = "8402123136:AAEfGNA4CHyxhQOUNAgQCebbqnzBEEaHEJk"

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
    
    keyboard = [
        [InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="login")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_message, reply_markup=reply_markup)

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("Ahad WinGo Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
