import asyncio
import logging
import json
import requests
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pathlib import Path

# Configuration
API_TOKEN = "8007852647:AAGDLNlkCljjuDWgSPbmtFj-QkFknGFYXIY"
OWNER_ID = "1155176099"
PEERS_FILE = "peers.json"
USERS_FILE = "users.json"
API_URL = "https://dashboard-math.gensyn.ai/api/v1/peer"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# User interaction tracking functions
def load_users():
    try:
        if Path(USERS_FILE).exists():
            with open(USERS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"User load error: {e}")
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.error(f"User save error: {e}")

def update_user(chat_id, username, first_name, last_name, command):
    users = load_users()
    now = datetime.datetime.utcnow().isoformat()
    
    if chat_id not in users:
        users[chat_id] = {
            "first_interaction": now,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "last_interaction": now,
            "command_count": 1,
            "commands": [command],
            "active": True
        }
    else:
        users[chat_id]["last_interaction"] = now
        users[chat_id]["command_count"] += 1
        users[chat_id]["commands"].append(command)
        users[chat_id]["active"] = True
    
    save_users(users)
    return users[chat_id]

# Peer management functions
def load_peers():
    try:
        if Path(PEERS_FILE).exists():
            with open(PEERS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Peer load error: {e}")
    return {}

def save_peers(peers):
    try:
        with open(PEERS_FILE, "w") as f:
            json.dump(peers, f, indent=2)
    except Exception as e:  # Fixed variable name
        logger.error(f"Peer save error: {e}")

def clean_peers(data):
    cleaned = {}
    for chat_id, peer_list in data.items():
        if not isinstance(peer_list, list):
            continue
        valid_peers = []
        for peer in peer_list:
            if (isinstance(peer, dict) and 
                "value" in peer and 
                isinstance(peer.get("id"), bool)):
                # Ensure all fields exist
                peer.setdefault("last_reward", 0)
                peer.setdefault("win_count", 0)
                peer.setdefault("online", False)
                peer.setdefault("last_24h_reward", 0)
                peer.setdefault("last_24h_wins", 0)
                peer.setdefault("last_snapshot_reward", peer["last_reward"])
                peer.setdefault("last_snapshot_win", peer["win_count"])
                valid_peers.append(peer)
        if valid_peers:
            cleaned[chat_id] = valid_peers
    return cleaned

# Initialize peer data
peers = clean_peers(load_peers())
save_peers(peers)

# API functions
async def fetch_peer_data(value, is_id=False):
    try:
        url = f"{API_URL}?{'id' if is_id else 'name'}={value}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("peerId"):
                return {
                    "peerId": data["peerId"],
                    "peerName": data.get("peerName", "Unknown"),
                    "reward": data.get("reward", 0),
                    "score": data.get("score", 0),
                    "online": data.get("online", False)
                }
    except Exception as e:
        logger.error(f"API error: {e}")
    return None

# Helper functions
def is_duplicate(chat_id, value, is_id):
    return any(p for p in peers.get(chat_id, []) 
            if p["value"] == value and p["id"] == is_id)

def format_peer_name(peer):
    name = peer.get("peerName", peer["value"])
    return name if len(name) <= 12 else f"{name[:6]}...{name[-6:]}"

# Command handlers
@dp.message(F.text.startswith("/start"))
@dp.message(F.text.startswith("/help"))
async def show_help(message: Message):
    # Update user interaction
    update_user(
        str(message.chat.id),
        message.chat.username,
        message.chat.first_name,
        message.chat.last_name,
        message.text.split()[0]
    )
    
    help_text = """
👾 <b>Welcome to Gensyn Peer Tracker Bot</b>!

Track your Gensyn peers with these commands:

➕ <b>/add_peer_name</b> <i>name1,name2,...</i>
🆔 <b>/add_peer_id</b> <i>id1,id2,...</i>
📜 <b>/list</b> - View tracked peers
🗑️ <b>/remove</b> <i>index</i> - Remove a peer

🔔 Automatic updates for:
- Reward/wins increases
- Online/offline status changes

⏰ Daily summary at 12 PM IST

Created by: <a href="https://t.me/shair25">Shair</a>
    """
    await message.answer(help_text)

@dp.message(F.text.startswith("/add_peer_name"))
async def add_peer_name(message: Message):
    # Update user interaction
    update_user(
        str(message.chat.id),
        message.chat.username,
        message.chat.first_name,
        message.chat.last_name,
        "/add_peer_name"
    )
    
    chat_id = str(message.chat.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❗ Usage: /add_peer_name peer1,peer2,...")
        return
    
    names = [n.strip() for n in parts[1].split(",")]
    if not names:
        await message.reply("❗ Provide peer names")
        return
    
    peers.setdefault(chat_id, [])
    added = 0
    duplicates = 0
    response = []
    
    for name in names:
        if is_duplicate(chat_id, name, False):
            response.append(f"⚠️ {name} already tracked")
            duplicates += 1
            continue
            
        data = await fetch_peer_data(name)
        if not data:
            response.append(f"❌ {name} not found")
            continue
            
        peer = {
            "value": name,
            "id": False,
            "last_reward": data["reward"],
            "win_count": data["score"],
            "online": data["online"],
            "last_snapshot_reward": data["reward"],
            "last_snapshot_win": data["score"],
            "last_24h_reward": 0,
            "last_24h_wins": 0
        }
        peers[chat_id].append(peer)
        added += 1
        
        status = "🟢 Online" if data["online"] else "🔴 Offline"
        response.append(
            f"✅ <b>{format_peer_name(data)}</b>\n"
            f"💰 Reward: {data['reward']}\n"
            f"🏆 Wins: {data['score']}\n"
            f"🔵 Status: {status}"
        )
    
    if added:
        save_peers(peers)
    
    header = f"Added {added} peer(s)"
    if duplicates:
        header += f", {duplicates} duplicate(s)"
    await message.reply(f"<b>{header}</b>\n\n" + "\n\n".join(response))

@dp.message(F.text.startswith("/add_peer_id"))
async def add_peer_id(message: Message):
    # Update user interaction
    update_user(
        str(message.chat.id),
        message.chat.username,
        message.chat.first_name,
        message.chat.last_name,
        "/add_peer_id"
    )
    
    chat_id = str(message.chat.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❗ Usage: /add_peer_id id1,id2,...")
        return
    
    ids = [i.strip() for i in parts[1].split(",")]
    if not ids:
        await message.reply("❗ Provide peer IDs")
        return
    
    peers.setdefault(chat_id, [])
    added = 0
    duplicates = 0
    response = []
    
    for pid in ids:
        if is_duplicate(chat_id, pid, True):
            response.append(f"⚠️ {pid} already tracked")
            duplicates += 1
            continue
            
        data = await fetch_peer_data(pid, True)
        if not data:
            response.append(f"❌ {pid} not found")
            continue
            
        peer = {
            "value": pid,
            "id": True,
            "last_reward": data["reward"],
            "win_count": data["score"],
            "online": data["online"],
            "last_snapshot_reward": data["reward"],
            "last_snapshot_win": data["score"],
            "last_24h_reward": 0,
            "last_24h_wins": 0
        }
        peers[chat_id].append(peer)
        added += 1
        
        status = "🟢 Online" if data["online"] else "🔴 Offline"
        short_id = f"{pid[:6]}...{pid[-6:]}" if len(pid) > 12 else pid
        response.append(
            f"✅ <b>{format_peer_name(data)}</b> (ID: {short_id})\n"
            f"💰 Reward: {data['reward']}\n"
            f"🏆 Wins: {data['score']}\n"
            f"🔵 Status: {status}"
        )
    
    if added:
        save_peers(peers)
    
    header = f"Added {added} peer(s)"
    if duplicates:
        header += f", {duplicates} duplicate(s)"
    await message.reply(f"<b>{header}</b>\n\n" + "\n\n".join(response))

@dp.message(F.text.startswith("/list"))
async def list_peers(message: Message):
    # Update user interaction
    update_user(
        str(message.chat.id),
        message.chat.username,
        message.chat.first_name,
        message.chat.last_name,
        "/list"
    )
    
    chat_id = str(message.chat.id)
    if chat_id not in peers or not peers[chat_id]:
        await message.reply("😕 No peers added")
        return
    
    total_reward = 0
    total_wins = 0
    online_count = 0
    peer_list = []
    
    for i, peer in enumerate(peers[chat_id], 1):
        data = await fetch_peer_data(peer["value"], peer["id"])
        if data:
            peer["last_reward"] = data["reward"]
            peer["win_count"] = data["score"]
            peer["online"] = data["online"]
        
        status = "🟢" if peer.get("online") else "🔴"
        if peer["id"]:
            ident = f"ID: {peer['value'][:6]}...{peer['value'][-6:]}"
        else:
            ident = f"Name: {format_peer_name(peer)}"
        
        peer_list.append(
            f"{i}. {status} <b>{ident}</b>\n"
            f"   💰 Reward: {peer['last_reward']}\n"
            f"   🏆 Wins: {peer['win_count']}"
        )
        
        total_reward += peer['last_reward']
        total_wins += peer['win_count']
        if peer.get("online"):
            online_count += 1
    
    summary = (
        f"📋 <b>Your Peers ({len(peers[chat_id])})</b>\n"
        f"🟢 Online: {online_count} | 🔴 Offline: {len(peers[chat_id]) - online_count}\n"
        f"💰 Total Rewards: {total_reward}\n"
        f"🏆 Total Wins: {total_wins}\n\n"
    )
    
    await message.reply(summary + "\n\n".join(peer_list))

@dp.message(F.text.startswith("/remove"))
async def remove_peer(message: Message):
    # Update user interaction
    update_user(
        str(message.chat.id),
        message.chat.username,
        message.chat.first_name,
        message.chat.last_name,
        "/remove"
    )
    
    chat_id = str(message.chat.id)
    if not peers.get(chat_id):
        await message.reply("😕 No peers to remove")
        return
    
    try:
        _, index_str = message.text.split(maxsplit=1)
        index = int(index_str) - 1
        if 0 <= index < len(peers[chat_id]):
            removed = peers[chat_id].pop(index)
            save_极狐eers(peers)
            await message.reply(f"🗑️ Removed: <b>{format_peer_name(removed)}</b>")
        else:
            await message.reply("❗ Invalid index")
    except:
        await message.reply("❗ Usage: /remove <number>")

# Owner commands
@dp.message(F.text.startswith("/users"))
async def list_users(message: Message):
    if str(message.from_user.id) != OWNER_ID:
        return
    
    users = load_users()
    user_count = len(users)
    response = [
        f"👑 <b>User Statistics</b>",
        f"👥 Total Users: {user_count}",
        "",
        "<b>User List:</b>"
    ]
    
    for chat_id, user_data in users.items():
        try:
            # Try to get updated info from Telegram
            chat = await bot.get_chat(chat_id)
            username = f"@{chat.username}" if chat.username else ""
            name = f"{chat.first_name or ''} {chat.last_name or ''}".strip()
        except:
            # Fallback to stored data
            username = user_data.get("username", "")
            name = f"{user_data.get("first_name", '')} {user_data.get("last_name", '')}".strip()
        
        display_name = f"{name} {username}".strip()
        if not display_name:
            display_name = f"User {chat_id}"
        
        # Calculate days since last interaction
        last_interaction = datetime.datetime.fromisoformat(user_data["last_interaction"])
        days_ago = (datetime.datetime.utcnow() - last_interaction).days
        
        response.append(
            f"\n👤 <b>{display_name}</b>",
            f"🆔: {chat_id}",
            f"📅 First seen: {user_data['first_interaction'][:10]}",
            f"⏱️ Last seen: {days_ago} day(s) ago",
            f"🔢 Commands used: {user_data['command_count']}",
            f"📝 Last command: {user_data['commands'][-1]}"
        )
    
    await message.reply("\n".join(response))

@dp.message(F.text.startswith("/userstats"))
async def user_stats(message: Message):
    if str(message.from_user.id) != OWNER_ID:
        return
    
    users = load_users()
    user_count = len(users)
    
    # Calculate activity metrics
    active_today = 0
    active_week = 0
    command_counts = {}
    
    for user_data in users.values():
        # Count active users
        last_interaction = datetime.datetime.fromisoformat(user_data["last_interaction"])
        days_ago = (datetime.datetime.utcnow() - last_interaction).days
        
        if days_ago == 0:
            active_today += 1
        if days_ago <= 7:
            active_week += 1
        
        # Count command usage
        for cmd in user_data["commands"]:
            command_counts[cmd] = command_counts.get(cmd, 0) + 1
    
    # Generate command popularity list
    popular_commands = sorted(command_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    command_list = "\n".join([f"• {cmd}: {count}" for cmd, count in popular_commands])
    
    stats = [
        f"📊 <b>User Statistics</b>",
        f"👥 Total Users: {user_count}",
        f"🟢 Active Today: {active_today}",
        f"🟡 Active This Week: {active_week}",
        f"🔴 Inactive (>7 days): {user_count - active_week}",
        "",
        f"📈 <b>Top Commands:</b>",
        command_list
    ]
    
    await message.reply("\n".join(stats))

@dp.message(F.text.startswith("/status"))
async def all_status(message: Message):
    if str(message.from_user.id) != OWNER_ID:
        return
    
    total_reward = 0
    total_wins = 0
    response = ["👑 <b>All Tracked Peers</b>"]
    
    for chat_id, peer_list in peers.items():
        try:
            chat = await bot.get_chat(chat_id)
            name = f"@{chat.username}" if chat.username else chat.first_name or "Unknown"
        except:
            name = "Unknown"
        
        for peer in peer_list:
            status = "🟢" if peer.get("online") else "🔴"
            ptype = "ID" if peer["id"] else "Name"
            value = peer['value']
            if len(value) > 12:
                value = f"{value[:6]}...{value[-6:]}"
            
            response.append(
                f"\n👤 {name}",
                f"{status} <b>{ptype}:</b> {value}",
                f"💰 Reward: {peer.get('last_reward', 0)}",
                f"🏆 Wins: {peer.get('win_count', 0)}"
            )
            
            total_reward += peer.get('last_reward', 0)
            total_wins += peer.get('win_count', 0)
    
    response.insert(1, f"💰 Total Rewards: {total_reward}")
    response.insert(2, f"🏆 Total Wins: {total_wins}")
    
    full_msg = "\n".join(response)
    if len(full_msg) > 4000:
        parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
        for part in parts:
            await message.reply(part)
            await asyncio.sleep(1)
    else:
        await message.reply(full_msg)

# BROADCAST FEATURE
@dp.message(F.text.startswith("/post"))
async def broadcast_message(message: Message):
    if str(message.from_user.id) != OWNER_ID:
        return
    
    try:
        # Extract the message to broadcast
        _, broadcast_text = message.text.split(maxsplit=1)
    except ValueError:
        await message.reply("❗ Usage: /post <message>")
        return
    
    users = load_users()
    total_users = len(users)
    successful = 0
    failed = 0
    
    # Send to owner first
    try:
        await message.reply(f"📢 Broadcast started to {total_users} users...")
    except:
        pass
    
    # Send to all users
    for chat_id in users:
        try:
            await bot.send_message(int(chat_id), f"📢 <b>Announcement from Bot Owner</b>\n\n{broadcast_text}")
            successful += 1
            await asyncio.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Broadcast failed to {chat_id}: {e}")
            failed += 1
            # Mark user as inactive if message fails
            if chat_id in users:
                users[chat_id]["active"] = False
                save_users(users)
    
    # Save updated user statuses
    save_users(users)
    
    # Report results to owner
    report = (
        f"📊 <b>Broadcast Report</b>\n"
        f"✅ Successful: {successful}\n"
        f"❌ Failed: {failed}\n"
        f"👤 Total Attempted: {total_users}\n\n"
        f"Note: Failed deliveries may indicate users who blocked the bot."
    )
    await message.reply(report)

# Background tasks
async def peer_watcher():
    logger.info("Peer watcher started")
    while True:
        for chat_id, peer_list in peers.items():
            for peer in peer_list:
                data = await fetch_peer_data(peer["value"], peer["id"])
                if not data:
                    continue
                
                reward_diff = data["reward"] - peer["last_reward"]
                wins_diff = data["score"] - peer["win_count"]
                status_change = data["online"] != peer["online"]
                
                # Update peer data
                peer["last_reward"] = data["reward"]
                peer["win_count"] = data["score"]
                peer["online"] = data["online"]
                
                # Prepare notifications
                notifications = []
                if reward_diff > 0 or wins_diff > 0:
                    msg = f"✨ <b>Update for {format_peer_name(peer)}</b>\n"
                    if reward_diff > 0:
                        msg += f"💰 Rewards: {data['reward']} (+{reward_diff})\n"
                    if wins_diff > 0:
                        msg += f"🏆 Wins: {data['score']} (+{wins_diff})\n"
                    notifications.append(msg)
                
                if status_change:
                    status_msg = "🟢 Online" if data["online"] else "🔴 Offline"
                    notifications.append(f"🔔 <b>{format_peer_name(peer)}</b> is now {status_msg}")
                
                # Send notifications
                for note in notifications:
                    try:
                        await bot.send_message(int(chat_id), note)
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.error(f"Notify error: {e}")
        
        save_peers(peers)
        await asyncio.sleep(60)

async def daily_summary():  # Fixed typo in function name
    logger.info("Daily summary started")
    while True:
        now = datetime.datetime.utcnow()
        target = now.replace(hour=6, minute=30, second=0)  # 12 PM IST = 6:30 AM UTC
        if now > target:
            target += datetime.timedelta(days=1)
        
        wait = (target - now).total_seconds()
        await asyncio.sleep(wait)
        
        for chat_id, peer_list in peers.items():
            summary = ["⏰ <b>24-Hour Summary</b>"]
            total_reward = 0
            total_wins = 0
            has_activity = False
            
            for peer in peer_list:
                reward_24h = peer["last_reward"] - peer["last_snapshot_reward"]  # Fixed variable name
                wins_24h = peer["win_count"] - peer["last_snapshot_win"]
                
                # Update snapshots
                peer["last_snapshot_reward"] = peer["last_reward"]
                peer["last_snapshot_win"] = peer["win_count"]
                peer["last_24h_reward"] = reward_24h
                peer["last_24h_wins"] = wins_24h
                
                # Only show peers with activity
                if reward_24h > 0 or wins_24h > 0:  # Fixed variable name
                    has_activity = True
                    total_reward += reward_24h
                    total_wins += wins_24h
                    
                    summary.append(f"\n• <b>{format_peer_name(peer)}</b>")
                    if reward_24h > 0:
                        summary.append(f"   💰 Rewards: +{reward_24h}")
                    if wins_24h > 0:
                        summary.append(f"   🏆 Wins: +{wins_24h}")
            
            if has_activity:
                summary.insert(1, f"\n📈 <b>Total Earnings</b>")
                summary.insert(2, f"💰 Rewards: +{total_reward}")
                summary.insert(3, f"🏆 Wins: +{total_wins}\n")
                
                try:
                    await bot.send_message(int(chat_id), "\n".join(summary))
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Summary error: {e}")
        
        save_peers(peers)
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(peer_watcher())
    asyncio.create_task(daily_summary())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
