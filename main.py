import logging
import asyncio
import nest_asyncio
from telegram.ext import ApplicationBuilder, Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from config import TOKEN
from database.database import *
from handlers.nsfw import *
from handlers.start import *
from handlers.utils import *
from handlers.broadcast import *
from flask import Flask, Response, jsonify, request, send_file, stream_with_context, render_template

# ✅ Fix event loop conflict
nest_asyncio.apply()

# ✅ Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ✅ Initialize Database
db = Database()






async def main():
    """Main function to initialize the bot and start polling."""
    await db.init_db()  # ✅ Ensure database is ready before starting bot

    application = ApplicationBuilder().token(TOKEN).build()

    # ✅ Register Handlers
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
  # 👈 added this

    logger.info("🤖 Bot is running...✅")

    await application.run_polling(timeout=30)  # Increase timeout to 30 seconds

    logger.info("🤖 Bot stopped...✅")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())  # ✅ Uses existing event loop (NO conflict)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
