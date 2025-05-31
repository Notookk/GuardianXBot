import asyncio
import logging
from typing import List

from telegram import Update, Chat
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from database.mongodb import get_recipients_for_broadcast

logger = logging.getLogger(__name__)

# --- SUDO USER MANAGEMENT ---
try:
    from config import SUDO_USERS
except ImportError:
    SUDO_USERS = [7875192045]  # Replace with your own Telegram user IDs

async def get_broadcast_recipients() -> List[int]:
    """
    Fetch all user_ids who have started the bot.
    """
    return await get_recipients_for_broadcast("all")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Telegram command handler for /broad, only for SUDO users.
    Broadcasts the replied-to message to all users/groups known to the bot.
    Shows progress and logs results.
    """
    user_id = update.effective_user.id

    # Sudo check
    if user_id not in SUDO_USERS:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    # Must reply to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("📌 Please reply to the message you want to broadcast.")
        return

    msg = await update.message.reply_text("📣 Broadcasting started...")

    message_to_forward = update.message.reply_to_message
    recipients = await get_broadcast_recipients()

    if not recipients:
        await msg.edit_text("⚠️ No users found to broadcast to.")
        return

    success, failed, pinned = 0, 0, 0

    for idx, uid in enumerate(recipients, 1):
        try:
            # Forward the message
            forwarded = await context.bot.forward_message(
                chat_id=uid,
                from_chat_id=message_to_forward.chat_id,
                message_id=message_to_forward.message_id
            )
            success += 1

            # Attempt to pin if this is a group or supergroup
            try:
                chat: Chat = await context.bot.get_chat(uid)
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    await context.bot.pin_chat_message(
                        chat_id=uid,
                        message_id=forwarded.message_id,
                        disable_notification=True
                    )
                    pinned += 1
            except Exception as e:
                logger.info(f"Could not pin message in chat {uid}: {e}")

        except Exception as e:
            failed += 1
            logger.warning(f"Failed to forward to {uid}: {e}")

        # Progress update for large broadcasts
        if idx % 100 == 0 or idx == len(recipients):
            try:
                await msg.edit_text(
                    f"📣 Broadcasting...\n"
                    f"✅ Delivered: {success}\n"
                    f"❌ Failed: {failed}\n"
                    f"📌 Pinned: {pinned}\n"
                    f"Progress: {idx}/{len(recipients)}"
                )
            except Exception as e:
                logger.debug(f"Could not update progress message: {e}")

        # Rate limiting: adjust as needed to avoid Telegram flood limits
        await asyncio.sleep(0.1)

    # Final status message
    await msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n"
        f"📨 <b>Delivered:</b> {success}\n"
        f"❌ <b>Failed:</b> {failed}\n"
        f"📌 <b>Pinned in groups:</b> {pinned}",
        parse_mode="HTML"
    )
