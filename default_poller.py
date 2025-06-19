from telebot import TeleBot
import os, requests

bot = TeleBot(os.getenv("BOT_TOKEN"))
bot.delete_webhook()

# Example handler
@bot.message_handler(commands=['up'])
def start_vpn(msg):
    host = os.getenv("ACTIVE_VM_HOST")  # set this in your env or registry
    requests.post(f"http://{host}:5000/start_vpn")
    bot.reply_to(msg, f"WireGuard started on {os.getenv('VM_NAME')}!")

# …add other handlers…

bot.infinity_polling(skip_pending=True)
