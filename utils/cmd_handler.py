import logging
from telegram import Update
from telegram.ext import ContextTypes
from settings.config import get_config
from managers.subscriber_manager import get_subscriber_manager
from rag.channel_context import get_channel_context_manager
from utils import shared
from utils.helper_functionals import (
    is_owner, 
    register_user_subscriber, 
    escape_markdown
)

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if is_owner(user.id, user.username, config):
        shared.owner_user_id = user.id
        if shared.broadcast_manager:
            shared.broadcast_manager.set_excluded_ids(
                owner_id=shared.owner_user_id, bot_id=shared.bot_user_id
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    q_size = shared.priority_queue.get_queue_size() if shared.priority_queue else 0
    pending = len(shared.question_store.get_pending()) if shared.question_store else 0
    rate_info = shared.rate_limiter.get_usage() if shared.rate_limiter else {}

    bm_running = shared.broadcast_manager and shared.broadcast_manager._running
    bm_pending = len(shared.broadcast_manager.get_pending_broadcasts()) if shared.broadcast_manager else 0
    bm_done = len(shared.broadcast_manager.get_completed_broadcasts()) if shared.broadcast_manager else 0

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

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /queue command - show queue status."""
    if not update.message:
        return

    q_size = shared.priority_queue.get_queue_size() if shared.priority_queue else 0

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

async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
