import os
import time
import threading
import subprocess
import logging
import requests
import shutil
from datetime import datetime
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
SWARM_PEM_PATH = "/root/rl-swarm/swarm.pem"
USER_DATA_PATH = "/root/rl-swarm/modal-login/temp-data/userData.json"
USER_APIKEY_PATH = "/root/rl-swarm/modal-login/temp-data/userApiKey.json"
BACKUP_USERDATA_DIR = "/root/gensyn-bot/backup-userdata"
PERIODIC_BACKUP_DIR = "/root/gensyn-bot/userdata"

logging.basicConfig(
    filename='/root/bot_error.log', 
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load configuration
with open(BOT_CONFIG) as f:
    lines = f.read().strip().split("\n")
    config = dict(line.split("=", 1) for line in lines if "=" in line)

BOT_TOKEN = config["BOT_TOKEN"]
USER_ID = int(config["USER_ID"])

bot = TeleBot(BOT_TOKEN)
waiting_for_pem = False
login_in_progress = False
login_lock = threading.Lock()

os.makedirs(BACKUP_USERDATA_DIR, exist_ok=True)
os.makedirs(PERIODIC_BACKUP_DIR, exist_ok=True)

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
    markup.row(
        InlineKeyboardButton("🛑 Kill Gensyn", callback_data="kill_gensyn")
    )
    markup.row(
        InlineKeyboardButton("🖥️ Terminal (tmate)", callback_data="run_tmate")
    )
    return markup

def start_vpn():
    try:
        subprocess.run(['wg-quick', 'up', 'wg0'], check=True)
        return True, "✅ VPN enabled"
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e):
            return True, "⚠️ VPN already enabled"
        return False, f"❌ VPN failed to start: {str(e)}"

def stop_vpn():
    try:
        subprocess.run(['wg-quick', 'down', 'wg0'], check=True)
        return True, "❌ VPN disabled"
    except subprocess.CalledProcessError as e:
        if "is not a WireGuard interface" in str(e):
            return True, "⚠️ VPN already disabled"
        return False, f"❌ VPN failed to stop: {str(e)}"

def start_gensyn_session(chat_id):
    try:
        backup_found = False
        for file in ["userData.json", "userApiKey.json"]:
            backup_path = os.path.join(PERIODIC_BACKUP_DIR, file)
            target_path = USER_DATA_PATH if file == "userData.json" else USER_APIKEY_PATH
            if os.path.exists(backup_path):
                shutil.copy(backup_path, target_path)
                backup_found = True
        commands = [
            "cd /root/rl-swarm",
            "screen -dmS gensyn bash -c 'python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh'"
        ]
        subprocess.run("; ".join(commands), shell=True, check=True)
        if backup_found:
            bot.send_message(chat_id, "✅ User data restored. Gensyn started in screen session 'gensyn'")
        else:
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
ExecStartPre=/usr/bin/wg-quick up wg0
ExecStartPre=/bin/bash -c 'mkdir -p /root/rl-swarm/modal-login/temp-data && cp {BACKUP_USERDATA_DIR}/userData.json {USER_DATA_PATH} || true'
ExecStartPre=/bin/bash -c 'cp {BACKUP_USERDATA_DIR}/userApiKey.json {USER_APIKEY_PATH} || true'
ExecStart=/bin/bash -c 'screen -dmS gensyn bash -c "python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh"'
ExecStopPost=/usr/bin/wg-quick down wg0
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
        bot.send_message(chat_id, "✅ Auto-start configured! Gensyn and VPN will now start on boot.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error setting up auto-start: {str(e)}")

def backup_user_data():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(PERIODIC_BACKUP_DIR, exist_ok=True)
        for path, name in [(USER_DATA_PATH, "userData.json"), (USER_APIKEY_PATH, "userApiKey.json")]:
            if os.path.exists(path):
                backup_file = f"{name.split('.')[0]}_{timestamp}.json"
                shutil.copy(path, os.path.join(PERIODIC_BACKUP_DIR, backup_file))
                latest_file = f"{name.split('.')[0]}_latest.json"
                shutil.copy(path, os.path.join(PERIODIC_BACKUP_DIR, latest_file))
                backups = sorted(
                    [f for f in os.listdir(PERIODIC_BACKUP_DIR) if f.startswith(name.split('.')[0]) and not f.endswith("_latest.json")],
                    key=lambda f: os.path.getmtime(os.path.join(PERIODIC_BACKUP_DIR, f)),
                    reverse=True
                )
                for old_backup in backups[5:]:
                    os.remove(os.path.join(PERIODIC_BACKUP_DIR, old_backup))
        return True
    except Exception as e:
        logging.error(f"Backup error: {str(e)}")
        return False

def periodic_backup():
    while True:
        try:
            if backup_user_data():
                logging.info("Periodic backup completed successfully")
            time.sleep(1800)
        except Exception as e:
            logging.error(f"Periodic backup thread error: {str(e)}")
            time.sleep(60)

threading.Thread(target=periodic_backup, daemon=True).start()

@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"🤖 Bot ready.", reply_markup=get_menu())

@bot.message_handler(commands=['who'])
def who_handler(message):
    if message.from_user.id == USER_ID:
        bot.send_message(message.chat.id, f"👤 This is your VPN Bot")

@bot.message_handler(func=lambda message: message.from_user.id == USER_ID)
def handle_credentials(message):
    global login_in_progress
    if not login_in_progress:
        return
    text = message.text.strip()
    if "@" in text and "." in text and len(text) > 5:
        with open("/root/email.txt", "w") as f:
            f.write(text)
        bot.send_message(message.chat.id, "✅ Email received. Check your email for OTP.")
        return
    if text.isdigit() and len(text) == 6:
        with open("/root/otp.txt", "w") as f:
            f.write(text)
        bot.send_message(message.chat.id, "✅ OTP received. Continuing login...")
        return
    bot.send_message(message.chat.id, "⚠️ Please send either:\n- Your email address\n- 6-digit OTP code")

@bot.message_handler(commands=['gensyn_status'])
def gensyn_status_handler(message):
    if message.from_user.id != USER_ID:
        return
    try:
        response = requests.get("http://localhost:3000", timeout=10)
        if "Sign in to Gensyn" in response.text:
            bot.send_message(message.chat.id, "✅ Gensyn running")
        else:
            bot.send_message(message.chat.id, f"❌ Gensyn response: {response.status_code}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Gensyn not running: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global waiting_for_pem, login_in_progress
    if call.from_user.id != USER_ID:
        return
    if call.data == 'check_ip':
        try:
            ip = requests.get('https://api.ipify.org', timeout=10).text.strip()
            bot.send_message(call.message.chat.id, f"🌐 Current Public IP: {ip}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error checking IP: {str(e)}")
    elif call.data == 'gensyn_login':
        global login_lock
        with login_lock:
            if login_in_progress:
                bot.send_message(call.message.chat.id, "⚠️ Login already in progress. Please complete current login first.")
                return
            try:
                for path in ["/root/email.txt", "/root/otp.txt"]:
                    if os.path.exists(path):
                        os.remove(path)
                login_in_progress = True
                bot.send_message(call.message.chat.id, "🚀 Starting GENSYN login...")
                bot.send_message(call.message.chat.id, "📧 Please send your email address")
                bot.send_message(call.message.chat.id, "🔐 Later, just send the 6-digit OTP code when received")
                venv_python = "/root/gensyn-bot/.venv/bin/python3"
                signup_script = "/root/gensyn-bot/signup.py"
                venv_site_packages = "/root/gensyn-bot/.venv/lib/python3.12/site-packages"
                with open("/root/signup.log", "w") as f:
                    subprocess.Popen(
                        [venv_python, signup_script],
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, "PYTHONPATH": venv_site_packages}
                    )
                threading.Thread(target=check_login_timeout, args=(call.message.chat.id,)).start()
            except Exception as e:
                login_in_progress = False
                bot.send_message(call.message.chat.id, f"❌ Error starting login: {str(e)}")
    elif call.data == 'vpn_on':
        success, message = start_vpn()
        bot.send_message(call.message.chat.id, message)
    elif call.data == 'vpn_off':
        success, message = stop_vpn()
        bot.send_message(call.message.chat.id, message)
    elif call.data == 'gensyn_status':
        try:
            response = requests.get("http://localhost:3000", timeout=10)
            if "Sign in to Gensyn" in response.text:
                bot.send_message(call.message.chat.id, "✅ Gensyn running")
            else:
                bot.send_message(call.message.chat.id, f"❌ Gensyn response: {response.status_code}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Gensyn not running: {str(e)}")
    elif call.data == 'start_gensyn':
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
    elif call.data == 'kill_gensyn':
        try:
            subprocess.run("screen -S gensyn -X quit", shell=True, check=True)
            bot.send_message(call.message.chat.id, "🛑 gensyn screen killed (and all child processes).")
        except subprocess.CalledProcessError as e:
            bot.send_message(call.message.chat.id, f"❌ Failed to kill gensyn screen: {str(e)}")
    elif call.data == 'run_tmate':
        try:
            # Start tmate session and wait for URLs to be ready
            subprocess.run("tmate -S /tmp/tmate.sock new-session -d", shell=True, check=True)
            subprocess.run("tmate -S /tmp/tmate.sock wait tmate-ready", shell=True, check=True)
            result = subprocess.run(
                "tmate -S /tmp/tmate.sock display -p '#{tmate_web}' && "
                "tmate -S /tmp/tmate.sock display -p '#{tmate_web_ro}' && "
                "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}' && "
                "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh_ro}'",
                shell=True, check=True, capture_output=True, text=True
            )
            urls = result.stdout.strip().split('\n')
            msg = (
                "Note: clear your terminal before sharing readonly access\n"
                f"web session read only: {urls[1]}\n"
                f"ssh session read only: {urls[3]}\n"
                f"web session: {urls[0]}\n"
                f"ssh session: {urls[2]}"
            )
            bot.send_message(call.message.chat.id, msg)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Failed to start tmate: {str(e)}")

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

def check_login_timeout(chat_id):
    global login_in_progress
    time.sleep(300)
    if login_in_progress:
        login_in_progress = False
        bot.send_message(chat_id, "⏰ Login timed out. Please try again.")

def monitor():
    previous_ip = ''
    previous_alive = None
    while True:
        try:
            try:
                response = requests.get('http://localhost:3000', timeout=10)
                alive = "Sign in to Gensyn" in response.text
            except requests.RequestException:
                alive = False
            try:
                ip = requests.get('https://api.ipify.org', timeout=10).text.strip()
            except:
                ip = "Unknown"
            if ip and ip != previous_ip:
                bot.send_message(USER_ID, f"⚠️ IP changed: {ip}")
                previous_ip = ip
            if previous_alive is not None and alive != previous_alive:
                status = '✅ Online' if alive else '❌ Offline'
                bot.send_message(USER_ID, f"⚠️ localhost:3000 status changed: {status}")
            previous_alive = alive
        except Exception as e:
            logging.error("Monitor error: %s", str(e))
        time.sleep(60)

if os.path.exists(USER_DATA_PATH):
    shutil.copy(USER_DATA_PATH, os.path.join(PERIODIC_BACKUP_DIR, "userData_latest.json"))
if os.path.exists(USER_APIKEY_PATH):
    shutil.copy(USER_APIKEY_PATH, os.path.join(PERIODIC_BACKUP_DIR, "userApiKey_latest.json"))

threading.Thread(target=monitor, daemon=True).start()

try:
    bot.infinity_polling()
except Exception as e:
    logging.error("Bot crashed: %s", str(e))
