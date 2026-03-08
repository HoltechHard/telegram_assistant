"""
Rate Limiter Module.
Token-bucket style rate limiter to enforce LLM API rate limits (e.g., 10 RPM).
Uses a sliding window of timestamps to track request frequency.
"""

import time
import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Async rate limiter using a sliding window approach.
    
    Limits the number of requests per minute (RPM) to avoid exceeding 
    the LLM API rate limit. Workers call `await acquire()` before each 
    LLM call; if the limit would be exceeded, the call blocks until 
    a slot becomes available.
    """
    
    def __init__(self, max_rpm: int = 10):
        """
        Initialize the rate limiter.
        
        Args:
            max_rpm: Maximum requests per minute (default: 10)
        """
        self.max_rpm = max_rpm
        self.window_seconds = 60.0
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()
        
        logger.info(f"RateLimiter initialized: max {max_rpm} requests/minute")
    
    async def acquire(self) -> None:
        """
        Acquire a rate limiter token. Blocks if rate limit would be exceeded.
        
        This method is safe to call from multiple concurrent workers.
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                
                # Remove timestamps outside the sliding window
                window_start = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < window_start:
                    self._timestamps.popleft()
                
                # Check if we can proceed
                if len(self._timestamps) < self.max_rpm:
                    self._timestamps.append(now)
                    logger.debug(
                        f"Rate limiter: token acquired "
                        f"({len(self._timestamps)}/{self.max_rpm} used)"
                    )
                    return
                
                # Calculate wait time until the oldest request exits the window
                wait_time = self._timestamps[0] - window_start
            
            # Wait outside the lock to avoid blocking other callers
            logger.info(
                f"Rate limiter: limit reached ({self.max_rpm} RPM). "
                f"Waiting {wait_time:.1f}s..."
            )
            await asyncio.sleep(wait_time + 0.1)  # Small buffer
    
    def get_usage(self) -> dict:
        """
        Get current rate limiter usage info.
        
        Returns:
            dict: Current usage statistics
        """
        now = time.monotonic()
        window_start = now - self.window_seconds
        active_count = sum(1 for t in self._timestamps if t >= window_start)
        
        return {
            "current_rpm": active_count,
            "max_rpm": self.max_rpm,
            "available": self.max_rpm - active_count,
        }
