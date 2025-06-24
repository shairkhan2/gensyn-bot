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

# Set up Python virtual environment and install dependencies
echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
sudo apt install \
  libicu74 \
  libnss3 \
  libatk1.0-0t64 \
  libatk-bridge2.0-0t64 \
  libcups2t64 \
  libatspi2.0-0t64 \
  libx11-6 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libxcb1 \
  libxkbcommon0 \
  libpango-1.0-0 \
  libcairo2 \
  libasound2t64


echo "✅ Python & Playwright setup complete."

# Prompt to run bot manager
read -p "👉 Do you want to run the bot manager now? (y/n): " RUNNOW
if [[ "$RUNNOW" == "y" || "$RUNNOW" == "Y" ]]; then
    echo "🚀 Launching bot manager..."
    python3 bot_manager.py
else
    echo "📌 You can run it later with: source venv/bin/activate && python3 /root/gensyn-bot/bot_manager.py"
fi

