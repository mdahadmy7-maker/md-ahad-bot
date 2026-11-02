import asyncio
import os
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright
from flask import Flask
import threading

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PROXY_URL = os.environ.get("PROXY_URL", "")
SITE_URL = "https://dkwin8.com/#/login"

web_app = Flask(__name__)
@web_app.route('/')
def health(): return "OK", 200

def run_server():
    web_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

user_data = {}

async def do_login(uid, ctx, phone, password):
    msg = await ctx.bot.send_message(chat_id=uid, text="🔄 কানেক্টিং...")
    async with async_playwright() as p:
        proxy = {"server": PROXY_URL} if PROXY_URL else None
        browser = await p.chromium.launch(headless=True, proxy=proxy)
        page = await browser.new_page()
        try:
            await page.goto("https://www.google.com", timeout=60000)
            await page.goto(SITE_URL, timeout=60000)
            await page.wait_for_timeout(5000)
            
            # ফোন নাম্বার এবং পাসওয়ার্ড
            await page.locator('input[type="text"]').first.fill(phone[3:] if phone.startswith("880") else phone)
            await page.locator('input[type="password"]').first.fill(password)
            await page.locator('button:has-text("Log in")').last.click()
            await page.wait_for_timeout(4000)
            
            text = await page.inner_text("body")
            if "UID" in text:
                await ctx.bot.edit_message_text(chat_id=uid, message_id=msg.message_id, text="✅ লগইন সফল! বট কাজ করছে।")
            else:
                await ctx.bot.edit_message_text(chat_id=uid, message_id=msg.message_id, text="❌ লগইন ফেইল! সাইট ব্লক করেছে বা পাসওয়ার্ড ভুল।")
        except Exception as e:
            await ctx.bot.edit_message_text(chat_id=uid, message_id=msg.message_id, text=f"⚠️ Error: {str(e)[:50]}")
        finally:
            await browser.close()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ফোন নাম্বার দিন:")
    user_data[update.effective_user.id] = {"step": "phone"}

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    if uid not in user_data: return
    
    if user_data[uid]["step"] == "phone":
        user_data[uid]["phone"] = text
        user_data[uid]["step"] = "pass"
        await update.message.reply_text("পাসওয়ার্ড দিন:")
    elif user_data[uid]["step"] == "pass":
        user_data[uid]["step"] = "done"
        await update.message.delete()
        asyncio.create_task(do_login(uid, ctx, user_data[uid]["phone"], text))

def main():
    threading.Thread(target=run_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()