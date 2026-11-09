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
SITE_URL = "https://dkwwin.com/" # মেইন সাইট (যেখানে লাল বাটন আছে)

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
    
    # নাম্বার ফরম্যাট (880 এবং 0 বাদ দেওয়া)
    clean_phone = phone.strip()
    if clean_phone.startswith("880"):
        clean_phone = clean_phone[3:]
    if clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]
    
    status_msg = await ctx.bot.send_message(chat_id=uid, text="🔄 **ব্রাউজার ওপেন হচ্ছে...**\nবট সাইটে ঢুকছে, অপেক্ষা করুন।", parse_mode="Markdown")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", 
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        ) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 400, "height": 800},
            is_mobile=True,
            has_touch=True
        )
        
        # অ্যান্টি-বট স্ক্রিপ্ট
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()
        
        try:
            # ==============================================
            # ধাপ ১: মেইন সাইটে ঢুকা
            # ==============================================
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5) 

            # ==============================================
            # ধাপ ২: লাল রঙের 'Dk Win Login' বাটন খোঁজা ও ক্লিক করা
            # ==============================================
            try:
                # বাটনটি খুঁজে বের করে অটোমেটিক্যালি স্ক্রল করে সেখানে ক্লিক করবে
                red_btn = page.locator('text="Dk Win Login"').first
                await red_btn.wait_for(state="visible", timeout=15000)
                await red_btn.click(force=True, timeout=10000)
                await asyncio.sleep(4) # পেজ লোড হওয়ার অপেক্ষা
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ লাল বাটন খুঁজে পাইনি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৩: পেজের একদম নিচে স্ক্রল করে 'Login' এ ক্লিক করা
            # ==============================================
            try:
                # পেজের একদম নিচে স্ক্রল করা
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(2)
                
                # নিচের 'Login' লেখাটি খোঁজা
                login_link = page.get_by_text("Login", exact=True).last
                if await login_link.count() > 0:
                    await login_link.click(force=True, timeout=10000)
                else:
                    await page.evaluate("""
                        () => { 
                            for(let el of document.querySelectorAll('span, div, a, p, button')) { 
                                if((el.innerText||'').trim().toLowerCase() === 'login') {
                                    el.click();
                                }
                            } 
                        }
                    """)
                await asyncio.sleep(3)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ নিচের Login লেখায় ক্লিক করা যায়নি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৪: ফোন নাম্বার বসানো
            # ==============================================
            try:
                phone_input = page.locator('input:visible').first
                await phone_input.wait_for(state="visible", timeout=15000)
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(clean_phone, delay=150)
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ ফোন নাম্বার ঘর খুঁজে পাইনি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৫: পাসওয়ার্ড বসানো
            # ==============================================
            try:
                pass_input = page.locator('input[type="password"]').first
                await pass_input.click()
                await pass_input.fill("")
                await pass_input.type(password, delay=150)
                await asyncio.sleep(1)
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ পাসওয়ার্ড ঘর খুঁজে পাইনি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৬: হলুদ রঙের 'Log in' বাটনে ক্লিক
            # ==============================================
            try:
                login_btn = page.get_by_role("button", name=re.compile("Log in", re.IGNORECASE)).last
                if await login_btn.count() > 0:
                    await login_btn.click(force=True, timeout=10000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { if((el.innerText||'').toLowerCase().trim()==='log in') el.click(); } }")
            except:
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { if((el.innerText||'').toLowerCase().trim()==='log in') el.click(); } }")
            
            await asyncio.sleep(7) # লগইন হওয়ার অপেক্ষা

            # চেক করা লগইন সফল হয়েছে কিনা
            page_text = await page.inner_text("body")
            if "Wrong account or password" in page_text or "incorrect" in page_text.lower():
                await status_msg.delete()
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED:** পাসওয়ার্ড ভুল হয়েছে!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৭: পপআপ সরানো এবং 'Account' পেজে যাওয়া
            # ==============================================
            for _ in range(5):
                await page.evaluate("""
                    () => { 
                        for(let el of document.querySelectorAll('button, div, span, i')) { 
                            let t = (el.innerText || el.className || '').toLowerCase(); 
                            if(t==='confirm' || t==='receive' || t==='close' || t==='ok' || t.includes('van-icon-cross')) {
                                el.click(); 
                            }
                        } 
                    }
                """)
                await asyncio.sleep(1)

            try:
                account_btn = page.get_by_text("Account", exact=True).last
                if await account_btn.count() > 0:
                    await account_btn.click(force=True, timeout=10000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('div, span, a, p')) { if((el.innerText||'').trim().toLowerCase()==='account') el.click(); } }")
                await asyncio.sleep(4) 
            except:
                pass

            # ==============================================
            # ধাপ ৮: আসল UID এবং Balance বের করা
            # ==============================================
            page_text = await page.inner_text("body")
            
            uid_match = re.search(r'UID\s*\|?\s*(\d+)', page_text, re.IGNORECASE)
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            
            real_uid = uid_match.group(1) if uid_match else "Unknown"
            real_balance = balance_match.group(1) if balance_match else "0.00"

            state["user_id"] = real_uid
            state["balance"] = real_balance

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
            
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), [KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_photo(chat_id=uid, photo=open(ss_path, 'rb'), caption=dashboard_msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
            try: os.remove(ss_path)
            except: pass
            
        except Exception as e:
            await status_msg.delete()
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **ERROR:** {str(e)[:100]}")
        finally:
            await browser.close()