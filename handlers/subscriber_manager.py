"""
Subscriber Manager Module for Telegram Bot System.
This module handles tracking and managing users who interact with the bot.
Since Telegram API doesn't expose channel subscriber lists, we track users
who interact with the bot (via /start or asking questions).
"""

import asyncio
import logging
import json
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """Represents a subscriber/user who has interacted with the bot."""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    registered_at: datetime = field(default_factory=datetime.now)
    last_interaction: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    total_queries: int = 0
    
    def update_interaction(self):
        """Update the last interaction timestamp."""
        self.last_interaction = datetime.now()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "registered_at": self.registered_at.isoformat(),
            "last_interaction": self.last_interaction.isoformat(),
            "is_active": self.is_active,
            "total_queries": self.total_queries
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Subscriber":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            user_id=data["user_id"],
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            last_interaction=datetime.fromisoformat(data["last_interaction"]),
            is_active=data.get("is_active", True),
            total_queries=data.get("total_queries", 0)
        )
    
    @property
    def display_name(self) -> str:
        """Get a display name for the user."""
        if self.username:
            return f"@{self.username}"
        parts = [self.first_name, self.last_name]
        return " ".join(filter(None, parts)) or f"User {self.user_id}"


class SubscriberManager:
    """
    Manages the subscriber database.
    Tracks users who interact with the bot for broadcast purposes.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the SubscriberManager.
        
        Args:
            storage_path: Path to the JSON file for persistent storage
        """
        self.storage_path = Path(storage_path or "subscribers.json")
        self._subscribers: Dict[int, Subscriber] = {}
        self._lock = asyncio.Lock()
        
        # Ensure parent directory exists
        parent_dir = self.storage_path.parent
        if parent_dir and not parent_dir.exists():
            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {parent_dir}")
            except Exception as e:
                logger.error(f"Failed to create directory {parent_dir}: {e}")
        
        # Load existing subscribers from file
        self._load_from_file()
    
    def _load_from_file(self) -> None:
        """Load subscribers from the JSON file."""
        if not self.storage_path.exists():
            logger.info("No existing subscriber file found, starting fresh")
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for user_data in data.get("subscribers", []):
                try:
                    subscriber = Subscriber.from_dict(user_data)
                    self._subscribers[subscriber.user_id] = subscriber
                except Exception as e:
                    logger.warning(f"Failed to load subscriber: {e}")
            
            logger.info(f"Loaded {len(self._subscribers)} subscribers from file")
            
        except Exception as e:
            logger.error(f"Failed to load subscribers file: {e}")
    
    async def _save_to_file(self) -> None:
        """Save subscribers to the JSON file."""
        try:
            data = {
                "version": 1,
                "last_updated": datetime.now().isoformat(),
                "subscribers": [s.to_dict() for s in self._subscribers.values()]
            }
            
            # Ensure parent directory exists
            parent_dir = self.storage_path.parent
            if parent_dir and not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first
            temp_path = self.storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Use shutil.move for cross-platform reliability
            # This handles the case where temp and final files are on different filesystems
            shutil.move(str(temp_path), str(self.storage_path))
            
            logger.info(f"Saved {len(self._subscribers)} subscribers to {self.storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to save subscribers file: {e}", exc_info=True)
            # Try to clean up temp file if it exists
            try:
                temp_path = self.storage_path.with_suffix(".tmp")
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
    
    async def register_subscriber(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Subscriber:
        """
        Register a new subscriber or update an existing one.
        
        Args:
            user_id: The user's Telegram ID
            username: The user's Telegram username
            first_name: The user's first name
            last_name: The user's last name
            
        Returns:
            Subscriber: The registered subscriber
        """
        async with self._lock:
            if user_id in self._subscribers:
                # Update existing subscriber
                subscriber = self._subscribers[user_id]
                subscriber.update_interaction()
                subscriber.is_active = True
                
                # Update name info if provided
                if username:
                    subscriber.username = username
                if first_name:
                    subscriber.first_name = first_name
                if last_name:
                    subscriber.last_name = last_name
            else:
                # Create new subscriber
                subscriber = Subscriber(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                self._subscribers[user_id] = subscriber
                logger.info(f"New subscriber registered: {subscriber.display_name}")
            
            await self._save_to_file()
            return subscriber
    
    async def increment_query_count(self, user_id: int) -> None:
        """Increment the query count for a user."""
        async with self._lock:
            if user_id in self._subscribers:
                self._subscribers[user_id].total_queries += 1
                self._subscribers[user_id].update_interaction()
                await self._save_to_file()
    
    async def deactivate_subscriber(self, user_id: int) -> None:
        """Mark a subscriber as inactive (e.g., if they block the bot)."""
        async with self._lock:
            if user_id in self._subscribers:
                self._subscribers[user_id].is_active = False
                await self._save_to_file()
                logger.info(f"Subscriber {user_id} deactivated")
    
    async def remove_subscriber(self, user_id: int) -> bool:
        """Remove a subscriber completely."""
        async with self._lock:
            if user_id in self._subscribers:
                del self._subscribers[user_id]
                await self._save_to_file()
                logger.info(f"Subscriber {user_id} removed")
                return True
        return False
    
    def get_subscriber(self, user_id: int) -> Optional[Subscriber]:
        """Get a subscriber by user ID."""
        return self._subscribers.get(user_id)
    
    def get_all_subscribers(self) -> List[Subscriber]:
        """Get all subscribers."""
        return list(self._subscribers.values())
    
    def get_active_subscribers(self) -> List[Subscriber]:
        """Get all active subscribers."""
        return [s for s in self._subscribers.values() if s.is_active]
    
    def get_subscriber_ids(self, active_only: bool = True, exclude_ids: Optional[Set[int]] = None) -> List[int]:
        """
        Get list of subscriber user IDs.
        
        Args:
            active_only: If True, only return active subscribers
            exclude_ids: Set of user IDs to exclude (e.g., owner, bot)
            
        Returns:
            List[int]: List of user IDs
        """
        exclude_ids = exclude_ids or set()
        
        subscribers = self.get_active_subscribers() if active_only else self.get_all_subscribers()
        return [s.user_id for s in subscribers if s.user_id not in exclude_ids]
    
    def get_subscriber_count(self, active_only: bool = True) -> int:
        """Get the total number of subscribers."""
        return len(self.get_active_subscribers()) if active_only else len(self._subscribers)
    
    async def mark_blocked(self, user_id: int) -> None:
        """Mark a user as having blocked the bot."""
        await self.deactivate_subscriber(user_id)


# Global subscriber manager instance
_subscriber_manager: Optional[SubscriberManager] = None


def get_subscriber_manager() -> SubscriberManager:
    """Get or create the global subscriber manager instance."""
    global _subscriber_manager
    if _subscriber_manager is None:
        _subscriber_manager = SubscriberManager()
    return _subscriber_manager


def init_subscriber_manager(storage_path: Optional[str] = None) -> SubscriberManager:
    """Initialize the global subscriber manager with optional storage path."""
    global _subscriber_manager
    _subscriber_manager = SubscriberManager(storage_path)
    return _subscriber_manager
