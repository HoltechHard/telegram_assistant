"""
Broadcast Manager Module for Telegram Bot System.
This module handles the delayed broadcast of channel messages to all tracked subscribers.
When the owner posts a message in the channel, after a configurable delay (default 1 hour),
the bot will broadcast a notification to all registered subscribers.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from telegram import Bot
from telegram.error import TelegramError, Forbidden, BadRequest

from settings.config import get_config
from managers.subscriber_manager import get_subscriber_manager, SubscriberManager

logger = logging.getLogger(__name__)


def get_utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def ensure_timezone_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (add UTC if naive)."""
    if dt is None:
        return get_utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class ScheduledBroadcast:
    """Represents a scheduled broadcast message."""
    message_id: int
    message_text: str
    channel_id: str
    scheduled_time: datetime
    original_time: datetime
    photo_file_id: Optional[str] = None  # Photo media reference for image posts
    voice_file_id: Optional[str] = None  # Voice media reference for voice posts
    audio_file_id: Optional[str] = None  # Audio media reference for audio posts
    completed: bool = False
    completed_at: Optional[datetime] = None
    sent_to: List[int] = field(default_factory=list)
    failed_for: List[int] = field(default_factory=list)
    error_log: List[str] = field(default_factory=list)


class BroadcastManager:
    """
    Manages the scheduling and execution of broadcast messages.
    
    This class handles:
    - Scheduling broadcasts when the owner posts in the channel
    - Using tracked subscribers from SubscriberManager
    - Sending broadcast messages after the configured delay
    - Handling failed deliveries (blocked users, etc.)
    """
    
    def __init__(self, bot: Bot):
        """
        Initialize the BroadcastManager.
        
        Args:
            bot: The Telegram Bot instance
        """
        self.bot = bot
        self.config = get_config()
        self.broadcast_config = self.config.broadcast
        
        # Get subscriber manager
        self.subscriber_manager = get_subscriber_manager()
        
        # Store scheduled broadcasts: message_id -> ScheduledBroadcast
        self._scheduled: Dict[int, ScheduledBroadcast] = {}
        
        # Background task reference
        self._task: Optional[asyncio.Task] = None
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Running flag
        self._running = False
        
        # IDs to exclude from broadcast (owner, bot)
        self._exclude_ids: Set[int] = set()
        
        logger.info(f"BroadcastManager initialized with {self.broadcast_config.delay_hours}h delay")
    
    def set_excluded_ids(self, owner_id: Optional[int], bot_id: Optional[int]) -> None:
        """
        Set user IDs to exclude from broadcasts.
        
        Args:
            owner_id: The owner's user ID
            bot_id: The bot's user ID
        """
        if owner_id:
            self._exclude_ids.add(owner_id)
        if bot_id:
            self._exclude_ids.add(bot_id)
        logger.info(f"Excluded IDs from broadcast: {self._exclude_ids}")
    
    async def start(self) -> None:
        """Start the broadcast manager background task."""
        if self._running:
            logger.warning("BroadcastManager is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._broadcast_worker())
        logger.info("BroadcastManager started - worker running")
    
    async def stop(self) -> None:
        """Stop the broadcast manager background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BroadcastManager stopped")
    
    async def _broadcast_worker(self) -> None:
        """Background worker that processes scheduled broadcasts."""
        logger.info("Broadcast worker started")
        
        while self._running:
            try:
                await self._process_scheduled_broadcasts()
                # Check every 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("Broadcast worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in broadcast worker: {e}", exc_info=True)
                await asyncio.sleep(60)
        
        logger.info("Broadcast worker stopped")
    
    async def _process_scheduled_broadcasts(self) -> None:
        """Process all scheduled broadcasts that are due."""
        now = get_utc_now()
        
        # Get broadcasts to process
        async with self._lock:
            to_process = [
                broadcast for broadcast in self._scheduled.values()
                if not broadcast.completed and ensure_timezone_aware(broadcast.scheduled_time) <= now
            ]
        
        if to_process:
            logger.info(f"Processing {len(to_process)} scheduled broadcasts")
        
        for broadcast in to_process:
            try:
                await self._execute_broadcast(broadcast)
            except Exception as e:
                logger.error(f"Error executing broadcast {broadcast.message_id}: {e}")
    
    async def _execute_broadcast(self, broadcast: ScheduledBroadcast) -> None:
        """
        Execute a scheduled broadcast to all tracked subscribers.
        
        Args:
            broadcast: The scheduled broadcast to execute
        """
        logger.info(f"Executing broadcast for message {broadcast.message_id}")
        if broadcast.photo_file_id:
            logger.info(f"Message has photo: {broadcast.photo_file_id}")
        logger.info(f"Message preview: {broadcast.message_text[:100]}...")
        
        # Get subscriber IDs (excluding owner and bot)
        subscriber_ids = self.subscriber_manager.get_subscriber_ids(
            active_only=True,
            exclude_ids=self._exclude_ids
        )
        
        if not subscriber_ids:
            logger.warning("No active subscribers to broadcast to!")
            broadcast.error_log.append("No active subscribers found")
            broadcast.completed = True
            broadcast.completed_at = get_utc_now()
            return
        
        logger.info(f"Broadcasting to {len(subscriber_ids)} subscribers")
        
        success_count = 0
        fail_count = 0
        
        for user_id in subscriber_ids:
            try:
                # Send the broadcast message
                await self._send_broadcast_to_user(broadcast, user_id)
                broadcast.sent_to.append(user_id)
                success_count += 1
                
                # Small delay to avoid rate limiting (30 messages per second limit)
                await asyncio.sleep(0.05)
                
            except Forbidden:
                # User has blocked the bot
                logger.warning(f"User {user_id} has blocked the bot - marking inactive")
                broadcast.failed_for.append(user_id)
                broadcast.error_log.append(f"User {user_id} blocked the bot")
                await self.subscriber_manager.mark_blocked(user_id)
                fail_count += 1
                
            except BadRequest as e:
                logger.warning(f"Bad request for user {user_id}: {e}")
                broadcast.failed_for.append(user_id)
                broadcast.error_log.append(f"BadRequest for {user_id}: {str(e)}")
                fail_count += 1
                
            except TelegramError as e:
                logger.warning(f"Telegram error for user {user_id}: {e}")
                broadcast.failed_for.append(user_id)
                broadcast.error_log.append(f"TelegramError for {user_id}: {str(e)}")
                fail_count += 1
                
            except Exception as e:
                logger.error(f"Unexpected error for user {user_id}: {e}")
                broadcast.failed_for.append(user_id)
                broadcast.error_log.append(f"Error for {user_id}: {str(e)}")
                fail_count += 1
        
        # Mark as completed
        broadcast.completed = True
        broadcast.completed_at = get_utc_now()
        
        logger.info(
            f"Broadcast completed: {success_count} sent, {fail_count} failed"
        )
    
    async def _send_broadcast_to_user(
        self,
        broadcast: ScheduledBroadcast,
        user_id: int
    ) -> None:
        """
        Send a broadcast message to a specific user.
        
        Args:
            broadcast: The broadcast to send
            user_id: The user ID to send to
        """
        # Get subscriber info for personalized greeting
        subscriber = self.subscriber_manager.get_subscriber(user_id)
        if subscriber:
            user_mention = subscriber.display_name
        else:
            user_mention = f"User"
        
        # Create the broadcast message payload
        greeting = (
            f"**{user_mention}, tienes un nuevo mensaje importante!**\n\n"
            f"**Mensaje del canal:**\n"
        )
        footer = (
            f"\n\n---\n"
            f"_Esta es una notificacion automatica del canal._"
        )

        content_text = broadcast.message_text or ""

        full_message = f"{greeting}{content_text}{footer}"

        # Select send method prioritizing voice/audio over photo, if present
        if broadcast.voice_file_id:
            # send voice with caption
            if len(full_message) > 1024:
                full_message = full_message[:1021] + "..."

            await self.bot.send_voice(
                chat_id=user_id,
                voice=broadcast.voice_file_id,
                caption=full_message,
                parse_mode="Markdown"
            )

        elif broadcast.audio_file_id:
            # send audio with caption
            if len(full_message) > 1024:
                full_message = full_message[:1021] + "..."

            await self.bot.send_audio(
                chat_id=user_id,
                audio=broadcast.audio_file_id,
                caption=full_message,
                parse_mode="Markdown"
            )

        elif broadcast.photo_file_id:
            # send photo with caption
            if len(full_message) > 1024:
                full_message = full_message[:1021] + "..."

            await self.bot.send_photo(
                chat_id=user_id,
                photo=broadcast.photo_file_id,
                caption=full_message,
                parse_mode="Markdown"
            )

        else:
            # send as text only
            if len(full_message) > 4096:
                full_message = full_message[:4093] + "..."

            await self.bot.send_message(
                chat_id=user_id,
                text=full_message,
                parse_mode="Markdown"
            )
    
    async def schedule_broadcast(
        self,
        message_id: int,
        message_text: str,
        channel_id: str,
        original_time: Optional[datetime] = None,
        delay_hours: Optional[int] = None,
        photo_file_id: Optional[str] = None,
        voice_file_id: Optional[str] = None,
        audio_file_id: Optional[str] = None
    ) -> ScheduledBroadcast:
        """
        Schedule a new broadcast message.
        
        Args:
            message_id: The original message ID in the channel
            message_text: The text content of the message
            channel_id: The channel ID where the message was posted
            original_time: The time the message was posted (defaults to now)
            delay_hours: Override the configured delay hours
            
        Returns:
            ScheduledBroadcast: The scheduled broadcast object
        """
        # Ensure timezone-aware datetimes
        original_time = ensure_timezone_aware(original_time) if original_time else get_utc_now()
        delay = delay_hours if delay_hours is not None else self.broadcast_config.delay_hours
        scheduled_time = original_time + timedelta(hours=delay)
        
        broadcast = ScheduledBroadcast(
            message_id=message_id,
            message_text=message_text,
            channel_id=channel_id,
            scheduled_time=scheduled_time,
            original_time=original_time,
            photo_file_id=photo_file_id,
            voice_file_id=voice_file_id,
            audio_file_id=audio_file_id
        )
        
        async with self._lock:
            self._scheduled[message_id] = broadcast
        
        logger.info(
            f"Scheduled broadcast for message {message_id} "
            f"at {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(in {delay} hours)"
        )
        
        return broadcast
    
    def cancel_broadcast(self, message_id: int) -> bool:
        """
        Cancel a scheduled broadcast.
        
        Args:
            message_id: The message ID to cancel
            
        Returns:
            bool: True if cancelled, False if not found or already completed
        """
        broadcast = self._scheduled.get(message_id)
        if broadcast and not broadcast.completed:
            del self._scheduled[message_id]
            logger.info(f"Cancelled broadcast for message {message_id}")
            return True
        return False
    
    def get_scheduled_broadcasts(self) -> List[ScheduledBroadcast]:
        """Get all scheduled broadcasts."""
        return list(self._scheduled.values())
    
    def get_pending_broadcasts(self) -> List[ScheduledBroadcast]:
        """Get all pending (not completed) broadcasts."""
        return [b for b in self._scheduled.values() if not b.completed]
    
    def get_completed_broadcasts(self) -> List[ScheduledBroadcast]:
        """Get all completed broadcasts."""
        return [b for b in self._scheduled.values() if b.completed]
    
    def get_subscriber_count(self) -> int:
        """Get the current number of active subscribers."""
        return self.subscriber_manager.get_subscriber_count(active_only=True)


# Convenience function for immediate broadcast (for testing)
async def broadcast_immediately(
    bot: Bot,
    message_text: str,
    user_ids: List[int]
) -> Dict[int, bool]:
    """
    Immediately broadcast a message to specified users.
    
    Args:
        bot: The Telegram Bot instance
        message_text: The message to broadcast
        user_ids: List of user IDs to send to
        
    Returns:
        Dict[int, bool]: Map of user_id -> success status
    """
    results = {}
    
    for user_id in user_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="Markdown"
            )
            results[user_id] = True
            await asyncio.sleep(0.05)  # Rate limiting
        except Exception as e:
            logger.error(f"Failed to broadcast to {user_id}: {e}")
            results[user_id] = False
    
    return results
