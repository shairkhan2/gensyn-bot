#!/bin/bash

echo "🔧 Updating system..."
apt-get update -y && apt-get upgrade -y

echo "🐍 Installing Python 3, venv, and pip..."
apt-get install -y python3 python3-pip python3-venv

echo "🛡️ Installing WireGuard..."
apt-get install -y wireguard

echo "📦 Installing required Python packages..."
pip3 install pyTelegramBotAPI

echo "📁 Creating project directory..."
mkdir -p /root/vpn-bot
cd /root/vpn-bot

echo "📋 Downloading bot manager script..."
wget -O bot_manager.py https://raw.githubusercontent.com/shairkhan2/gensyn-bot/main/bot_manager.py || echo "⚠️ Manual copy may be needed."

echo "✅ Setup complete. Run the script using:"
echo "    python3 bot_manager.py"
