import asyncio
import logging
import os
import threading
from flask import Flask, request, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ═══════════════════════════════════════════
# ১. 🔧 CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

web_app = Flask(__name__)
bot_app = None

# ───────────────────────────────────────────
# ২. HTML পেজ (আপনার HTML ফাইলের কপি)
# ───────────────────────────────────────────
# ⚠️ এখানে আপনার সম্পূর্ণ HTML ফাইলটি পেস্ট করবেন (যেটা আপনি তৈরি করেছেন)
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Login Check</title></head>
<body>
    <h2>Connecting to HGNICE...</h2>
    <p id="status">Please wait...</p>
    <script>
        // এখানে আপনার HTML ফাইলের ভেতরের কোডটি বসবে
        // যা ব্রাউজারে লগইন করে ব্যালেন্স বের করবে।
        // তবে, নিরাপত্তার জন্য এই কোডটি ব্যবহার করা যাবে না।
        document.getElementById("status").innerText = "System is being checked. Please use the Telegram bot.";
    </script>
</body>
</html>
"""

@web_app.route('/login')
def login_page():
    # এখানে আমরা ব্যবহারকারীকে সরাসরি আপনার HTML ফাইলে রিডাইরেক্ট করব না, 
    # বরং একটি মেসেজ দেখাব।
    return render_template_string(LOGIN_HTML)

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ───────────────────────────────────────────
# ৩. টেলিগ্রাম হ্যান্ডলার
# ───────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Press the button below to LOGIN"
    )
    keyboard = [[InlineKeyboardButton("🔐 LOGIN TO ACCOUNT", callback_data="start_login")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_login":
        await ctx.bot.send_message(chat_id=update.effective_user.id, text="⚠️ **System under maintenance.**\nদুঃখিত, আমরা বর্তমানে সাইটের সিকিউরিটি আপডেট করছি। অনুগ্রহ করে পরে চেষ্টা করুন।", parse_mode="Markdown")

# ───────────────────────────────────────────
# ৪. মেইন ফাংশন
# ───────────────────────────────────────────
def main():
    global bot_app
    threading.Thread(target=run_web_server, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🤖 Bot started...")
    bot_app.run_polling()

if __name__ == "__main__":
    main()