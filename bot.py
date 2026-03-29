"""
Main Telegram Bot Application.
This is the entry point for the Telegram Bot System with:
- Redis-backed priority queue with category classification
- Worker pool for parallel LLM processing
- Rate limiting for LLM API (20 RPM)
- Channel context integration
- Broadcast functionality (with subscriber tracking)
- Escalation system for user dissatisfaction
- Multimodal ingestion (Photo + Transcription)
"""

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    CommandHandler
)

from settings.config import get_config, BASE_DIR
from rag.channel_context import (
    init_channel_context_manager,
    get_channel_context_manager
)
from rag.llm_client import LLMClient
from managers.broadcast_manager import BroadcastManager
from managers.escalation_manager import EscalationManager
from managers.subscriber_manager import init_subscriber_manager
from managers.category_manager import (
    CATEGORY_CALLBACK_PREFIX
)
from queue_qa.redis_client import get_redis, close_redis
from queue_qa.priority_queue import PriorityQueueManager
from queue_qa.question_store import QuestionStore
from queue_qa.rate_limiter import RateLimiter

# Multimodal Ingestion Imports
from ingest.vision.media_downloader import MediaDownloader
from ingest.vision.ai_client import AIClient
from ingest.vision.ai_image_transcriber import AIImageTranscriber
from ingest.vision.multimodal_processor import MultimodalProcessor

# Speech Ingestion Imports
from ingest.speech.media_downloader import SpeechMediaDownloader
from ingest.speech.audio_processor import AudioProcessor

# Utils Package Imports
from utils import shared
from utils.workers import queue_worker
from utils.cmd_handler import (
    start_command, 
    help_command, 
    stats_command, 
    queue_command, 
    context_command
)
from utils.message_handler import (
    handle_channel_post, 
    handle_private_message
)
from utils.query_handler import (
    handle_callback_query, 
    error_handler
)

# ---------------------------
# Logging Configuration
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ---------------------------
# Post Init & Shutdown
# ---------------------------
async def post_init(application):
    """Initialize managers and start background tasks."""
    config = get_config()
    bot = application.bot

    # Store shared bot reference for workers
    shared._shared_bot = bot

    bot_user = await bot.get_me()
    shared.bot_user_id = bot_user.id
    logger.info(f"Bot user ID: {shared.bot_user_id}")

    # Initialize subscriber manager
    storage_path = str(BASE_DIR / "data" / "subscribers.json")
    init_subscriber_manager(storage_path)

    # Initialize channel context manager
    logger.warning("?? post_init: Initializing channel context manager...")
    init_channel_context_manager()
    shared.channel_context_manager = get_channel_context_manager()
    logger.warning(f"? Channel context manager initialized")

    # Initialize other managers
    logger.warning("?? post_init: Initializing managers...")
    shared.broadcast_manager = BroadcastManager(bot)
    shared.escalation_manager = EscalationManager(bot)
    shared.llm_client = LLMClient()
    logger.warning(f"? Managers initialized")

    # Initialize multimodal services
    logger.warning("?? post_init: Initializing vision/multimodal services...")
    shared.media_downloader = MediaDownloader(media_folder=config.media_folder)
    logger.warning(f"? Media downloader initialized: {config.media_folder}")
    
    # Initialize speech services
    logger.warning("?? post_init: Initializing speech/audio services...")
    logger.warning(f"   - Speech folder config: {config.speech_folder}")
    shared.speech_downloader = SpeechMediaDownloader()
    logger.warning(f"? Speech media downloader initialized")
    
    logger.warning(f"   - Creating AudioProcessor...")
    shared.audio_processor = AudioProcessor()
    logger.warning(f"? AudioProcessor created")
    
    logger.warning(f"   - Starting AudioProcessor workers...")
    await shared.audio_processor.start()
    logger.warning(f"? AudioProcessor workers started")
    
    # Reuse LLM config for multimodal AI
    logger.warning("?? post_init: Initializing multimodal AI...")
    ai_client = AIClient(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model
    )
    transcriber = AIImageTranscriber(ai_client)
    shared.multimodal_processor = MultimodalProcessor(transcriber)
    logger.warning(f"? Multimodal processor initialized")

    shared.broadcast_manager.set_excluded_ids(
        owner_id=None, bot_id=shared.bot_user_id
    )
    await shared.broadcast_manager.start()
    logger.warning(f"? Broadcast manager started")

    # ========== REDIS & QUEUE INITIALIZATION ==========
    try:
        logger.warning("?? post_init: Connecting to Redis...")
        get_redis()
        logger.warning("? Redis connection established")

        shared.priority_queue = PriorityQueueManager()
        shared.question_store = QuestionStore()
        shared.rate_limiter = RateLimiter(max_rpm=config.queue.max_rpm)
        logger.warning(f"? Queue managers initialized")

        # Start worker pool
        num_workers = config.queue.num_workers
        loop = asyncio.get_running_loop()

        for i in range(num_workers):
            task = loop.create_task(queue_worker(i))
            shared._worker_tasks.append(task)

        logger.info(f"Worker pool started: {num_workers} workers")
        logger.info(
            f"Queue config: max_size={config.queue.max_queue_size}, "
            f"max_rpm={config.queue.max_rpm}"
        )

    except ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        logger.error("Bot cannot process questions without Redis!")
        raise

    logger.info("Bot inicializado correctamente")
    logger.info(
        f"   - Broadcast delay: {config.broadcast.delay_hours} horas"
    )
    logger.info(
        f"   - Context window: {config.context.context_hours} horas"
    )
    logger.info(
        f"   - Suscriptores: "
        f"{shared.broadcast_manager.get_subscriber_count()}"
    )
    logger.info(
        f"   - Mensajes canal: "
        f"{shared.channel_context_manager.get_message_count()}"
    )
    logger.info(f"   - Workers: {config.queue.num_workers}")
    logger.info(f"   - Rate limit: {config.queue.max_rpm} RPM")


async def post_shutdown(application):
    """Cleanup on shutdown."""
    if shared.broadcast_manager:
        await shared.broadcast_manager.stop()
        
    if shared.audio_processor:
        await shared.audio_processor.stop()

    for task in shared._worker_tasks:
        task.cancel()

    if shared._worker_tasks:
        await asyncio.gather(*shared._worker_tasks, return_exceptions=True)
        logger.info(f"Cancelled {len(shared._worker_tasks)} worker tasks")

    shared._worker_tasks.clear()
    shared._shared_bot = None
    close_redis()

    logger.info("Bot shutdown complete")


def main():
    """Main entry point for the Telegram bot."""
    config = get_config()
    logging.getLogger().setLevel(
        getattr(logging, config.log_level.upper(), logging.INFO)
    )

    application = (
        ApplicationBuilder()
        .token(config.telegram.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("context", context_command))

    # Channel post handler - handles TEXT, PHOTO, VOICE, AUDIO, etc.
    logger.warning("?? Registering channel post handler...")
    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, handle_channel_post)
    )
    logger.warning("? Channel post handler registered (all message types)")

    # Private messages handler - TEXT, PHOTO, VOICE, AUDIO (with category selection after audio transcription)
    logger.warning("?? Registering private message handlers...")
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO) & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_private_message
        )
    )
    logger.warning("? Private message handler registered (TEXT | PHOTO | VOICE | AUDIO)")

    # Callback query handler (category + satisfaction buttons)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Error handler
    application.add_error_handler(error_handler)

    logger.warning("=" * 60)
    logger.warning("**STARTING BOT...**")
    logger.warning("=" * 60)
    logger.warning(f"   - Channel: {config.telegram.channel_id}")
    logger.warning(f"   - Owner: {config.telegram.owner_username}")
    logger.warning(f"   - All handlers registered successfully")
    logger.warning("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
