import os
import sys
import logging
import tempfile
import zipfile
import json
import base64
import numpy as np
from PIL import Image
import imageio
import cv2
import re

from typing import Optional, Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import CallbackContext
from telegram.error import BadRequest

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import OWNER_ID, ALERT_CHANNEL_ID, MEDIA_DIR

from database.mongodb import (
    is_approved,
    update_violations,
    add_approved_user,
    remove_approved_user,
    get_user_violations,
    get_all_users,
)
from .predict import detect_nsfw

logger = logging.getLogger(__name__)
os.makedirs(MEDIA_DIR, exist_ok=True)

def escape_md_template(text: str) -> str:
    """
    Escape MarkdownV2 reserved characters in static template lines.
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

class MediaConverter:
    @staticmethod
    def convert_webp_to_png(file_path: str) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                with Image.open(file_path) as img:
                    img.convert("RGB").save(tmp.name, "PNG")
                return tmp.name
        except Exception as e:
            logger.error(f"WebP conversion failed: {e}", exc_info=True)
            return None

    @staticmethod
    def extract_frame_from_webm(input_path: str) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                with imageio.get_reader(input_path, format="webm") as reader:
                    frame = reader.get_next_data()
                    imageio.imwrite(tmp.name, np.array(frame, dtype=np.uint8), format="JPEG")
                return tmp.name
        except Exception as e:
            logger.error(f"WEBM frame extraction failed: {e}", exc_info=True)
            return None

    @staticmethod
    def convert_tgs_to_png(file_path: str) -> Optional[str]:
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                with z.open('animation.json') as f:
                    animation_data = json.load(f)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                for asset in animation_data.get('assets', []):
                    if 'p' in asset:
                        img_data = base64.b64decode(asset['p'].split(',')[1])
                        with open(tmp.name, 'wb') as f:
                            f.write(img_data)
                        return tmp.name
                Image.new('RGB', (512, 512), (255, 255, 255)).save(tmp.name)
                return tmp.name
        except Exception as e:
            logger.error(f"TGS conversion failed: {e}", exc_info=True)
            return None

def extract_video_frame(video_path: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            vidcap = cv2.VideoCapture(video_path)
            success, image = vidcap.read()
            if success:
                cv2.imwrite(tmp.name, image)
                return tmp.name
        return None
    except Exception as e:
        logger.error(f"OpenCV frame extraction failed: {e}", exc_info=True)
        return None

async def handle_media(update: Update, context: CallbackContext) -> None:
    """Main media handling function"""
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat_id = update.message.chat_id

    try:
        # Skip for OWNER or approved user
        if user.id == OWNER_ID or await is_approved(user.id):
            return
    except Exception as e:
        logger.error(f"Failed to check approval status: {e}", exc_info=True)
        return

    original_path: Optional[str] = None
    processed_path: Optional[str] = None

    try:
        # Handle different media types
        if update.message.photo:
            file = update.message.photo[-1]
            file_extension = ".jpg"
        elif update.message.video:
            file = update.message.video
            file_extension = ".mp4"
        elif update.message.sticker:
            file = update.message.sticker
            if file.is_animated:
                file_extension = ".tgs"
            elif file.is_video:
                file_extension = ".webm"
            else:
                file_extension = ".webp"
        elif update.message.document:
            file = update.message.document
            # Only allow certain document types
            if file.mime_type and file.mime_type.startswith("image/"):
                file_extension = os.path.splitext(file.file_name)[1] if file.file_name else ".jpg"
            elif file.mime_type and file.mime_type.startswith("video/"):
                file_extension = os.path.splitext(file.file_name)[1] if file.file_name else ".mp4"
            else:
                await update.message.reply_text("❌ Unsupported document type for NSFW scanning.")
                return
        else:
            await update.message.reply_text("❌ Unsupported media type.")
            return

        if not hasattr(file, "file_id"):
            return

        # Download file
        original_path = os.path.join(MEDIA_DIR, f"{user.id}_{file.file_id}{file_extension}")
        file_obj = await context.bot.get_file(file.file_id)
        await file_obj.download_to_drive(original_path)

        if not os.path.exists(original_path):
            logger.error(f"Download failed: {original_path}")
            await update.message.reply_text("❌ Failed to download media.")
            return

        # Process based on media type
        if update.message.video:
            processed_path = extract_video_frame(original_path)
        elif update.message.sticker:
            if file.is_animated:
                processed_path = MediaConverter.convert_tgs_to_png(original_path)
            elif file.is_video:
                processed_path = MediaConverter.extract_frame_from_webm(original_path)
            else:
                processed_path = MediaConverter.convert_webp_to_png(original_path)
        else:
            processed_path = original_path

        if not processed_path or not os.path.exists(processed_path):
            logger.error(f"Processing failed for {original_path}")
            await update.message.reply_text("❌ Failed to process media for NSFW scan.")
            return

        # NSFW Detection (assume sync, change to 'await' if async)
        result = detect_nsfw(processed_path)
        if not result:
            logger.info("No NSFW content detected")
            return

        max_category = max(result, key=result.get)
        if max_category in ["porn", "sexy", "hentai"]:
            await handle_nsfw_violation(update, context, user, chat_id, result, max_category)

    except Exception as e:
        logger.error(f"Media handling error: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred during NSFW scanning.")
    finally:
        # Cleanup files
        for path in [original_path, processed_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Cleanup failed for {path}: {e}", exc_info=True)

async def handle_nsfw_violation(
    update: Update,
    context: CallbackContext,
    user: User,
    chat_id: int,
    result: Dict[str, float],
    max_category: str,
) -> None:
    """Handle NSFW violation with proper error handling"""
    try:
        try:
            await update.message.delete()
        except BadRequest as e:
            logger.warning(f"Couldn't delete message: {e}", exc_info=True)

        await update_violations(user.id, max_category)

        user_alert = format_user_alert(user, result)
        admin_alert = format_admin_alert(user, result, chat_id, update)

        try:
            await context.bot.send_message(
                chat_id,
                user_alert,
                parse_mode="MarkdownV2"
            )
        except BadRequest as e:
            logger.warning(f"Couldn't send user alert: {e}", exc_info=True)

        try:
            await context.bot.send_message(
                ALERT_CHANNEL_ID,
                admin_alert,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👤 View Profile", url=f"tg://user?id={user.id}")]
                ]),
                parse_mode="MarkdownV2"
            )
        except BadRequest as e:
            if "Button_user_privacy_restricted" in str(e):
                await context.bot.send_message(
                    ALERT_CHANNEL_ID,
                    admin_alert,
                    parse_mode="MarkdownV2"
                )
            else:
                logger.error(f"Admin alert failed: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Violation handling failed: {e}", exc_info=True)

def format_user_alert(user, result):
    """
    Format the user alert message for Telegram MarkdownV2.
    Name (mention), then username, then id.
    User fields and numbers are safely escaped for MarkdownV2.
    """
    first_name = escape_md(user.first_name)
    username = f"@{escape_md(user.username)}" if user.username else "None"
    user_id = str(user.id)
    mention = f"[{first_name}](tg://user?id={user.id})"

    def escnum(val):
        return escape_md(f"{val:.2f}")

    msg = (
        "╭─────────────────\n"
        "╰──●𝙽𝚂𝙵𝚆 𝙳𝙴𝚃𝙴𝙲𝚃𝙴𝙳 🔞\n"
        "╭✠╼━━━━━━❖━━━━━━━✠╮ \n"
        f"│➺𝙽𝚊𝚖𝚎: {mention}\n"
        f"│➺𝚄𝚜𝚎𝚛𝚗𝚊𝚖𝚎: {username}\n"
        f"│➺𝚄𝚜𝚎𝚛: {user_id}\n"
        "│➺𝙳𝚎𝚝𝚊𝚒𝚕𝚜:\n"
        f"│➺𝙳𝚛𝚊𝚠𝚒𝚗𝚐𝚜: {escnum(result.get('drawings', 0))}\n"
        f"│➺𝙽𝚎𝚞𝚝𝚛𝚊𝚕: {escnum(result.get('neutral', 0))}\n"
        f"│➺𝙿𝚘𝚛𝚗: {escnum(result.get('porn', 0))}\n"
        f"│➺𝙷𝚎𝚗𝚝𝚊𝚒: {escnum(result.get('hentai', 0))}\n"
        f"│➺𝚂𝚎𝚡𝚢: {escnum(result.get('sexy', 0))}\n"
        "╰✠╼━━━━━━❖━━━━━━━✠╯"
    )
    return msg

def format_admin_alert(user: User, result: Dict[str, float], chat_id: int, update: Update) -> str:
    first_name = escape_md(user.first_name)
    last_name = escape_md(user.last_name) if user.last_name else ""
    username = f"@{escape_md(user.username)}" if user.username else "None"
    def escnum(val):
        return escape_md(f"{val:.2f}")

    lines = [
        "🚨 NSFW DETECTED 🔞",
        "",
        f"User: {user.id}",
        f"Username: {username}",
        f"First Name: {first_name}",
        f"Last Name: {last_name}",
        "",
        "Detection Scores:",
        f"Drawings: {escnum(result.get('drawings', 0))}",
        f"Neutral: {escnum(result.get('neutral', 0))}",
        f"Porn: {escnum(result.get('porn', 0))}",
        f"Hentai: {escnum(result.get('hentai', 0))}",
        f"Sexy: {escnum(result.get('sexy', 0))}",
        "",
        f"Chat ID: {chat_id}",
        f"Message ID: {str(update.message.message_id) if update.message else 'N/A'}"
    ]
    # Escape all lines EXCEPT those containing [markdown links](...)!
    lines = [escape_md_template(line) if not ("[" in line and "](" in line) else line for line in lines]
    return '\n'.join(lines)


async def add_approved(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("» ᴀᴡᴡ, ᴛʜɪs ɪs ɴᴏᴛ ғᴏʀ ʏᴏᴜ ʙᴀʙʏ.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /approve <user_id>")
        return

    try:
        user_id = int(context.args[0])
        await add_approved_user(user_id, update.message.from_user.id)
        await update.message.reply_text(f"✅ User {user_id} added to approved list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")

async def remove_approved(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("» ᴀᴡᴡ, ᴛʜɪs ɪs ɴᴏᴛ ғᴏʀ ʏᴏᴜ ʙᴀʙʏ.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /remove <user_id>")
        return

    try:
        user_id = int(context.args[0])
        await remove_approved_user(user_id)
        await update.message.reply_text(f"❌ User {user_id} removed from approved list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")

async def my_info(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    violations = await get_user_violations(user_id)

    if not violations:
        await update.message.reply_text("✅ You have a clean record.")
        return

    try:
        if len(violations[0]) == 3:
            response = "📊 *Your Violation History*\n" + "\n".join(
                f"🔸 {cat}: {count} times (last: {str(timestamp).split()[0]})"
                for cat, count, timestamp in violations
            )
        elif len(violations[0]) == 2:
            response = "📊 *Your Violation History*\n" + "\n".join(
                f"🔸 {cat}: {count} times"
                for cat, count in violations
            )
        else:
            response = "📊 *Your Violation History*\n" + "\n".join(
                f"🔸 {str(violation)}"
                for violation in violations
            )
        await update.message.reply_text(escape_md(response), parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Error formatting violations: {e}", exc_info=True)
        await update.message.reply_text("❌ Could not retrieve violation history.")

async def user_info(update: Update, context: CallbackContext) -> None:
    if not context.args:
        return await my_info(update, context)

    try:
        user_id = int(context.args[0])
        violations = await get_user_violations(user_id)

        if not violations:
            await update.message.reply_text(f"✅ User {user_id} has no violations.")
            return

        if len(violations[0]) == 3:
            response = f"📊 *Violation History for {user_id}*\n" + "\n".join(
                f"🔸 {cat}: {count} times (last: {str(timestamp).split()[0]})"
                for cat, count, timestamp in violations
            )
        elif len(violations[0]) == 2:
            response = f"📊 *Violation History for {user_id}*\n" + "\n".join(
                f"🔸 {cat}: {count} times"
                for cat, count in violations
            )
        else:
            response = f"📊 *Violation History for {user_id}*\n" + "\n".join(
                f"🔸 {str(violation)}"
                for violation in violations
            )
        await update.message.reply_text(escape_md(response), parse_mode="MarkdownV2")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error in user_info: {e}", exc_info=True)
        await update.message.reply_text("❌ Could not retrieve user's violation history.")

async def get_approved_users_list(update: Update, context: CallbackContext) -> None:
    approved_users = await get_all_users()
    if not approved_users:
        await update.message.reply_text("❌ No approved users found.")
        return

    response = (
        "✨ *Approved Users* ✨\n"
        "╭✠╼━━━━━━❖━━━━━━━✠╮\n"
    )

    for user in approved_users:
        try:
            chat = await context.bot.get_chat(user['user_id'])
            username = f"@{chat.username}" if chat.username else f"ID: {user['user_id']}"
            response += f"\n{user['user_id']} - {username} (Added: {user['date_added']})"
        except Exception as e:
            logger.warning(f"Couldn't fetch user {user['user_id']}: {e}", exc_info=True)
            response += f"\n{user['user_id']} - [Unknown User] (Added: {user['date_added']})"

    response += (
        "\n╰✠╼━━━━━━❖━━━━━━━✠╯\n"
        f"💫 Total Approved: {len(approved_users)}"
    )
    await update.message.reply_text(escape_md(response), parse_mode="MarkdownV2")
