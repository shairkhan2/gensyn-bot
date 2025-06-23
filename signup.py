import os
import asyncio
import socket
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import telebot

load_dotenv("/root/bot_config.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_ID = int(os.getenv("USER_ID"))
bot = telebot.TeleBot(BOT_TOKEN)

async def wait_for_file(path, timeout=120):
    for _ in range(timeout):
        if os.path.exists(path):
            with open(path) as f:
                content = f.read().strip()
            if content:
                return content
        await asyncio.sleep(1)
    raise TimeoutError(f"Timeout waiting for {path}")

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
    if not await wait_for_port("localhost", 3000):
        print("❌ Timeout waiting for localhost:3000")
        return

    print("🚀 Launching browser for GENSYN login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto("http://localhost:3000", timeout=60000)
            print("🖱 Clicking 'Login' button...")
            await page.get_by_role("button", name="Login").click(timeout=30000)

            bot.send_message(USER_ID, "📨 Please send your email in format: `email: your@email.com`")
            email = await wait_for_file("/root/email.txt")
            await page.fill("input[type=email]", email)

            await page.get_by_role("button", name="Continue").click()
            await page.wait_for_selector("text=Enter verification code", timeout=60000)

            bot.send_message(USER_ID, "🔐 Please send the OTP in format: `otp: 123456`")
            otp = await wait_for_file("/root/otp.txt")
            await page.focus("input")
            await page.keyboard.type(otp, delay=100)
            await page.keyboard.press("Enter")

            try:
                await page.wait_for_selector("text=/successfully logged in/i", timeout=60000)
                await page.screenshot(path="/root/final_login_success.png", full_page=True)
                bot.send_message(USER_ID, "✅ Login successful!")
                bot.send_photo(USER_ID, open("/root/final_login_success.png", "rb"))
            except:
                await page.screenshot(path="/root/login_failed.png", full_page=True)
                bot.send_message(USER_ID, "❌ Login failed. Screenshot sent.")
                bot.send_photo(USER_ID, open("/root/login_failed.png", "rb"))

        except Exception as e:
            bot.send_message(USER_ID, f"❌ Error in signup: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

