from telegram import Update, Chat
from telegram.constants import ChatType
from telegram.ext import ContextTypes
import asyncio
from database import db, Database

# Replace this with your own SUDO_USERS list or database check
SUDO_USERS = [7875192045]  # Add your Telegram user ID(s) here


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if user is sudo
    if user_id not in SUDO_USERS:
        return await update.message.reply_text("🚫 You are not authorized to use this command.")

    # Ensure the command is used as a reply to the message to forward
    if not update.message.reply_to_message:
        return await update.message.reply_text("📌 Please reply to the message you want to broadcast.")

    msg = await update.message.reply_text("📣 Broadcasting started...")

    message_to_forward = update.message.reply_to_message

    # Fetch all user IDs (users + groups)
    users = await db._execute("SELECT user_id FROM users")

    success, failed, pinned = 0, 0, 0

    for (uid,) in users:
        try:
            # Forward the message
            forwarded = await context.bot.forward_message(
                chat_id=uid,
                from_chat_id=message_to_forward.chat_id,
                message_id=message_to_forward.message_id
            )
            success += 1

            # Try to pin if it's a group
            try:
                chat: Chat = await context.bot.get_chat(uid)
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    await context.bot.pin_chat_message(
                        chat_id=uid,
                        message_id=forwarded.message_id,
                        disable_notification=True
                    )
                    pinned += 1
            except:
                pass  # Skip if not group or no permission

        except Exception as e:
            failed += 1

        # Optional: slow down to avoid flooding
        await asyncio.sleep(0.05)

    # Final status message
    await msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n"
        f"📨 <b>Delivered:</b> {success}\n"
        f"❌ <b>Failed:</b> {failed}\n"
        f"📌 <b>Pinned in groups:</b> {pinned}",
        parse_mode="HTML"
    )
