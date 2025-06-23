# signup.py

import os
import asyncio
import socket
from dotenv import load_dotenv
import telebot
from playwright.async_api import async_playwright

# Load from /root/bot_config.env
load_dotenv("/root/bot_config.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_ID = int(os.getenv("USER_ID"))

bot = telebot.TeleBot(BOT_TOKEN)
user_reply = {}

def handle_reply(message):
    if message.from_user.id == USER_ID:
        user_reply["text"] = message.text
        bot.stop_polling()

def ask_user_on_telegram(question):
    global user_reply
    user_reply = {}
    bot.send_message(USER_ID, question)
    bot.register_next_step_handler_by_chat_id(USER_ID, handle_reply)
    bot.polling(none_stop=False, timeout=60)
    return user_reply.get("text", "").strip()

async def wait_for_port(host: str, port: int, timeout: int = 60):
    for _ in range(timeout):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except Exception:
            await asyncio.sleep(1)
    return False

async def main():
    print("🔁 Waiting for localhost:3000 to become reachable...")
    port_ready = await wait_for_port("localhost", 3000)
    if not port_ready:
        print("❌ Timeout waiting for localhost:3000 to be available.")
        return

    print("🚀 Launching browser for GENSYN login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto("http://localhost:3000", timeout=60000)

            await page.get_by_role("button", name="Login").click()
            await page.screenshot(path="/root/after_login_click.png", full_page=True)
            bot.send_photo(USER_ID, open("/root/after_login_click.png", "rb"))

            email_input = await page.wait_for_selector("input[type=email]", timeout=30000)
            email = ask_user_on_telegram("📨 Enter your GENSYN email address:")
            await email_input.fill(email)
            await page.screenshot(path="/root/after_email_fill.png", full_page=True)
            bot.send_photo(USER_ID, open("/root/after_email_fill.png", "rb"))

            continue_button = await page.wait_for_selector("button:has-text('Continue')", timeout=10000)
            await continue_button.click()
            await page.wait_for_selector("text=Enter verification code", timeout=60000)
            await asyncio.sleep(1)

            await page.screenshot(path="/root/before_otp_fill.png", full_page=True)
            bot.send_photo(USER_ID, open("/root/before_otp_fill.png", "rb"))

            otp = ask_user_on_telegram("🔐 Enter the 6-digit OTP from your email:")
            if len(otp) != 6:
                raise Exception("OTP must be exactly 6 digits.")

            await page.evaluate("""const input = document.querySelector('input'); if (input) input.focus();""")
            await asyncio.sleep(0.2)
            await page.keyboard.type(otp, delay=100)
            await page.screenshot(path="/root/after_otp_fill.png", full_page=True)
            bot.send_photo(USER_ID, open("/root/after_otp_fill.png", "rb"))

            await page.keyboard.press("Enter")

            try:
                await page.wait_for_selector("text=/successfully logged in/i", timeout=60000)
                await page.screenshot(path="/root/final_logged_in.png", full_page=True)
                bot.send_message(USER_ID, "✅ Login successful!")
                bot.send_photo(USER_ID, open("/root/final_logged_in.png", "rb"))
            except Exception:
                await page.screenshot(path="/root/login_failed.png", full_page=True)
                html = await page.content()
                with open("/root/login_failed.html", "w") as f:
                    f.write(html)
                bot.send_message(USER_ID, "❌ Login possibly failed. Screenshot + HTML saved.")
                bot.send_photo(USER_ID, open("/root/login_failed.png", "rb"))

        except Exception as e:
            bot.send_message(USER_ID, f"❌ Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
