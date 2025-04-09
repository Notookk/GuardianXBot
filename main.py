import logging
import asyncio
import nest_asyncio
import pytz
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TOKEN
from database.database import *
from handlers.nsfw import *
from handlers.start import *
from handlers.utils import *
from handlers.broadcast import *

# Fix event loop conflict
nest_asyncio.apply()

# Patch AsyncIOScheduler's _configure to always use UTC unless overridden
original_configure = AsyncIOScheduler._configure
def patched_configure(self, config):
    # Ensure timezone is always a pytz timezone, defaulting to UTC
    config = config.copy()  # Avoid modifying the original config dict
    config['timezone'] = config.get('timezone', pytz.UTC)
    original_configure(self, config)
AsyncIOScheduler._configure = patched_configure

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
    try:
        await db.init_db()

        # Build Application (JobQueue will use the patched AsyncIOScheduler)
        application = ApplicationBuilder() \
            .token(TOKEN) \
            .arbitrary_callback_data(True) \
            .build()

        # Register Handlers
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
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        loop.close()
