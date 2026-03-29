import redis.asyncio as redis
import json
import uuid
import logging
from settings.config import get_config

logger = logging.getLogger(__name__)

class RedisSpeechQueue:
    def __init__(self):
        config = get_config()
        self.redis = redis.Redis(
            #host=config.speech.redis_host,
            host=config.redis.host,
            port=config.redis.port,
            db=config.speech.redis_db,
            username=config.redis.username, # Resusing QA creds or if they differ
            password=config.redis.password,
            decode_responses=True
        )
        self.queue = config.speech.redis_queue

    async def push(self, audio_path: str, message_id: int):
        job = {
            "id": str(uuid.uuid4()),
            "message_id": message_id,
            "audio_path": audio_path,
        }
        await self.redis.rpush(self.queue, json.dumps(job))
        return job["id"]

    async def pop(self):
        """Async pop using BLPOP"""
        try:
            item = await self.redis.blpop(self.queue, timeout=5)
            if item:
                return json.loads(item[1])
        except Exception as e:
            logger.error(f"Speech Queue Pop Error: {e}")
        return None

    async def close(self):
        await self.redis.close()
