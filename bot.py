"""
Main Telegram Bot Application.
This is the entry point for the Telegram Bot System with:
- Redis-backed priority queue with category classification
- Worker pool for parallel LLM processing
- Rate limiting for LLM API (10 RPM)
- Channel context integration
- Broadcast functionality (with subscriber tracking)
- Escalation system for user dissatisfaction
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    CommandHandler
)
from telegram.error import TelegramError

from settings.config import get_config, AppConfig, BASE_DIR
from rag.channel_context import (
    init_channel_context_manager,
    get_channel_context_manager,
    ChannelContextManager
)
from rag.llm_client import LLMClient, query_llm_with_context, LLMResponse
from handlers.broadcast_manager import BroadcastManager
from handlers.escalation_manager import (
    EscalationManager,
    create_satisfaction_keyboard,
    parse_satisfaction_callback
)
from handlers.subscriber_manager import init_subscriber_manager, get_subscriber_manager
from handlers.category_handler import (
    create_category_keyboard,
    parse_category_callback,
    get_category_display_name,
    CATEGORY_CALLBACK_PREFIX
)
from queue_manager.redis_client import get_redis, close_redis
from queue_manager.priority_queue import PriorityQueueManager, generate_question_id
from queue_manager.question_store import QuestionStore
from queue_manager.rate_limiter import RateLimiter

# ---------------------------
# Logging Configuration
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO
)
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
    other special characters. Must be done in two passes so the bold
    markers are not escaped along with the rest.
    """
    import re
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


# ---------------------------
# Global Managers
# ---------------------------
channel_context_manager: Optional[ChannelContextManager] = None
broadcast_manager: Optional[BroadcastManager] = None
escalation_manager: Optional[EscalationManager] = None
llm_client: Optional[LLMClient] = None

# Queue infrastructure
priority_queue: Optional[PriorityQueueManager] = None
question_store: Optional[QuestionStore] = None
rate_limiter: Optional[RateLimiter] = None

# Shared bot reference (set in post_init, used by workers)
_shared_bot: Optional[Bot] = None

# IDs to track
owner_user_id: Optional[int] = None
bot_user_id: Optional[int] = None

# Worker tasks
_worker_tasks = []


# ---------------------------
# Helper Functions
# ---------------------------
def is_owner(user_id: int, username: Optional[str], config: AppConfig) -> bool:
    """Check if the user is the channel owner."""
    owner_username = config.telegram.owner_username
    if owner_user_id and user_id == owner_user_id:
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


# ---------------------------
# Worker Pool
# ---------------------------
async def queue_worker(worker_id: int):
    """
    Worker that continuously pops questions from the Redis priority queue
    and processes them through the LLM.

    Each worker:
    1. Pops the highest-priority question (ZPOPMIN)
    2. Acquires a rate limiter token (blocks if 10 RPM exceeded)
    3. Calls the LLM API
    4. Sends the response to the user via the shared bot instance
    5. Updates question status
    """
    global priority_queue, question_store, rate_limiter
    global escalation_manager, _shared_bot

    logger.info(f"Worker-{worker_id} started")

    while True:
        try:
            # Pop highest priority question from Redis
            question_data = await asyncio.to_thread(priority_queue.dequeue)

            if question_data is None:
                # Queue is empty, wait before checking again
                await asyncio.sleep(1.0)
                continue

            question_id = question_data["question_id"]
            question_text = question_data["question_description"]
            context_str = question_data.get("context", "")
            user_id = int(question_data["user_id"])
            chat_id = int(question_data["chat_id"])
            category = question_data.get("category", "otros")

            logger.info(
                f"Worker-{worker_id} processing: {question_id} "
                f"(category={category}, user={user_id})"
            )

            # Acquire rate limiter token
            await rate_limiter.acquire()

            # Call the LLM with context
            try:
                llm_response: LLMResponse = await asyncio.to_thread(
                    query_llm_with_context,
                    question_text,
                    context_str
                )
            except Exception as e:
                logger.error(
                    f"Worker-{worker_id} LLM error: {e}", exc_info=True
                )
                await asyncio.to_thread(
                    priority_queue.mark_failed, question_id, str(e)
                )
                await question_store.mark_failed(question_id)
                try:
                    await _shared_bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "Lo siento, ocurrio un error procesando "
                            "tu pregunta. Por favor, intentalo de nuevo."
                        )
                    )
                except Exception:
                    pass
                continue

            # Send response to user
            try:
                if not llm_response.success:
                    await _shared_bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "Lo siento, encontre un error procesando "
                            "tu solicitud.\n\n"
                            f"Error: {llm_response.error_message}"
                        )
                    )
                    await asyncio.to_thread(
                        priority_queue.mark_failed,
                        question_id,
                        llm_response.error_message or "LLM error"
                    )
                    await question_store.mark_failed(question_id)
                    continue

                # Build response with feedback prompt
                response_text = llm_response.content
                response_with_feedback = (
                    f"{response_text}\n\n---\n"
                    "Ha respondido esto a tu pregunta?"
                )

                keyboard = create_satisfaction_keyboard()

                bot_message = await _shared_bot.send_message(
                    chat_id=chat_id,
                    text=prepare_llm_response(response_with_feedback),
                    parse_mode="MarkdownV2",
                    reply_markup=keyboard
                )

                # Register for escalation tracking
                if escalation_manager:
                    # Look up subscriber to get username/first_name
                    sub_mgr = get_subscriber_manager()
                    subscriber = sub_mgr.get_subscriber(user_id)
                    await escalation_manager.register_query(
                        user_id=user_id,
                        username=subscriber.username if subscriber else None,
                        first_name=subscriber.first_name if subscriber else None,
                        question=question_text,
                        bot_response=response_text,
                        message_id=bot_message.message_id
                    )

                # Increment query count
                sub_mgr = get_subscriber_manager()
                await sub_mgr.increment_query_count(user_id)

                # Mark as completed
                await asyncio.to_thread(
                    priority_queue.mark_completed, question_id
                )
                await question_store.mark_completed(question_id)

                logger.info(
                    f"Worker-{worker_id} completed: {question_id} "
                    f"(response: {len(response_text)} chars)"
                )

            except Exception as e:
                logger.error(
                    f"Worker-{worker_id} send error for "
                    f"{question_id}: {e}",
                    exc_info=True
                )
                await asyncio.to_thread(
                    priority_queue.mark_failed, question_id, str(e)
                )
                await question_store.mark_failed(question_id)

        except asyncio.CancelledError:
            logger.info(f"Worker-{worker_id} cancelled")
            break
        except Exception as e:
            logger.error(
                f"Worker-{worker_id} unexpected error: {e}",
                exc_info=True
            )
            await asyncio.sleep(2.0)


# ---------------------------
# Command Handlers
# ---------------------------
async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the /start command - registers user as subscriber."""
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    config = get_config()

    await register_user_subscriber(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    global owner_user_id
    if is_owner(user.id, user.username, config):
        owner_user_id = user.id
        if broadcast_manager:
            broadcast_manager.set_excluded_ids(
                owner_id=owner_user_id, bot_id=bot_user_id
            )
        logger.info(f"Owner identified with user_id: {user.id}")

    welcome_msg = (
        " **Bienvenido al Bot Asistente del Canal!**\n\n"
        "Estoy aqui para ayudarte a responder tus preguntas "
        "sobre el contenido del canal.\n\n"
        "**Como funciona:**\n"
        "1. Enviame cualquier pregunta\n"
        "2. Selecciona la categoria de tu pregunta\n"
        "3. Tu pregunta sera procesada segun su prioridad\n"
        "4. Recibiras la respuesta cuando este lista\n\n"
        "**Categorias de preguntas:**\n"
        "- Notas (prioridad mas alta)\n"
        "- Evaluaciones\n"
        "- Tareas\n"
        "- Otros\n\n"
        "**Comandos:**\n"
        "- /start - Mostrar este mensaje de bienvenida\n"
        "- /help - Obtener informacion de ayuda\n"
        "- /queue - Ver estado de la cola\n\n"
        "!! **Nota:** Recibiras notificaciones cuando el dueno "
        "del canal publique mensajes importantes.\n\n"
        "!! No dudes en preguntarme cualquier cosa!"
    )

    await update.message.reply_markdown_v2(escape_markdown(welcome_msg))


async def help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the /help command."""
    if not update.message:
        return

    help_msg = (
        "**Informacion de Ayuda**\n\n"
        "**Que puedo hacer?**\n"
        "Puedo responder preguntas basadas en los mensajes "
        "recientes de nuestro canal de Telegram.\n\n"
        "**Como usar:**\n"
        "- Simplemente envia tu pregunta como un mensaje\n"
        "- Selecciona la categoria con los botones\n"
        "- Tu pregunta se anadira a la cola con prioridad\n"
        "- Recibiras la respuesta cuando sea procesada\n"
        "- Despues de recibir mi respuesta, haz clic en:\n"
        "  - **SI** si fue respondida satisfactoriamente\n"
        "  - **NO** si necesitas mas ayuda\n\n"
        "**Prioridades:**\n"
        "- Las preguntas de Notas se procesan primero\n"
        "- Seguidas por Evaluaciones, Tareas, y Otros\n"
        "- Dentro de la misma categoria, FIFO\n\n"
        "Necesitas mas ayuda? Solo pregunta!"
    )

    await update.message.reply_markdown_v2(escape_markdown(help_msg))


async def stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the /stats command - show stats (owner only)."""
    if not update.message or not update.message.from_user:
        return

    config = get_config()
    user = update.message.from_user

    if not is_owner(user.id, user.username, config):
        await update.message.reply_text(
            "Este comando solo esta disponible para el dueno del canal."
        )
        return

    sub_mgr = get_subscriber_manager()
    subscriber_count = sub_mgr.get_subscriber_count()

    ctx_mgr = get_channel_context_manager()
    message_count = ctx_mgr.get_message_count() if ctx_mgr else 0

    q_size = priority_queue.get_queue_size() if priority_queue else 0
    pending = len(question_store.get_pending()) if question_store else 0
    rate_info = rate_limiter.get_usage() if rate_limiter else {}

    bm_running = broadcast_manager and broadcast_manager._running
    bm_pending = len(broadcast_manager.get_pending_broadcasts()) if broadcast_manager else 0
    bm_done = len(broadcast_manager.get_completed_broadcasts()) if broadcast_manager else 0

    stats_msg = (
        " **Estadisticas del Bot**\n\n"
        f"**Suscriptores:** {subscriber_count} usuarios activos\n"
        f"**Mensajes del Canal:** {message_count} mensajes\n\n"
        "**Cola de Preguntas:**\n"
        f"- En cola (Redis): {q_size} preguntas\n"
        f"- Pendientes (JSON): {pending} preguntas\n"
        f"- LLM API: {rate_info.get('current_rpm', 0)}/"
        f"{rate_info.get('max_rpm', 10)} RPM usados\n\n"
        f"**Difusion:** {'En ejecucion' if bm_running else 'Detenido'}\n"
        f"**Difusiones Pendientes:** {bm_pending}\n"
        f"**Difusiones Completadas:** {bm_done}\n\n"
        f"**Ventana de Contexto:** {config.context.context_hours} horas\n"
        f"**Workers Activos:** {config.queue.num_workers}"
    )

    await update.message.reply_markdown_v2(escape_markdown(stats_msg))


async def queue_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the /queue command - show queue status."""
    if not update.message:
        return

    q_size = priority_queue.get_queue_size() if priority_queue else 0

    if q_size == 0:
        await update.message.reply_text(
            "La cola de preguntas esta vacia. Envia tu pregunta!"
        )
    else:
        await update.message.reply_markdown_v2(
            escape_markdown(
                f"**Estado de la Cola**\n\n"
                f"Hay **{q_size}** pregunta(s) en cola.\n\n"
                "Las preguntas se procesan segun categoria y orden de llegada."
            )
        )


async def context_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the /context command - show channel context (owner only)."""
    if not update.message or not update.message.from_user:
        return

    config = get_config()
    user = update.message.from_user

    if not is_owner(user.id, user.username, config):
        await update.message.reply_text(
            "Este comando solo esta disponible para el dueno."
        )
        return

    ctx_mgr = get_channel_context_manager()
    if not ctx_mgr:
        await update.message.reply_text(
            "**Gestor de contexto no inicializado.**"
        )
        return

    messages = ctx_mgr.get_recent_messages(10)
    message_count = ctx_mgr.get_message_count()

    if not messages:
        await update.message.reply_text(
            "**No hay mensajes del canal en el contexto!**"
        )
        return

    response = (
        f"**Mensajes del Canal ({message_count} en total)**\n\n"
    )

    for msg in messages:
        date_str = msg.date.strftime("%Y-%m-%d %H:%M")
        preview = msg.text[:200] + "..." if len(msg.text) > 200 else msg.text
        response += f"**[{date_str}]**\n{preview}\n\n"

    if len(response) > 4000:
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for chunk in chunks:
            await update.message.reply_markdown_v2(
                escape_markdown(chunk)
            )
    else:
        await update.message.reply_markdown_v2(
            escape_markdown(response)
        )


# ---------------------------
# Message Handlers
# ---------------------------
async def handle_channel_post(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Handle new posts in the channel.
    1. Store the message in local context storage (for RAG)
    2. Schedule broadcast for owner messages
    """
    global broadcast_manager

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
    if context_mgr:
        await context_mgr.store_message(
            message_id=message.message_id,
            text=message_text,
            date=message.date or datetime.now(),
            sender_id=None,
            sender_name="Channel",
            is_owner=True
        )
        logger.info(
            f"Mensaje del canal {message.message_id} almacenado"
        )

    if broadcast_manager:
        await broadcast_manager.schedule_broadcast(
            message_id=message.message_id,
            message_text=message_text,
            channel_id=channel_id,
            original_time=message.date or datetime.now()
        )


async def handle_private_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Handle private messages to the bot.
    Step 1: receive question, show category buttons.
    The question is stored temporarily in user_data until
    the category is selected.
    """
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    user_text = update.message.text

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


# ---------------------------
# Callback Query Handlers
# ---------------------------
async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Handle inline button callbacks.
    Routes based on callback data prefix.
    """
    query = update.callback_query
    if not query or not query.message:
        return

    callback_data = query.data

    if callback_data.startswith(CATEGORY_CALLBACK_PREFIX):
        await _handle_category_selection(update, context)
        return

    if callback_data.startswith("satisfied_"):
        await _handle_satisfaction_feedback(update, context)
        return

    logger.warning(f"Unknown callback data: {callback_data}")


async def _handle_category_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle category button press - enqueue to Redis priority queue."""
    global priority_queue, question_store

    query = update.callback_query
    await query.answer()

    category = parse_category_callback(query.data)
    if category is None:
        await query.message.edit_text(
            "Categoria no valida. Envia tu pregunta de nuevo."
        )
        return

    pending_question = context.user_data.get("pending_question")
    if not pending_question:
        await query.message.edit_text(
            "No se encontro tu pregunta. Envia tu pregunta de nuevo."
        )
        return

    user = query.from_user
    chat_id = query.message.chat_id

    question_id = generate_question_id()
    context_str = get_context_for_query()

    enqueued = await asyncio.to_thread(
        priority_queue.enqueue,
        question_id=question_id,
        question_description=pending_question,
        category=category,
        user_id=user.id,
        chat_id=chat_id,
        context=context_str
    )

    if not enqueued:
        await query.message.edit_text(
            "La cola esta llena. Intentalo en unos minutos."
        )
        return

    await question_store.add_question(
        question_id=question_id,
        question_description=pending_question,
        category=category,
        user_id=user.id
    )

    context.user_data.pop("pending_question", None)
    context.user_data.pop("pending_message_id", None)

    q_size = await asyncio.to_thread(priority_queue.get_queue_size)
    cat_display = get_category_display_name(category)

    await query.message.edit_text(
        f"Tu pregunta ha sido anadida a la cola.\n\n"
        f"Categoria: {cat_display}\n"
        f"Posicion en cola: {q_size}\n\n"
        "_Recibiras la respuesta cuando sea procesada._",
        parse_mode="Markdown"
    )

    logger.info(
        f"Question enqueued: {question_id} | "
        f"user={user.id} | category={category} | "
        f"queue_size={q_size}"
    )


async def _handle_satisfaction_feedback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle satisfaction button press (SI/NO)."""
    global escalation_manager

    query = update.callback_query
    if not query or not query.message:
        return

    await query.answer()

    satisfied = parse_satisfaction_callback(query.data)
    if satisfied is None:
        return

    message = query.message

    if satisfied:
        try:
            await message.edit_text(
                message.text + "\n\n Gracias por tu comentario!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[]])
            )
        except Exception:
            pass
        if escalation_manager:
            await escalation_manager.handle_user_satisfaction(
                message_id=message.message_id, satisfied=True
            )
    else:
        user = query.from_user
        try:
            await message.edit_text(
                message.text + "\n\n Escalada al docente.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[]])
            )
        except Exception:
            pass
        if escalation_manager:
            escalated = await escalation_manager.handle_user_satisfaction(
                message_id=message.message_id, satisfied=False
            )
            if escalated:
                await escalation_manager.send_acknowledgment_to_user(
                    user_id=user.id, query=escalated
                )


# ---------------------------
# Error Handler
# ---------------------------
async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
):
    """Handle errors in the telegram bot."""
    logger.error(
        f"Excepcion: {context.error}", exc_info=context.error
    )
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "Ocurrio un error. Intentalo de nuevo mas tarde."
            )
        except Exception:
            pass


# ---------------------------
# Main Application
# ---------------------------
async def post_init(application):
    """Initialize managers and start background tasks."""
    global channel_context_manager, broadcast_manager
    global escalation_manager, llm_client
    global bot_user_id, owner_user_id
    global priority_queue, question_store, rate_limiter
    global _worker_tasks, _shared_bot

    config = get_config()
    bot = application.bot

    # Store shared bot reference for workers
    _shared_bot = bot

    bot_user = await bot.get_me()
    bot_user_id = bot_user.id
    logger.info(f"Bot user ID: {bot_user_id}")

    # Initialize subscriber manager
    storage_path = str(BASE_DIR / "data" / "subscribers.json")
    init_subscriber_manager(storage_path)

    # Initialize channel context manager
    init_channel_context_manager()
    channel_context_manager = get_channel_context_manager()

    # Initialize other managers
    broadcast_manager = BroadcastManager(bot)
    escalation_manager = EscalationManager(bot)
    llm_client = LLMClient()

    broadcast_manager.set_excluded_ids(
        owner_id=None, bot_id=bot_user_id
    )
    await broadcast_manager.start()

    # ========== REDIS & QUEUE INITIALIZATION ==========
    try:
        get_redis()
        logger.info("Redis connection established")

        priority_queue = PriorityQueueManager()
        question_store = QuestionStore()
        rate_limiter = RateLimiter(max_rpm=config.queue.max_rpm)

        # Start worker pool
        num_workers = config.queue.num_workers
        loop = asyncio.get_running_loop()

        for i in range(num_workers):
            task = loop.create_task(queue_worker(i))
            _worker_tasks.append(task)

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
        f"{broadcast_manager.get_subscriber_count()}"
    )
    logger.info(
        f"   - Mensajes canal: "
        f"{channel_context_manager.get_message_count()}"
    )
    logger.info(f"   - Workers: {config.queue.num_workers}")
    logger.info(f"   - Rate limit: {config.queue.max_rpm} RPM")


async def post_shutdown(application):
    """Cleanup on shutdown."""
    global broadcast_manager, _worker_tasks, _shared_bot

    if broadcast_manager:
        await broadcast_manager.stop()

    for task in _worker_tasks:
        task.cancel()

    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        logger.info(f"Cancelled {len(_worker_tasks)} worker tasks")

    _worker_tasks.clear()
    _shared_bot = None
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

    # Channel post handler
    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, handle_channel_post)
    )

    # Private messages - triggers category selection
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_private_message
        )
    )

    # Callback query handler (category + satisfaction buttons)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("**Starting bot...**")
    logger.info(f"   - Channel: {config.telegram.channel_id}")
    logger.info(f"   - Owner: {config.telegram.owner_username}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
