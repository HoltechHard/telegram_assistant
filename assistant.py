import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from rag.llm_client import query_llm

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables.")

# concurrency lock
llm_lock = asyncio.Lock()

# Manage the incoming telegram messages and send to llm
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    # take new user input message
    user_text = update.message.text
    logging.info(f"Received message: {user_text}")

    # Send temporary processing message
    processing_msg = await update.message.reply_text("?? Processing...")

    try:
        # Prevent concurrent LLM overload
        async with llm_lock:
            llm_response = await asyncio.wait_for(
                asyncio.to_thread(query_llm, user_text),
                timeout=300
            )

        logging.info(f"LLM response: {llm_response}")

    except asyncio.TimeoutError:
        logging.error("LLM request timed out.")
        await processing_msg.edit_text("?? The model took too long to respond.")
        return

    except Exception as e:
        logging.error(f"LLM error: {str(e)}")
        await processing_msg.edit_text(f"?? Error: {str(e)}")
        return

    # Delete "Processing..." message
    try:
        await processing_msg.delete()
    except Exception:
        pass

    # Send raw LLM response directly to user
    try:
        await update.message.reply_text(llm_response)
    except Exception as e:
        logging.error(f"Telegram send error: {str(e)}")

def main():
    # create a bot instance
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # add message handler to process all text messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot running...")

    # checks telegram servers for new messages
    app.run_polling()


if __name__ == "__main__":
    main()
