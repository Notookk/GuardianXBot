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

from typing import Optional, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import CallbackContext
from telegram.error import BadRequest

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
#---------------------------------<>---------------------------------------#
def escape_md(text: str) -> str:
    """Escape all Telegram MarkdownV2 reserved characters, including '.' in floats."""
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    import re
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', str(text))

def escape_md_template(text: str) -> str:
    """Escape all Telegram MarkdownV2 reserved characters for static lines."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    import re
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', str(text))
#---------------------------------<>---------------------------------------#    

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
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat_id = update.message.chat_id

    try:
        if user.id == OWNER_ID or await is_approved(user.id):
            return
    except Exception as e:
        logger.error(f"Failed to check approval status: {e}", exc_info=True)
        return

    original_path: Optional[str] = None
    processed_path: Optional[str] = None

    try:
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

        original_path = os.path.join(MEDIA_DIR, f"{user.id}_{file.file_id}{file_extension}")
        file_obj = await context.bot.get_file(file.file_id)
        await file_obj.download_to_drive(original_path)

        if not os.path.exists(original_path):
            logger.error(f"Download failed: {original_path}")
            await update.message.reply_text("❌ Failed to download media.")
            return

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
                parse_mode="Markdown"
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
                parse_mode="Markdown"
            )
        except BadRequest as e:
            if "Button_user_privacy_restricted" in str(e):
                await context.bot.send_message(
                    ALERT_CHANNEL_ID,
                    admin_alert,
                    parse_mode="Markdown"
                )
            else:
                logger.error(f"Admin alert failed: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Violation handling failed: {e}", exc_info=True)

def escape_markdown(text: str) -> str:
    if not text:
        return ""
    for ch in ('_', '*', '[', '`'):
        text = text.replace(ch, f'\\{ch}')
    return text

def format_user_alert(user, result: Dict[str, float]) -> str:
    name = escape_markdown(user.first_name or 'None')
    username = escape_markdown(user.username or 'None')
    user_id = user.id

    return f"""
╭─────────────────
╰──● NSFW DETECTED 🔞
╭✠╼━━━━━━❖━━━━━━━✠╮ 
│➺ Name: {name}
│➺ Username: @{username if user.username else 'None'}
│➺ User ID: {user_id}
│➺ Details:
│➺ Drawings: {result.get('drawings', 0):.2f}
│➺ Neutral: {result.get('neutral', 0):.2f}
│➺ Porn: {result.get('porn', 0):.2f}
│➺ Hentai: {result.get('hentai', 0):.2f}
│➺ Sexy: {result.get('sexy', 0):.2f}
╰✠╼━━━━━━❖━━━━━━━✠╯
""".strip()

def format_admin_alert(user: User, result: Dict[str, float], chat_id: int, update: Update) -> str:
    """Format the admin alert message"""
    return f"""
🚨 NSFW DETECTED 🔞

Name: {user.first_name or 'None'}
Username: @{user.username or 'None'}
User ID: {user.id}

Detection Scores:
Drawings: {result.get('drawings', 0):.2f}
Neutral: {result.get('neutral', 0):.2f}
Porn: {result.get('porn', 0):.2f}
Hentai: {result.get('hentai', 0):.2f}
Sexy: {result.get('sexy', 0):.2f}

Chat ID: {chat_id}
Message ID: {update.message.message_id if update.message else 'N/A'}"""

def format_admin_alert(user: User, result: Dict[str, float], chat_id: int, update: Update) -> str:
    first_name = escape_md(user.first_name)
    last_name = escape_md(user.last_name) if user.last_name else ""
    username = f"@{escape_md(user.username)}" if user.username else "None"
    def escnum(val):
        return escape_md(f"{val:.2f}")

    lines = [
        "🚨 NSFW DETECTED 🔞",
        "",
        f"User: {escape_md(str(user.id))}",
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
        f"Chat ID: {escape_md(str(chat_id))}",
        f"Message ID: {escape_md(str(update.message.message_id)) if update.message else 'N/A'}"
    ]
    # Escape all lines
    lines = [escape_md_template(line) for line in lines]
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
        response = "📊 *Your Violation History*\n"
        for v in violations:
            cat = v.get("category", "Unknown")
            count = v.get("count", 0)
            last = v.get("last_updated")
            if last:
                response += f"🔸 {cat}: {count} times (last: {str(last).split()[0]})\n"
            else:
                response += f"🔸 {cat}: {count} times\n"
        response = response.strip()
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

        response = f"📊 *Violation History for {user_id}*\n"
        for v in violations:
            cat = v.get("category", "Unknown")
            count = v.get("count", 0)
            last = v.get("last_updated")
            if last:
                response += f"🔸 {cat}: {count} times (last: {str(last).split()[0]})\n"
            else:
                response += f"🔸 {cat}: {count} times\n"
        response = response.strip()
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
