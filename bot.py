import os
import time
import threading
import subprocess
import logging
import requests
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"

logging.basicConfig(filename='/root/bot_error.log', level=logging.ERROR)

# Load bot config
with open(BOT_CONFIG) as f:
    lines = f.read().strip().split("\n")
    config = dict(line.split("=", 1) for line in lines if "=" in line)

BOT_TOKEN = config["BOT_TOKEN"]
USER_ID = int(config["USER_ID"])

bot = TeleBot(BOT_TOKEN)

def get_menu():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌐 Check IP", callback_data="check_ip"),
        InlineKeyboardButton("📶 VPN ON", callback_data="vpn_on"),
        InlineKeyboardButton("📴 VPN OFF", callback_data="vpn_off")
    )
    markup.add(
        InlineKeyboardButton("📊 Gensyn Status", callback_data="gensyn_status")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"🤖 Bot ready.", reply_markup=get_menu())

@bot.message_handler(commands=['who'])
def who_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"👤 This is your VPN Bot")

@bot.message_handler(commands=['gensyn_status'])
def gensyn_status_handler(message):
    if message.from_user.id != USER_ID:
        return
    try:
        response = requests.get("http://localhost:3000", timeout=3)
        if "Sign in to Gensyn" in response.text:
            bot.send_message(message.chat.id, "✅ Gensyn running")
        else:
            bot.send_message(message.chat.id, f"❌ Gensyn response did not match expected content")
    except Exception:
        bot.send_message(message.chat.id, "❌ Gensyn not running")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.from_user.id != USER_ID:
        return

    if call.data == 'check_ip':
        try:
            ip = requests.get('https://api.ipify.org').text.strip()
            bot.send_message(call.message.chat.id, f"🌐 Current Public IP: {ip}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error checking IP: {str(e)}")

    elif call.data == 'gensyn_login':
        try:
            bot.send_message(call.message.chat.id, "🚀 Launching GENSYN login...")
            subprocess.Popen(["python3", "/root/gensyn-bot/signup.py"])
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error launching signup: {str(e)}")

    elif call.data == 'vpn_on':
        subprocess.run(['wg-quick', 'up', 'wg0'])
        bot.send_message(call.message.chat.id, '✅ VPN enabled')

    elif call.data == 'vpn_off':
        subprocess.run(['wg-quick', 'down', 'wg0'])
        bot.send_message(call.message.chat.id, '❌ VPN disabled')

    elif call.data == 'gensyn_status':
        try:
            response = requests.get("http://localhost:3000", timeout=3)
            if "Sign in to Gensyn" in response.text:
                bot.send_message(call.message.chat.id, "✅ Gensyn running")
            else:
                bot.send_message(call.message.chat.id, f"❌ Gensyn response did not match expected content")
        except Exception:
            bot.send_message(call.message.chat.id, "❌ Gensyn not running")


def monitor():
    previous_ip = ''
    previous_alive = None
    while True:
        try:
            try:
                response = requests.get('http://localhost:3000', timeout=3)
                alive = "Sign in to Gensyn" in response.text
            except requests.RequestException:
                alive = False

            ip = requests.get('https://api.ipify.org').text.strip()

            if ip and ip != previous_ip:
                bot.send_message(USER_ID, f"⚠️ IP changed: {ip}")
                previous_ip = ip

            if previous_alive is not None and alive != previous_alive:
                status = '✅ Online' if alive else '❌ Offline'
                bot.send_message(USER_ID, f"⚠️ localhost:3000 status changed: {status}")

            previous_alive = alive
        except Exception as e:
            bot.send_message(USER_ID, f"❌ Monitor error: {str(e)}")
            logging.error("Monitor error: %s", str(e))

        time.sleep(60)

# Start monitor thread
threading.Thread(target=monitor, daemon=True).start()

# Start polling
try:
    bot.infinity_polling()
except Exception as e:
    logging.error("Bot crashed: %s", str(e))


