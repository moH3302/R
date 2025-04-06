import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "7244625688:AAFYZ_b5S8VQqMmrhu22XKy-QEtUqZBa4B8"
ADMIN_IDS = [8091696994]  # Replace with your Telegram ID

# Report categories
REPORT_CATEGORIES = {
    "DDoS": "🚫 DDoS/Server Attack",
    "ChildAbuse": "⚠️ Child Abuse/Illegal Content",
    "BGMI_Hack": "🎮 BGMI/Free Fire Hacks",
    "Spam": "📢 Spam/Scam",
    "Piracy": "🏴‍☠️ Piracy/Illegal Sharing"
}

# Database simulation (use a real database in production)
reports_db = {}

def extract_channel_info(text):
    """Extract channel username or ID from various formats"""
    # Handle @username format
    if text.startswith('@'):
        return text.strip()
    
    # Handle t.me/username or https://t.me/username
    link_pattern = r'(?:https?://)?t\.me/([a-zA-Z0-9_]+)'
    match = re.search(link_pattern, text)
    if match:
        return f"@{match.group(1)}"
    
    return None

def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    update.message.reply_markdown_v2(
        f"👋 Hello {user.mention_markdown_v2()}!\n\n"
        "🔹 You can report harmful Telegram channels using:\n"
        "- Channel username (@channelname)\n"
        "- Channel link (t.me/channelname)\n"
        "- Forwarded message from channel\n\n"
        "📌 Supported report categories:\n"
        "- DDoS/Server Attacks\n"
        "- Child Abuse/Illegal Content\n"
        "- Game Hacks/Cheats\n"
        "- Spam/Scam\n"
        "- Piracy"
    )

def handle_message(update: Update, context: CallbackContext) -> None:
    message = update.message
    channel = None
    
    # Case 1: Text message containing username or link
    if message.text:
        channel = extract_channel_info(message.text)
    
    # Case 2: Forwarded message from channel
    elif message.forward_from_chat and message.forward_from_chat.type == 'channel':
        if message.forward_from_chat.username:
            channel = f"@{message.forward_from_chat.username}"
        else:
            channel = f"ID:{message.forward_from_chat.id}"
    
    if not channel:
        update.message.reply_text(
            "❌ Please send:\n"
            "- Channel username (@example)\n"
            "- Channel link (t.me/example)\n"
            "- Or forward a message from the channel"
        )
        return
    
    context.user_data['channel_to_report'] = channel
    show_report_categories(update)

def show_report_categories(update: Update):
    """Show inline keyboard with report categories"""
    keyboard = []
    row = []
    
    for code, label in REPORT_CATEGORIES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"report_{code}"))
        if len(row) == 2:  # 2 buttons per row
            keyboard.append(row)
            row = []
    
    if row:  # Add remaining buttons if any
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        update.callback_query.edit_message_text(
            "Select report category:",
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            "Select report category:",
            reply_markup=reply_markup
        )

def handle_category_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    _, category = query.data.split('_')
    channel = context.user_data.get('channel_to_report')
    
    if not channel:
        query.edit_message_text("❌ Error: Channel not found. Please try again.")
        return
    
    # Store report
    if channel not in reports_db:
        reports_db[channel] = {cat: 0 for cat in REPORT_CATEGORIES}
    
    reports_db[channel][category] += 1
    
    # Notify admins
    notify_admins(context, channel, category)
    
    query.edit_message_text(
        f"✅ Report submitted!\n\n"
        f"Channel: {channel}\n"
        f"Category: {REPORT_CATEGORIES[category]}\n\n"
        f"Thank you for making Telegram safer!"
    )

def notify_admins(context: CallbackContext, channel: str, category: str):
    """Notify all admins about new report"""
    report_count = reports_db[channel][category]
    
    message = (
        f"⚠️ **New Report** ⚠️\n\n"
        f"🔹 Channel: {channel}\n"
        f"🔹 Category: {REPORT_CATEGORIES[category]}\n"
        f"🔹 Total reports: {report_count}\n\n"
        f"Handle with caution!"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            context.bot.send_message(
                admin_id,
                message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

def show_stats(update: Update, context: CallbackContext):
    """Show report statistics (admin only)"""
    if update.effective_user.id not in ADMIN_IDS:
        update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not reports_db:
        update.message.reply_text("No reports yet.")
        return
    
    stats = ["📊 **Report Statistics**\n"]
    for channel, categories in reports_db.items():
        channel_stats = [f"\n🔹 **{channel}**"]
        for cat, count in categories.items():
            if count > 0:
                channel_stats.append(f"{REPORT_CATEGORIES[cat]}: {count}")
        stats.append("\n".join(channel_stats))
    
    update.message.reply_markdown_v2("\n".join(stats))

def main():
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Commands
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stats", show_stats))
    
    # Message handlers
    dispatcher.add_handler(MessageHandler(
        Filters.text | Filters.forwarded,
        handle_message
    ))
    
    # Button handlers
    dispatcher.add_handler(CallbackQueryHandler(
        handle_category_selection,
        pattern="^report_"
    ))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
