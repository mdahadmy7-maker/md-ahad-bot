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
SITE_URL = "https://dkwin0.com/#/" # মেইন সাইট (যেটা আপনার স্ক্রিনশটে আছে)

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
# ২. Playwright লগইন ফাংশন (আপনার স্ক্রিনশট অনুযায়ী)
# ═══════════════════════════════════════════
async def playwright_login(uid, ctx, phone, password):
    state = get_state(uid)
    
    # নাম্বার ফরম্যাট ঠিক করা (880 এবং 0 বাদ দেওয়া)
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
            # ধাপ ১: মেইন সাইটে ঢুকা (যেখানে Register ফর্ম আছে)
            # ==============================================
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4) # সাইট লোড হওয়ার অপেক্ষা

            # ==============================================
            # ধাপ ২: সবার নিচে থাকা 'Login' লেখায় ক্লিক করা
            # ==============================================
            try:
                # 'I have an account Login' বা শুধু 'Login' লেখাটি খোঁজা
                login_link = page.get_by_text("Login", exact=True).last
                if await login_link.count() > 0 and await login_link.is_visible():
                    await login_link.click(force=True, timeout=10000)
                else:
                    # জাভাস্ক্রিপ্ট দিয়ে নিচের Login লেখায় ক্লিক
                    await page.evaluate("""
                        () => { 
                            for(let el of document.querySelectorAll('span, div, a, p')) { 
                                if((el.innerText||'').trim().toLowerCase() === 'login') {
                                    el.click();
                                }
                            } 
                        }
                    """)
                await asyncio.sleep(3) # লগইন ফর্ম আসার অপেক্ষা
            except Exception as e:
                await ctx.bot.send_message(chat_id=uid, text="⚠️ Login বাটনে ক্লিক করা যায়নি!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৩: ফোন নাম্বার বসানো
            # ==============================================
            try:
                # পেজের প্রথম দৃশ্যমান (Visible) ইনপুট বক্স (যেটা ফোন নাম্বারের ঘর)
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
            # ধাপ ৪: পাসওয়ার্ড বসানো
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
            # ধাপ ৫: হলুদ রঙের 'Log in' বাটনে ক্লিক
            # ==============================================
            try:
                login_btn = page.get_by_role("button", name=re.compile("Log in", re.IGNORECASE)).last
                if await login_btn.count() > 0 and await login_btn.is_visible():
                    await login_btn.click(force=True, timeout=10000)
                else:
                    await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { if((el.innerText||'').toLowerCase().trim()==='log in') el.click(); } }")
            except:
                await page.evaluate("() => { for(let el of document.querySelectorAll('button, div, span')) { if((el.innerText||'').toLowerCase().trim()==='log in') el.click(); } }")
            
            await asyncio.sleep(6) # লগইন হওয়ার জন্য অপেক্ষা

            # লগইন সফল হয়েছে কিনা চেক করা
            page_text = await page.inner_text("body")
            if "Wrong account or password" in page_text or "incorrect" in page_text.lower():
                await status_msg.delete()
                await ctx.bot.send_message(chat_id=uid, text="❌ **LOGIN FAILED:** পাসওয়ার্ড ভুল হয়েছে!")
                await browser.close()
                return

            # ==============================================
            # ধাপ ৬: পপআপ সরানো এবং 'Account' পেজে যাওয়া
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
            # ধাপ ৭: আসল UID এবং Balance বের করা
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