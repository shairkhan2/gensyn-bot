#!/bin/bash

set -e

echo "🔧 Installing base dependencies..."

# Install system packages
sudo apt update && sudo apt install -y \
    python3 \
    python3-pip \
    python3.12-venv \
    git \
    curl \
    wireguard \
    net-tools \
    dos2unix \
    screen \
    nodejs \
    npm

echo "✅ System packages installed."

# Clone the gensyn-bot repository
cd /root || exit
if [ ! -d "gensyn-bot" ]; then
    echo "📥 Cloning gensyn-bot repository..."
    git clone https://github.com/shairkhan2/gensyn-bot.git
else
    echo "📂 gensyn-bot already exists. Pulling latest..."
    cd gensyn-bot
    git pull
fi

cd /root/gensyn-bot

# Convert all scripts to Unix format
find . -name "*.py" -exec dos2unix {} \;
dos2unix *.sh || true

# Install Playwright browser dependencies
echo "📦 Installing Playwright browser dependencies..."
npm install -g playwright
playwright install-deps

# Set up Python virtual environment and install dependencies
echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
python3 -m playwright install

echo "✅ Python & Playwright setup complete."

# Prompt to run bot manager
read -p "👉 Do you want to run the bot manager now? (y/n): " RUNNOW
if [[ "$RUNNOW" == "y" || "$RUNNOW" == "Y" ]]; then
    echo "🚀 Launching bot manager..."
    python3 bot_manager.py
else
    echo "📌 You can run it later with: source venv/bin/activate && python3 /root/gensyn-bot/bot_manager.py"
fi

