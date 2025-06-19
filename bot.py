import os
import time
import json
import threading
import subprocess
import logging
import requests
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
CONFIG_FILE = "/root/vm_registry.json"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"

logging.basicConfig(filename='/root/bot_error.log', level=logging.ERROR)

with open(BOT_CONFIG) as f:
    lines = f.read().strip().split("\n")
    config = dict(line.split("=", 1) for line in lines if "=" in line)

BOT_TOKEN = config["BOT_TOKEN"]
USER_ID = int(config["USER_ID"])
VM_NAME = config["VM_NAME"]
ACTIVE_VM = VM_NAME

bot = TeleBot(BOT_TOKEN)

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump({VM_NAME: True}, f)
else:
    with open(CONFIG_FILE, "r") as f:
        try:
            vms = json.load(f)
        except json.JSONDecodeError:
            vms = {}
    vms[VM_NAME] = True
    with open(CONFIG_FILE, "w") as f:
        json.dump(vms, f)

def get_menu():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌐 Check IP", callback_data="check_ip"),
        InlineKeyboardButton("📶 VPN ON", callback_data="vpn_on"),
        InlineKeyboardButton("📴 VPN OFF", callback_data="vpn_off")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"🤖 {VM_NAME} ready. Use /switch {VM_NAME} to activate it.", reply_markup=get_menu())

@bot.message_handler(commands=['switch'])
def switch_vm(message):
    global ACTIVE_VM
    if message.from_user.id != USER_ID:
        return
    parts = message.text.strip().split()
    if len(parts) == 2:
        new_vm = parts[1]
        ACTIVE_VM = new_vm
        bot.send_message(message.chat.id, f"✅ Switched to VM: {ACTIVE_VM}", reply_markup=get_menu())

@bot.message_handler(commands=['who'])
def who_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"👤 Current active VM: {ACTIVE_VM}")

@bot.message_handler(commands=['list'])
def list_handler(message):
    if message.from_user.id != USER_ID:
        return
    try:
        with open(CONFIG_FILE, 'r') as f:
            vms = json.load(f)
        vm_list = '\n'.join(f"• {vm}" for vm in vms)
        bot.send_message(message.chat.id, f"📜 Registered VMs:\n{vm_list}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error reading VM list: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.from_user.id != USER_ID or ACTIVE_VM != VM_NAME:
        return

    if call.data == 'check_ip':
        try:
            ip = requests.get('https://api.ipify.org').text.strip()
            bot.send_message(call.message.chat.id, f"🌐 Current Public IP: {ip}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error checking IP: {str(e)}")

    elif call.data == 'vpn_on':
        subprocess.run(['wg-quick', 'up', 'wg0'])
        bot.send_message(call.message.chat.id, '✅ VPN enabled')

    elif call.data == 'vpn_off':
        subprocess.run(['wg-quick', 'down', 'wg0'])
        bot.send_message(call.message.chat.id, '❌ VPN disabled')

def monitor():
    previous_ip = ''
    previous_alive = None
    while True:
        try:
            try:
                requests.get('http://localhost:3000', timeout=3)
                alive = True
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

threading.Thread(target=monitor, daemon=True).start()

try:
    bot.infinity_polling()
except Exception as e:
    logging.error("Bot crashed: %s", str(e))
