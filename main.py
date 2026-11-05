import asyncio
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. এখানে আপনার টেলিগ্রাম বটের টোকেন বসান
# ═══════════════════════════════════════════
BOT_TOKEN = "9032921988:AAGo2Bni1gc4SA2d541nnaz1uwsGqzQ4JVk"

user_data = {}

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid] = {"state": "phone"}
    await update.message.reply_text("📱 আপনার DK WIN ফোন নাম্বার দিন:")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    
    if uid not in user_data:
        await update.message.reply_text("দয়া করে /start দিন।")
        return

    if user_data[uid]["state"] == "phone":
        user_data[uid]["phone"] = text
        user_data[uid]["state"] = "password"
        await update.message.reply_text("🔑 এখন আপনার পাসওয়ার্ড দিন:")
        
    elif user_data[uid]["state"] == "password":
        user_data[uid]["password"] = text
        user_data[uid]["state"] = "testing"
        
        try: await update.message.delete()
        except: pass
        
        await update.message.reply_text("🔄 **টেস্ট করা হচ্ছে... ব্রাউজার ওপেন হচ্ছে।**")
        
        # ব্রাউজার ও লগইন টেস্ট কল করা
        await run_test(uid, ctx, user_data[uid]["phone"], user_data[uid]["password"])

async def run_test(uid, ctx, phone, password):
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    try:
        async with async_playwright() as p:
            # Ubuntu এর ক্রোমিয়াম ব্রাউজার পাথ
            browser = await p.chromium.launch(
                headless=True, 
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = await browser.new_page()
            
            # ১. সাইটে ঢোকা
            await page.goto("https://dkwwin.com/#/login", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # ২. স্ক্রিনশট নেওয়া (প্রথমে সাইট কেমন দেখাচ্ছে)
            await page.screenshot(path="before_login.jpg", type="jpeg", quality=70)
            await ctx.bot.send_photo(chat_id=uid, photo=open("before_login.jpg", "rb"), caption="📸 সাইটে ঢোকার পর স্ক্রিনশট।")
            
            # ৩. ইনপুট ফিল্ড খোঁজা
            try:
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                if await phone_input.count() > 0:
                    await phone_input.fill(login_phone)
                    await ctx.bot.send_message(chat_id=uid, text="✅ ফোন নাম্বার বসানো হয়েছে।")
                else:
                    await ctx.bot.send_message(chat_id=uid, text="❌ ফোন নাম্বার লেখার ঘর পাওয়া যায়নি!")
                    await browser.close()
                    return
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ নাম্বার বসাতে সমস্যা: {e}")
                await browser.close()
                return

            # ৪. পাসওয়ার্ড বসানো ও লগইন ক্লিক
            try:
                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)
                await page.get_by_text("Log in", exact=False).last.click()
                await ctx.bot.send_message(chat_id=uid, text="🔄 লগইন বাটনে ক্লিক করা হয়েছে।")
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ লগইন করতে সমস্যা: {e}")

            # ৫. লগইন প্রসেস হওয়ার অপেক্ষা
            await page.wait_for_timeout(6000)
            
            # ৬. লগইন পরবর্তী স্ক্রিনশট
            await page.screenshot(path="after_login.jpg", type="jpeg", quality=70)
            await ctx.bot.send_photo(chat_id=uid, photo=open("after_login.jpg", "rb"), caption="📸 লগইন ক্লিক করার পর স্ক্রিনশট।")
            
            await browser.close()

    except Exception as e:
        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ সিস্টেম এরর: {str(e)[:100]}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running... Go to Telegram and type /start")
    app.run_polling()

if __name__ == "__main__":
    main()