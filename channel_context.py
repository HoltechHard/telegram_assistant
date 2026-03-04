"""
Channel Context Module for Telegram Bot System.
This module handles storing and retrieving channel messages as context for the RAG system.

IMPORTANT: Instead of fetching from Telegram API (which is unreliable for channels),
we store messages locally as they arrive and read from local storage.
This is more reliable, faster, and always up-to-date.
"""

import asyncio
import logging
import json
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path

from config import get_config, BASE_DIR

logger = logging.getLogger(__name__)


def get_utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def ensure_timezone_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (add UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class ChannelMessage:
    """Represents a single message from the Telegram channel."""
    message_id: int
    text: str
    date: datetime
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    is_owner: bool = False
    
    def to_context_string(self) -> str:
        """Convert message to a formatted string for context."""
        sender_label = "Owner" if self.is_owner else (self.sender_name or "Channel")
        date_str = self.date.strftime("%Y-%m-%d %H:%M:%S")
        return f"[{date_str}] {sender_label}: {self.text}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "text": self.text,
            "date": self.date.isoformat(),
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "is_owner": self.is_owner
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChannelMessage":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            message_id=data["message_id"],
            text=data["text"],
            date=datetime.fromisoformat(data["date"]),
            sender_id=data.get("sender_id"),
            sender_name=data.get("sender_name"),
            is_owner=data.get("is_owner", True)
        )


@dataclass
class ChannelContext:
    """Represents the collected context from the channel."""
    messages: List[ChannelMessage] = field(default_factory=list)
    collected_at: datetime = field(default_factory=get_utc_now)
    time_range_hours: int = 24
    
    def to_context_string(self) -> str:
        """Convert all messages to a formatted context string for the LLM."""
        if not self.messages:
            return "NO_CHANNEL_CONTEXT: No recent messages found in the channel."
        
        lines = [
            "=== IMPORTANT: CHANNEL CONTEXT INFORMATION ===",
            f"The following {len(self.messages)} message(s) were posted in the Telegram channel recently:",
            f"Time range: Last {self.time_range_hours} hours",
            "",
            "Use this information to answer the user's question. If the answer is in these messages, reference them.",
            "",
            "--- CHANNEL MESSAGES ---",
            ""
        ]
        
        for msg in self.messages:
            lines.append(msg.to_context_string())
            lines.append("")  # Add blank line between messages
        
        lines.append("--- END OF CHANNEL MESSAGES ---")
        lines.append("")
        lines.append("IMPORTANT: If the user's question relates to information in these messages, use it!")
        
        return "\n".join(lines)
    
    def get_owner_messages_only(self) -> List[ChannelMessage]:
        """Filter and return only messages from the channel owner."""
        return [msg for msg in self.messages if msg.is_owner]


class ChannelContextManager:
    """
    Manages the storage and retrieval of channel messages for context.
    
    This class uses a LOCAL STORAGE approach instead of fetching from Telegram API:
    1. Messages are stored immediately when they arrive (via store_message())
    2. Messages are read from local JSON file when context is needed
    3. Old messages are automatically cleaned up
    """
    
    def __init__(self):
        """Initialize the ChannelContextManager with local storage."""
        self.config = get_config()
        
        # Storage file path
        self.storage_path = BASE_DIR / "data" / "channel_messages.json"
        
        # Ensure data directory exists
        self._ensure_storage_dir()
        
        # In-memory cache of messages
        self._messages: Dict[int, ChannelMessage] = {}
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Load existing messages from file
        self._load_from_file()
        
        logger.info(f"ChannelContextManager initialized with storage: {self.storage_path}")
    
    def _ensure_storage_dir(self) -> None:
        """Ensure the storage directory exists."""
        parent_dir = self.storage_path.parent
        if parent_dir and not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created storage directory: {parent_dir}")
    
    def _load_from_file(self) -> None:
        """Load messages from the JSON file."""
        if not self.storage_path.exists():
            logger.info("No existing channel messages file, starting fresh")
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for msg_data in data.get("messages", []):
                try:
                    msg = ChannelMessage.from_dict(msg_data)
                    self._messages[msg.message_id] = msg
                except Exception as e:
                    logger.warning(f"Failed to load message: {e}")
            
            logger.info(f"Loaded {len(self._messages)} channel messages from storage")
            
        except Exception as e:
            logger.error(f"Failed to load channel messages file: {e}")
    
    async def _save_to_file(self) -> None:
        """Save messages to the JSON file."""
        try:
            self._ensure_storage_dir()
            
            data = {
                "version": 1,
                "last_updated": get_utc_now().isoformat(),
                "messages": [msg.to_dict() for msg in self._messages.values()]
            }
            
            # Write to temp file first
            temp_path = self.storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Move to final location
            shutil.move(str(temp_path), str(self.storage_path))
            
            logger.debug(f"Saved {len(self._messages)} channel messages to storage")
            
        except Exception as e:
            logger.error(f"Failed to save channel messages: {e}", exc_info=True)
    
    async def store_message(
        self,
        message_id: int,
        text: str,
        date: datetime,
        sender_id: Optional[int] = None,
        sender_name: Optional[str] = None,
        is_owner: bool = True
    ) -> ChannelMessage:
        """
        Store a new channel message.
        This should be called when a new channel post is received.
        
        Args:
            message_id: The Telegram message ID
            text: The message text
            date: The message date/time
            sender_id: The sender's user ID (if available)
            sender_name: The sender's name
            is_owner: Whether this is from the channel owner
            
        Returns:
            ChannelMessage: The stored message
        """
        async with self._lock:
            # Ensure date is timezone-aware
            aware_date = ensure_timezone_aware(date)
            
            msg = ChannelMessage(
                message_id=message_id,
                text=text,
                date=aware_date,
                sender_id=sender_id,
                sender_name=sender_name,
                is_owner=is_owner
            )
            
            self._messages[message_id] = msg
            
            # Clean up old messages
            await self._cleanup_old_messages()
            
            # Save to file
            await self._save_to_file()
            
            logger.info(f"? Stored channel message {message_id}: {text[:50]}...")
            
            return msg
    
    async def _cleanup_old_messages(self) -> None:
        """Remove messages older than the configured time range."""
        hours = self.config.context.context_hours
        cutoff_time = get_utc_now() - timedelta(hours=hours)
        
        old_count = len(self._messages)
        self._messages = {
            msg_id: msg for msg_id, msg in self._messages.items()
            if ensure_timezone_aware(msg.date) >= cutoff_time
        }
        new_count = len(self._messages)
        
        if old_count > new_count:
            logger.info(f"Cleaned up {old_count - new_count} old messages (>{hours}h old)")
    
    def get_context(self, force_refresh: bool = False) -> ChannelContext:
        """
        Get the channel context from local storage.
        
        Args:
            force_refresh: Ignored (kept for API compatibility)
            
        Returns:
            ChannelContext: The collected context from the channel
        """
        hours = self.config.context.context_hours
        cutoff_time = get_utc_now() - timedelta(hours=hours)
        
        # Filter messages within time range and sort by date (oldest first)
        messages = [
            msg for msg in self._messages.values()
            if ensure_timezone_aware(msg.date) >= cutoff_time
        ]
        messages.sort(key=lambda m: m.date)
        
        logger.info(f"?? Retrieved {len(messages)} channel messages for context")
        
        return ChannelContext(
            messages=messages,
            collected_at=get_utc_now(),
            time_range_hours=hours
        )
    
    def get_context_string(self) -> str:
        """
        Get the channel context as a formatted string.
        
        Returns:
            str: The formatted context string for the LLM
        """
        context = self.get_context()
        return context.to_context_string()
    
    def invalidate_cache(self) -> None:
        """Reload messages from file."""
        self._load_from_file()
        logger.info("Context cache invalidated - reloaded from file")
    
    def get_message_count(self) -> int:
        """Get the total number of stored messages."""
        return len(self._messages)
    
    def get_recent_messages(self, limit: int = 10) -> List[ChannelMessage]:
        """Get the most recent messages."""
        messages = sorted(self._messages.values(), key=lambda m: m.date, reverse=True)
        return messages[:limit]


# Global instance
_channel_context_manager: Optional[ChannelContextManager] = None


def get_channel_context_manager() -> ChannelContextManager:
    """Get or create the global channel context manager instance."""
    global _channel_context_manager
    if _channel_context_manager is None:
        _channel_context_manager = ChannelContextManager()
    return _channel_context_manager


def init_channel_context_manager() -> ChannelContextManager:
    """Initialize the global channel context manager."""
    global _channel_context_manager
    _channel_context_manager = ChannelContextManager()
    return _channel_context_manager
