import logging
import re
import asyncio
import smtplib
from email.mime.text import MIMEText
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

# Configuration
TOKEN = "7244625688:AAFYZ_b5S8VQqMmrhu22XKy-QEtUqZBa4B8"
ADMIN_IDS = [8091696994]  # Your Telegram ID
REPORT_INTERVAL = 5 # 

# Official Telegram report destinations
REPORT_RECIPIENTS = {
    "Abuse": "abuse@telegram.org",
    "DMCA": "dmca@telegram.org",
    "Support": "support@telegram.org",
    "Legal": "legal@telegram.org",
    "Copyright": "copyright@telegram.org"
}

# Report categories
REPORT_CATEGORIES = {
    "DDoS": "🚫 DDoS/Server Attack",
    "ChildAbuse": "⚠️ Child Abuse/Illegal Content", 
    "Hacking": "💻 Hacking/Cheating Services",
    "Spam": "📢 Spam/Scam",
    "Piracy": "🏴‍☠️ Piracy/Copyright Violation"
}

# Database
reports_db = {}
active_reports = {}

def extract_channel_link(text):
    """Extract only t.me links"""
    patterns = [
        r'(https?://t\.me/[a-zA-Z0-9_]+)',
        r'(t\.me/[a-zA-Z0-9_]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

async def send_email_report(channel, category, report_count):
    """Send email to all Telegram departments"""
    subject = f"Violation Report: {channel} - {category}"
    body = f"""
    Official Violation Report ({report_count} reports)
    
    Channel: {channel}
    Category: {category}
    Violation Type: {REPORT_CATEGORIES[category]}
    
    Evidence suggests this channel is violating Telegram's Terms of Service.
    Please investigate and take appropriate action.
    """
    
    for dept, email in REPORT_RECIPIENTS.items():
        try:
            msg = MIMEText(body)
            msg['Subject'] = f"{subject} [{dept}]"
            msg['From'] = "your_email@example.com"
            msg['To'] = email
            
            # Configure your SMTP settings
            with smtplib.SMTP('smtp.example.com', 587) as server:
                server.starttls()
                server.login("your_email@example.com", "your_password")
                server.send_message(msg)
            
            logger.info(f"Report sent to {dept} department")
        except Exception as e:
            logger.error(f"Failed to send to {email}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ Telegram Channel Reporter Bot\n\n"
        "🔹 Only accepts t.me links (e.g., t.me/channel or https://t.me/channel)\n\n"
        "📌 Commands:\n"
        "/report - Start reporting a channel\n"
        "/stopreport - Stop active reports\n"
        "/status - Check active reports\n"
        "/stats - View all reports (admin)"
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please send the channel link in format:\n"
        "• t.me/channelname\n"
        "• https://t.me/channelname\n\n"
        "This bot will continuously report to all Telegram departments."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = extract_channel_link(update.message.text)
    if not channel:
        await update.message.reply_text(
            "❌ Invalid format. Only t.me links accepted.\n"
            "Examples:\n"
            "t.me/channelname\n"
            "https://t.me/channelname"
        )
        return
    
    context.user_data['channel_to_report'] = channel
    await show_categories(update)

async def show_categories(update: Update):
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"cat_{code}")] 
        for code, text in REPORT_CATEGORIES.items()
    ]
    await update.message.reply_text(
        "Select violation type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, category = query.data.split('_')
    channel = context.user_data.get('channel_to_report')
    
    if not channel:
        await query.edit_message_text("❌ Error: Channel missing")
        return
    
    # Initialize tracking
    if channel not in reports_db:
        reports_db[channel] = {
            'category': category,
            'count': 0,
            'reports_sent': {dept: 0 for dept in REPORT_RECIPIENTS}
        }
    
    # Start continuous reporting
    active_reports[channel] = True
    asyncio.create_task(report_loop(context, channel, category))
    
    await query.edit_message_text(
        f"🚨 Continuous Reporting Activated 🚨\n\n"
        f"Channel: {channel}\n"
        f"Category: {REPORT_CATEGORIES[category]}\n\n"
        f"Reports will be sent to:\n"
        f"• Abuse Team\n• Copyright Team\n• Support Team\n• Legal Team\n\n"
        f"Use /stopreport to cancel."
    )

async def report_loop(context: ContextTypes.DEFAULT_TYPE, channel: str, category: str):
    """Continuous reporting to all departments"""
    while active_reports.get(channel, False):
        reports_db[channel]['count'] += 1
        
        # Send to all departments
        await send_email_report(channel, category, reports_db[channel]['count'])
        
        # Update counts
        for dept in REPORT_RECIPIENTS:
            reports_db[channel]['reports_sent'][dept] += 1
        
        # Notify admin
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"✅ Report #{reports_db[channel]['count']} sent for {channel}"
                )
            except Exception as e:
                logger.error(f"Admin notify failed: {e}")
        
        await asyncio.sleep(REPORT_INTERVAL)

async def stop_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = context.user_data.get('channel_to_report')
    if not channel or channel not in active_reports:
        await update.message.reply_text("No active reports for this channel")
        return
    
    active_reports.pop(channel)
    await update.message.reply_text(
        f"🛑 Stopped reporting for {channel}\n"
        f"Total reports sent: {reports_db[channel]['count']}"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_reports:
        await update.message.reply_text("No active reports running")
        return
    
    msg = ["🚀 Active Reports:"]
    for channel in active_reports:
        data = reports_db[channel]
        msg.append(
            f"\n🔹 {channel}\n"
            f"Category: {REPORT_CATEGORIES[data['category']}\n"
            f"Reports sent: {data['count']}"
        )
    
    await update.message.reply_text("\n".join(msg))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin access required")
        return
    
    if not reports_db:
        await update.message.reply_text("No reports in database")
        return
    
    msg = ["📊 Report Statistics"]
    for channel, data in reports_db.items():
        msg.append(
            f"\n📌 {channel}\n"
            f"Category: {REPORT_CATEGORIES[data['category']}\n"
            f"Total Reports: {data['count']}\n"
            "Sent to:"
        )
        for dept, count in data['reports_sent'].items():
            msg.append(f"  • {dept}: {count}")
    
    await update.message.reply_text("\n".join(msg))

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("stopreport", stop_report))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    
    # Messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(
        handle_category,
        pattern="^cat_"
    ))
    
    app.run_polling()

if __name__ == '__main__':
    main()
