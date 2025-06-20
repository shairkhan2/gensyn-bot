import os
import time
import subprocess

BOT_CONFIG = "/root/bot_config.env"
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
BOT_PATH = "/root/gensyn-bot/bot.py"
VENV_PATH = "/root/gensyn-bot/venv"
PYTHON_BIN = f"{VENV_PATH}/bin/python3"

def menu():
    while True:
        print("\n🛠️ VPN Bot Manager")
        print("1. Paste WireGuard config")
        print("2. Setup Telegram Bot")
        print("3. Enable Bot on Boot")
        print("4. Exit")
        print("5. Start Bot")
        print("6. Stop Bot")
        print("7. View Bot Logs")
        choice = input("\nSelect an option: ")

        if choice == "1":
            setup_vpn()
        elif choice == "2":
            setup_bot()
        elif choice == "3":
            setup_systemd()
        elif choice == "4":
            break
        elif choice == "5":
            start_bot()
        elif choice == "6":
            stop_bot()
        elif choice == "7":
            os.system("journalctl -u bot -f")
        else:
            print("❌ Invalid option.")

def setup_vpn():
    print("\n📋 Paste full WireGuard config. Type 'END' on a new line to finish:")
    config = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        config.append(line)

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

    if not os.path.exists(BOT_PATH):
        os.system("cp ./default_bot.py /root/gensyn-bot/bot.py")
        os.system(f"chmod +x {BOT_PATH}")

    print("✅ Bot config saved and default bot.py is ready.")

def start_bot():
    print("🚀 Launching bot in background...")

    if not os.path.exists(VENV_PATH):
        print("🔧 Creating virtual environment...")
        os.system(f"python3 -m venv {VENV_PATH}")
        os.system(f"{VENV_PATH}/bin/pip install --upgrade pip")
        os.system(f"{VENV_PATH}/bin/pip install pyTelegramBotAPI")

    # Check if the bot is already running
    if os.system(f"pgrep -f '{PYTHON_BIN} {BOT_PATH}' > /dev/null") == 0:
        print("⚠️ Bot is already running.")
    else:
        os.system(f"nohup {PYTHON_BIN} {BOT_PATH} > /root/bot.log 2>&1 &")
        print("✅ Bot started using virtual environment. Logs: /root/bot.log")

def stop_bot():
    print("🛑 Stopping bot...")
    if os.system(f"pgrep -f '{BOT_PATH}' > /dev/null") == 0:
        os.system(f"pkill -f '{BOT_PATH}'")
        print("✅ Bot stopped.")
    else:
        print("ℹ️ Bot is not running.")

def setup_systemd():
    print("\n⚙️ Enabling bot service...")
    service = f"""[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
ExecStart={PYTHON_BIN} {BOT_PATH}
EnvironmentFile={BOT_CONFIG}
Restart=always
User=root
WorkingDirectory=/root/gensyn-bot
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/bot.service", "w") as f:
        f.write(service)
    os.system("systemctl daemon-reexec")
    os.system("systemctl daemon-reload")
    os.system("systemctl enable bot")
    os.system("systemctl restart bot")
    print("✅ Bot service enabled and running via systemd.")

if __name__ == "__main__":
    menu()

