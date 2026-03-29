from typing import Optional, List
import asyncio
from telegram import Bot

# Global Managers
channel_context_manager = None
broadcast_manager = None
escalation_manager = None
llm_client = None

# Queue infrastructure
priority_queue = None
question_store = None
rate_limiter = None

# Multimodal Ingestion Managers
media_downloader = None
multimodal_processor = None

# Speech Ingestion Managers
speech_downloader = None
audio_processor = None

# Shared bot reference (set in post_init, used by workers)
_shared_bot: Optional[Bot] = None

# IDs to track
owner_user_id: Optional[int] = None
bot_user_id: Optional[int] = None

# Worker tasks
_worker_tasks: List[asyncio.Task] = []
