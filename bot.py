import os
import time
import threading
import subprocess
import logging
import requests
import shutil
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
SWARM_PEM_PATH = "/root/rl-swarm/swarm.pem"
USER_DATA_PATH = "/root/rl-swarm/modal-login/temp-data/userData.json"
USER_APIKEY_PATH = "/root/rl-swarm/modal-login/temp-data/userApiKey.json"
BACKUP_USERDATA_DIR = "/root/gensyn-bot/backup-userdata"

logging.basicConfig(filename='/root/bot_error.log', level=logging.ERROR)

# Load bot config
with open(BOT_CONFIG) as f:
    lines = f.read().strip().split("\n")
    config = dict(line.split("=", 1) for line in lines if "=" in line)

BOT_TOKEN = config["BOT_TOKEN"]
USER_ID = int(config["USER_ID"])

bot = TeleBot(BOT_TOKEN)
waiting_for_pem = False

# Ensure backup dir exists
os.makedirs(BACKUP_USERDATA_DIR, exist_ok=True)

def get_menu():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🌐 Check IP", callback_data="check_ip"),
        InlineKeyboardButton("📶 VPN ON", callback_data="vpn_on"),
        InlineKeyboardButton("📴 VPN OFF", callback_data="vpn_off")
    )
    markup.row(
        InlineKeyboardButton("📊 Gensyn Status", callback_data="gensyn_status"),
        InlineKeyboardButton("🔑 Gensyn Login", callback_data="gensyn_login")
    )
    markup.row(
        InlineKeyboardButton("▶️ Start Gensyn", callback_data="start_gensyn"),
        InlineKeyboardButton("🔁 Set Auto-Start", callback_data="set_autostart")
    )
    return markup

def start_gensyn_session(chat_id):
    try:
        commands = [
            "cd /root/rl-swarm",
            "screen -dmS gensyn bash -c 'python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh'"
        ]
        subprocess.run("; ".join(commands), shell=True, check=True)
        bot.send_message(chat_id, "✅ Gensyn started in screen session 'gensyn'")
    except subprocess.CalledProcessError as e:
        bot.send_message(chat_id, f"❌ Error starting Gensyn: {str(e)}")

def setup_autostart(chat_id):
    try:
        os.makedirs(BACKUP_USERDATA_DIR, exist_ok=True)
        if os.path.exists(USER_DATA_PATH):
            shutil.copy(USER_DATA_PATH, os.path.join(BACKUP_USERDATA_DIR, "userData.json"))
        if os.path.exists(USER_APIKEY_PATH):
            shutil.copy(USER_APIKEY_PATH, os.path.join(BACKUP_USERDATA_DIR, "userApiKey.json"))

        service_content = f"""[Unit]
Description=Gensyn Swarm Service
After=network.target

[Service]
Type=forking
User=root
WorkingDirectory=/root/rl-swarm
ExecStartPre=/bin/bash -c 'mkdir -p /root/rl-swarm/modal-login/temp-data && cp {BACKUP_USERDATA_DIR}/userData.json {USER_DATA_PATH} || true'
ExecStartPre=/bin/bash -c 'cp {BACKUP_USERDATA_DIR}/userApiKey.json {USER_APIKEY_PATH} || true'
ExecStart=/bin/bash -c 'screen -dmS gensyn bash -c "python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh"'
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
"""
        with open("/etc/systemd/system/gensyn.service", "w") as f:
            f.write(service_content)

        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "gensyn.service"], check=True)
        subprocess.run(["systemctl", "start", "gensyn.service"], check=True)

        bot.send_message(chat_id, "✅ Auto-start configured! Gensyn will now start on boot.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error setting up auto-start: {str(e)}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"🤖 Bot ready.", reply_markup=get_menu())

@bot.message_handler(commands=['who'])
def who_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"👤 This is your VPN Bot")

@bot.message_handler(func=lambda message: message.from_user.id == USER_ID and message.text.startswith("otp:"))
def handle_otp(message):
    otp = message.text.replace("otp:", "").strip()
    with open("/root/otp.txt", "w") as f:
        f.write(otp)
    bot.send_message(message.chat.id, "✅ OTP saved.")

@bot.message_handler(func=lambda message: message.from_user.id == USER_ID and message.text.startswith("email:"))
def handle_email(message):
    email = message.text.replace("email:", "").strip()
    with open("/root/email.txt", "w") as f:
        f.write(email)
    bot.send_message(message.chat.id, "✅ Email saved.")

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
    global waiting_for_pem

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
            open("/root/email.txt", "w").close()
            open("/root/otp.txt", "w").close()
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

    elif call.data == 'start_gensyn':
        # NEW: Restore user data if backup exists
        restored = False
        os.makedirs(os.path.dirname(USER_DATA_PATH), exist_ok=True)
        if os.path.exists(os.path.join(BACKUP_USERDATA_DIR, "userData.json")):
            shutil.copy(os.path.join(BACKUP_USERDATA_DIR, "userData.json"), USER_DATA_PATH)
            restored = True
        if os.path.exists(os.path.join(BACKUP_USERDATA_DIR, "userApiKey.json")):
            shutil.copy(os.path.join(BACKUP_USERDATA_DIR, "userApiKey.json"), USER_APIKEY_PATH)
            restored = True

        if restored:
            bot.send_message(call.message.chat.id, "✅ Previous user data found & restored. No need to login again!")

        if os.path.exists(SWARM_PEM_PATH):
            start_gensyn_session(call.message.chat.id)
        else:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🆕 Start Fresh", callback_data="start_fresh"),
                InlineKeyboardButton("📤 Upload swarm.pem", callback_data="upload_pem")
            )
            bot.send_message(call.message.chat.id, "🔑 swarm.pem not found. Choose an option:", reply_markup=markup)

    elif call.data == 'start_fresh':
        start_gensyn_session(call.message.chat.id)

    elif call.data == 'upload_pem':
        waiting_for_pem = True
        bot.send_message(call.message.chat.id, "⬆️ Please send the swarm.pem file now...")

    elif call.data == 'set_autostart':
        setup_autostart(call.message.chat.id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    global waiting_for_pem

    if message.from_user.id != USER_ID or not waiting_for_pem:
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        file_data = bot.download_file(file_info.file_path)

        os.makedirs(os.path.dirname(SWARM_PEM_PATH), exist_ok=True)

        with open(SWARM_PEM_PATH, 'wb') as f:
            f.write(file_data)

        waiting_for_pem = False
        bot.send_message(message.chat.id, "✅ swarm.pem saved! Starting Gensyn...")
        start_gensyn_session(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error saving file: {str(e)}")
        waiting_for_pem = False

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

def backup_userdata_loop():
    while True:
        os.makedirs(BACKUP_USERDATA_DIR, exist_ok=True)
        if os.path.exists(USER_DATA_PATH):
            shutil.copy(USER_DATA_PATH, os.path.join(BACKUP_USERDATA_DIR, "userData.json"))
        if os.path.exists(USER_APIKEY_PATH):
            shutil.copy(USER_APIKEY_PATH, os.path.join(BACKUP_USERDATA_DIR, "userApiKey.json"))
        time.sleep(1800)  # every 30 min

# Start threads
threading.Thread(target=monitor, daemon=True).start()
threading.Thread(target=backup_userdata_loop, daemon=True).start()

# Start polling
try:
    bot.infinity_polling()
except Exception as e:
    logging.error("Bot crashed: %s", str(e))


