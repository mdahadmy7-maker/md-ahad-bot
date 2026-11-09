import asyncio
import logging
import os
import re
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") # আপনার টেলিগ্রাম বটের টোকেন
BLOG_URL = "https://dkwwin.com/" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {"awaiting": None, "temp_phone": "", "temp_password": "", "balance": "0.00", "user_id": "Unknown"}
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. Playwright লগইন ফাংশন
# ═══════════════════════════════════════════
async def playwright_login(uid, ctx, phone, password):
    state = get_state(uid)
    
    clean_phone = phone.strip()
    if clean_phone.startswith("880"): clean_phone = clean_phone[3:]
    if clean_phone.startswith("0"): clean_phone = clean_phone[1:]
    
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **ব্রাউজার ওপেন হচ্ছে...**\nঅপেক্ষা করুন।", parse_mode="Markdown")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800}, is_mobile=True, has_touch=True
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        page = await context.new_page()
        
        try:
            # ১. ব্লগ পেজে ঢোকা
            await page.goto(BLOG_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4) 

            # ২. লাল বাটনে ক্লিক করা
            await ctx.bot.send_message(chat_id=uid, text="🔍 লাল বাটন (Quick Sign-In) খুঁজছি...")
            
            # লাল বাটনটি খোঁজার জন্য একাধিক টেক্সট চেক করা হবে
            red_btn = page.locator('text="Quick Sign-In Link"').first
            if await red_btn.count() == 0:
                red_btn = page.locator('text="Dk Win Login"').first
                
            try:
                await red_btn.wait_for(state="visible", timeout=10000)
                
                # নতুন ট্যাব ধরার জন্য সেটআপ
                pages_before = len(context.pages)
                await red_btn.click(force=True)
                await asyncio.sleep(4) # নতুন ট্যাব লোড হওয়ার অপেক্ষা
                
                if len(context.pages) > pages_before:
                    page = context.pages[-1] # নতুন ট্যাবে সুইচ করা
                    await page.wait_for_load_state("domcontentloaded")
                    await ctx.bot.send_message(chat_id=uid, text="✅ নতুন ট্যাবে গেম সাইট ওপেন হয়েছে।")
                else:
                    await ctx.bot.send_message(chat_id=uid, text="✅ একই ট্যাবে গেম সাইট ওপেন হয়েছে।")
                    
                await asyncio.sleep(3)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text=f"⚠️ লাল বাটনে ক্লিক করা যায়নি! Error: {str(e)[:50]}\nসরাসরি গেম সাইটে যাচ্ছি...")
                await page.goto("https://dkwin0.com/#/", wait_until="domcontentloaded")
                await asyncio.sleep(4)

            # ডিবাগ স্ক্রিনশট (গেম পেজে ঢোকার পর)
            ss_debug = f"step1_{uid}.png"
            await page.screenshot(path=ss_debug)
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_debug, 'rb'), caption="১. গেম সাইটে ঢুকেছি। এখন নিচে স্ক্রল করে Login খুঁজব।")
            os.remove(ss_debug)

            # ৩. নিচে স্ক্রল করে Login এ ক্লিক
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(2)
            
            try:
                login_link = page.locator('text="Login"').last
                if await login_link.count() > 0:
                    await login_link.click(force=True, timeout=5000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('span, div, a, p')) { if((el.innerText||'').trim().toLowerCase() === 'login') el.click(); } }")
                await asyncio.sleep(3)
                await ctx.bot.send_message(chat_id=uid, text="✅ Login পেজে ঢুকেছি।")
            except:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ Login লেখায় ক্লিক করা যায়নি!")

            # ৪. ফোন নাম্বার ও পাসওয়ার্ড বসানো
            await ctx.bot.send_message(chat_id=uid, text="✍️ নাম্বার ও পাসওয়ার্ড বসাচ্ছি...")
            try:
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.fill(clean_phone)
                await asyncio.sleep(1)

                pass_input = page.locator('input[type="password"]').first
                await pass_input.fill(password)
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ ইনপুট ঘর খুঁজে পাইনি!")
                await browser.close()
                return

            # ৫. লগইন বাটনে ক্লিক
            await ctx.bot.send_message(chat_id=uid, text="🔘 Log in বাটনে ক্লিক করছি...")
            try:
                login_btn = page.locator('button:has-text("Log in"), button:has-text("Login")').last
                if await login_btn.count() > 0:
                    await login_btn.click(force=True, timeout=5000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { let t=(el.innerText||'').toLowerCase().trim(); if(t==='log in'||t==='login') el.click(); } }")
            except:
                pass
            
            await asyncio.sleep(7)

            # ডিবাগ স্ক্রিনশট (লগইন করার পর)
            ss_debug2 = f"step2_{uid}.png"
            await page.screenshot(path=ss_debug2)
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_debug2, 'rb'), caption="২. লগইন করার পর সাইট কেমন দেখাচ্ছে।")
            os.remove(ss_debug2)

            # ৬. পপআপ সরানো এবং Account এ যাওয়া
            for _ in range(5):
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span, i')) { let t = (el.innerText || el.className || '').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok'||t.includes('van-icon-cross')) el.click(); } }")
                await asyncio.sleep(1)

            try:
                account_btn = page.get_by_text("Account", exact=True).last
                if await account_btn.count() > 0:
                    await account_btn.click(force=True, timeout=5000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
                await asyncio.sleep(4) 
            except:
                pass

            # ৭. UID এবং Balance বের করা
            page_text = await page.inner_text("body")
            uid_match = re.search(r'UID\s*\|?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            real_uid = uid_match.group(1) if uid_match else "Unknown"
            real_balance = balance_match.group(1) if balance_match else "0.00"

            ss_path = f"dash_{uid}.png"
            await page.screenshot(path=ss_path)
            
            await status_msg.delete()
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                f"☎️ Phone : {phone}\n"
                f"👤 Real UID : `{real_uid}`\n"
                f"💰 Real Balance : **৳ {real_balance}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Engine: ONLINE\n"
            )
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), [KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_path, 'rb'), caption=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
            os.remove(ss_path)
            
        except Exception as e:
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **ERROR:** {str(e)[:150]}")
        finally:
            await browser.close()

# ═══════════════════════════════════════════
# ৩. টেলিগ্রাম হ্যান্ডলারস
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    welcome_text = "🧠 **BD=WIN~GO=AUTO~BET**\n👇 লগইন করতে নিচের বাটনে ক্লিক করুন।"
    reply_keyboard = [[KeyboardButton("🔐 LOGIN")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if text == "🔐 LOGIN" or text == "/login":
        state["awaiting"] = "phone"
        await update.message.reply_text("📱 আপনার ফোন নাম্বার দিন:")
        return

    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text("🔑 এখন আপনার পাসওয়ার্ড দিন:")
        return

    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        try: await update.message.delete()
        except: pass
        await playwright_login(uid, ctx, state["temp_phone"], state["temp_password"])
        return

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()