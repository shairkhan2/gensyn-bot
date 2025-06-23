#!/bin/bash

set -e

echo "🔧 Installing dependencies..."

sudo apt update && sudo apt install -y \
    python3 \
    python3-pip \
    python3.12-venv \
    git \
    curl \
    wireguard \
    net-tools \
    dos2unix \
    screen
echo "✅ System packages installed."

# Clone gensyn-bot repo
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

# Ensure scripts use Unix line endings
find . -name "*.py" -exec dos2unix {} \;
dos2unix *.sh || true

# Set up virtual environment
echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Create requirements.txt if it doesn't exist
if [ ! -f "requirements.txt" ]; then
    cat > requirements.txt <<EOF
pyTelegramBotAPI==4.13.0
python-dotenv==1.0.1
requests==2.32.3
playwright==1.44.0
EOF
fi

echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
# Install Playwright browser dependencies
echo "🌐 Installing Playwright browsers..."
python3 -m playwright install

echo "✅ All Python packages and browsers installed."

# Ask user to run the bot manager
read -p "👉 Do you want to run the bot manager now? (y/n): " RUNNOW
if [[ "$RUNNOW" == "y" || "$RUNNOW" == "Y" ]]; then
    echo "🚀 Launching bot manager..."
    python3 bot_manager.py
else
    echo "📌 You can run it later with: source venv/bin/activate && python3 bot_manager.py"
fi
