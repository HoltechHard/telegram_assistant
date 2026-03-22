import asyncio
import logging
from rag.llm_client import query_llm_with_context, LLMResponse
from managers.subscriber_manager import get_subscriber_manager
from managers.escalation_manager import create_satisfaction_keyboard
from utils import shared
from utils.helper_functionals import prepare_llm_response

logger = logging.getLogger(__name__)

async def queue_worker(worker_id: int):
    """
    Worker that continuously pops questions from the Redis priority queue
    and processes them through the LLM.
    """
    logger.info(f"Worker-{worker_id} started")

    while True:
        try:
            # Pop highest priority question from Redis
            question_data = await asyncio.to_thread(shared.priority_queue.dequeue)

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
            await shared.rate_limiter.acquire()

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
                    shared.priority_queue.mark_failed, question_id, str(e)
                )
                await shared.question_store.mark_failed(question_id)
                try:
                    await shared._shared_bot.send_message(
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
                    await shared._shared_bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "Lo siento, encontre un error procesando "
                            "tu solicitud.\n\n"
                            f"Error: {llm_response.error_message}"
                        )
                    )
                    await asyncio.to_thread(
                        shared.priority_queue.mark_failed,
                        question_id,
                        llm_response.error_message or "LLM error"
                    )
                    await shared.question_store.mark_failed(question_id)
                    continue

                # Build response with feedback prompt
                response_text = llm_response.content
                response_with_feedback = (
                    f"{response_text}\n\n---\n"
                    "Ha respondido esto a tu pregunta?"
                )

                keyboard = create_satisfaction_keyboard()

                bot_message = await shared._shared_bot.send_message(
                    chat_id=chat_id,
                    text=prepare_llm_response(response_with_feedback),
                    parse_mode="MarkdownV2",
                    reply_markup=keyboard
                )

                # Register for escalation tracking
                if shared.escalation_manager:
                    # Look up subscriber to get username/first_name
                    sub_mgr = get_subscriber_manager()
                    subscriber = sub_mgr.get_subscriber(user_id)
                    await shared.escalation_manager.register_query(
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
                    shared.priority_queue.mark_completed, question_id
                )
                await shared.question_store.mark_completed(question_id)

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
                    shared.priority_queue.mark_failed, question_id, str(e)
                )
                await shared.question_store.mark_failed(question_id)

        except asyncio.CancelledError:
            logger.info(f"Worker-{worker_id} cancelled")
            break
        except Exception as e:
            logger.error(
                f"Worker-{worker_id} unexpected error: {e}",
                exc_info=True
            )
            await asyncio.sleep(2.0)
