import os
import json
import time
import threading
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

CONFIG_FILE = "config.json"
PEERS_FILE = "peers.json"
CHECK_INTERVAL = 300  # seconds

# ----------------------------
# Helpers
# ----------------------------

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise Exception("Please create config.json with your Telegram BOT TOKEN")
    with open(CONFIG_FILE) as f:
        return json.load(f)

def load_peers():
    if os.path.exists(PEERS_FILE):
        with open(PEERS_FILE) as f:
            return json.load(f)
    return {}

def save_peers(peers):
    with open(PEERS_FILE, "w") as f:
        json.dump(peers, f, indent=4)

def fetch_peer_data(peer_name):
    url_name = peer_name.replace(" ", "%20")
    url = f"https://dashboard-math.gensyn.ai/api/v1/peer?name={url_name}"
    try:
        r = requests.get(url, timeout=10)
        if r.ok:
            return r.json()
    except Exception as e:
        print(f"Error fetching {peer_name}: {e}")
    return None

# ----------------------------
# Background watcher
# ----------------------------

def peer_watcher(app):
    last_states = {}

    while True:
        peers = load_peers()
        for user_id, peer_list in peers.items():
            for peer_name in peer_list:
                data = fetch_peer_data(peer_name)
                if data:
                    reward = data.get('reward')
                    won = data.get('has_won')
                    prev = last_states.get(f"{user_id}:{peer_name}", {})
                    if prev.get('reward') != reward or prev.get('won') != won:
                        msg = f"🔔 <b>{peer_name}</b>\nReward: {reward}\nWon: {won}"
                        try:
                            app.bot.send_message(
                                chat_id=int(user_id),
                                text=msg,
                                parse_mode='HTML'
                            )
                            print(f"[INFO] Sent update to {user_id} for {peer_name}")
                        except Exception as e:
                            print(f"Error sending to {user_id}: {e}")
                        last_states[f"{user_id}:{peer_name}"] = {
                            'reward': reward,
                            'won': won
                        }

        time.sleep(CHECK_INTERVAL)

# ----------------------------
# Bot commands
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Use /add_peer, /remove_peer, /list_peers")

async def add_peer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /add_peer <peer_name>")
        return
    peer_name = " ".join(context.args)
    user_id = str(update.effective_user.id)
    peers = load_peers()
    if user_id not in peers:
        peers[user_id] = []
    if peer_name not in peers[user_id]:
        peers[user_id].append(peer_name)
        save_peers(peers)
        await update.message.reply_text(f"✅ Added peer: {peer_name}")
    else:
        await update.message.reply_text(f"Already tracking: {peer_name}")

async def remove_peer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /remove_peer <peer_name>")
        return
    peer_name = " ".join(context.args)
    user_id = str(update.effective_user.id)
    peers = load_peers()
    if user_id in peers and peer_name in peers[user_id]:
        peers[user_id].remove(peer_name)
        save_peers(peers)
        await update.message.reply_text(f"❌ Removed peer: {peer_name}")
    else:
        await update.message.reply_text("Peer not found in your list.")

async def list_peers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    peers = load_peers()
    peer_list = peers.get(user_id, [])
    if not peer_list:
        await update.message.reply_text("You are not tracking any peers.")
    else:
        msg = "\n".join(peer_list)
        await update.message.reply_text(f"📌 Your peers:\n{msg}")

# ----------------------------
# Main
# ----------------------------

def main():
    config = load_config()
    app = ApplicationBuilder().token(config["TELEGRAM_API_TOKEN"]).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_peer", add_peer))
    app.add_handler(CommandHandler("remove_peer", remove_peer))
    app.add_handler(CommandHandler("list_peers", list_peers))

    threading.Thread(target=peer_watcher, args=(app,), daemon=True).start()

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
