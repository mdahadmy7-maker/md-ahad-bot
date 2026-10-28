async def playwright_login_and_bet(uid, ctx, loading_msg_id, phone, password):
    state = get_state(uid)
    # 💡 880 সহ পুরো নম্বরটিই ব্যবহার করা হচ্ছে
    login_phone = phone 
    
    async def update_loading(percent, text="CONNECTING TO HGNICE"):
        if not loading_msg_id: return
        filled = "█" * (percent // 10)
        empty = "░" * (10 - (percent // 10))
        try:
            await ctx.bot.edit_message_text(
                chat_id=uid, message_id=loading_msg_id, 
                text=f"🔄 **{text}**\n[{filled}{empty}] {percent}%", parse_mode="Markdown"
            )
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"]) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = await context.new_page()
        
        # ==========================================
        # 💡 এপিআই ক্যাপচার (WinGoBet)
        # ==========================================
        async def log_bet_api(request):
            if request.method == "POST":
                auth_header = request.headers.get("authorization", "")
                if "Bearer" in auth_header:
                    state["bearer_token"] = auth_header.replace("Bearer ", "")

                # URL-এ wingobet থাকলেই ক্যাপচার করবে (case-insensitive)
                if "wingobet" in request.url.lower():
                    try:
                        api_msg = (
                            "🚨 <b>REAL BET API CAPTURED!</b> 🚨\n\n"
                            f"🔗 <b>URL:</b>\n<code>{request.url}</code>\n\n"
                            f"📦 <b>Payload:</b>\n<pre>{request.post_data}</pre>\n\n"
                            f"🔑 <b>Bearer Token:</b>\n<code>{state.get('bearer_token', 'Not Found')[:50]}...</code>"
                        )
                        await ctx.bot.send_message(chat_id=uid, text=api_msg, parse_mode="HTML")
                        logger.info("WinGoBet API Captured Successfully!")
                    except Exception as e:
                        logger.error(f"Telegram capture failed: {e}")

        page.on("request", log_bet_api)
        # ==========================================

        try:
            # ---------------- ১. লগইন ----------------
            await update_loading(10)
            await page.goto(SITE_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000) # পেজ পুরোপুরি লোড হওয়ার জন্য অপেক্ষা

            await update_loading(30)
            try:
                # পপআপ থাকলে আগে বন্ধ করা
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(1000)

                # ইনপুট ফিল্ডগুলো খুঁজে বের করা
                phone_input = page.locator('input[type="text"], input[type="tel"]').first
                await phone_input.wait_for(state="visible", timeout=10000)
                await phone_input.fill(login_phone)
                
                pwd_input = page.locator('input[type="password"]').first
                await pwd_input.fill(password)
                
                # লগইন বাটনে ক্লিক
                login_btn = page.get_by_role("button", name=re.compile("log in", re.IGNORECASE)).last
                await login_btn.click(force=True, timeout=10000)
            except Exception as e:
                logger.error(f"Login fill error: {e}")

            await update_loading(60)
            # লগইনের পর পপআপ ক্লোজ
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

            await update_loading(80)
            # 💡 Account পেজে যাওয়া
            try:
                await page.locator('text="Account"').first.click(timeout=5000, force=True)
            except:
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
            await page.wait_for_timeout(4000) 

            # লগইন স্ট্যাটাস চেক
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
                await page.wait_for_timeout(1000)

            await update_loading(100)
            await asyncio.sleep(0.5)

            if loading_msg_id:
                try: await ctx.bot.delete_message(chat_id=uid, message_id=loading_msg_id)
                except: pass

            # 💡 লগইন ফেইল হলে স্ক্রিনশট পাঠাবে
            if login_status == "failed" or uid_val == "Unknown":
                error_img = f"login_error_{uid}.png"
                await page.screenshot(path=error_img)
                try:
                    await ctx.bot.send_photo(
                        chat_id=uid, 
                        photo=open(error_img, 'rb'), 
                        caption=f"❌ **LOGIN FAILED** ({phone})\nস্ক্রিনশট দেখে বুঝুন কী সমস্যা হয়েছে।"
                    )
                except Exception as e:
                    await ctx.bot.send_message(chat_id=uid, text=f"❌ **LOGIN FAILED**\nError: {str(e)}")
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

            # ---------------- ২. অটো-বেট লুপ ----------------
            initial_balance = float(balance)
            target_balance = initial_balance + float(state['target'])
            current_step_idx = 0
            
            await page.goto(HOME_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) 
            
            for _ in range(3):
                await page.evaluate("""() => { for(let el of document.querySelectorAll('button, div, span, a')) { let t = (el.innerText||'').toLowerCase(); if(t==='confirm'||t==='receive'||t==='close'||t==='ok') el.click(); } }""")
                await page.wait_for_timeout(500)
                
            try:
                await page.locator('text="Lottery"').first.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, a')) { if((el.innerText||'').toLowerCase().includes('lottery')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(2000)
            
            try:
                win_go_card = page.locator('div:has-text("Win Go")').filter(has_text="Guess Number").last
                await win_go_card.click(timeout=5000, force=True)
            except:
                await page.evaluate("""() => { for(let el of document.querySelectorAll('div, span, p')) { if((el.innerText||'').includes('Win Go') && (el.innerText||'').includes('Guess Number')) { el.click(); return true; } } return false; }""")
            await page.wait_for_timeout(3000) 

            while state["trade_running"]:
                try:
                    current_bal = state["balance"]
                    
                    if current_bal >= target_balance:
                        await ctx.bot.send_message(chat_id=uid, text=f"🎯 **TARGET REACHED!**\nProfit: ৳ {current_bal - initial_balance:.2f}\nবট বন্ধ হচ্ছে।")
                        state["trade_running"] = False
                        break

                    if current_step_idx >= len(state['step_amounts']):
                        await ctx.bot.send_message(chat_id=uid, text=f"⚠️ **সব স্টেপ শেষ!**")
                        state["trade_running"] = False
                        break
                        
                    bet_amount = float(state['step_amounts'][current_step_idx])
                    if current_bal < bet_amount:
                        await ctx.bot.send_message(chat_id=uid, text=f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**")
                        state["trade_running"] = False
                        break

                    choice, current_period = get_history_and_prediction()

                    logger.info("Waiting for 28s or 29s phase...")
                    timer_found = False
                    for _ in range(700): 
                        try:
                            body_text = await page.evaluate("() => document.body.innerText")
                            if re.search(r'0\s*0\s*[:.]?\s*(28|29)', body_text):
                                timer_found = True
                                break
                        except: pass
                        await asyncio.sleep(0.05) 

                    if not timer_found:
                        continue

                    js_click = f"""
                    (() => {{
                        let els = document.querySelectorAll('div, span, button');
                        for (let el of els) {{
                            if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                if (el.getBoundingClientRect().width > 0) {{ el.click(); return true; }}
                            }}
                        }}
                        return false;
                    }})()
                    """
                    await page.evaluate(js_click)
                    await page.wait_for_timeout(1000) 

                    try:
                        inp = page.locator('input[type="text"], input[type="number"]').first
                        await inp.wait_for(state="visible", timeout=5000)
                        await inp.fill(str(int(bet_amount)))

                        agree = page.locator('text="I agree"').first
                        if await agree.is_visible(): await agree.click(force=True)

                        confirm_btn = page.locator("text=/Total amount/i").last
                        await confirm_btn.wait_for(state="visible", timeout=5000)
                        await confirm_btn.click(force=True)
                        logger.info("Bet placed successfully!")
                    except Exception as e:
                        logger.error(f"Bet click error: {e}")
                        continue 

                    await asyncio.sleep(32) 

                    body_text = await page.evaluate("() => document.body.innerText")
                    new_balance_match = re.search(r'(?:Total|Wallet)\s*balance\s*[৳:]?\s*([\d.]+)', body_text)
                    
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
                            next_step_txt = f"➡️ Next Step : {current_step_idx+1} (৳ {state['step_amounts'][current_step_idx]})" if current_step_idx < len(state['step_amounts']) else "🛑 No more steps left."
                            await ctx.bot.send_message(chat_id=uid, text=f"🔴 **LOSS!**\nব্যালেন্স: ৳ {new_balance:.2f}\n{next_step_txt}")

                except Exception as e:
                    logger.error(f"Betting error: {e}")
                    state["trade_running"] = False
                    break
                    
        except Exception as e:
            logger.error(f"Browser Error: {e}")
        finally:
            await browser.close()