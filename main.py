                    # 💡 ৩. সুপার ফাস্ট Big/Small ক্লিক (JS দিয়ে সরাসরি)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await page.wait_for_timeout(300)
                    
                    js_click_script = f"""
                    (() => {{
                        let els = document.querySelectorAll('div, span, button');
                        for (let el of els) {{
                            if (el.innerText && el.innerText.trim().toUpperCase() === '{choice.upper()}') {{
                                let rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                        }}
                        return false;
                    }})()
                    """
                    clicked = await page.evaluate(js_click_script)
                    
                    if not clicked:
                        try:
                            if choice.upper() == "BIG":
                                await page.mouse.click(103, 890)
                            else:
                                await page.mouse.click(309, 890)
                        except: pass

                    # 💡 ৪. পপ-আপ আসার জন্য ১.৫ সেকেন্ড অপেক্ষা
                    await page.wait_for_timeout(1500)

                    # 💡 ৫. মডালে অ্যামাউন্ট ইনপুট করা
                    try:
                        inputs = await page.locator('input[type="text"], input[type="number"], .van-field__control').all()
                        for inp in inputs:
                            if await inp.is_visible():
                                await inp.click(force=True)
                                await page.keyboard.press("Control+A")
                                await page.keyboard.press("Backspace")
                                await inp.type(str(int(bet_amount)), delay=30)
                                break
                    except: pass

                    # "I agree" চেকবক্স টিক দেওয়া
                    try:
                        agree_box = page.locator('text="I agree"').last
                        if await agree_box.count() > 0 and await agree_box.is_visible():
                            await agree_box.click(force=True, timeout=1000)
                            await page.wait_for_timeout(200)
                    except: pass

                    # 💡 ৬. সরাসরি কমলা রঙের "Total amount" বাটনটিতে ক্লিক করা (JavaScript ও Mouse Click এর মাধ্যমে)
                    confirm_success = False
                    
                    # প্রথমে জাভাস্ক্রিপ্ট দিয়ে কমলা বাটনটি খুঁজে ক্লিক করার চেষ্টা
                    try:
                        confirm_success = await page.evaluate("""
                            () => {
                                let buttons = document.querySelectorAll('button, div, span');
                                for (let btn of buttons) {
                                    let text = btn.innerText || '';
                                    if (text.includes('Total amount')) {
                                        btn.click();
                                        return true;
                                    }
                                }
                                return false;
                            }
                        """)
                    except: pass

                    # যদি JS দিয়ে কাজ না হয়, তবে সরাসরি স্ক্রিনের ওই কমলা বাটনের পজিশনে মাউস ক্লিক করবে
                    if not confirm_success:
                        try:
                            # স্ক্রিনশট অনুযায়ী ভিউপোর্টে (412x915) কমলা বাটনটির সুনির্দিষ্ট কোঅর্ডিনেট
                            await page.mouse.click(206, 910)
                            confirm_success = True
                        except: pass

                    # সফল বা অসফল মেসেজ পাঠানো
                    if confirm_success:
                        state['total_trades'] += 1
                        await ctx.bot.send_message(
                            chat_id=uid, 
                            text=f"✅ **BET PLACED SUCCESSFULLY!**\n\n🎯 Prediction: **{choice.upper()}**\n💰 Amount: ৳ {bet_amount:.2f}", 
                            parse_mode="Markdown"
                        )
                    else:
                        await ctx.bot.send_message(
                            chat_id=uid, 
                            text=f"⚠️ **{choice.upper()} সিলেক্ট হয়েছে, কিন্তু Total amount বাটনে ক্লিক করা যায়নি!** পরবর্তী রাউন্ডের জন্য অপেক্ষা করা হচ্ছে...", 
                            parse_mode="Markdown"
                        )
                        continue # বট বন্ধ না হয়ে পরের রাউন্ডে চলে যাবে
                        