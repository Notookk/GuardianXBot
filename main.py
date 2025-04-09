import logging
import asyncio
import nest_asyncio
import pytz  # Make sure pytz is installed
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from config import TOKEN
from database.database import *
from handlers.nsfw import *
from handlers.start import *
from handlers.utils import *
from handlers.broadcast import *

# Fix event loop conflict
nest_asyncio.apply()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Database
db = Database()

async def main():
    """Main function to initialize the bot and start polling."""
    await db.init_db()

    # Build Application with UTC timezone
    application = ApplicationBuilder() \
        .token(TOKEN) \
        .arbitrary_callback_data(True) \
        .build()
    
    # Set UTC timezone for job queue using pytz
    application.job_queue.scheduler.configure(timezone=pytz.UTC)

    # Register Handlers (your existing handlers remain unchanged)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("userinfo", user_info))
    application.add_handler(CommandHandler("myinfo", my_info))
    application.add_handler(CommandHandler("sudolist", get_approved_users_list))
    application.add_handler(CommandHandler("add", add_approved))
    application.add_handler(CommandHandler("remove", remove_approved))
    application.add_handler(CommandHandler("broad", broadcast_command))
    application.add_handler(MessageHandler(filters.ALL, handle_media))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_member))

    logger.info("🤖 Bot is running...✅")

    await application.run_polling()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
