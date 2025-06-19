#!/bin/bash

set -e

echo "🔧 Installing dependencies..."

sudo apt update && sudo apt install -y \
    python3 \
    python3-pip \
    git \
    curl \
    wireguard \
    net-tools \
    dos2unix \
    screen  # Optional: if using screen

echo "✅ System packages installed."

# Clone your gensyn-bot repo
cd /root || exit
if [ ! -d "gensyn-bot" ]; then
    echo "📥 Cloning gensyn-bot repository..."
    git clone https://github.com/shairkhan2/gensyn-bot.git
    cd gensyn-bot
else
    echo "📂 gensyn-bot already exists. Pulling latest..."
    cd gensyn-bot
    git pull
fi
python3 -m venv venv
source venv/bin/activate
# Make sure scripts are Unix formatted
find . -name "*.py" -exec dos2unix {} \;
dos2unix *.sh || true

# Install required Python modules
echo "🐍 Installing Python modules in venv..."
pip install --upgrade pip
pip install pyTelegramBotAPI


echo "✅ Python dependencies installed."

# Ask to run manager
read -p "👉 Do you want to run the bot manager now? (y/n): " RUNNOW
if [[ "$RUNNOW" == "y" || "$RUNNOW" == "Y" ]]; then
    echo "🚀 Launching bot manager..."
    python3 bot_manager.py
else
    echo "📌 You can run it later with: python3 /root/gensyn-bot/bot_manager.py"
fi
