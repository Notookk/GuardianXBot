import os
import logging
import shutil
from typing import Optional
from telegram import User, Update
from config import MEDIA_DIR

# Only configure the root logger if it hasn't been set up yet
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler("bot_utils.log"),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

def mention_user(user: User) -> str:
    """
    Creates a clickable mention for a Telegram user with fallback handling.

    Args:
        user: Telegram User object

    Returns:
        str: Markdown-formatted user mention
    """
    try:
        name = user.first_name or "User"
        return f"[{name}](tg://user?id={user.id})"
    except Exception as e:
        logger.error(f"Failed to create user mention: {e}", exc_info=True)
        return "User"

def clean_media_folder() -> bool:
    """
    Cleans the media directory and ensures it exists.

    Returns:
        bool: True if operation succeeded, False otherwise
    """
    try:
        if not os.path.exists(MEDIA_DIR):
            os.makedirs(MEDIA_DIR, exist_ok=True)
            logger.info(f"Created media directory: {MEDIA_DIR}")
            return True

        for filename in os.listdir(MEDIA_DIR):
            file_path = os.path.join(MEDIA_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

        logger.info(f"Cleaned media directory: {MEDIA_DIR}")
        return True

    except Exception as e:
        logger.error(f"Failed to clean media folder: {e}", exc_info=True)
        return False

def log_message(update: Update, nsfw_category: Optional[str] = None) -> None:
    """
    Logs message details including NSFW classification if provided.

    Args:
        update: Telegram Update object
        nsfw_category: Optional NSFW classification category
    """
    try:
        if not update or not update.message:
            logger.warning("Invalid update object in log_message")
            return

        user = update.message.from_user
        chat = update.message.chat
        content_type = (
            type(update.message.effective_attachment).__name__
            if hasattr(update.message, "effective_attachment") and update.message.effective_attachment
            else "Unknown"
        )

        log_data = {
            "user_id": user.id if user else None,
            "username": user.username if user else None,
            "chat_id": chat.id if chat else None,
            "chat_type": chat.type if chat else None,
            "content_type": content_type,
            "nsfw_category": nsfw_category or "Safe",
            "message": update.message.text or "[media message]"
        }

        logger.info(
            "Message received - "
            f"User: {log_data['user_id']} (@{log_data['username']}) | "
            f"Chat: {log_data['chat_id']} ({log_data['chat_type']}) | "
            f"Type: {log_data['content_type']} | "
            f"NSFW: {log_data['nsfw_category']}"
        )

    except Exception as e:
        logger.error(f"Failed to log message: {e}", exc_info=True)

def get_media_path(user_id: int, file_id: str) -> str:
    """
    Generates a standardized media file path.

    Args:
        user_id: Telegram user ID
        file_id: Telegram file ID

    Returns:
        str: Full path to the media file
    """
    try:
        return os.path.join(MEDIA_DIR, f"{user_id}_{file_id}")
    except Exception as e:
        logger.error(f"Failed to generate media path: {e}", exc_info=True)
        raise
