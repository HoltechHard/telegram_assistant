import logging
import re
from typing import Optional
from settings.config import AppConfig
from managers.subscriber_manager import get_subscriber_manager
from rag.channel_context import get_channel_context_manager
from utils import shared

logger = logging.getLogger(__name__)

def escape_markdown(text: str) -> str:
    """
    Escape special characters for Telegram Markdown V2.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    result = ""
    for char in text:
        if char in escape_chars:
            result += f"\\{char}"
        else:
            result += char
    return result

def prepare_llm_response(text: str) -> str:
    """
    Prepare an LLM response for Telegram MarkdownV2.
    Converts **bold** markers to MarkdownV2 *bold*, then escapes all
    other special characters.
    """
    result = ""
    # Split on **...** patterns so we can handle them separately
    parts = re.split(r'\*\*(.*?)\*\*', text)
    # parts alternates: plain, bold, plain, bold, ...
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Regular text: escape all special chars for MarkdownV2
            result += escape_markdown(part)
        else:
            # Bold text: escape the content, then wrap in *...*
            result += f"*{escape_markdown(part)}*"
    return result

def is_owner(user_id: int, username: Optional[str], config: AppConfig) -> bool:
    """Check if the user is the channel owner."""
    owner_username = config.telegram.owner_username
    if shared.owner_user_id and user_id == shared.owner_user_id:
        return True
    if username and owner_username:
        normalized_username = f"@{username}" if not username.startswith("@") else username
        return normalized_username.lower() == owner_username.lower()
    return False

def get_context_for_query() -> str:
    """Get the channel context for a user query."""
    context_manager = get_channel_context_manager()
    if context_manager:
        context_str = context_manager.get_context_string()
        logger.info(
            f"Context for query: {len(context_str)} chars, "
            f"{context_manager.get_message_count()} messages"
        )
        return context_str
    logger.warning("No channel context manager available!")
    return "No channel context available."

async def register_user_subscriber(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str]
) -> None:
    """Register a user as a subscriber when they interact with the bot."""
    subscriber_manager = get_subscriber_manager()
    await subscriber_manager.register_subscriber(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
