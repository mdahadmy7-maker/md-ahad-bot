import asyncio
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ══════════════════════════════════════════════════════════════
# 🔧 ১. কনফিগারেশন (এখানে আপনার বট টোকেন বসান)
# ══════════════════════════════════════════════════════════════
BOT_TOKEN = "8850232346:AAFSa0GMt5KPoH-L4ZexuJqRR4XPmgw-8Zg" 

# ওয়েবসাইটের সঠিক লগইন লিংক
SITE_URL = "https://www.hgnice.vip/#/login"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ইউজারের ডেটা সাময়িকভাবে সেভ রাখার জায়গা
user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, "steps": 0
        }
    return user_state[uid]

# ══════════════════════════════════════════════════════════════
# 💡 ২. প্লে-রাইট (Playwright) দিয়ে ওয়েবসাইটে লগইন করার ফাংশন
# ══════════════════════════════════════════════════════════════
async def playwright_login(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    # ৮৮০ বাদ দেওয়া (যেমন: 8801884495095 থেকে 1884495095)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async with async_playwright() as p:
        # অদৃশ্য ব্রাউজার ওপেন করা
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        
        # মোবাইল ব্রাউজার সিমুলেশন
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        try:
            # ১. ওয়েবসাইটে যাওয়া
            if loading_msg_id:
                try: await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text="🌐 **ব্রাউজার ওপেন হচ্ছে এবং সাইটে ঢুকছে...**", parse_mode="Markdown")
                except: pass

            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            
            # ইন্টারনেট স্লো হলে ৫ সেকেন্ড অপেক্ষা করবে
            await page.wait_for_timeout(5000) 
            
            # ২. নাম্বার ও পাসওয়ার্ড বসানো
            if loading_msg_id:
                try: await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text="📝 **নাম্বার ও পাসওয়ার্ড বসানো হচ্ছে...**", parse_mode="Markdown")
                except: pass

            try:
                # ইনপুট বক্স খোঁজা এবং তথ্য বসানো
                await page.fill('input[type="text"], input[type="tel"]', login_phone, timeout=15000)
                await page.wait_for_timeout(1000)
                await page.fill('input[type="password"]', password, timeout=15000)
            except Exception as e:
                # ইনপুট বক্স না পেলে স্ক্রিনশট নিয়ে টেলিগ্রামে পাঠাবে
                screenshot_path = f"error_{uid}.png"
                await page.screenshot(path=screenshot_path)
                if loading_msg_id:
                    try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                    except: pass
                with open(screenshot_path, "rb") as photo:
                    await ctx.bot.send_photo(
                        chat_id=uid, 
                        photo=photo, 
                        caption=f"⚠️ দুঃখিত, ইনপুট বক্স পাওয়া যায়নি। সার্ভার থেকে ব্রাউজারটি এরকম দেখাচ্ছে।"
                    )
                await browser.close()
                return

            # ৩. লগইন বাটনে ক্লিক
            if loading_msg_id:
                try: await ctx.bot.edit_message_text(chat_id=uid, message_id=loading_msg_id, text="🔑 **লগইন বাটনে ক্লিক করা হচ্ছে...**", parse_mode="Markdown")
                except: pass

            await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=15000)
            
            # লগইন প্রসেস শেষ হতে ৮ সেকেন্ড অপেক্ষা (ইন্টারনেট স্লো হলে কাজে দেবে)
            await page.wait_for_timeout(8000)
            
            # ৪. রেজাল্ট চেক করা
            page_text = await page.inner_text("body")
            
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            # ভুল পাসওয়ার্ড চেক
            if "Wrong account or password" in page_text:
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **লগইন ব্যর্থ!**\n\nভুল নাম্বার অথবা পাসওয়ার্ড দেওয়া হয়েছে।", parse_mode="Markdown")
                await browser.close()
                return
                
            # UID এবং Balance খোঁজা
            uid_val = "Unknown"
            balance = "0.00"
            
            uid_match = re.search(r'UID\s*\|\s*(\d+)', page_text, re.IGNORECASE)
            if uid_match: uid_val = uid_match.group(1)
                
            balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
            if balance_match: balance = balance_match.group(1)

            if uid_val == "Unknown":
                 await ctx.bot.send_message(chat_id=uid, text=f"⚠️ লগইন হয়েছে কিন্তু ড্যাশবোর্ড থেকে UID পাওয়া যায়নি।")
                 await browser.close()
                 return

            # অ্যাকাউন্ট সেভ করা
            account_info = {"phone": phone, "password": password, "uid": uid_val, "balance": balance}
            existing = False
            for acc in state["accounts"]:
                if acc["phone"] == phone:
                    acc.update(account_info)
                    existing = True
                    break
            if not existing:
                state["accounts"].append(account_info)
                
            state["balance"] = balance
            masked_phone = f"***{phone[-4:]}"
            
            # 💡 ৫. আপনার পছন্দের ড্যাশবোর্ড ডিজাইন
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 লগইন সফল হয়েছে ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ ফোন নাম্বার\n{masked_phone}\n\n"
                f"👤 অ্যাকাউন্ট UID\n{uid_val}\n\n"
                f"💰 অ্যাকাউন্ট ব্যালেন্স\n৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 অ্যানালাইসিস ইঞ্জিন:  প্রস্তুত\n"
                "🚀 অটো-ট্রেড সিস্টেম: প্রস্তুত\n\n"
                "👇 শুরু করতে নিচের বাটনে চাপ দিন"
            )
            
            reply_keyboard = [
                [KeyboardButton("🚀 টার্গেট শুরু করুন")],
                [KeyboardButton("🛑 ট্রেড বন্ধ করুন"), KeyboardButton("🚪 লগআউট")]
            ]
            markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=markup)
            
            if len(state["accounts"]) < 6:
                await ctx.bot.send_message(chat_id=uid, text=f"✅ অ্যাকাউন্ট সেভ হয়েছে ({len(state['accounts'])}/6)। নতুন অ্যাকাউন্ট যোগ করতে /start দিন।")

        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সার্ভার সমস্যা:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()

# ══════════════════════════════════════════════════════════════
# ৩. টেলিগ্রাম হ্যান্ডলার (কমান্ড ও মেসেজ প্রসেসিং)
# ══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    
    if len(state["accounts"]) >= 6:
        await update.message.reply_text("✅ আপনার ৬টি অ্যাকাউন্ট ইতিমধ্যে সেভ করা আছে। নতুন করে শুরু করতে /reset দিন।")
        return

    # সুন্দর ওয়েলকাম মেসেজ
    welcome_text = (
        "🧠 **BD=WIN~GO=AUTO~BET 💥**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 মোড    : অটো অ্যানালাইসিস এবং বাজি\n"
        "🔐 অ্যাক্সেস  : প্রাইভেট · অনুমোদিত সদস্য\n"
        "🔴 স্ট্যাটাস  : লগইন করা নেই\n"
        f"👥 অ্যাকাউন্ট: {len(state['accounts'])}/৬\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 প্রেডিকশন ইঞ্জিন — ৯টি লেয়ার\n"
        "⚡ স্ট্রিক · 🔷 প্যাটার্ন · 📈 ট্রেন্ড\n"
        "🔍 ম্যানিপুলেশন · 🎨 কালার · 🔢 ফ্রিকোয়েন্সি\n"
        "🔄 মার্কভ · ♻️ সাইকেল · 💠 মোমেন্টাম\n"
        "🔁 প্রতিটি লেয়ার লাইভ ব্যাক-টেস্টেড\n"
        "🔴 কনফিডেন্স ৩০% এর নিচে → বিরতি\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 ৪ সেকেন্ডের প্রেডিকশন অ্যানিমেশন\n"
        "🚀 অ্যানালাইসিস → প্রতি ৩০ সেকেন্ডে অটো বাজি\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 লগইন করতে নিচের বাটনে ক্লিক করুন"
    )
    keyboard = [[InlineKeyboardButton("🔐 অ্যাকাউন্টে লগইন করুন", callback_data="start_login")]]
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = update.message.text.strip()

    # ১. ফোন নাম্বার নেওয়া
    if state.get("awaiting") == "phone":
        state["temp_phone"] = text
        state["awaiting"] = "password"
        await update.message.reply_text(
            "╔════════════════════════╗\n"
            "║  🔐 অ্যাকাউন্ট লগইন 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            f"☎️ নাম্বার : {text}\n\n"
            "🔑 **এখন আপনার পাসওয়ার্ড দিন:**\n"
            "নিরাপত্তার জন্য আপনার মেসেজটি সাথে সাথে ডিলিট হয়ে যাবে।"
        )
        return

    # ২. পাসওয়ার্ড নেওয়া এবং লগইন শুরু করা
    if state.get("awaiting") == "password":
        state["temp_password"] = text
        state["awaiting"] = None 
        
        try: await update.message.delete()
        except: pass
        
        loading_msg = await update.message.reply_text("🔄 কানেক্ট হচ্ছে... [░░░░░░░░░░] ০%")
        for i in range(1, 11):
            await asyncio.sleep(0.1)
            try: await loading_msg.edit_text(f"🔄 কানেক্ট হচ্ছে... [{'█'*i}{'░'*(10-i)}] {i*10}%")
            except: pass
        
        await playwright_login(uid, ctx, loading_msg.message_id, state["temp_phone"], state["temp_password"])
        return

    # ৩. "টার্গেট শুরু করুন" বাটনে ক্লিক করলে
    if text == "🚀 টার্গেট শুরু করুন":
        state["awaiting"] = "target"
        target_msg = (
            "╔════════════════════════╗\n"
            "║   🚀 টার্গেট শুরু করুন 🚀   ║\n"
            "╚════════════════════════╝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 আপনার ব্যালেন্স\n"
            f"৳ {state.get('balance', '0.00')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 আপনার টার্গেট প্রফিট লিখুন:\n"
            "আপনি কত টাকা আয় করতে চান? (৳)"
        )
        await update.message.reply_text(target_msg)
        return

    # ৪. টার্গেট প্রফিট নেওয়া
    if state.get("awaiting") == "target":
        try:
            target_amount = float(text)
            state["target"] = target_amount
            balance = float(state.get('balance', '0.00'))
            stop_at = balance + target_amount
            
            target_set_msg = (
                "╔════════════════════════╗\n"
                "║   🎯 টার্গেট সেট 🎯   ║\n"
                "╚════════════════════════╝\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 ব্যালেন্স  : ৳ {balance:.2f}\n"
                f"🎯 টার্গেট   : ৳ {target_amount:.2f} প্রফিট\n"
                f"🏦 স্টপ অ্যাট  : ৳ {stop_at:.2f}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 আপনার স্টেপ কাউন্ট লিখুন:\n"
                "কত ধাপে বাজি ধরবেন? (যেমন: ৫, সর্বোচ্চ ৫০)"
            )
            state["awaiting"] = "steps"
            await update.message.reply_text(target_set_msg)
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! দয়া করে শুধু সংখ্যা লিখুন (যেমন: 50)।")
        return
        
    # ৫. স্টেপ কাউন্ট নেওয়া
    if state.get("awaiting") == "steps":
        try:
            steps = int(text)
            state["steps"] = steps
            state["awaiting"] = None
            await update.message.reply_text(f"✅ স্টেপ কাউন্ট সেট: {steps}\n\nবট এখন কাজ শুরু করবে (অটো-বেট লজিক পরবর্তী ধাপে যোগ হবে)।")
        except ValueError:
            await update.message.reply_text("❌ ভুল ফরম্যাট! ১ থেকে ৫০ এর মধ্যে একটি সংখ্যা দিন (যেমন: 5)।")
        return

    # ৬. অন্যান্য বাটন
    if text == "🛑 ট্রেড বন্ধ করুন":
        await update.message.reply_text("🛑 ট্রেড বন্ধ করা হয়েছে।")
        return
        
    if text == "🚪 লগআউট":
        state["temp_phone"] = ""
        state["temp_password"] = ""
        await update.message.reply_text("🚪 লগআউট সম্পন্ন হয়েছে। আবার শুরু করতে /start দিন।")
        return

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = get_state(uid)
    
    if query.data == "start_login":
        state["awaiting"] = "phone"
        login_msg = (
            "╔════════════════════════╗\n"
            "║  🔐 অ্যাকাউন্ট লগইন 🔐  ║\n"
            "╚════════════════════════╝\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 আপনার HGNICE ফোন নাম্বার দিন:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "প্রত্যেকে নিজের অ্যাকাউন্ট ব্যবহার করুন — আপনার সেশনটি প্রাইভেট।"
        )
        await ctx.bot.send_message(chat_id=uid, text=login_msg)

# রিসেট কমান্ড (সব ডেটা মুছে ফেলার জন্য)
async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {
        "awaiting": None, "temp_phone": "", "temp_password": "",
        "accounts": [], "balance": "0.00", "target": 0, "steps": 0
    }
    await update.message.reply_text("🔄 সব ডেটা রিসেট হয়েছে। নতুন করে শুরু করতে /start দিন।")

# ══════════════════════════════════════════════════════════════
# ৪. মেইন ফাংশন (বট চালু করা)
# ══════════════════════════════════════════════════════════════
def main():
    # টোকেন চেক করা
    if not BOT_TOKEN or BOT_TOKEN == "এখানে_আপনার_টেলিগ্রাম_বটের_টোকেন_বসান":
        print("❌ এরর: BOT_TOKEN সেট করা নেই! কোডের ১২ নম্বর লাইনে টোকেন বসান।")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🤖 বট চালু হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()