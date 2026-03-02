import os
import asyncio
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from rag.llm_client import query_llm  # Your API-based function

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables.")

# ---------------------------
# Queue Setup
# ---------------------------
@dataclass
class LLMRequest:
    update: "Update"
    future: asyncio.Future  # Future to store LLM result

llm_queue = asyncio.Queue()


async def llm_worker():
    """
    Worker that processes LLM requests sequentially.
    """
    while True:
        request: LLMRequest = await llm_queue.get()
        try:
            # Call the API in a thread (blocking)
            logging.info(f"Sending request to LLM API: {request.update.message.text}")
            llm_result = await asyncio.to_thread(query_llm, request.update.message.text)
            request.future.set_result(llm_result)
        except Exception as e:
            logging.error(f"LLM API error: {e}")
            request.future.set_exception(e)
        finally:
            llm_queue.task_done()


# ---------------------------
# Telegram Handler
# ---------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text

    # Send temporary "processing" message
    processing_msg = await update.message.reply_text("?? Processing your request...")

    # Create a Future for the LLM result
    future = asyncio.get_event_loop().create_future()
    request = LLMRequest(update=update, future=future)

    # Enqueue request
    await llm_queue.put(request)

    try:
        # Wait for LLM API result, with generous timeout
        llm_response = await asyncio.wait_for(future, timeout=600)  # 10 minutes
        logging.info(f"Received LLM response for user: {llm_response[:100]}...")
    except asyncio.TimeoutError:
        await processing_msg.edit_text("?? The model took too long to respond.")
        return
    except Exception as e:
        await processing_msg.edit_text(f"?? LLM API error: {str(e)}")
        return

    # Delete "processing" message
    try:
        await processing_msg.delete()
    except Exception:
        pass

    # Send the API response to user
    try:
        await update.message.reply_text(llm_response)
    except Exception as e:
        logging.error(f"Telegram send error: {str(e)}")


# ---------------------------
# Main
# ---------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add handler for text messages
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    )

    print("Bot running...")

    # Start worker task
    loop = asyncio.get_event_loop()
    loop.create_task(llm_worker())

    # Start polling
    app.run_polling()


if __name__ == "__main__":
    main()
    