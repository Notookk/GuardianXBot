import random
import asyncio
import logging
from database.mongodb import add_user_if_new, user_exists, record_bot_start, record_group_join
from telegram import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    InputMediaPhoto, 
    InputMediaVideo, 
    Update,
    Bot,
    Chat
)
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, CallbackContext
)
from telegram.helpers import escape_markdown

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import re
SUPPORT_GROUP_ID = -1002240372506  # replace with your support group ID
from telegram.constants import ParseMode
from html import escape as escape_html

async def notify_support_group(bot: Bot, user, context_type: str, chat: Chat = None):
    """Notify support group when someone starts bot or adds bot to group"""
    if context_type == "private":
        message = (
            f"#started_users"
            f"🚀 <b>New User Started Bot</b>\n"
            f"• User: {user.mention_html()}\n"
            f"• ID: <code>{user.id}</code>\n"
            f"• Username: @{user.username if user.username else 'N/A'}\n"
            f"• Name: {escape_html(user.full_name)}"
        )
    elif context_type == "group" and chat:
        message = (
            f"#added_group"
            f"👥 <b>Bot Added to Group</b>\n"
            f"• By: {user.mention_html()}\n"
            f"• User ID: <code>{user.id}</code>\n"
            f"• Group: {escape_html(chat.title)}\n"
            f"• Group ID: <code>{chat.id}</code>"
        )
    else:
        return

    try:
        await bot.send_message(chat_id=SUPPORT_GROUP_ID, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Failed to notify support group: {e}")

def escape_md(text: str) -> str:
    """Properly escapes all MarkdownV2 special characters"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([\\' + re.escape(escape_chars) + r'])', r'\\\1', text)

# Constants
VIDEOS = [
    "https://new6.edithxbase.eu.org/105726/free2-7875192045",
    "https://new6.edithxbase.eu.org/105730/free2-7875192045",
    "https://new6.edithxbase.eu.org/105717/free6-7875192045",
]

OWNER_LINK = "https://t.me/xazoc"
OWNER_IMAGE = "https://files.catbox.moe/0jb630.jpg"

MESSAGES = {
    "start": (
        "𝐓ʜɪs ɪs [˹ɢᴜᴀʀᴅɪᴀɴ ✗ ʙᴏᴛ˼](https://t.me/GuardianX_Robot) 🤍\n"
        "➻ 𝐀 𝐅ᴀsᴛ & 𝐏ᴏᴡᴇʀғᴜʟ 𝐓ᴇʟᴇɢʀᴀᴍ 𝐒ᴇᴄᴜʀɪᴛʏ 𝐁ᴏᴛ\n"
        "𝐅ᴀsᴛ 𝐍sғᴡ 𝐌ᴏᴅᴇʟ ɪɴsᴛᴀʟʟᴇᴅ 𝐇ᴇʟᴩs 𝐓ᴏ 𝐏ʀᴏᴛᴇᴄᴛ 𝐘ᴏᴜʀ 𝐆ʀᴏᴜᴘ\n"
        "──────────────────\n"
        "๏ 𝐂ʟɪᴄᴋ ᴛʜᴇ 𝐇ᴇʟᴘ ʙᴜᴛᴛᴏɴ ғᴏʀ ᴄᴏᴍᴍᴀɴᴅs"
    ),
    "help": (
        f"{escape_md('💫 𝐇ᴇʀᴇ ᴀʀᴇ sᴏᴍᴇ ᴄᴏᴍᴍᴀɴᴅs:')}\n\n"
        f"{escape_md('● 𝐓ʜɪs ʙᴏᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴅᴇʟᴇᴛᴇs ɴsғᴡ 18+ ᴄᴏɴᴛᴇɴᴛ 🍃')}\n"
        f"{escape_md('● 𝐈ғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴀᴅᴅ ʏᴏᴜʀsᴇʟғ ᴀs sᴜᴅᴏ, 𝐃𝐌 - ')}"
        f"[{escape_md('xazoc')}](https://t.me/xazoc)"
        f"{escape_md(' 💛')}\n"
        f"{escape_md('● 𝐓ʜᴇʀᴇ ɪs ɴᴏ ᴅɪʀᴇᴄᴛ ᴄᴏᴍᴍᴀɴᴅ')}\n"
        f"\\#𝐒ᴀфᴇ ᴇᴄᴏ🍃 \\#𝐗ᴏᴛɪᴋ❤️‍🔥"
    ),
    "owner": (
        f"{escape_md('╭─⎋ 𝐎𝐰𝐧𝐞𝐫 𝐈𝐧𝐟𝐨𝐫𝐦𝐚𝐭𝐢𝐨𝐧 ❏')}\n"
        f"{escape_md('│')} 💫 {escape_md('ᴍʏ ᴄʀᴇᴀᴛᴏʀ & ɢᴜɪᴅᴇ ɪs ʜᴇʀᴇ!')}\n"
        f"{escape_md('│')} 💫 {escape_md('ʜᴀᴠᴇ ǫᴜᴇʀɪᴇs ᴏʀ ɴᴇᴇᴅ sᴜᴘᴘᴏʀᴛ?')}\n"
        f"{escape_md('│')} 💫 {escape_md('ғᴇᴇʟ ғʀᴇᴇ ᴛᴏ ʀᴇᴀᴄʜ ᴏᴜᴛ ᴀɴʏᴛɪᴍᴇ!')}\n"
        f"{escape_md('╰──────────────────')}\n\n"
        f"➤ 🥂 [𓍼⤹🇲 ❍‌‌ ᰻⃪᱂ ꪀ ɪ ꪀ 𝙶 𓆰🇸ʈ 𝛂 ᰻⃪᱂ 🜲\\-//\\- ❛🤍]({escape_md(OWNER_LINK)})"
    )
}

# When the bot is added to a new group
from database.mongodb import record_group_join

async def new_chat_member(update: Update, context: CallbackContext):
    print("✅ new_chat_member triggered")
    if not update.message:
        return

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Record the group join!
            await record_group_join(
                user_id=update.effective_user.id,
                group_id=update.effective_chat.id,
                group_title=update.effective_chat.title or ""
            )

            # Notify support group on bot add
            await notify_support_group(context.bot, update.effective_user, "group", update.effective_chat)
            # Send welcome in group
            await update.message.reply_video(
                video="https://new6.edithxbase.eu.org/105730/free2-7875192045",
                caption=(
                    "[˹ ɢᴜᴀʀᴅɪᴀɴ ✗ ʙᴏᴛ ˼](https://t.me/GuardianX_Robot) 𝐈s 𝐎ɴ 𝐁ᴀʙʏ 𝐉ᴜsᴛ 𝐆ᴏ 𝐁ᴀᴄᴋ 𝐓ᴏ 𝐒ɪᴛ\n"
                    "𝐋ᴇᴛ 𝐌ᴇ 𝐇ᴀɴᴅʟᴇ 𝐓ʜɪs ✨"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("˹ᴀᴅᴅ ᴍᴇ˼", url="https://t.me/GuardianX_Robot?startgroup=true"),
                        InlineKeyboardButton("˹ʜᴇʟᴘ˼", callback_data="help")
                    ]
                ])
            )
            
async def start_command(update: Update, context: CallbackContext):
    """Handles /start command with animated text and random video."""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat

    # Check if the user is new
    is_new = not await user_exists(user.id)
    await add_user_if_new(user.id)
    await record_bot_start(user.id)
    # Always notify support group
    if chat.type == "private":
        await notify_support_group(context.bot, user, "private")
    elif chat.type in ["group", "supergroup"]:
        await notify_support_group(context.bot, user, "group", chat)

    # Animated start message
    starting_msg = await message.reply_text("❤️‍🔥ᴅιиg ᴅιиg ꨄ︎ ѕтαятιиg••")
    for text in [
    "💛ᴅιиg ᴅιиg ꨄ︎ sтαятιиg•••",
    "🩵ᴅιиg ᴅιиg ꨄ︎ sтαятιиg•••••",
    "🤍ᴅιиg ᴅιиg ꨄ︎ sтαятιиg•••••••"
    ]:
        await asyncio.sleep(0.2)
        await starting_msg.edit_text(text)
    await starting_msg.delete()

    # Send video with inline buttons
    caption = f"Hey [{escape_md(user.first_name)}](tg://user?id={user.id}), 🥀\n{MESSAGES['start']}"
    await message.reply_video(
        video=random.choice(VIDEOS),
        caption=caption,
        parse_mode="MarkdownV2",
        reply_markup=get_main_keyboard()
    )

async def button_handler(update: Update, context: CallbackContext):
    """Handles inline button presses."""
    query = update.callback_query
    await query.answer()

    try:
        if query.data == "help":
            await update_message_content(
                query,
                caption=MESSAGES["help"],
                keyboard=get_help_keyboard(),
                media=None
            )

        elif query.data == "owner":
            await update_message_content(
                query,
                caption=MESSAGES["owner"],
                keyboard=get_owner_keyboard(),
                media=InputMediaPhoto(media=OWNER_IMAGE)
            )

        elif query.data == "back":
            await update_message_content(
                query,
                caption=f"Hey [{escape_md(query.from_user.first_name)}](tg://user?id={query.from_user.id}), 🥀\n{MESSAGES['start']}",
                keyboard=get_main_keyboard(),
                media=InputMediaVideo(media=random.choice(VIDEOS))
            )
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")

async def update_message_content(query, caption: str, keyboard: InlineKeyboardMarkup, media=None):
    """Helper function to update message content."""
    try:
        if media:
            await query.message.edit_media(media)
            await asyncio.sleep(0.5)  # Small delay to ensure media is processed

        await query.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Error in update_message_content: {e}")

def get_main_keyboard():
    """Returns the main inline keyboard with three buttons"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("˹ᴏᴡɴᴇʀ˼", callback_data="owner"),
            InlineKeyboardButton("˹ʜᴇʟᴘ˼", callback_data="help")
        ],
        [InlineKeyboardButton("˹ᴀᴅᴅ ᴍᴇ˼", url="https://t.me/GuardianX_Robot?startgroup=true")]
    ])

def get_help_keyboard():
    """Returns the help inline keyboard with correct layout."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("˹sᴜᴘᴘᴏʀᴛ˼", url="t.me/x_support_chat"), InlineKeyboardButton("˹ᴜᴘᴅᴀᴛᴇ˼", url="t.me/your_support_chat")],
        [InlineKeyboardButton("˹ʙᴀᴄᴋ˼", callback_data="back")],
    ])

def get_owner_keyboard():
    """Returns the owner section keyboard with correct layout."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("˹ʜᴀᴠᴇɴ˼", url="t.me/vibes_i"), InlineKeyboardButton("˹ᴀʙᴏᴜᴛ˼", url="t.me/love_mhe")],
        [InlineKeyboardButton("˹ʙᴀᴄᴋ˼", callback_data="back")],
    ])
