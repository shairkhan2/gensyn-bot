import os
import time
import subprocess
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
ACTIVE = True

# Setup section

def menu():
    while True:
        print("\n🛠️ VPN Bot Manager")
        print("1. Paste WireGuard config")
        print("2. Setup Telegram Bot")
        print("3. Enable Bot on Boot")
        print("4. Exit")
        choice = input("\nSelect an option: ")

        if choice == "1":
            setup_vpn()
        elif choice == "2":
            setup_bot()
        elif choice == "3":
            setup_systemd()
        elif choice == "4":
            break
        else:
            print("❌ Invalid option.")

def setup_vpn():
    print("\n📋 Paste full WireGuard config (end with Ctrl+D):\n")
    try:
        config = []
        while True:
            line = input()
            config.append(line)
    except EOFError:
        pass

    os.makedirs("/etc/wireguard", exist_ok=True)
    with open(WG_CONFIG_PATH, "w") as f:
        f.write("\n".join(config))
    os.system("chmod 600 " + WG_CONFIG_PATH)
    print("✅ WireGuard config saved.")

def setup_bot():
    print("\n🤖 Telegram Bot Setup")
    token = input("Bot Token: ")
    user_id = input("Your Telegram User ID: ")

    with open(BOT_CONFIG, "w") as f:
        f.write(f"BOT_TOKEN={token}\n")
        f.write(f"USER_ID={user_id}\n")

    with open("/root/bot.py", "w") as f:
        f.write(generate_bot_script())
    os.system("chmod +x /root/bot.py")
    print("✅ Bot script created at /root/bot.py")

def setup_systemd():
    print("\n⚙️ Enabling bot service...")
    service = f"""[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /root/bot.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/bot.service", "w") as f:
        f.write(service)
    os.system("systemctl daemon-reexec")
    os.system("systemctl daemon-reload")
    os.system("systemctl enable bot")
    os.system("systemctl start bot")
    print("✅ Bot service enabled and running.")

def generate_bot_script():
    return f"""
import os
import time
import subprocess
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

with open('{BOT_CONFIG}') as f:
    lines = f.read().strip().split('\n')
    config = dict(line.split('=') for line in lines)

bot = TeleBot(config['BOT_TOKEN'])
USER_ID = int(config['USER_ID'])
ACTIVE = True

previous_ip = ""
previous_alive = None

def get_menu():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("🌐 Check IP", callback_data="check_ip"),
        InlineKeyboardButton("📶 VPN ON", callback_data="vpn_on"),
        InlineKeyboardButton("📴 VPN OFF", callback_data="vpn_off")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, "🤖 VPN Control Bot Ready", reply_markup=get_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global previous_ip
    if call.from_user.id != USER_ID:
        return

    if call.data == "check_ip":
        try:
            ip = os.popen("curl -s ifconfig.me").read().strip()
            bot.send_message(call.message.chat.id, f"🌐 Current Public IP: {ip}")
        except:
            bot.send_message(call.message.chat.id, "❌ Failed to fetch IP")

    elif call.data == "vpn_on":
        os.system("wg-quick up wg0")
        bot.send_message(call.message.chat.id, "✅ VPN enabled")

    elif call.data == "vpn_off":
        os.system("wg-quick down wg0")
        bot.send_message(call.message.chat.id, "❌ VPN disabled")

def monitor():
    global previous_ip, previous_alive
    while True:
        try:
            alive = os.system("ping -c 1 -W 1 localhost:3000 > /dev/null 2>&1") == 0
            ip = os.popen("curl -s ifconfig.me").read().strip()

            if ip != previous_ip:
                bot.send_message(USER_ID, f"⚠️ IP changed: {ip}")
                previous_ip = ip

            if previous_alive is not None and alive != previous_alive:
                status = "✅ Online" if alive else "❌ Offline"
                bot.send_message(USER_ID, f"⚠️ Localhost:3000 status changed: {status}")

            previous_alive = alive
        except Exception as e:
            bot.send_message(USER_ID, f"❌ Monitor error: {str(e)}")

        time.sleep(60)

import threading
threading.Thread(target=monitor, daemon=True).start()
bot.infinity_polling()
"""

if __name__ == "__main__":
    menu()
