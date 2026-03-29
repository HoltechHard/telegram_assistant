"""
Redis Client Module.
Provides a singleton Redis connection for the application.
"""

import logging
import redis
from typing import Optional

from settings.config import get_config

logger = logging.getLogger(__name__)

# Global Redis instance
_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """
    Get or create the global Redis client instance.
    
    Returns:
        redis.Redis: The Redis client
        
    Raises:
        ConnectionError: If Redis connection fails
    """
    global _redis_client
    
    if _redis_client is None:
        config = get_config()
        redis_config = config.redis
        
        try:
            _redis_client = redis.Redis(
                host=redis_config.host,
                port=redis_config.port,
                db=redis_config.db,
                username=redis_config.username,
                password=redis_config.password,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True
            )
            
            # Validate connection
            _redis_client.ping()
            logger.info(
                f"Redis connected: {redis_config.host}:{redis_config.port}"
            )
            
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            _redis_client = None
            raise ConnectionError(f"Cannot connect to Redis: {e}")
        except Exception as e:
            logger.error(f"Redis initialization error: {e}")
            _redis_client = None
            raise
    
    return _redis_client


def close_redis() -> None:
    """Close the global Redis connection."""
    global _redis_client
    
    if _redis_client is not None:
        try:
            _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
        finally:
            _redis_client = None
