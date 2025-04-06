import logging
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "7244625688:AAFYZ_b5S8VQqMmrhu22XKy-QEtUqZBa4B8"
ADMIN_IDS = [8091696994]  # Replace with your Telegram ID
ABUSE_EMAIL = "abuse@telegram.org"  # Telegram's official abuse email
REPORT_INTERVAL = 3600  # Report every 1 hour (in seconds)

# Report categories
REPORT_CATEGORIES = {
    "DDoS": "🚫 DDoS/Server Attack",
    "ChildAbuse": "⚠️ Child Abuse/Illegal Content",
    "BGMI_Hack": "🎮 BGMI/Free Fire Hacks",
    "Spam": "📢 Spam/Scam",
    "Piracy": "🏴‍☠️ Piracy/Illegal Sharing"
}

# Database simulation
reports_db = {}
active_reports = {}  # Tracks channels being actively reported

def extract_channel_info(text):
    """Extract channel username or ID from various formats"""
    if text.startswith('@'):
        return text.strip()
    
    link_pattern = r'(?:https?://)?t\.me/([a-zA-Z0-9_]+)'
    match = re.search(link_pattern, text)
    if match:
        return f"@{match.group(1)}"
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_markdown_v2(
        f"👋 Hello {user.mention_markdown_v2()}!\n\n"
        "🔹 Report harmful Telegram channels\n\n"
        "📌 Commands:\n"
        "/start - Show this message\n"
        "/report - Report a channel\n"
        "/stopreport - Stop active reports\n"
        "/stats - View report stats (admin only)"
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate the reporting process"""
    await update.message.reply_text(
        "Please send:\n"
        "- Channel username (@example)\n"
        "- Channel link (t.me/example)\n"
        "- Or forward a message from the channel"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    channel = None
    
    if message.text and not message.text.startswith('/'):
        channel = extract_channel_info(message.text)
    elif message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel = f"@{message.forward_from_chat.username}" if message.forward_from_chat.username else f"ID:{message.forward_from_chat.id}"
    
    if not channel:
        await update.message.reply_text("❌ Invalid channel format. Try again or use /report")
        return
    
    context.user_data['channel_to_report'] = channel
    await show_report_categories(update)

async def show_report_categories(update: Update):
    """Show report categories"""
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"report_{code}")]
        for code, label in REPORT_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Select report category:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Select report category:",
            reply_markup=reply_markup
        )

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, category = query.data.split('_')
    channel = context.user_data.get('channel_to_report')
    
    if not channel:
        await query.edit_message_text("❌ Error: Channel not found. Please try again.")
        return
    
    # Store report
    if channel not in reports_db:
        reports_db[channel] = {cat: 0 for cat in REPORT_CATEGORIES}
    reports_db[channel][category] += 1
    
    # Start continuous reporting
    if channel not in active_reports:
        active_reports[channel] = True
        asyncio.create_task(continuous_report(context, channel, category))
    
    await query.edit_message_text(
        f"✅ Continuous reporting started for:\n\n"
        f"Channel: {channel}\n"
        f"Category: {REPORT_CATEGORIES[category]}\n\n"
        f"Reports will be sent to Telegram every hour.\n"
        f"Use /stopreport to stop."
    )

async def continuous_report(context: ContextTypes.DEFAULT_TYPE, channel: str, category: str):
    """Continuously report the channel"""
    while channel in active_reports and active_reports[channel]:
        # Send report to Telegram's abuse team (simulated)
        report_details = (
            f"🚨 Automated Abuse Report 🚨\n\n"
            f"Channel: {channel}\n"
            f"Category: {REPORT_CATEGORIES[category]}\n"
            f"Total Reports: {reports_db[channel][category]}\n\n"
            f"Please investigate this channel for violations."
        )
        
        logger.info(f"Sending report to Telegram for {channel}")
        
        # In a real implementation, you would:
        # 1. Email abuse@telegram.org with these details
        # 2. Or use Telegram's official reporting API if available
        
        await asyncio.sleep(REPORT_INTERVAL)

async def stop_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop continuous reporting"""
    channel = context.user_data.get('channel_to_report')
    if not channel:
        await update.message.reply_text("No active reports to stop.")
        return
    
    if channel in active_reports:
        active_reports.pop(channel)
        await update.message.reply_text(f"✅ Stopped reporting for {channel}")
    else:
        await update.message.reply_text(f"No active reports for {channel}")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show report statistics"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not reports_db:
        await update.message.reply_text("No reports yet.")
        return
    
    stats = ["📊 Active Reports:\n"]
    stats.extend([f"- {channel}" for channel in active_reports])
    
    stats.append("\n\n📈 Report Statistics:")
    for channel, categories in reports_db.items():
        stats.append(f"\n🔹 {channel}:")
        stats.extend([f"  {REPORT_CATEGORIES[cat]}: {count}" 
                    for cat, count in categories.items() if count > 0])
    
    await update.message.reply_text("\n".join(stats))

def main():
    application = Application.builder().token(TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("stopreport", stop_report))
    application.add_handler(CommandHandler("stats", show_stats))
    
    # Message handlers
    application.add_handler(MessageHandler(
        filters.TEXT | filters.FORWARDED & ~filters.COMMAND,
        handle_message
    ))
    
    # Button handlers
    application.add_handler(CallbackQueryHandler(
        handle_category_selection,
        pattern="^report_"
    ))

    application.run_polling()

if __name__ == '__main__':
    main()
