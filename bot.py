"""
Main Telegram Bot Application.
This is the entry point for the Telegram Bot System with:
- Queue-based LLM processing
- Channel context integration
- Broadcast functionality (with subscriber tracking)
- Escalation system for user dissatisfaction
"""

import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Set

from telegram import Update, InlineKeyboardMarkup
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
    Telegram is very strict about what needs to be escaped in V2.
    """
    # Characters that must be escaped in MarkdownV2
    # _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # We avoid escaping already escaped characters
    result = ""
    for char in text:
        if char in escape_chars:
            result += f"\\{char}"
        else:
            result += char
    return result


# ---------------------------
# Queue Setup
# ---------------------------
@dataclass
class LLMRequest:
    """Represents an LLM processing request in the queue."""
    update: Update
    future: asyncio.Future
    user_question: str
    context: str


# Global queue for LLM requests
llm_queue: asyncio.Queue[LLMRequest] = asyncio.Queue()

# Global managers
channel_context_manager: Optional[ChannelContextManager] = None
broadcast_manager: Optional[BroadcastManager] = None
escalation_manager: Optional[EscalationManager] = None
llm_client: Optional[LLMClient] = None

# IDs to track
owner_user_id: Optional[int] = None
bot_user_id: Optional[int] = None


# ---------------------------
# LLM Worker
# ---------------------------
async def llm_worker():
    """
    Worker that processes LLM requests sequentially from the queue.
    This ensures API rate limits are respected and responses are ordered.
    """
    global llm_client
    
    while True:
        request: LLMRequest = await llm_queue.get()
        try:
            logger.info(f"Processing query: {request.user_question[:100]}...")
            
            # Call the LLM with context
            llm_result = await asyncio.to_thread(
                query_llm_with_context,
                request.user_question,
                request.context
            )
            
            request.future.set_result(llm_result)
        
        except Exception as e:
            logger.error(f"LLM API error: {e}", exc_info=True)
            request.future.set_exception(e)
        
        finally:
            llm_queue.task_done()


# ---------------------------
# Helper Functions
# ---------------------------
def is_owner(user_id: int, username: Optional[str], config: AppConfig) -> bool:
    """Check if the user is the channel owner."""
    owner_username = config.telegram.owner_username
    
    # Check by user ID (most reliable)
    if owner_user_id and user_id == owner_user_id:
        return True
    
    # Check by username as fallback
    if username and owner_username:
        normalized_username = f"@{username}" if not username.startswith("@") else username
        return normalized_username.lower() == owner_username.lower()
    
    return False


def get_context_for_query() -> str:
    """Get the channel context for a user query."""
    context_manager = get_channel_context_manager()
    if context_manager:
        context_str = context_manager.get_context_string()
        logger.info(f"Context for query: {len(context_str)} chars, {context_manager.get_message_count()} messages")
        return context_str
    
    logger.warning("No channel context manager available!")
    return "No channel context available."


async def register_user_subscriber(user_id: int, username: Optional[str], 
                                    first_name: Optional[str], last_name: Optional[str]) -> None:
    """Register a user as a subscriber when they interact with the bot."""
    subscriber_manager = get_subscriber_manager()
    await subscriber_manager.register_subscriber(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )


# ---------------------------
# Command Handlers
# ---------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command - registers user as subscriber."""
    if not update.message or not update.message.from_user:
        return
    
    user = update.message.from_user
    config = get_config()
    
    # Register user as subscriber
    await register_user_subscriber(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Check if this is the owner starting the bot
    global owner_user_id
    if is_owner(user.id, user.username, config):
        owner_user_id = user.id
        if broadcast_manager:
            broadcast_manager.set_excluded_ids(owner_id=owner_user_id, bot_id=bot_user_id)
        logger.info(f"Owner identified with user_id: {user.id}")
    
    welcome_message = """ **Bienvenido al Bot Asistente del Canal!**

Estoy aqui para ayudarte a responder tus preguntas sobre el contenido del canal.

**Como funciona:**
1. Enviame cualquier pregunta
2. Buscar en los mensajes recientes del canal para darte respuestas relevantes
3. Despues de mi respuesta, puedes indicar si fue de ayuda

**Comandos:**
- /start - Mostrar este mensaje de bienvenida
- /help - Obtener informacion de ayuda

!! **Nota:** Recibiras notificaciones cuando el dueno del canal publique mensajes importantes.

!! No dudes en preguntarme cualquier cosa!"""
    
    await update.message.reply_markdown_v2(escape_markdown(welcome_message))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
    if not update.message:
        return
    
    help_message = """**Informacion de Ayuda**

**Que puedo hacer?**
Puedo responder preguntas basadas en los mensajes recientes de nuestro canal de Telegram.

**Como usar:**
- Simplemente envia tu pregunta como un mensaje
- Analizar el contenido reciente del canal para proporcionar respuestas relevantes
- Despues de recibir mi respuesta, haz clic en:
  - **SI** si tu pregunta fue respondida satisfactoriamente
  - **NO** si necesitas mas ayuda (tu consulta sera escalada al dueno)

**Consejos:**
- Se especifico en tus preguntas
- Tengo acceso a mensajes de las ultimas 24 horas
- Si no puedo ayudarte, el dueno del canal te asistira directamente

**Difusiones:**
Cuando el dueno del canal publica mensajes importantes, recibiras una notificacion despues de un breve retraso.

Necesitas mas ayuda? Solo pregunta!"""
    
    await update.message.reply_markdown_v2(escape_markdown(help_message))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /stats command - show broadcast stats (owner only)."""
    if not update.message or not update.message.from_user:
        return
    
    config = get_config()
    user = update.message.from_user
    
    # Only owner can view stats
    if not is_owner(user.id, user.username, config):
        await update.message.reply_text("?? Este comando solo esta disponible para el dueno del canal.")
        return
    
    subscriber_manager = get_subscriber_manager()
    subscriber_count = subscriber_manager.get_subscriber_count()
    
    # Get channel context stats
    ctx_manager = get_channel_context_manager()
    message_count = ctx_manager.get_message_count() if ctx_manager else 0
    recent_messages = ctx_manager.get_recent_messages(5) if ctx_manager else []
    
    stats_message = f""" **Estadisticas del Bot**

**Suscriptores:** {subscriber_count} usuarios activos
**Mensajes del Canal Almacenados:** {message_count} mensajes

**Estado de Difusion:** {"En ejecucion" if broadcast_manager and broadcast_manager._running else "Detenido"}
**Difusiones Pendientes:** {len(broadcast_manager.get_pending_broadcasts()) if broadcast_manager else 0}
**Difusiones Completadas:** {len(broadcast_manager.get_completed_broadcasts()) if broadcast_manager else 0}

**Ventana de Contexto:** {config.context.context_hours} horas
"""
    
    await update.message.reply_markdown_v2(escape_markdown(stats_message))


async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /context command - show current channel context (owner only)."""
    if not update.message or not update.message.from_user:
        return
    
    config = get_config()
    user = update.message.from_user
    
    # Only owner can view context
    if not is_owner(user.id, user.username, config):
        await update.message.reply_text("Este comando solo esta disponible para el dueno del canal.")
        return
    
    ctx_manager = get_channel_context_manager()
    if not ctx_manager:
        await update.message.reply_text("**Gestor de contexto no inicializado.**")
        return
    
    messages = ctx_manager.get_recent_messages(10)
    message_count = ctx_manager.get_message_count()
    
    if not messages:
        await update.message.reply_text("**No hay mensajes del canal almacenados en el contexto!**")
        return

    response = f"**Mensajes del Canal Almacenados ({message_count} en total)**\n\n"
    
    for msg in messages:
        date_str = msg.date.strftime("%Y-%m-%d %H:%M")
        text_preview = msg.text[:200] + "..." if len(msg.text) > 200 else msg.text
        response += f"**[{date_str}]**\n{text_preview}\n\n"
    
    # Split if too long
    if len(response) > 4000:
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for chunk in chunks:
            await update.message.reply_markdown_v2(escape_markdown(chunk))
    else:
        await update.message.reply_markdown_v2(escape_markdown(response))


# ---------------------------
# Message Handlers
# ---------------------------
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle new posts in the channel.
    1. Store the message in local context storage (for RAG)
    2. Schedule broadcast for owner messages
    
    IMPORTANT: This handler captures messages posted in the channel.
    In Telegram channels, posts are typically from the owner/admins.
    """
    global broadcast_manager
    
    # Check for channel post
    if not update.channel_post:
        return
    
    config = get_config()
    message = update.channel_post
    
    # Get the channel ID from the message
    channel_id = str(message.chat_id)
    expected_channel_id = config.telegram.channel_id
    
    # Normalize channel IDs for comparison
    # Handle both @username and -100... formats
    if expected_channel_id.startswith("@"):
        # Compare by username
        chat_username = message.chat.username
        if chat_username:
            expected_username = expected_channel_id[1:]  # Remove @
            if chat_username.lower() != expected_username.lower():
                logger.debug(f"Channel mismatch: {chat_username} vs {expected_username}")
                return
        else:
            # Can't verify by username, allow it
            pass
    else:
        # Compare by ID
        if channel_id != expected_channel_id:
            logger.debug(f"Channel ID mismatch: {channel_id} vs {expected_channel_id}")
            return
    
    # Get message text
    message_text = message.text or message.caption or ""
    
    if not message_text:
        logger.debug("Empty message text, skipping")
        return
    
    # ========== STORE MESSAGE IN CONTEXT STORAGE ==========
    # This is critical for the RAG system to work properly
    context_mgr = get_channel_context_manager()
    if context_mgr:
        await context_mgr.store_message(
            message_id=message.message_id,
            text=message_text,
            date=message.date or datetime.now(),
            sender_id=None,  # Channel posts don't have individual sender IDs
            sender_name="Channel",
            is_owner=True  # Assume all channel posts are from owner
        )
        logger.info(f"Mensaje del canal {message.message_id} almacenado en contexto")
    else:
        logger.warning("Gestor de contexto no inicializado - el mensaje NO fue almacenado!")
    
    # ========== SCHEDULE BROADCAST ==========
    if broadcast_manager:
        await broadcast_manager.schedule_broadcast(
            message_id=message.message_id,
            message_text=message_text,
            channel_id=channel_id,
            original_time=message.date or datetime.now()
        )
        logger.info(f"Difusion programada para la publicacion del canal {message.message_id}")
    else:
        logger.warning("Gestor de broadcast no inicializado!")


async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle private messages to the bot.
    This is the main query handling flow with queue-based processing.
    """
    global escalation_manager
    
    if not update.message or not update.message.text:
        return
    
    user = update.message.from_user
    user_text = update.message.text
    
    # Ignore commands
    if user_text.startswith("/"):
        return
    
    # Register user as subscriber
    await register_user_subscriber(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    logger.info(f"Query from user {user.id} (@{user.username}): {user_text[:100]}...")
    
    # Send temporary "processing" message
    processing_msg = await update.message.reply_markdown_v2(
        escape_markdown("Procesando tu solicitud...\n\n_Analizando mensajes recientes del canal para darte la mejor respuesta._")
    )
    
    try:
        # Get channel context (synchronous now)
        context_str = get_context_for_query()
        
        # Log context for debugging
        logger.info(f"Context preview: {context_str[:200]}..." if len(context_str) > 200 else f"Context: {context_str}")
        
        # Create a Future for the LLM result
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Create and enqueue request
        request = LLMRequest(
            update=update,
            future=future,
            user_question=user_text,
            context=context_str
        )
        
        await llm_queue.put(request)
        
        # Wait for LLM API result with timeout
        llm_response: LLMResponse = await asyncio.wait_for(future, timeout=300)  # 5 minutes
        
        if not llm_response.success:
            await processing_msg.edit_text(
                f"Lo siento, encontre un error procesando tu solicitud.\n\n"
                f"Error: {llm_response.error_message}"
            )
            return
        
        # Delete "processing" message
        try:
            await processing_msg.delete()
        except Exception:
            pass
        
        # Send the response with satisfaction buttons
        response_text = llm_response.content
        
        # Add prompt for feedback
        response_with_feedback = f"{response_text}\n\n---\n_Ha respondido esto a tu pregunta?_"
        
        keyboard = create_satisfaction_keyboard()
        
        bot_message = await update.message.reply_markdown_v2(
            escape_markdown(response_with_feedback),
            reply_markup=keyboard
        )
        
        # Register the query for potential escalation
        if escalation_manager:
            await escalation_manager.register_query(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                question=user_text,
                bot_response=response_text,
                message_id=bot_message.message_id
            )
        
        # Increment query count
        subscriber_manager = get_subscriber_manager()
        await subscriber_manager.increment_query_count(user.id)
        
    except asyncio.TimeoutError:
        try:
            await processing_msg.edit_text(
                "El modelo tarda demasiado en responder. Por favor, intentalo nuevamente mas tarde."
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(
                f"Ocurrio un error mientras se procesaba tu solicitud.\n\n"
                f"Por favor, intantalo de nuevo o contacta al administrador del canal."
            )
        except Exception:
            pass


# ---------------------------
# Callback Query Handlers
# ---------------------------
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle inline button callbacks (satisfaction feedback).
    """
    global escalation_manager
    
    query = update.callback_query
    if not query or not query.message:
        return
    
    await query.answer()  # Acknowledge the callback
    
    # Parse the callback data
    satisfied = parse_satisfaction_callback(query.data)
    
    if satisfied is None:
        logger.warning(f"Unknown callback data: {query.data}")
        return
    
    # Get the original message
    message = query.message
    
    if satisfied:
        # User is satisfied
        # Remove the keyboard and update the message
        try:
            await message.edit_text(
                message.text + "\n\n _Thank you for your feedback!_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[]])  # Remove keyboard
            )
        except Exception:
            pass
        
        # Mark query as resolved
        if escalation_manager:
            await escalation_manager.handle_user_satisfaction(
                message_id=message.message_id,
                satisfied=True
            )
    else:
        # User is not satisfied - escalate
        user = query.from_user
        
        # Update message to show escalation
        try:
            await message.edit_text(
                message.text + "\n\n _Your query has been escalated to the owner._",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[]])  # Remove keyboard
            )
        except Exception:
            pass
        
        # Process escalation
        if escalation_manager:
            escalated_query = await escalation_manager.handle_user_satisfaction(
                message_id=message.message_id,
                satisfied=False
            )
            
            if escalated_query:
                # Send acknowledgment to user
                await escalation_manager.send_acknowledgment_to_user(
                    user_id=user.id,
                    query=escalated_query
                )


# ---------------------------
# Error Handler
# ---------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Excepcion mientras se manejaba una actualizacion: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "Ocurrio un error inesperado. Por favor, intentalo de nuevo mas tarde."
            )
        except Exception:
            pass


# ---------------------------
# Main Application
# ---------------------------
async def post_init(application):
    """Initialize managers and start background tasks after bot initialization."""
    global channel_context_manager, broadcast_manager, escalation_manager, llm_client
    global bot_user_id, owner_user_id
    
    config = get_config()
    bot = application.bot
    
    # Get bot's user ID
    bot_user = await bot.get_me()
    bot_user_id = bot_user.id
    logger.info(f"Bot user ID: {bot_user_id}")
    
    # Initialize subscriber manager with storage path
    storage_path = str(BASE_DIR / "data" / "subscribers.json")
    init_subscriber_manager(storage_path)
    
    # Initialize channel context manager (local storage - no bot needed)
    init_channel_context_manager()
    channel_context_manager = get_channel_context_manager()
    
    # Initialize other managers
    broadcast_manager = BroadcastManager(bot)
    escalation_manager = EscalationManager(bot)
    llm_client = LLMClient()
    
    # Set excluded IDs for broadcast
    # Owner ID will be set when they start the bot
    broadcast_manager.set_excluded_ids(owner_id=None, bot_id=bot_user_id)
    
    # Start broadcast manager
    await broadcast_manager.start()
    
    # Start LLM worker
    loop = asyncio.get_running_loop()
    loop.create_task(llm_worker())
    
    logger.info("Bot inicializado correctamente")
    logger.info(f"   - Retraso de broadcast: {config.broadcast.delay_hours} horas")
    logger.info(f"   - Ventana de contexto: {config.context.context_hours} horas")
    logger.info(f"   - Suscriptores activos: {broadcast_manager.get_subscriber_count()}")
    logger.info(f"   - Mensajes del canal almacenados: {channel_context_manager.get_message_count()}")


async def post_shutdown(application):
    """Cleanup on shutdown."""
    global broadcast_manager
    
    if broadcast_manager:
        await broadcast_manager.stop()
    
    logger.info("Bot shutdown complete")


def main():
    """Main entry point for the Telegram bot."""
    # Load configuration
    config = get_config()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    # Build the application
    application = (
        ApplicationBuilder()
        .token(config.telegram.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("context", context_command))
    
    # Channel post handler - captures messages posted in the channel
    # This is triggered when someone posts in a channel where the bot is admin
    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, handle_channel_post)
    )
    
    # Private messages (queries from users)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_private_message
        )
    )
    
    # Callback query handler (for satisfaction buttons)
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    logger.info("**Starting bot...**")
    logger.info(f"   - Channel: {config.telegram.channel_id}")
    logger.info(f"   - Owner: {config.telegram.owner_username}")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
