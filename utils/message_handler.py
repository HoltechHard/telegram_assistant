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

# main manager of owner posts in the channel
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
    
    logger.warning(f"?? handle_channel_post: New message in channel")
    logger.warning(f"   - Message ID: {message.message_id}")
    logger.warning(f"   - Chat ID: {channel_id}")

    if expected_channel_id.startswith("@"):
        chat_username = message.chat.username
        if chat_username:
            expected_username = expected_channel_id[1:]
            if chat_username.lower() != expected_username.lower():
                return
    else:
        if channel_id != expected_channel_id:
            return

    logger.warning(f"   ? Correct channel detected")
    logger.warning(f"   - Has text: {bool(message.text)}")
    logger.warning(f"   - Has caption: {bool(message.caption)}")
    logger.warning(f"   - Has photo: {bool(message.photo)}")
    logger.warning(f"   - Has voice: {bool(message.voice)}")
    logger.warning(f"   - Has audio: {bool(message.audio)}")

    message_text = message.text or message.caption or ""
    
    # IMPORTANT: Audio can come without text!
    if not message_text and not message.voice and not message.audio and not message.photo:
        logger.info(f"   ??  No text, audio, photo found - skipping")
        return

    context_mgr = get_channel_context_manager()
    if not context_mgr:
        logger.error("Context manager not initialized!")
        return

    # Detection Logic: Multimodal (Photo + Text) vs Text-only
    final_text = message_text
    
    if message.photo:
        logger.warning(f"?? MULTIMODAL DETECTED: Processing photo...")
        
        # Multimodal Flow
        try:
            # 1. Download photo
            if shared.media_downloader:
                image_path = await shared.media_downloader.download(message)
                
                if image_path and shared.multimodal_processor:
                    # 2. Process: AI Transcription + Concat
                    logger.warning(f"   - Processing with AI...")
                    final_text = await shared.multimodal_processor.build_multimodal_caption(
                        image_path, 
                        message_text
                    )
                    logger.warning(f"? Multimodal ingestion complete for msg {message.message_id}")
                else:
                    logger.warning("? Media downloader or processor not initialized")
        except Exception as e:
            logger.error(f"? Error in multimodal ingestion for msg {message.message_id}: {e}", exc_info=True)
            # Fallback to original text if AI processing fails
            final_text = f"[Multimodal processing failed]\n\n{message_text}"

    # Detection logic: Speech (Voice or Audio) vs Non-Speech
    if message.voice or message.audio:
        logger.warning(f"???  AUDIO DETECTED: Processing audio...")
        logger.warning(f"   - Voice: {bool(message.voice)}, Audio: {bool(message.audio)}")
        
        try:
            if not shared.speech_downloader:
                logger.error(f"? speech_downloader NOT INITIALIZED!")
                final_text = "[Audio processing failed: speech_downloader not initialized]"
            elif not shared.audio_processor:
                logger.error(f"? audio_processor NOT INITIALIZED!")
                final_text = "[Audio processing failed: audio_processor not initialized]"
            else:
                logger.warning(f"   ? Both processors initialized, starting download...")
                
                audio_path = await shared.speech_downloader.download(message)
                if not audio_path:
                    logger.error(f"? Failed to download audio")
                    final_text = "[Audio processing failed: download error]"
                else:
                    logger.warning(f"? Audio downloaded successfully")
                    
                    try:
                        logger.warning(f"   - Submitting to queue...")
                        job_id = await shared.audio_processor.submit_audio(audio_path, message.message_id)
                        logger.warning(f"   ? Job submitted, Job ID: {job_id}")
                        
                        logger.warning(f"   - Waiting for transcription (timeout: 60s)...")
                        final_text = await shared.audio_processor.wait_for_transcript(job_id, timeout=60)
                        logger.warning(f"? Speech ingestion complete for msg {message.message_id}")
                        logger.warning(f"   - Transcript length: {len(final_text)} chars")
                        
                        # Send transcript back to channel
                        try:
                            await context.bot.send_message(
                                chat_id=message.chat_id,
                                text=f"??? **Transcripci?n de Audio**:\n\n{final_text}",
                                parse_mode="Markdown"
                            )
                            logger.warning(f"? Transcript sent to channel")
                        except Exception as send_err:
                            logger.error(f"? Failed to send transcript to channel: {send_err}")
                        
                    except TimeoutError as timeout_err:
                        logger.error(f"? Transcription timeout: {timeout_err}")
                        final_text = f"[Audio processing failed: transcription timeout]"
                    except Exception as proc_err:
                        logger.error(f"? Transcription error: {proc_err}", exc_info=True)
                        final_text = f"[Audio processing failed: {type(proc_err).__name__}]"
                        
        except Exception as e:
            logger.error(f"? Unexpected error in speech ingestion for msg {message.message_id}: {e}", exc_info=True)
            final_text = f"[Speech processing failed]"

    # 3. Store in local context storage (for RAG)
    logger.warning(f"?? Storing message in context...")
    await context_mgr.store_message(
        message_id=message.message_id,
        text=final_text,
        date=message.date or datetime.now(),
        sender_id=None,
        sender_name="Channel",
        is_owner=True
    )
    logger.warning(f"? Mensaje del canal {message.message_id} almacenado")
    logger.warning(f"   - Has multimodal: {bool(message.photo)}")
    logger.warning(f"   - Text length: {len(final_text)} chars")

    if shared.broadcast_manager:
        # Get the highest resolution photo file_id if present
        photo_file_id = message.photo[-1].file_id if message.photo else None
        # Get voice/audio file IDs for audio posts
        voice_file_id = message.voice.file_id if message.voice else None
        audio_file_id = message.audio.file_id if message.audio else None

        # For audio-only posts, broadcast should include transcription
        is_audio_post = bool(voice_file_id or audio_file_id)
        broadcast_message_text = final_text if is_audio_post else message_text

        logger.warning(f"?? Scheduling broadcast...")
        await shared.broadcast_manager.schedule_broadcast(
            message_id=message.message_id,
            message_text=broadcast_message_text,
            channel_id=channel_id,
            original_time=message.date or datetime.now(),
            photo_file_id=photo_file_id,
            voice_file_id=voice_file_id,
            audio_file_id=audio_file_id
        )
        logger.warning(f"? Broadcast scheduled")

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
    
    logger.warning(f"?? handle_private_message: New message from user {user.id}")
    logger.warning(f"   - Username: @{user.username}")
    logger.warning(f"   - Has text: {bool(message.text)}")
    logger.warning(f"   - Has caption: {bool(message.caption)}")
    logger.warning(f"   - Has photo: {bool(message.photo)}")
    logger.warning(f"   - Has voice: {bool(message.voice)}")
    logger.warning(f"   - Has audio: {bool(message.audio)}")
    
    # If it's a photo, we need to process it
    if message.photo:
        logger.warning(f"?? Multimodal message detected from user {user.id}")
        try:
            # 1. Download photo
            if shared.media_downloader:
                image_path = await shared.media_downloader.download(message)
                
                if image_path and shared.multimodal_processor:
                    # 2. Process: AI Transcription + Concat
                    logger.warning(f"   - Processing with AI...")
                    user_text = await shared.multimodal_processor.build_multimodal_caption(
                        image_path, 
                        user_text
                    )
                    logger.warning(f"? Multimodal ingestion complete for user question {message.message_id}")
                else:
                    logger.warning("? Media downloader or processor not initialized")
        except Exception as e:
            logger.error(f"? Error in multimodal question ingestion: {e}", exc_info=True)
            # fallback to caption only if processing fails
            user_text = f"[Multimodal processing failed]\n\n{user_text}"

    # If it's a audio, we need process it
    if message.voice or message.audio:
        logger.warning(f"???  Audio message detected from user {user.id}")
        logger.warning(f"   - Voice: {bool(message.voice)}, Audio: {bool(message.audio)}")
        
        # We need an initial feedback if transcript takes long
        processing_msg = await update.message.reply_text("??? Procesando el audio, por favor espera...")
        
        try:
            if not shared.speech_downloader:
                logger.error(f"? speech_downloader NOT INITIALIZED!")
                await processing_msg.edit_text("? Error: Sistema no configurado para audio")
            elif not shared.audio_processor:
                logger.error(f"? audio_processor NOT INITIALIZED!")
                await processing_msg.edit_text("? Error: Procesador de audio no disponible")
            else:
                logger.warning(f"   - Downloading audio...")
                audio_path = await shared.speech_downloader.download(message)
                
                if not audio_path:
                    logger.error(f"? Failed to download audio from user {user.id}")
                    await processing_msg.edit_text("? Error al descargar el audio")
                else:
                    logger.warning(f"? Audio downloaded: {audio_path}")
                    
                    try:
                        logger.warning(f"   - Submitting to transcription queue...")
                        job_id = await shared.audio_processor.submit_audio(audio_path, message.message_id)
                        logger.warning(f"   ? Job created: {job_id}")
                        
                        logger.warning(f"   - Waiting for transcription...")
                        user_text = await shared.audio_processor.wait_for_transcript(job_id, timeout=60)
                        logger.warning(f"? Speech ingestion complete for user message")
                        logger.warning(f"   - Transcript: {user_text[:100]}...")
                        
                        await processing_msg.delete()
                    except TimeoutError:
                        logger.error(f"? Transcription timeout for user {user.id}")
                        user_text = f"[Transcription timeout]"
                        await processing_msg.edit_text("? Error: Timeout al procesar el audio")
                    except Exception as proc_err:
                        logger.error(f"? Transcription error for user {user.id}: {proc_err}", exc_info=True)
                        user_text = f"[Transcription failed]"
                        await processing_msg.edit_text(f"? Error: {type(proc_err).__name__}")
                        
        except Exception as e:
            logger.error(f"? Error in speech ingestion for user {user.id}: {e}", exc_info=True)
            user_text = f"[Speech processing failed]"
            await processing_msg.edit_text("? Error al procesar el audio")

    if not user_text:
        # If still no text (e.g. just a photo that failed transcript or just empty)
        # and it's not a command, we might want to ask for text.
        if not message.text and not message.caption and not message.photo and not message.voice and not message.audio:
            logger.warning(f"   - No processable content, ignoring")
            return
        
    if user_text.startswith("/"):
        logger.info(f"   - Command detected, skipping category flow")
        return

    await register_user_subscriber(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    logger.warning(f"? Query from user {user.id} (@{user.username})")
    logger.warning(f"   - Text preview: {user_text[:80]}...")

    # Store question temporarily
    context.user_data["pending_question"] = user_text
    context.user_data["pending_message_id"] = update.message.message_id

    keyboard = create_category_keyboard()

    await update.message.reply_markdown_v2(
        escape_markdown(
            "?Cual categoria de pregunta tienes?\n\n"
            "Selecciona una categoria para procesar tu pregunta:"
        ),
        reply_markup=keyboard
    )
