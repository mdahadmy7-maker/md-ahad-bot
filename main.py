async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    login_phone = phone[3:] if phone.startswith("880") else phone
    
    async def update_loading(percent):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **CONNECTING TO HGNICE**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        # API ক্যাপচার
        def log_bet_api(request):
            if request.method == "POST" and "api" in request.url and "Login" not in request.url:
                logger.info("\n" + "="*50)
                logger.info(f"🔴 CAPTURED API: {request.url}")
                logger.info(f"📦 PAYLOAD: {request.post_data}")
                logger.info("="*50 + "\n")
        page.on("request", log_bet_api)

        try:
            # ---------------- ১. লগইন ----------------
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            await update_loading(30)
            try:
                await page.get_by_placeholder("Please enter the phone number").fill(login_phone)
                await page.locator('input[type="password"]').first.fill(password)
            except: pass

            await update_loading(50)
            try:
                await page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last.click(timeout=10000)
            except:
                await page.locator('button:has-text("Log in")').last.click(timeout=10000)
            
            await update_loading(70)
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
                await page.wait_for_timeout(400)

            await update_loading(85)
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
                await page.wait_for_timeout(3000) 
            except: pass

            await update_loading(95)
            login_status = "unknown"
            uid_val = "Unknown"
            balance = "0.00"

            for _ in range(10): 
                page_text = await page.inner_text("body")
                if "Wrong account or password" in page_text:
                    login_status = "failed"
                    break
                
                uid_match = re.search(r'UID\s*[|:]?\s*(\d+)', page_text, re.IGNORECASE)
                balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', page_text, re.IGNORECASE)
                
                if uid_match:
                    uid_val = uid_match.group(1)
                    if balance_match: 
                        balance = balance_match.group(1)
                    login_status = "success"
                    break
                await page.wait_for_timeout(500)

            await update_loading(100)
            await asyncio.sleep(0.2)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            if login_status == "failed" or uid_val == "Unknown":
                await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED** ({phone})")
                await browser.close()
                return

            state["balance"] = float(balance)
            masked_phone = f"***{phone[-4:]}"
            
            dashboard_msg = (
                f"🎉 **LOGIN SUCCESSFUL** ✅\n"
                f"☎️ Number: {masked_phone}\n"
                f"👤 UID: {uid_val}\n"
                f"💰 Balance: ৳ {balance}\n\n"
                f"👇 Press START YOUR TARGET to begin"
            )
            reply_keyboard = [[KeyboardButton("🚀 START YOUR TARGET")], [KeyboardButton("🛑 STOP TRADE"), KeyboardButton("🚪 LOGOUT")]]
            await ctx.bot.send_message(chat_id=uid, text=dashboard_msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

            while not state.get("trade_running", False):
                await asyncio.sleep(1)
                if state.get("task") != asyncio.current_task():
                    await browser.close()
                    return

            # ---------------- ৪. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            
            # WinGo পেজে যাওয়া
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            
            # গেম পেজে ঢোকার জন্য ক্লিক
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
                await page.wait_for_timeout(1000)
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except: pass
            await page.wait_for_timeout(3000) 

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳ {current_bal - initial_balance:.2f}\nবট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!** বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])

                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!** বট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    choice, current_period = get_history_and_prediction()

                    # 💡 ১. টাইমার চেক (নতুন রাউন্ড শুরু হওয়ার অপেক্ষা - ২৫ থেকে ২৯ সেকেন্ড)
                    logger.info("Waiting for 25s-29s phase...")
                    timer_val = "0s"
                    for _ in range(350): # ৩৫ সেকেন্ড পর্যন্ত অপেক্ষা করবে
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            
                            # টাইমার ফরম্যাট খোঁজা (যেমন: 0 0 : 25 অথবা 00:25)
                            match = re.search(r'0\s*0\s*[:.]?\s*(2[5-9])', body_text)
                            if not match:
                                match = re.search(r'00\s*[:.]?\s*(2[5-9])', body_text)
                                
                            if match:
                                sec = match.group(1)
                                timer_val = f"{sec}s"
                                break
                        except: pass
                        await asyncio.sleep(0.1) 

                    if state.get("first_bet", True):
                        await ctx.bot.send_message(chat_id=uid, text=(
                            f"🚀 **AUTO TRADE ACTIVE**\n"
                            f"💰 Balance: ৳ {current_bal:.2f}\n"
                            f"⏱️ Period: {current_period}\n"
                            f"🧠 Prediction: **{choice}**"
                        ), parse_mode="Markdown")
                        state["first_bet"] = False 

                    # 💡 ২. Big/Small এ ক্লিক করা
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        await page.wait_for_timeout(200)
                        
                        # BIG বা SMALL এ ক্লিক
                        await page.get_by_text(choice.upper(), exact=True).first.click(force=True, timeout=3000)
                        logger.info(f"Clicked on {choice}")
                    except Exception as e:
                        logger.error(f"Failed to click Big/Small: {e}")
                    
                    # মডাল ওপেন হওয়ার জন্য অপেক্ষা
                    await page.wait_for_timeout(1500)

                    # 💡 ৩. Amount বসানো
                    try:
                        inputs = await page.locator('input[type="text"], input[type="number"]').all()
                        for inp in inputs:
                            if await inp.is_visible():
                                await inp.fill(str(int(bet_amount))) 
                                break
                    except Exception as e:
                        logger.error(f"Input error: {e}")

                    # "I agree" চেকবক্স ক্লিক
                    try:
                        agree_box = page.locator('text="I agree"').first
                        if await agree_box.is_visible():
                            await agree_box.click(force=True, timeout=1000)
                    except: pass

                    # 💡 ৪. "Total amount" বাটনে ক্লিক করা (সবচেয়ে গুরুত্বপূর্ণ অংশ)
                    confirm_success = False
                    try:
                        # Total amount টেক্সটটি খোঁজা
                        total_amount_btn = page.locator("text=Total amount").last
                        # বাটনটি স্ক্রিনে আসার জন্য অপেক্ষা করা (সর্বোচ্চ ৫ সেকেন্ড)
                        await total_amount_btn.wait_for(state="visible", timeout=5000)
                        await total_amount_btn.click(force=True, timeout=3000)
                        confirm_success = True
                        logger.info("Clicked 'Total amount' successfully!")
                    except Exception as e:
                        logger.error(f"'Total amount' click failed: {e}")
                        
                        # যদি ব্যর্থ হয়, তবে স্ক্রিনশট নিয়ে টেলিগ্রামে পাঠাবে ডিবাগ করার জন্য
                        await page.screenshot(path=f"error_confirm_{uid}.png")
                        await ctx.bot.send_photo(
                            chat_id=uid, 
                            photo=open(f"error_confirm_{uid}.png", 'rb'), 
                            caption="⚠️ **'Total amount' বাটনে ক্লিক করা যায়নি!**\nস্ক্রিনশটে দেখুন বাটনটি এসেছিল কি না।"
                        )
                        continue # পরের রাউন্ডে চলে যাবে

                    # স্ক্রিনশট নেওয়া (সফল হলে)
                    await page.wait_for_timeout(1500)
                    proof_path = f"proof_success_{uid}.png"
                    await page.screenshot(path=proof_path)
                    
                    await ctx.bot.send_photo(
                        chat_id=uid, photo=open(proof_path, 'rb'), 
                        caption=f"✅ **BET PLACED!**\n🎯 Prediction: **{choice}**\n💵 Amount: ৳ {bet_amount:.2f}"
                    )

                    # রেজাল্টের জন্য অপেক্ষা
                    await asyncio.sleep(32)

                    # রেজাল্ট চেক
                    await page.goto("https://www.hgnice.vip/#/Account", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000) 
                    
                    new_page_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', new_page_text, re.IGNORECASE)
                    
                    if new_balance_match:
                        new_balance = float(new_balance_match.group(1))
                        state['total_trades'] += 1
                        
                        if new_balance > current_bal:
                            state["balance"] = new_balance
                            state["wins"] += 1
                            current_step_idx = 0
                            await ctx.bot.send_message(chat_id=uid, text=f"🟢 **WIN!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: 1")
                        else:
                            state["balance"] = new_balance
                            state["losses"] += 1
                            current_step_idx += 1
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n➡️ Next Step: {current_step_idx+1}")

                    # আবার WinGo পেজে ফেরা
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)
                    try:
                        await page.locator('text="Lottery"').first.click(timeout=3000, force=True)
                        await page.wait_for_timeout(1000)
                        win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                        await win_go_card.click(timeout=3000, force=True)
                    except: pass
                    await page.wait_for_timeout(2000)

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **TRADE STOPPED**\nError: {str(e)[:50]}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass
            await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **Browser Error:**\n`{str(e)[:150]}`", parse_mode="Markdown")
        finally:
            await browser.close()