import os
import logging
import tempfile
import zipfile
import json
import base64
import sys
import numpy as np
from PIL import Image
import imageio
from typing import Optional, Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ContextTypes,
)
from telegram.error import BadRequest

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Local imports
from config import TOKEN, OWNER_ID, ALERT_CHANNEL_ID, MEDIA_DIR
from database import (
    Database,
    is_approved,
    update_violations,
    add_approved_user,
    remove_approved_user,
    get_user_violations,
    get_all_users,
)
from .predict import detect_nsfw

# Initialize database and media directory
db = Database()
os.makedirs(MEDIA_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("nsfw_bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

class MediaConverter:
    @staticmethod
    def convert_webp_to_png(file_path: str) -> Optional[str]:
        """Convert WebP to PNG"""
        try:
            png_path = f"{tempfile.mktemp()}.png"
            with Image.open(file_path) as img:
                img.convert("RGB").save(png_path, "PNG")
            return png_path
        except Exception as e:
            logger.error(f"WebP conversion failed: {e}", exc_info=True)
            return None

    @staticmethod
    def extract_frame_from_webm(input_path: str) -> Optional[str]:
        """Extract frame from WebM"""
        try:
            output_path = f"{tempfile.mktemp()}.jpg"
            with imageio.get_reader(input_path, format="webm") as reader:
                frame = reader.get_next_data()
                imageio.imwrite(output_path, np.array(frame, dtype=np.uint8), format="JPEG")
            return output_path
        except Exception as e:
            logger.error(f"WEBM frame extraction failed: {e}", exc_info=True)
            return None

    @staticmethod
    def convert_tgs_to_png(file_path: str) -> Optional[str]:
        """Convert TGS to PNG using pure Python"""
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                with z.open('animation.json') as f:
                    animation_data = json.load(f)
            
            output_path = f"{tempfile.mktemp()}.png"
            
            for asset in animation_data.get('assets', []):
                if 'p' in asset:
                    img_data = base64.b64decode(asset['p'].split(',')[1])
                    with open(output_path, 'wb') as f:
                        f.write(img_data)
                    return output_path
            
            Image.new('RGB', (512, 512), (255, 255, 255)).save(output_path)
            return output_path
            
        except Exception as e:
            logger.error(f"TGS conversion failed: {e}", exc_info=True)
            return None

import cv2

def extract_video_frame(video_path: str) -> Optional[str]:
    try:
        output_path = f"{tempfile.mktemp()}.jpg"
        vidcap = cv2.VideoCapture(video_path)
        success, image = vidcap.read()
        if success:
            cv2.imwrite(output_path, image)
            return output_path
        return None
    except Exception as e:
        logger.error(f"OpenCV frame extraction failed: {e}")
        return None

async def handle_media(update: Update, context: CallbackContext) -> None:
    """Main media handling function"""
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat_id = update.message.chat_id

    if user.id == OWNER_ID:
        return

    if await is_approved(user.id):
        return

    original_path = None
    processed_path = None
    
    try:
        # Handle different media types
        if update.message.photo:
            file = update.message.photo[-1]  # Get highest resolution
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
            file_extension = os.path.splitext(file.file_name)[1] if file.file_name else ""
        else:
            return  # Unsupported media type

        if not hasattr(file, "file_id"):
            return

        # Download file
        file_obj = await context.bot.get_file(file.file_id)
        original_path = os.path.join(MEDIA_DIR, f"{user.id}_{file.file_id}{file_extension}")
        await file_obj.download_to_drive(original_path)

        if not os.path.exists(original_path):
            logger.error(f"Download failed: {original_path}")
            return

        # Process based on media type
        if update.message.video:
            # Extract frame from video
            processed_path = extract_video_frame(original_path)
        elif update.message.sticker:
            if file.is_animated:
                processed_path = MediaConverter.convert_tgs_to_png(original_path)
            elif file.is_video:
                processed_path = MediaConverter.extract_frame_from_webm(original_path)
            else:
                processed_path = MediaConverter.convert_webp_to_png(original_path)
        else:
            # For photos and documents, use the original file
            processed_path = original_path

        if not processed_path or not os.path.exists(processed_path):
            logger.error(f"Processing failed for {original_path}")
            return

        # NSFW Detection
        result = detect_nsfw(processed_path)
        if not result:
            logger.info("No NSFW content detected")
            return

        max_category = max(result, key=result.get)
        if max_category in ["porn", "sexy", "hentai"]:
            await handle_nsfw_violation(update, context, user, chat_id, result, max_category)

    except Exception as e:
        logger.error(f"Media handling error: {e}", exc_info=True)
    finally:
        # Cleanup files
        for path in [original_path, processed_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Cleanup failed for {path}: {e}")

async def handle_nsfw_violation(
    update: Update,
    context: CallbackContext,
    user,
    chat_id: int,
    result: Dict[str, float],
    max_category: str,
) -> None:
    """Handle NSFW violation with proper error handling"""
    try:
        try:
            await update.message.delete()
        except BadRequest as e:
            logger.warning(f"Couldn't delete message: {e}")

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
            logger.warning(f"Couldn't send user alert: {e}")

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
                raise

    except Exception as e:
        logger.error(f"Violation handling failed: {e}", exc_info=True)

def format_user_alert(user, result: Dict[str, float]) -> str:
    """Format the user alert message"""
    return f"""
╭─────────────────
╰──●𝙽𝚂𝙵𝚆 𝙳𝙴𝚃𝙴𝙲𝚃𝙴𝙳 🔞
╭✠╼━━━━━━❖━━━━━━━✠╮ 
│➺𝚄𝚜𝚎𝚛: {user.id}
│➺𝚄𝚜𝚎𝚛𝚗𝚊𝚖𝚎: @{user.username or 'None'}
│➺𝙳𝚎𝚝𝚊𝚒𝚕𝚜:
│➺𝙳𝚛𝚊𝚠𝚒𝚗𝚐𝚜: {result.get('drawings', 0):.2f}
│➺𝙽𝚎𝚞𝚝𝚛𝚊𝚕: {result.get('neutral', 0):.2f}
│➺𝙿𝚘𝚛𝚗: {result.get('porn', 0):.2f}
│➺𝙷𝚎𝚗𝚝𝚊𝚒: {result.get('hentai', 0):.2f}
│➺𝚂𝚎𝚡𝚢: {result.get('sexy', 0):.2f}
╰✠╼━━━━━━❖━━━━━━━✠╯"""

def format_admin_alert(user, result: Dict[str, float], chat_id: int, update: Update) -> str:
    """Format the admin alert message"""
    return f"""
🚨 NSFW DETECTED 🔞

User: {user.id}
Username: @{user.username or 'None'}
First Name: {user.first_name or 'None'}
Last Name: {user.last_name or 'None'}

Detection Scores:
Drawings: {result.get('drawings', 0):.2f}
Neutral: {result.get('neutral', 0):.2f}
Porn: {result.get('porn', 0):.2f}
Hentai: {result.get('hentai', 0):.2f}
Sexy: {result.get('sexy', 0):.2f}

Chat ID: {chat_id}
Message ID: {update.message.message_id if update.message else 'N/A'}"""

async def add_approved(update: Update, context: CallbackContext) -> None:
    """Add user to approved list"""
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
    """Remove user from approved list"""
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
    """Show user's violation history"""
    user_id = update.message.from_user.id
    violations = await get_user_violations(user_id)

    if not violations:
        await update.message.reply_text("✅ You have a clean record.")
        return

    try:
        # Handle different violation data structures
        if len(violations[0]) == 3:  # (category, count, timestamp)
            response = "📊 **Your Violation History**\n" + "\n".join(
                f"🔸 {cat}: {count} times (last: {timestamp.split()[0]})" 
                for cat, count, timestamp in violations
            )
        elif len(violations[0]) == 2:  # (category, count)
            response = "📊 **Your Violation History**\n" + "\n".join(
                f"🔸 {cat}: {count} times" 
                for cat, count in violations
            )
        else:
            response = "📊 **Your Violation History**\n" + "\n".join(
                f"🔸 {str(violation)}" 
                for violation in violations
            )
        
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error formatting violations: {e}")
        await update.message.reply_text("❌ Could not retrieve violation history.")

async def user_info(update: Update, context: CallbackContext) -> None:
    """Show another user's violation history"""
    if not context.args:
        return await my_info(update, context)

    try:
        user_id = int(context.args[0])
        violations = await get_user_violations(user_id)

        if not violations:
            await update.message.reply_text(f"✅ User {user_id} has no violations.")
            return

        # Handle different violation data structures
        if len(violations[0]) == 3:  # (category, count, timestamp)
            response = f"📊 **Violation History for {user_id}**\n" + "\n".join(
                f"🔸 {cat}: {count} times (last: {timestamp.split()[0]})" 
                for cat, count, timestamp in violations
            )
        elif len(violations[0]) == 2:  # (category, count)
            response = f"📊 **Violation History for {user_id}**\n" + "\n".join(
                f"🔸 {cat}: {count} times" 
                for cat, count in violations
            )
        else:
            response = f"📊 **Violation History for {user_id}**\n" + "\n".join(
                f"🔸 {str(violation)}" 
                for violation in violations
            )

        await update.message.reply_text(response, parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error in user_info: {e}")
        await update.message.reply_text("❌ Could not retrieve user's violation history.")

async def get_approved_users_list(update: Update, context: CallbackContext) -> None:
    """List all approved users"""
    approved_users = await get_all_users()
    if not approved_users:
        await update.message.reply_text("❌ No approved users found.")
        return

    response = (
        "✨ **Approved Users** ✨\n"
        "╭✠╼━━━━━━❖━━━━━━━✠╮\n"
    )
    
    for user in approved_users:
        try:
            chat = await context.bot.get_chat(user['user_id'])
            username = f"@{chat.username}" if chat.username else f"ID: {user['user_id']}"
            response += f"\n{user['user_id']} - {username} (Added: {user['date_added']})"
        except Exception as e:
            logger.warning(f"Couldn't fetch user {user['user_id']}: {e}")
            response += f"\n{user['user_id']} - [Unknown User] (Added: {user['date_added']})"

    response += (
        "\n╰✠╼━━━━━━❖━━━━━━━✠╯\n"
        f"💫 Total Approved: {len(approved_users)}"
    )
    await update.message.reply_text(response, parse_mode="Markdown")