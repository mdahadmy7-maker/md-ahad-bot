import asyncio
import logging
import re
import os
import requests
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

BOT_TOKEN = os.environ.get("BOT_TOKEN") 
SITE_URL = "https://dkwin8.com/#/login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": ""
        }
    return user_state[uid]

async def playwright_login_and_get_token(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text="CONNECTING"):
        if not loading_msg_id: return
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text}** ({percent}%)", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()

        try:
            await update_loading(20, "OPENING SITE")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            await update_loading(50, "ENTERING CREDENTIALS")
            await page.evaluate(f"""
                () => {{
                    let inputs = document.querySelectorAll('input');
                    for(let i of inputs) {{
                        if(i.type === 'text' || i.type === 'tel') {{
                            i.value = '{login_phone}';
                            i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            i.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                        if(i.type === 'password') {{
                            i.value = '{password}';
                            i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            i.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }}
            """)

            await update_loading(70, "CLICKING LOGIN")
            
            # 🌟 API রেসপন্স ক্যাপচার
            async with page.expect_response(lambda response: "Login" in response.url and response.request.method == "POST") as response_info:
                await page.evaluate("""
                    () => {
                        let els = document.querySelectorAll('button, div, span, a');
                        for(let el of els) {
                            let text = (el.innerText || el.value || '').trim().toLowerCase();
                            if (text === 'log in' || text === 'login') { el.click(); return true; }
                        }
                        return false;
                    }
                """)
            
            response = await response_info.value
            api_response_data = await response.json()
            
            await update_loading(100, "SUCCESS")
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if api_response_data.get("code") == 0:
                token = api_response_data.get("data", {}).get("token")
                balance = api_response_data.get("data", {}).get("balance", "0.00")
                await ctx.bot.send_message(chat_id=uid, text=f"✅ **LOGIN SUCCESSFUL!**\n\n🔑 **Token:** `{token[:20]}...`\n💰 **Balance:** ৳ {balance}\n\n(বটটি এখন API মোডে চলার জন্য প্রস্তুত)")
            else:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED!**\n\nরেসপন্স: `{api_response_data.get('msg', 'Unknown')}`")
                
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Error:** `{str(e)[:100]}`")
        finally:
            await browser.close()

# হ্যান্ডলার
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔐 LOGIN & GET TOKEN", callback_data="start_login")]]
    await update.message.reply_text("🧠 **DKWIN LOGIN**\n\n👇 Press to login:", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(f"☎️ Number: {text}\n\n🔑 Enter password:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 **CONNECTING...**")
        asyncio.create_task(playwright_login_and_get_token(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"]))
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    state = get_state(update.effective_user.id)
    if query.data == "start_login":
        state["awaiting"] = "phone"
        await ctx.bot.send_message(chat_id=update.effective_user.id, text="📱 Enter your DKWIN8 phone number:")

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()