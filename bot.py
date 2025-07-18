import os
import time
import threading
import subprocess
import logging
import requests
import shutil
from datetime import datetime, timedelta
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
SWARM_PEM_PATH = "/root/rl-swarm/swarm.pem"
USER_DATA_PATH = "/root/rl-swarm/modal-login/temp-data/userData.json"
USER_APIKEY_PATH = "/root/rl-swarm/modal-login/temp-data/userApiKey.json"
BACKUP_USERDATA_DIR = "/root/gensyn-bot/backup-userdata"
SYNC_BACKUP_DIR = "/root/gensyn-bot/sync-backup"
GENSYN_LOG_PATH = "/root/rl-swarm/logs/swarm_launcher.log"
WANDB_LOG_DIR = "/root/rl-swarm/logs/wandb"

logging.basicConfig(
    filename='/root/bot_error.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

with open(BOT_CONFIG) as f:
    lines = f.read().strip().split("\n")
    config = dict(line.split("=", 1) for line in lines if "=" in line)

BOT_TOKEN = config["BOT_TOKEN"]
USER_ID = int(config["USER_ID"])

bot = TeleBot(BOT_TOKEN)
waiting_for_pem = False
login_in_progress = False
login_lock = threading.Lock()
tmate_running = False
last_action_time = {}
COOLDOWN_SECONDS = 2

os.makedirs(BACKUP_USERDATA_DIR, exist_ok=True)
os.makedirs(SYNC_BACKUP_DIR, exist_ok=True)

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
    terminal_label = "🖥️ Terminal: ON" if tmate_running else "🖥️ Terminal: OFF"
    markup.row(
        InlineKeyboardButton(terminal_label, callback_data="toggle_tmate")
    )
    markup.row(
        InlineKeyboardButton("🗂️ Get Backup", callback_data="get_backup")
    )
    markup.row(
        InlineKeyboardButton("🔄 Update", callback_data="update_menu")
    )
    return markup

def check_internet_connection():
    """
    Check if internet is working by connecting to Google
    Returns True if connection successful, False otherwise
    """
    try:
        response = requests.get("https://www.google.com/", timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def internet_watchdog():
    """
    Monitor internet connectivity and take action if connection fails
    """
    failed_attempts = 0
    max_failures = 5
    
    while True:
        try:
            if check_internet_connection():
                failed_attempts = 0  # Reset counter on successful connection
            else:
                failed_attempts += 1
                logging.error(f"Internet check failed. Attempt {failed_attempts}/{max_failures}")
                
                if failed_attempts >= max_failures:
                    try:
                        # Kill Gensyn screen
                        subprocess.run("screen -S gensyn -X quit", shell=True, check=False)
                        
                        # Turn off WireGuard
                        subprocess.run(['wg-quick', 'down', 'wg0'], check=False)
                        
                        # Wait 2 minutes
                        time.sleep(120)
                        
                        # Send message to user
                        bot.send_message(USER_ID, "🚨 Internet connection failed 5 times in 10 minutes. Gensyn killed and VPN turned off.")
                        
                        # Reset counter
                        failed_attempts = 0
                        
                    except Exception as e:
                        logging.error(f"Error in internet watchdog action: {str(e)}")
            
            # Wait 2 minutes before next check
            time.sleep(120)
            
        except Exception as e:
            logging.error(f"Error in internet watchdog: {str(e)}")
            time.sleep(60)

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

def backup_user_data_sync():
    try:
        for src, name in [(USER_DATA_PATH, "userData.json"), (USER_APIKEY_PATH, "userApiKey.json")]:
            dst = os.path.join(SYNC_BACKUP_DIR, name)
            if os.path.exists(src):
                shutil.copy(src, dst)
        return True
    except Exception as e:
        logging.error(f"Sync backup error: {str(e)}")
        return False

def periodic_sync_backup():
    while True:
        try:
            backup_user_data_sync()
            time.sleep(60)
        except Exception as e:
            logging.error(f"Periodic sync backup thread error: {str(e)}")
            time.sleep(10)

threading.Thread(target=periodic_sync_backup, daemon=True).start()

def backup_user_data():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path, name in [(USER_DATA_PATH, "userData.json"), (USER_APIKEY_PATH, "userApiKey.json")]:
            if os.path.exists(path):
                backup_file = f"{name.split('.')[0]}_{timestamp}.json"
                shutil.copy(path, os.path.join(BACKUP_USERDATA_DIR, backup_file))
                latest_file = f"{name.split('.')[0]}_latest.json"
                shutil.copy(path, os.path.join(BACKUP_USERDATA_DIR, latest_file))
        return True
    except Exception as e:
        logging.error(f"Backup error: {str(e)}")
        return False

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

def gensyn_soft_update(chat_id):
    backup_paths = [
        USER_DATA_PATH,
        USER_APIKEY_PATH
    ]
    backup_dir = "/root/gensyn-bot/soft-update-backup"
    os.makedirs(backup_dir, exist_ok=True)
    try:
        for path in backup_paths:
            if os.path.exists(path):
                shutil.copy(path, backup_dir)
        bot.send_message(chat_id, "Backup done. Killing Gensyn...")
        subprocess.run("screen -S gensyn -X quit", shell=True, check=True)
        bot.send_message(chat_id, "Gensyn killed. Updating (git pull)...")
        result = subprocess.run("cd /root/rl-swarm && git pull", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            msg = "Update done. Restarting node..."
        else:
            msg = "Update failed. Restoring backup..."
        for filename in ["userData.json", "userApiKey.json"]:
            src = os.path.join(backup_dir, filename)
            dst = f"/root/rl-swarm/modal-login/temp-data/{filename}"
            if os.path.exists(src):
                shutil.copy(src, dst)
        subprocess.run("cd /root/rl-swarm && screen -dmS gensyn bash -c 'python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh'", shell=True)
        bot.send_message(chat_id, f"{msg}\nGensyn started.")
    except Exception as e:
        bot.send_message(chat_id, f"Soft update failed: {str(e)}")

def gensyn_hard_update(chat_id):
    backup_paths = [
        SWARM_PEM_PATH,
        USER_DATA_PATH,
        USER_APIKEY_PATH
    ]
    backup_dir = "/root/gensyn-bot/hard-update-backup"
    os.makedirs(backup_dir, exist_ok=True)
    try:
        for path in backup_paths:
            if os.path.exists(path):
                shutil.copy(path, backup_dir)
        bot.send_message(chat_id, "Backup done. Killing Gensyn...")
        subprocess.run("screen -S gensyn -X quit", shell=True, check=True)
        bot.send_message(chat_id, "Gensyn killed. Cloning repo...")
        subprocess.run("rm -rf /root/rl-swarm", shell=True)
        result = subprocess.run("git clone https://github.com/shairkhan2/rl-swarm.git /root/rl-swarm", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            msg = "Hard update done. Restoring backup..."
        else:
            msg = "Hard update failed. Restoring backup to last state."
        for filename in ["swarm.pem", "userData.json", "userApiKey.json"]:
            src = os.path.join(backup_dir, filename)
            dst = f"/root/rl-swarm/{filename}" if filename == "swarm.pem" else f"/root/rl-swarm/modal-login/temp-data/{filename}"
            if os.path.exists(src):
                shutil.copy(src, dst)
        subprocess.run("cd /root/rl-swarm && screen -dmS gensyn bash -c 'python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh'", shell=True)
        bot.send_message(chat_id, f"{msg}\nGensyn started.")
    except Exception as e:
        bot.send_message(chat_id, f"Hard update failed: {str(e)}")

def send_backup_files(chat_id):
    files = [
        SWARM_PEM_PATH,
        USER_DATA_PATH,
        USER_APIKEY_PATH
    ]
    for fpath in files:
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                bot.send_document(chat_id, f)
        else:
            bot.send_message(chat_id, f"{os.path.basename(fpath)} not found.")

def check_gensyn_screen_running():
    """
    Check if the 'gensyn' screen session is running
    Returns True if running, False otherwise
    """
    try:
        result = subprocess.run("screen -ls", shell=True, capture_output=True, text=True)
        return "gensyn" in result.stdout
    except Exception as e:
        logging.error(f"Error checking screen: {str(e)}")
        return False

def start_gensyn_session(chat_id, use_sync_backup=True):
    # Check if gensyn screen is already running
    if check_gensyn_screen_running():
        bot.send_message(chat_id, "⚠️ Gensyn already running!")
        return
    
    # Check if swarm.pem exists
    if not os.path.exists(SWARM_PEM_PATH):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Upload old swarm.pem", callback_data="upload_pem"),
            InlineKeyboardButton("Start Fresh Node", callback_data="start_fresh")
        )
        bot.send_message(
            chat_id,
            "❗ swarm.pem not found! If you have a backup of your old Gensyn node, please upload it.\nOtherwise, start fresh (new node, new keys).",
            reply_markup=markup
        )
        return
    try:
        backup_found = False
        if use_sync_backup:
            for file in ["userData.json", "userApiKey.json"]:
                backup_path = os.path.join(SYNC_BACKUP_DIR, file)
                target_path = USER_DATA_PATH if file == "userData.json" else USER_APIKEY_PATH
                if os.path.exists(backup_path):
                    shutil.copy(backup_path, target_path)
                    backup_found = True
        commands = [
            "cd /root/rl-swarm",
            "screen -dmS gensyn bash -c 'python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh'"
        ]
        subprocess.run("; ".join(commands), shell=True, check=True)
        if backup_found and use_sync_backup:
            bot.send_message(chat_id, "✅ Login backup restored. Gensyn started in screen session 'gensyn'")
        else:
            bot.send_message(chat_id, "✅ Gensyn started in screen session 'gensyn'")
    except subprocess.CalledProcessError as e:
        bot.send_message(chat_id, f"❌ Error starting Gensyn: {str(e)}")

def get_gensyn_log_status(log_path=GENSYN_LOG_PATH):
    """
    Parses the last 50 lines of the Gensyn log to find the latest activity.
    Returns a dictionary with timestamp, joining, and starting round info, or None.
    """
    try:
        if not os.path.exists(log_path):
            return None

        with open(log_path, "r") as f:
            lines = f.readlines()[-50:]

        latest_ts = None
        joining_round = None
        starting_round = None

        for line in reversed(lines):
            if "] - " in line:
                try:
                    ts_str = line.split("]")[0][1:]
                    ts = datetime.strptime(ts_str.split(",")[0], "%Y-%m-%d %H:%M:%S")
                    msg = line.split("] - ", 1)[-1].strip()

                    if not latest_ts:
                        latest_ts = ts
                    if "Joining round" in msg and not joining_round:
                        joining_round = msg
                    if "Starting round" in msg and not starting_round:
                        starting_round = msg
                    
                    if latest_ts and joining_round and starting_round:
                        break
                except (ValueError, IndexError):
                    continue
        
        return {
            "timestamp": latest_ts,
            "joining": joining_round,
            "starting": starting_round,
        }
    except Exception as e:
        logging.error(f"Error reading Gensyn log: {str(e)}")
        return None

def check_gensyn_api():
    """
    Original working API check from old bot version
    """
    try:
        response = requests.get("http://localhost:3000", timeout=3)
        if response.status_code == 200:
            return True  # Any 200 response means API is online
        return False
    except Exception:
        return False


def format_gensyn_status():
    """
    Formats the complete Gensyn status message
    """
    # Check API status
    api_online = check_gensyn_api()
    api_status = "API: ✅ Online" if api_online else "API: ❌ Offline"
    
    # Check log status
    log_data = get_gensyn_log_status()
    log_status_lines = []

    if log_data and any(log_data.values()):
        if log_data.get("timestamp"):
            ts = log_data["timestamp"]
            delta_min = int((datetime.utcnow() - ts).total_seconds() / 60)
            log_status_lines.append(f"🕰️ *Last Activity:* {delta_min} mins ago")

        if log_data.get("joining"):
            joining_text = log_data["joining"].replace("Joining round ", "")
            log_status_lines.append(f"🤝 *Joining:* `{joining_text}`")
        
        if log_data.get("starting"):
            starting_text = log_data["starting"].replace("Starting round ", "")
            log_status_lines.append(f"▶️ *Starting:* `{starting_text}`")

    if not log_status_lines:
        log_status = "Round: No data found"
    else:
        log_status = "\n".join(log_status_lines)

    return f"{api_status}\n\n{log_status}"

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
        status_message = format_gensyn_status()
        bot.send_message(message.chat.id, status_message, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in gensyn_status_handler: {str(e)}")
        bot.send_message(message.chat.id, "❌ Error getting status. Check logs.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global waiting_for_pem, login_in_progress, tmate_running, last_action_time
    user_id = call.from_user.id
    now = time.time()
    
    if user_id != USER_ID:
        return
        
    if user_id in last_action_time and (now - last_action_time[user_id]) < COOLDOWN_SECONDS:
        return
    last_action_time[user_id] = now

    try:
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
                status_message = format_gensyn_status()
                bot.send_message(call.message.chat.id, status_message, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Error in gensyn_status callback: {str(e)}")
                bot.send_message(call.message.chat.id, "❌ Error getting status. Check logs.")
                
        elif call.data == 'start_gensyn':
            backup_exists = (
                os.path.exists(os.path.join(SYNC_BACKUP_DIR, "userData.json")) and
                os.path.exists(os.path.join(SYNC_BACKUP_DIR, "userApiKey.json"))
            )
            if backup_exists:
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Run with Login Backup", callback_data="start_gensyn_with_backup"),
                    InlineKeyboardButton("Run Without Login Backup", callback_data="start_gensyn_no_backup")
                )
                bot.send_message(call.message.chat.id, "Login backup found. How do you want to start?", reply_markup=markup)
            else:
                start_gensyn_session(call.message.chat.id, use_sync_backup=False)
                
        elif call.data == 'start_gensyn_with_backup':
            start_gensyn_session(call.message.chat.id, use_sync_backup=True)
            
        elif call.data == 'start_gensyn_no_backup':
            start_gensyn_session(call.message.chat.id, use_sync_backup=False)
            
        elif call.data == 'start_fresh':
            start_gensyn_session(call.message.chat.id, use_sync_backup=False)
            
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
                
        elif call.data == 'toggle_tmate':
            if not tmate_running:
                try:
                    subprocess.run("tmate -S /tmp/tmate.sock new-session -d", shell=True, check=True)
                    subprocess.run("tmate -S /tmp/tmate.sock wait tmate-ready", shell=True, check=True)
                    result = subprocess.run(
                        "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'",
                        shell=True, check=True, capture_output=True, text=True
                    )
                    ssh_line = result.stdout.strip()
                    tmate_running = True
                    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_menu())
                    bot.send_message(
                        call.message.chat.id,
                        f"<code>{ssh_line}</code>",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    tmate_running = False
                    bot.send_message(call.message.chat.id, f"❌ Failed to start tmate: {str(e)}")
            else:
                try:
                    subprocess.run("tmate -S /tmp/tmate.sock kill-server", shell=True, check=True)
                    tmate_running = False
                    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_menu())
                    bot.send_message(call.message.chat.id, "🛑 Terminal session killed.")
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"❌ Failed to kill tmate: {str(e)}")
                    
        elif call.data == "update_menu":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("Gensyn Update", callback_data="gensyn_update"),
                InlineKeyboardButton("Bot Update", callback_data="bot_update")
            )
            bot.send_message(call.message.chat.id, "What do you want to update?", reply_markup=markup)
            
        elif call.data == "gensyn_update":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("Soft Update", callback_data="gensyn_soft_update"),
                InlineKeyboardButton("Hard Update", callback_data="gensyn_hard_update")
            )
            bot.send_message(call.message.chat.id, "Choose update type:", reply_markup=markup)
            
        elif call.data == "gensyn_soft_update":
            threading.Thread(target=gensyn_soft_update, args=(call.message.chat.id,), daemon=True).start()
            
        elif call.data == "gensyn_hard_update":
            threading.Thread(target=gensyn_hard_update, args=(call.message.chat.id,), daemon=True).start()
            
        elif call.data == "bot_update":
            try:
                bot.send_message(call.message.chat.id, "Bot update started. Bot will be back in about 1 minute.")
                update_script_path = "/tmp/bot_update_run.sh"
                with open(update_script_path, "w") as f:
                    f.write("curl -s https://raw.githubusercontent.com/shairkhan2/gensyn-bot/refs/heads/main/update_bot.sh | bash\n")
                os.chmod(update_script_path, 0o700)
                subprocess.run(f"echo 'bash {update_script_path} >/tmp/bot_update.log 2>&1' | at now + 1 minute", shell=True)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Failed to update bot: {str(e)}")
                
        elif call.data == "get_backup":
            send_backup_files(call.message.chat.id)
            
        elif call.data == "wandb_send_log":
            try:
                # Find the most recent log file
                latest_log = None
                if os.path.exists(WANDB_LOG_DIR):
                    for root, dirs, files in os.walk(WANDB_LOG_DIR):
                        for file in files:
                            if file.endswith('.log'):
                                file_path = os.path.join(root, file)
                                if not latest_log or os.path.getmtime(file_path) > os.path.getmtime(latest_log):
                                    latest_log = file_path
                
                if latest_log and os.path.exists(latest_log):
                    with open(latest_log, "rb") as f:
                        bot.send_document(call.message.chat.id, f)
                else:
                    bot.send_message(call.message.chat.id, "No log file found.")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Error sending log: {str(e)}")
                
        elif call.data == "wandb_skip_log":
            bot.send_message(call.message.chat.id, "Log skipped.")
            
    except Exception as e:
        logging.error(f"Error in callback_query: {str(e)}")
        bot.send_message(call.message.chat.id, "❌ An error occurred. Check logs.")

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
        start_gensyn_session(message.chat.id, use_sync_backup=False)
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
    wandb_file_cache = set()
    wandb_folder_cache = set()
    last_stale_sent_ts = None
    
    while True:
        try:
            # 1. API status - using the FIXED function
            alive = check_gensyn_api()
            
            # 2. IP change
            try:
                ip = requests.get('https://api.ipify.org', timeout=10).text.strip()
            except:
                ip = "Unknown"
                
            if ip and ip != previous_ip:
                bot.send_message(USER_ID, f"⚠️ IP changed: {ip}")
                previous_ip = ip
                
            if previous_alive is not None and alive != previous_alive:
                status = '✅ Online' if alive else '❌ Offline'
                bot.send_message(USER_ID, f"⚠️ API status changed: {status}")
            previous_alive = alive
            
            # 3. Log freshness
            log_data = get_gensyn_log_status()
            if log_data and log_data.get("timestamp"):
                latest_ts = log_data["timestamp"]
                if (datetime.utcnow() - latest_ts > timedelta(minutes=90)):
                    if not last_stale_sent_ts or last_stale_sent_ts != latest_ts:
                        bot.send_message(
                            USER_ID,
                            f"❗ No new Gensyn log entry since {latest_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC (>1.5h ago)!"
                        )
                        last_stale_sent_ts = latest_ts
                else:
                    last_stale_sent_ts = None
                    
            # 4. WANDB monitoring - simplified
            new_folders = []
            new_files = []
            if os.path.exists(WANDB_LOG_DIR):
                for root, dirs, files in os.walk(WANDB_LOG_DIR):
                    for d in dirs:
                        folder_path = os.path.join(root, d)
                        if folder_path not in wandb_folder_cache:
                            wandb_folder_cache.add(folder_path)
                            new_folders.append(folder_path)
                    for name in files:
                        path = os.path.join(root, name)
                        if path not in wandb_file_cache:
                            wandb_file_cache.add(path)
                            new_files.append(path)
                            
                if new_folders or new_files:
                    # Simple message with Yes/No buttons
                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("Yes", callback_data="wandb_send_log"),
                        InlineKeyboardButton("No", callback_data="wandb_skip_log")
                    )
                    bot.send_message(USER_ID, "🪄 WANDB detected. Want log file?", reply_markup=markup)
                            
            time.sleep(60)
            
        except Exception as e:
            logging.error("Monitor error: %s", str(e))
            time.sleep(10)

# Start internet watchdog thread
threading.Thread(target=internet_watchdog, daemon=True).start()

# Start monitor thread
threading.Thread(target=monitor, daemon=True).start()

try:
    bot.infinity_polling()
except Exception as e:
    logging.error("Bot crashed: %s", str(e))



