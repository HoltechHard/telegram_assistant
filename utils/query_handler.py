import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from managers.category_manager import (
    CATEGORY_CALLBACK_PREFIX,
    parse_category_callback,
    get_category_display_name
)
from managers.escalation_manager import parse_satisfaction_callback
from queue_qa.priority_queue import generate_question_id
from utils import shared
from utils.helper_functionals import get_context_for_query

logger = logging.getLogger(__name__)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def _handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category button press - enqueue to Redis priority queue."""
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
        shared.priority_queue.enqueue,
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

    await shared.question_store.add_question(
        question_id=question_id,
        question_description=pending_question,
        category=category,
        user_id=user.id
    )

    context.user_data.pop("pending_question", None)
    context.user_data.pop("pending_message_id", None)

    q_size = await asyncio.to_thread(shared.priority_queue.get_queue_size)
    cat_display = get_category_display_name(category)

    await query.message.edit_text(
        f"Tu pregunta ha sido anadida a la cola.\n\n"
        f"Categoria: {cat_display}\n"
        f"Posicion en cola: {q_size}\n\n"
        "Recibiras la respuesta cuando sea procesada ...",
        parse_mode="Markdown"
    )

    logger.info(
        f"Question enqueued: {question_id} | "
        f"user={user.id} | category={category} | "
        f"queue_size={q_size}"
    )

async def _handle_satisfaction_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle satisfaction button press (SI/NO)."""
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
        if shared.escalation_manager:
            await shared.escalation_manager.handle_user_satisfaction(
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
        if shared.escalation_manager:
            escalated = await shared.escalation_manager.handle_user_satisfaction(
                message_id=message.message_id, satisfied=False
            )
            if escalated:
                await shared.escalation_manager.send_acknowledgment_to_user(
                    user_id=user.id, query=escalated
                )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
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
