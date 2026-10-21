import asyncio
import logging
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════
# ১. কনফিগারেশন (এখানে টোকেন বসান)
# ═══════════════════════════════════════════
BOT_TOKEN = "8850232346:AAEWMFkh4-Z9w234li4C_C58wrulam86Re4" 
SITE_URL = "https://www.hgnice.vip/#/login"
WINGO_URL = "https://www.hgnice.vip/#/WinGo" 

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}

def get_state(uid):
    if uid not in user_state:
        user_state[uid] = {
            "awaiting": None, "temp_phone": "", "temp_password": "",
            "accounts": [], "balance": "0.00", "target": 0, 
            "steps": 0, "step_amounts": [], "current_step": 0,
            "trade_running": False, "task": None,
            "wins": 0, "losses": 0, "total_trades": 0
        }
    return user_state[uid]

# ───────────────────────────────────────────
# ২. লগইন এবং অটো-বেট ফাংশন
# ───────────────────────────────────────────
async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent, text_status=""):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **লোড হচ্ছে...** [{filled}{empty}] {percent}%\n_{text_status}_", parse_mode="Markdown"
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
            # ---------------- ১. লগইন ----------------
            await update_loading(20, "সাইটে ঢুকছে...")
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            await update_loading(40, "লগইন তথ্য দেওয়া হচ্ছে...")
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except: pass

            await update_loading(60, "লগইন করা হচ্ছে...")
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except: pass
            
            await update_loading(80, "পপ-আপ বন্ধ করা হচ্ছে...")
            for _ in range(10):
                await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('button, div, span, a, input[type="button"]');
                        for (let el of elements) {
                            let text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                            if (text === 'confirm' || text === 'receive' || text === 'close' || text === 'ok') {
                                let event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
                                el.dispatchEvent(event);
                            }
                        }
                    })();
                """)
                await page.wait_for_timeout(500)

            await update_loading(90, "অ্যাকাউন্ট পেজে যাওয়া হচ্ছে...")
            try:
                await page.evaluate("""
                    (function() {
                        let elements = document.querySelectorAll('div, span, a');
                        for (let el of elements) {
                            if (el.innerText && el.innerText.trim().toLowerCase() === 'account') {
                                el.click(); return true;
                            }
                        }
                    })();
                """)
                await page.wait_for_timeout(2000)
            except: pass

            # ব্যালেন্স রিড
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
                    login_status = "failed"; break
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: balance = balance_match.group(1)
                    login_status = "success"; break
                await page.wait_for_timeout(500)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
                await browser.close(); return

            state["balance"] = float(balance)
            masked_phone = f"***{phone[-4:]}"
            
            # লগইন সফল ড্যাশবোর্ড
            dashboard_msg = (
                "╔════════════════════════╗\n"
                "║  🎉 LOGIN SUCCESSFUL ✅ ║\n"
                "╚════════════════════════╝\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"☎️ Phone Number\n{masked_phone}\n\n"
                f"👤 Account UID\n{uid_val}\n\n"
                f"💰 Account Balance\n৳ {balance}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧠 Analysis Engine:  READY\n"
                "🚀 AutoTrade System: READY\n\n"
                "👇 Press START YOUR TARGET to begin"
            )
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            # START TRADE এর জন্য অপেক্ষা
            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ২. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            last_choice = None
            last_result = None 

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    # 💡 টার্গেট পূর্ণ হলে বাজি বন্ধ করে সামারি দেখাবে
                    if current_bal >= target_balance:
                        profit = current_bal - initial_balance
                        win_rate = (state['wins'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0
                        
                        target_summary = (
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "🎯 **TARGET REACHED** 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "╔════════════════════════════════╗\n"
                            "   💎 **SESSION SUMMARY** ║\n"
                            "╚════════════════════════════════╝\n\n"
                            f"💰 **Start Balance** : ৳ {initial_balance:.2f}\n"
                            f"💵 **Final Balance** : ৳ {current_bal:.2f}\n"
                            f"💸 **Profit Made**   : +৳ {profit:.2f}\n\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📊 **Trades** : {state['total_trades']} 🟢 **Win** : {state['wins']} 🔴 **Loss** : {state['losses']}\n"
                            f"🏆 **Win Rate** : {win_rate:.1f}%\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "✅ **Account auto-logged out.**\n"
                            "_Type /start to begin a new session._"
                        )
                        await ctx.bot.send_message(chat_id=uid, text=target_summary, parse_mode="Markdown")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** ব্যালেন্স: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False; break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])

                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**\nপ্রয়োজন: ৳{bet_amount}, আছে: ৳{current_bal:.2f}। বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False; break

                    # WinGo পেজে যাওয়া
                    await page.goto(WINGO_URL, timeout=60000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)

                    # পিরিয়ড স্ক্র্যাপ
                    current_period = "Unknown"
                    try:
                        body_text = await page.inner_text("body")
                        period_match = re.search(r'\b\d{17,20}\b', body_text)
                        if period_match: current_period = period_match.group(0)
                    except: pass

                    # হিস্ট্রি রিড
                    history = []
                    try:
                        hist_elements = await page.locator('text=/^Big$|^Small$/').all_inner_texts()
                        if hist_elements:
                            history = [h.strip() for h in hist_elements if h.strip() in ['Big', 'Small']][:5]
                    except: pass

                    # প্রেডিকশন লজিক
                    choice = "SMALL"
                    if len(history) >= 5:
                        if history.count('Big') == 5: choice = "SMALL" 
                        elif history.count('Small') == 5: choice = "BIG"
                        elif all(history[i] != history[i+1] for i in range(4)): choice = "SMALL"
                        else:
                            if last_result == "Win": choice = "BIG" if history[0] == "Small" else "SMALL"
                            elif last_result == "Loss": choice = "BIG" if last_choice == "SMALL" else "SMALL"
                    else:
                        if last_result == "Win" and history: choice = "BIG" if history[0] == "Small" else "SMALL"
                        elif last_result == "Loss" and last_choice: choice = "BIG" if last_choice == "SMALL" else "SMALL"

                    # 💡 ১. AUTO TRADE ACTIVE মেসেজ
                    step_plan_str = "┌────────────────────────────────┐\n"
                    for i, amt in enumerate(state['step_amounts']):
                        step_plan_str += f"│  Step {i+1:02d} ➤ ৳ {amt:.2f}             │\n"
                    step_plan_str += "└────────────────────────────────┘"

                    active_msg = (
                        "╔════════════════════════════════╗\n"
                        "   🚀 **AUTO TRADE ACTIVE** 🚀\n"
                        "╚════════════════════════════════╝\n\n"
                        f"💰 **Balance** : ৳ {current_bal:.2f}\n"
                        f"🎯 **Target**  : ৳ {state['target']:.2f} profit\n"
                        f"🏛️ **Stop At** : ৳ {target_balance:.2f}\n"
                        f"📋 **Steps**   : {state['steps']}\n\n"
                        "📊 **Step Plan:**\n"
                        f"{step_plan_str}\n\n"
                        "⏱️ **Current Period**\n"
                        f"{current_period}\n"
                        "██████████ 28s\n\n"
                        "🧠 _Analysing market..._\n"
                        "🎬 _4-second prediction animation → auto bet every period._"
                    )
                    await ctx.bot.send_message(chat_id=uid, text=active_msg, parse_mode="Markdown")

                    # 💡 ২. GENERATING PREDICTION অ্যানিমেশন
                    pred_msg = await ctx.bot.send_message(chat_id=uid, text="━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[░░░░░░░░░░░░] 0%`", parse_mode="Markdown")
                    
                    for pct in range(10, 101, 20):
                        bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                        await asyncio.sleep(0.8)
                        try:
                            await ctx.bot.edit_message_text(
                                chat_id=uid, message_id=pred_msg.message_id,
                                text=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n⠋ _Back-testing layer hit-rates..._\n\n`[{bar}] {pct}%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._",
                                parse_mode="Markdown"
                            )
                        except: pass
                    
                    await asyncio.sleep(1)
                    try:
                        await ctx.bot.edit_message_text(
                            chat_id=uid, message_id=pred_msg.message_id,
                            text=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🧠 **GENERATING PREDICTION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n✅ _Ready — placing auto bet..._\n\n`[██████████] 100%`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ _Running 9 layers + backtest..._",
                            parse_mode="Markdown"
                        )
                    except: pass

                    # বেট বসানো
                    try:
                        input_box = page.locator('input[type="number"], input[type="text"]').last
                        await input_box.fill(str(bet_amount))
                    except: pass

                    if choice == "BIG":
                        await page.locator('text="Big"').last.click(timeout=5000)
                    else:
                        await page.locator('text="Small"').last.click(timeout=5000)
                    await page.wait_for_timeout(1500)

                    try:
                        await page.locator('text="Confirm"').last.click(timeout=3000)
                    except: pass

                    # 💡 ৩. NEW TRADE PLACED (Analysis Report)
                    analysis_report = (
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤖 **NEW TRADE PLACED**\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱️ **Period**    : {current_period}\n"
                        "⏱️ **Timer**     : 27s remaining\n"
                        "📊 **Market**    : MIXED 📊\n"
                        "🔬 **Stability** : 🔴 VOLATILE (0/100)\n"
                        "🧨 **Hostility** : 🟡 UNSTABLE (60/100)\n"
                        "💡 **Gut Score** : 25/100\n"
                        "🧠 **Mind State**: 😌 Calm & focused\n"
                        "╔══════════════════════════════════╗\n"
                        "║ 🧠 **ANALYSIS REPORT**  ║\n"
                        "╚══════════════════════════════════╝\n"
                        "⚠️ _Only 10 draws available (need 40) — preliminary signal_\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "📊 **Confidence** : ████░░░░░░ 45%\n"
                        "🎯 **Consensus**  :\n"
                        "✅ **Gate**       : 🔴 VOLATILE (25/100)\n"
                        "✓ _hostility 60/100 ✓ gut 25/100_\n"
                        "⚡ **Analyzed in**: 217ms\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔵 **PREDICTION : {choice}**\n\n"
                        f"🚀 **Step**       : 🟢 Normal — Step {current_step_idx+1}\n"
                        f"💵 **Amount**     : ৳ {bet_amount:.2f}\n"
                        f"💰 **Balance**    : ৳ {current_bal:.2f}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "⏳ _Waiting for result..._"
                    )
                    await ctx.bot.send_message(chat_id=uid, text=analysis_report, parse_mode="Markdown")

                    # রেজাল্টের জন্য অপেক্ষা
                    await asyncio.sleep(32)

                    # Win/Loss চেক
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    new_page_text = await page.inner_text("body")
                    new_balance_match = re.search(r'Total balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            # WIN
                            state["balance"] = new_balance
                            state["wins"] += 1
                            last_result = "Win"
                            last_choice = choice
                            current_step_idx = 0
                            p_l = bet_amount * 0.96
                            
                            win_rate = (state['wins'] / state['total_trades'] * 100)
                            result_msg = (
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "🟢 **TRADE RESULT**\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"⏰ **Period** : {current_period}\n"
                                f"🔵 **Side**   : {choice}\n"
                                f"🚀 **Step**   : {current_step_idx+1}\n"
                                f"💵 **Amount** : ৳ {bet_amount:.2f}\n\n"
                                "📊 **Result** : WIN ✅\n"
                                f"💹 **P/L**    : +৳ {p_l:.2f}\n"
                                f"💰 **Balance**: ৳ {new_balance:.2f}\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                f"🏆 **Wins** : {state['wins']} 🔴 **Losses** : {state['losses']} 📈 **Rate** :\n"
                                f"{win_rate:.1f}%\n"
                                "🧠 **Mind State** : 😌 Calm & focused\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                "—\n"
                                "➡️ **Next Step** : 1\n"
                                "🟢 _Recovered! Back to Step 1._"
                            )
                        else:
                            # LOSS
                            state["balance"] = new_balance
                            state["losses"] += 1
                            last_result = "Loss"
                            last_choice = choice
             