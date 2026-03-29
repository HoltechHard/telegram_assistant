"""
Priority Queue Module.
Redis-backed priority queue using Sorted Sets (ZSET) for the question processing system.

Priority mapping:
    Notas       = 1 (highest priority)
    Evaluaciones = 2
    Tareas      = 3
    Otros       = 4 (lowest priority)

Within the same category, FIFO ordering is maintained using a timestamp fraction
added to the category score. This ensures that earlier questions are processed first
when they share the same category.
"""

import time
import logging
import uuid
from typing import Optional, Dict, Any, List

from queue_qa.redis_client import get_redis
from settings.config import get_config

logger = logging.getLogger(__name__)

# Redis key names
QUEUE_KEY = "question_queue"
QUESTION_PREFIX = "question:"

# Category ? priority score mapping
CATEGORY_PRIORITY = {
    "notas": 1,
    "evaluaciones": 2,
    "tareas": 3,
    "otros": 4,
}


def generate_question_id() -> str:
    """Generate a unique question ID."""
    return f"q_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def compute_score(category: str) -> float:
    """
    Compute the composite priority score for a question.
    
    The score combines category priority (integer part) with a normalized
    timestamp fraction (decimal part) so that:
    - Lower category number = higher priority
    - Within the same category, earlier timestamps = lower score (FIFO)
    
    Args:
        category: The question category (notas, evaluaciones, tareas, otros)
        
    Returns:
        float: The composite score for ZADD
    """
    base_priority = CATEGORY_PRIORITY.get(category.lower(), 5)
    # Normalize current time to a fraction in [0, 1)
    # Using modulo to keep the fractional part small and meaningful
    timestamp_fraction = (time.time() % 1_000_000) / 1_000_000
    return base_priority + timestamp_fraction


class PriorityQueueManager:
    """
    Manages the Redis-backed priority queue for user questions.
    
    Uses:
    - Redis Sorted Set (ZSET) for priority ordering
    - Redis Hashes for storing question details
    """
    
    def __init__(self):
        """Initialize the priority queue manager."""
        self.config = get_config()
        self.max_queue_size = self.config.queue.max_queue_size
        self.r = get_redis()
        logger.info(f"PriorityQueueManager initialized (max_size={self.max_queue_size})")
    
    def enqueue(
        self,
        question_id: str,
        question_description: str,
        category: str,
        user_id: int,
        chat_id: int,
        context: str
    ) -> bool:
        """
        Add a question to the priority queue.
        
        Args:
            question_id: Unique question identifier
            question_description: The user's question text
            category: Question category (notas, evaluaciones, tareas, otros)
            user_id: Telegram user ID
            chat_id: Telegram chat ID for response delivery
            context: Channel context string for LLM
            
        Returns:
            bool: True if enqueued successfully, False if queue is full
        """
        # Admission control: check queue size
        current_size = self.r.zcard(QUEUE_KEY)
        if current_size >= self.max_queue_size:
            logger.warning(
                f"Queue full ({current_size}/{self.max_queue_size}). "
                f"Rejecting question {question_id}"
            )
            return False
        
        # Compute priority score
        score = compute_score(category)
        
        # Store question details as a Redis Hash
        question_data = {
            "question_id": question_id,
            "question_description": question_description,
            "category": category,
            "status": "pending",
            "user_id": str(user_id),
            "chat_id": str(chat_id),
            "timestamp": str(time.time()),
            "context": context,
        }
        
        hash_key = f"{QUESTION_PREFIX}{question_id}"
        
        # Use pipeline for atomicity
        pipe = self.r.pipeline()
        pipe.hset(hash_key, mapping=question_data)
        pipe.zadd(QUEUE_KEY, {question_id: score})
        pipe.execute()
        
        logger.info(
            f"Enqueued question {question_id} | "
            f"category={category} | score={score:.6f} | "
            f"queue_size={current_size + 1}"
        )
        return True
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Pop the highest priority question from the queue.
        
        Returns:
            Optional[Dict[str, Any]]: Question data dict, or None if queue is empty
        """
        # Pop the item with the lowest score (highest priority)
        result = self.r.zpopmin(QUEUE_KEY)
        
        if not result:
            return None
        
        question_id, score = result[0]
        
        # Fetch question details from Hash
        hash_key = f"{QUESTION_PREFIX}{question_id}"
        question_data = self.r.hgetall(hash_key)
        
        if not question_data:
            logger.warning(f"Question data missing for {question_id}")
            return None
        
        # Mark as processing in Redis
        self.r.hset(hash_key, "status", "processing")
        
        logger.info(
            f"Dequeued question {question_id} | "
            f"category={question_data.get('category')} | score={score:.6f}"
        )
        
        return question_data
    
    def mark_completed(self, question_id: str) -> None:
        """
        Mark a question as completed and clean up Redis data.
        
        Args:
            question_id: The question ID to mark as completed
        """
        hash_key = f"{QUESTION_PREFIX}{question_id}"
        self.r.hset(hash_key, "status", "completed")
        
        # Set TTL to auto-clean after 1 hour (keep for debugging)
        self.r.expire(hash_key, 3600)
        
        logger.info(f"Question {question_id} marked as completed")
    
    def mark_failed(self, question_id: str, error: str) -> None:
        """
        Mark a question as failed.
        
        Args:
            question_id: The question ID
            error: Error description
        """
        hash_key = f"{QUESTION_PREFIX}{question_id}"
        pipe = self.r.pipeline()
        pipe.hset(hash_key, "status", "failed")
        pipe.hset(hash_key, "error", error)
        pipe.expire(hash_key, 3600)
        pipe.execute()
        
        logger.warning(f"Question {question_id} marked as failed: {error}")
    
    def get_queue_size(self) -> int:
        """Get the current number of items in the queue."""
        return self.r.zcard(QUEUE_KEY)
    
    def get_queue_contents(self) -> List[Dict[str, Any]]:
        """
        Get all items currently in the queue (for debugging/monitoring).
        
        Returns:
            List[Dict[str, Any]]: List of question data dicts with scores
        """
        items = self.r.zrange(QUEUE_KEY, 0, -1, withscores=True)
        result = []
        
        for question_id, score in items:
            hash_key = f"{QUESTION_PREFIX}{question_id}"
            data = self.r.hgetall(hash_key)
            if data:
                data["_score"] = score
                result.append(data)
        
        return result
    
    def clear_queue(self) -> int:
        """
        Clear all items from the queue (for maintenance/testing).
        
        Returns:
            int: Number of items removed
        """
        count = self.r.zcard(QUEUE_KEY)
        
        # Get all question IDs to clean up hashes
        items = self.r.zrange(QUEUE_KEY, 0, -1)
        
        pipe = self.r.pipeline()
        pipe.delete(QUEUE_KEY)
        for question_id in items:
            pipe.delete(f"{QUESTION_PREFIX}{question_id}")
        pipe.execute()
        
        logger.info(f"Queue cleared: {count} items removed")
        return count
