import os
import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Render Environment Variable থেকে টোকেন নেওয়া হবে
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("হ্যালো! WinGo প্রেডিকশন বটে আপনাকে স্বাগতম। প্রেডিকশন পেতে /predict লিখুন।")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # WinGo প্রেডিকশন লজিক
    await update.message.reply_text("📊 **WinGo 1M Prediction:**\n\nResult: GREEN (Big)\nConfidence: 85%")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN পরিবেশক ভ্যারিয়েবল সেট করা নেই!")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("predict", predict))
        print("Bot is running...")
        app.run_polling()
      
