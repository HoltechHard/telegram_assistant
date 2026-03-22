import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from settings.config import get_config
from rag.channel_context import get_channel_context_manager
from managers.category_manager import create_category_keyboard
from utils import shared
from utils.helper_functionals import (
    register_user_subscriber, 
    escape_markdown
)

logger = logging.getLogger(__name__)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle new posts in the channel.
    1. Store the message in local context storage (for RAG)
    2. Schedule broadcast for owner messages
    """
    if not update.channel_post:
        return

    config = get_config()
    message = update.channel_post

    channel_id = str(message.chat_id)
    expected_channel_id = config.telegram.channel_id

    if expected_channel_id.startswith("@"):
        chat_username = message.chat.username
        if chat_username:
            expected_username = expected_channel_id[1:]
            if chat_username.lower() != expected_username.lower():
                return
    else:
        if channel_id != expected_channel_id:
            return

    message_text = message.text or message.caption or ""
    if not message_text:
        return

    context_mgr = get_channel_context_manager()
    if not context_mgr:
        logger.error("Context manager not initialized!")
        return

    # Detection Logic: Multimodal (Photo + Text) vs Text-only
    final_text = message_text
    
    if message.photo:
        logger.info(f"Detected multimodal post in channel (msg {message.message_id})")
        
        # Multimodal Flow
        try:
            # 1. Download photo
            if shared.media_downloader:
                image_path = await shared.media_downloader.download(message)
                
                if image_path and shared.multimodal_processor:
                    # 2. Process: AI Transcription + Concat
                    final_text = await shared.multimodal_processor.build_multimodal_caption(
                        image_path, 
                        message_text
                    )
                    logger.info(f"Multimodal ingestion complete for msg {message.message_id}")
                else:
                    logger.warning("Media downloader or processor not initialized")
        except Exception as e:
            logger.error(f"Error in multimodal ingestion for msg {message.message_id}: {e}", exc_info=True)
            # Fallback to original text if AI processing fails
            final_text = f"[Multimodal processing failed]\n\n{message_text}"

    # 3. Store in local context storage (for RAG)
    await context_mgr.store_message(
        message_id=message.message_id,
        text=final_text,
        date=message.date or datetime.now(),
        sender_id=None,
        sender_name="Channel",
        is_owner=True
    )
    logger.info(
        f"Mensaje del canal {message.message_id} almacenado (Multimodal: {bool(message.photo)})"
    )

    if shared.broadcast_manager:
        # Get the highest resolution photo file_id if present
        photo_file_id = message.photo[-1].file_id if message.photo else None
        
        await shared.broadcast_manager.schedule_broadcast(
            message_id=message.message_id,
            message_text=message_text, # Original caption
            channel_id=channel_id,
            original_time=message.date or datetime.now(),
            photo_file_id=photo_file_id
        )

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle private messages to the bot.
    Step 1: receive question (text or photo+text), show category buttons.
    """
    if not update.message:
        return

    message = update.message
    user = message.from_user
    user_text = message.text or message.caption or ""
    
    # If it's a photo, we need to process it
    if message.photo:
        logger.info(f"Detected multimodal question from user {user.id}")
        try:
            # 1. Download photo
            if shared.media_downloader:
                image_path = await shared.media_downloader.download(message)
                
                if image_path and shared.multimodal_processor:
                    # 2. Process: AI Transcription + Concat
                    user_text = await shared.multimodal_processor.build_multimodal_caption(
                        image_path, 
                        user_text
                    )
                    logger.info(f"Multimodal ingestion complete for user question {message.message_id}")
                else:
                    logger.warning("Media downloader or processor not initialized")
        except Exception as e:
            logger.error(f"Error in multimodal question ingestion: {e}", exc_info=True)
            # fallback to caption only if processing fails
            user_text = f"[Multimodal processing failed]\n\n{user_text}"

    if not user_text:
        # If still no text (e.g. just a photo that failed transcript or just empty)
        # and it's not a command, we might want to ask for text.
        if not message.text and not message.caption and not message.photo:
            return
        
    if user_text.startswith("/"):
        return

    await register_user_subscriber(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    logger.info(
        f"Query from user {user.id} "
        f"(@{user.username}): {user_text[:100]}..."
    )

    # Store question temporarily
    context.user_data["pending_question"] = user_text
    context.user_data["pending_message_id"] = update.message.message_id

    keyboard = create_category_keyboard()

    await update.message.reply_markdown_v2(
        escape_markdown(
            "Qual categoria de pregunta tienes?\n\n"
            "Selecciona una categoria para procesar tu pregunta:"
        ),
        reply_markup=keyboard
    )
