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
SITE_URL = "https://dkwin0.com/#/" # মেইন সাইট (হোমপেজ)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, 
            "temp_phone": "", 
            "temp_password": "",
            "balance": "0.00", 
            "user_id": "Unknown"
        }
    return user_state[uid]

# ═══════════════════════════════════════════
# ২. Playwright লগইন ফাংশন (আপনার ৫টি ধাপ অনুযায়ী)
# ═══════════════════════════════════════════
async def playwright_login(uid, ctx, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **ব্রাউজার ওপেন হচ্ছে...**\nবট মেইন সাইটে ঢুকছে, অপেক্ষা করুন।", parse_mode="Markdown")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", 
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800},
            is_mobile=True,
            has_touch=True
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()
        
        try:
            # ==============================================
            # ধাপ ১: মেইন সাইটে ঢুকে লাল লেখায় ('Dk Win Login') ক্লিক করা
            # ==============================================
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4) 

            try:
                # 'Dk Win Login (Quick Sign-In Link)' লেখাটি খোঁজা
                red_btn = page.locator('text="Dk Win Login"').first
                if await red_btn.count() > 0:
                    await red_btn.click(force=True, timeout=10000)
                    await asyncio.sleep(3) # পেজ লোড হওয়ার অপেক্ষা
                else:
                    # যদি লাল বাটন না পাওয়া যায়, তবে সরাসরি লগইন পেজে যাবে
                    await page.goto("https://dkwin0.com/#/login", wait_until="domcontentloaded")
                    await asyncio.sleep(3)
            except:
                await page.goto("https://dkwin0.com/#/login", wait_until="domcontentloaded")
                await asyncio.sleep(3)

            # ==============================================
            # ধাপ ২ ও ৩: ফোন নাম্বার ও পাসওয়ার্ড বসানো
            # ==============================================
            
            # ফোন নাম্বার ঘর
            try:
                phone_input = page.locator('input[placeholder*="phone" i]').first
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(login_phone, delay=100)
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ ফোন নাম্বার ঘর খুঁজে পাইনি!")
                await browser.close()
                return

            # পাসওয়ার্ড ঘর
            try:
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.type(password, delay=100)
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ পাসওয়ার্ড ঘর খুঁজে পাইনি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৩: হলুদ রঙের 'Log in' বাটনে ক্লিক করা
            # ==============================================
            try:
                login_btn = page.get_by_role("button", name=re.compile("Log in", re.IGNORECASE)).last
                if await login_btn.count() > 0:
                    await login_btn.click(force=True, timeout=10000)
                else:
                    await page.locator('text="Log in"').last.click(force=True)
            except:
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div')) { if((el.innerText||'').toLowerCase()==='log in') el.click(); } }")
            
            await asyncio.sleep(6) # লগইন প্রসেস হওয়ার জন্য অপেক্ষা

            # চেক করা লগইন সফল হয়েছে কিনা
            page_text = await page.inner_text("body")
            if "Wrong account or password" in page_text or "incorrect" in page_text.lower():
                await status_msg.delete()
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED:** পাসওয়ার্ড ভুল হয়েছে!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৪: যদি কোনো পপআপ বা প্রভাব (Popup) আসে, সেটি সরানো
            # ==============================================
            for _ in range(5): # ৫ বার চেষ্টা করবে পপআপ বন্ধ করার
                await page.evaluate("""
                    () => { 
                        for(let el of document.querySelectorAll('button, div, span, i')) { 
                            let t = (el.innerText || el.className || '').toLowerCase(); 
                            if(t==='confirm' || t==='receive' || t==='close' || t==='ok' || t==='cancel' || t.includes('close-icon') || t.includes('van-icon-cross')) {
                                el.click(); 
                            }
                        } 
                    }
                """)
                await asyncio.sleep(1) # পপআপ মিলিয়ে যাওয়ার অপেক্ষা

            # ==============================================
            # ধাপ ৫: নিচের ডানদিকের 'Account' বাটনে ক্লিক করে আসল UID ও Balance বের করা
            # ==============================================
            try:
                account_btn = page.get_by_text("Account", exact=True).last
                if await account_btn.count() > 0:
                    await account_btn.click(force=True, timeout=10000)
                else:
                    await page.locator('text="Account"').last.click(force=True)
                await asyncio.sleep(4) # অ্যাকাউন্ট পেজ পুরোপুরি লোড হওয়ার অপেক্ষা
            except:
                pass

            # পেজের ভেতরের লেখা থেকে UID এবং Balance রেজেক্স দিয়ে খোঁজা
            page_text = await page.inner_text("body")
            
            # UID খোঁজা (যেমন: UID | 1010493)
            uid_match = re.search(r'UID\s*\|?\s*(\d+)', page_text, re.IGNORECASE)
            # ব্যালেন্স খোঁজা (যেমন: Total balance ৳1.58)
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            real_uid = uid_match.group(1) if uid_match else "Unknown"
            real_balance = balance_match.group(1) if balance_match else "0.00"

            state["user_id"] = real_uid
            state["balance"] = real_balance

            # ফাইনাল স্ক্রিনশট এবং ড্যাশবোর্ড পাঠানো
            ss_path = f"dash_{uid}.png"
            await page.screenshot(path=ss_path)
            
            await status_msg.delete()
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone : {phone}\n\n"
                f"👤 Real UID : `{real_uid}`\n\n"
                f"💰 Real Balance : **৳ {real_balance}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Engine: ONLINE\n"
                "🚀 Ready to trade"
            )
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_path, 'rb'), caption=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
            try: os.remove(ss_path)
            except: pass
            
        except Exception as e:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **ERROR:** {str(e)[:100]}")
        finally:
            await browser.close()

# ═══════════════════════════════════════════
# ৩. টেলিগ্রাম হ্যান্ডলারস
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 লগইন করতে নিচের বাটনে ক্লিক করুন।"
    )
    reply_keyboard = [[KeyboardButton("🔐 LOGIN")]]
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()
    
    if text == "🔐 LOGIN" or text == "/login":
        state["awaiting"] = "phone"
        await update.message.reply_text("📱 আপনার ফোন নাম্বার দিন:\n(যেমন: 017XXXXXXXX)")
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
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN সেট করা নেই!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("login", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 Playwright Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()