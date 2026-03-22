"""
Escalation Manager Module for Telegram Bot System.
This module handles the escalation of user queries to the channel owner
when the bot's response is not satisfactory (user clicks NO button).
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from settings.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class UserQuery:
    """Represents a user query that may need escalation."""
    query_id: str
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    original_question: str
    bot_response: str
    timestamp: datetime
    escalated: bool = False
    escalated_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class EscalationRecord:
    """Represents an escalation record sent to the owner."""
    escalation_id: str
    query: UserQuery
    sent_to_owner: bool = False
    sent_at: Optional[datetime] = None
    owner_message_id: Optional[int] = None


class EscalationManager:
    """
    Manages the escalation of user queries to the channel owner.
    
    This class handles:
    - Tracking user queries and their satisfaction status
    - Sending escalation notifications to the owner
    - Managing the escalation workflow
    """
    
    def __init__(self, bot: Bot):
        """
        Initialize the EscalationManager.
        
        Args:
            bot: The Telegram Bot instance
        """
        self.bot = bot
        self.config = get_config()
        
        # Store user queries: query_id -> UserQuery
        self._queries: Dict[str, UserQuery] = {}
        
        # Store escalation records: escalation_id -> EscalationRecord
        self._escalations: Dict[str, EscalationRecord] = {}
        
        # Map message_id to query_id for button callback tracking
        self._message_to_query: Dict[int, str] = {}
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Counter for generating IDs
        self._query_counter = 0
        self._escalation_counter = 0
    
    async def _generate_query_id(self) -> str:
        """Generate a unique query ID."""
        async with self._lock:
            self._query_counter += 1
            return f"q_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._query_counter}"
    
    async def _generate_escalation_id(self) -> str:
        """Generate a unique escalation ID."""
        async with self._lock:
            self._escalation_counter += 1
            return f"e_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._escalation_counter}"
    
    async def register_query(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        question: str,
        bot_response: str,
        message_id: int
    ) -> UserQuery:
        """
        Register a new user query for potential escalation tracking.
        
        Args:
            user_id: The user's Telegram ID
            username: The user's Telegram username
            first_name: The user's first name
            question: The user's original question
            bot_response: The bot's response
            message_id: The message ID of the bot's response
            
        Returns:
            UserQuery: The registered query object
        """
        query_id = await self._generate_query_id()
        
        query = UserQuery(
            query_id=query_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            original_question=question,
            bot_response=bot_response,
            timestamp=datetime.now()
        )
        
        async with self._lock:
            self._queries[query_id] = query
            self._message_to_query[message_id] = query_id
        
        logger.info(f"Registered query {query_id} from user {user_id}")
        return query
    
    async def get_query_by_message_id(self, message_id: int) -> Optional[UserQuery]:
        """
        Get a query by the bot's response message ID.
        
        Args:
            message_id: The message ID of the bot's response
            
        Returns:
            Optional[UserQuery]: The query if found, None otherwise
        """
        async with self._lock:
            query_id = self._message_to_query.get(message_id)
            if query_id:
                return self._queries.get(query_id)
        return None
    
    async def handle_user_satisfaction(
        self,
        message_id: int,
        satisfied: bool
    ) -> Optional[UserQuery]:
        """
        Handle the user's satisfaction response from the inline buttons.
        
        Args:
            message_id: The message ID of the bot's response
            satisfied: True if user clicked YES, False if NO
            
        Returns:
            Optional[UserQuery]: The query if found and needs escalation, None otherwise
        """
        query = await self.get_query_by_message_id(message_id)
        
        if not query:
            logger.warning(f"No query found for message_id {message_id}")
            return None
        
        if satisfied:
            # User is satisfied, mark as resolved
            query.resolved = True
            query.resolved_at = datetime.now()
            logger.info(f"Query {query.query_id} resolved - user satisfied")
            return None
        else:
            # User is not satisfied, escalate to owner
            query.escalated = True
            query.escalated_at = datetime.now()
            await self._escalate_to_owner(query)
            return query
            
    def _format_multimodal_question(self, question: str) -> str:
        """
        Extract only the 'Main text' from a multimodal AI transcription.
        
        Args:
            question: The original question string (possibly multimodal)
            
        Returns:
            str: The formatted question
        """
        if "[AI TRANSCRIPTION]:" not in question:
            return question
            
        # Extract Main text using regex
        # Pattern looks for **Main text:** followed by content until the next header or the end of the AI part
        main_text_match = re.search(
            r"\*\*Main text:\*\*\s*(.*?)(?=\s*\*\*|\s*\[ORIGINAL CAPTION\]|$)", 
            question, 
            re.DOTALL | re.IGNORECASE
        )
        
        if not main_text_match:
            # Fallback if structure is unexpected
            return question
            
        main_text = main_text_match.group(1).strip()
        
        # Check for original caption
        caption_match = re.search(r"\[ORIGINAL CAPTION\]:\s*(.*)", question, re.DOTALL)
        if caption_match:
            caption = caption_match.group(1).strip()
            # Only include if it's not the default empty placeholder
            if caption and "(No original caption provided)" not in caption:
                return f"{main_text}\n\n[CAPTION]: {caption}"
                
        return main_text
    
    async def _escalate_to_owner(self, query: UserQuery) -> EscalationRecord:
        """
        Escalate a query to the channel owner.
        
        Args:
            query: The query to escalate
            
        Returns:
            EscalationRecord: The escalation record
        """
        escalation_id = await self._generate_escalation_id()
        
        # Format user mention
        if query.username:
            user_mention = f"@{query.username}"
        else:
            user_mention = query.first_name or f"User {query.user_id}"
        
        # Create escalation message for owner
        escalation_message = f""" **SE REQUIERE ESCALAR**

Un usuario no esta satisfecho con la respuesta del bot y necesita asistencia humana!

**Informacion del Usuario:**
- Nombre: {user_mention}
- ID de Usuario: `{query.user_id}`
- Hora: {query.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

**Pregunta del Usuario:**
```
{self._format_multimodal_question(query.original_question)}
```

**Respuesta del Bot:**
```
{query.bot_response[:500]}{'...' if len(query.bot_response) > 500 else ''}
```

---
Por favor, contacta al usuario directamente para proporcionar una mejor asistencia.
"""
        
        escalation = EscalationRecord(
            escalation_id=escalation_id,
            query=query
        )
        
        try:
            # Try to send to owner's chat ID if configured
            owner_chat_id = self.config.telegram.owner_chat_id
            owner_username = self.config.telegram.owner_username
            
            if owner_chat_id:
                message = await self.bot.send_message(
                    chat_id=owner_chat_id,
                    text=escalation_message,
                    parse_mode="Markdown"
                )
                escalation.owner_message_id = message.message_id
                escalation.sent_to_owner = True
                escalation.sent_at = datetime.now()
                
                logger.info(f"Escalation {escalation_id} sent to owner (chat_id: {owner_chat_id})")
            else:
                # Log that we couldn't send directly
                logger.warning(
                    f"OWNER_CHAT_ID not configured. "
                    f"Cannot send escalation directly. "
                    f"Owner: {owner_username}"
                )
                # Store the escalation for manual review
                escalation.sent_to_owner = False
                logger.info(f"Escalation {escalation_id} recorded but not sent directly")
        
        except TelegramError as e:
            logger.error(f"Failed to send escalation to owner: {e}")
            escalation.sent_to_owner = False
        
        async with self._lock:
            self._escalations[escalation_id] = escalation
        
        return escalation
    
    async def send_acknowledgment_to_user(self, user_id: int, query: UserQuery) -> bool:
        """
        Send an acknowledgment to the user that their query has been escalated.
        
        Args:
            user_id: The user's Telegram ID
            query: The escalated query
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        acknowledgment_message = """ **Gracias por tu comentario!**

Tu consulta ha sido escalada al dueno del canal. Se pondran en contacto contigo directamente para proporcionarte una mejor asistencia.

_Por favor, ten paciencia mientras te conectamos con el experto humano._"""
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=acknowledgment_message,
                parse_mode="Markdown"                
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send acknowledgment to user {user_id}: {e}")
            return False
    
    def get_pending_escalations(self) -> List[EscalationRecord]:
        """Get all escalation records that haven't been sent to the owner."""
        return [
            e for e in self._escalations.values()
            if not e.sent_to_owner
        ]
    
    def get_all_escalations(self) -> List[EscalationRecord]:
        """Get all escalation records."""
        return list(self._escalations.values())
    
    def get_user_queries(self, user_id: int) -> List[UserQuery]:
        """Get all queries from a specific user."""
        return [q for q in self._queries.values() if q.user_id == user_id]
    
    def get_unresolved_queries(self) -> List[UserQuery]:
        """Get all unresolved queries."""
        return [q for q in self._queries.values() if not q.resolved]


def create_satisfaction_keyboard() -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with YES/NO buttons for user satisfaction.
    
    Returns:
        InlineKeyboardMarkup: The keyboard with satisfaction buttons
    """
    keyboard = [
        [
            InlineKeyboardButton("SI", callback_data="satisfied_yes"),
            InlineKeyboardButton("NO", callback_data="satisfied_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def parse_satisfaction_callback(callback_data: str) -> Optional[bool]:
    """
    Parse the callback data from the satisfaction buttons.
    
    Args:
        callback_data: The callback data string
        
    Returns:
        Optional[bool]: True if satisfied, False if not, None if invalid
    """
    if callback_data == "satisfied_yes":
        return True
    elif callback_data == "satisfied_no":
        return False
    return None
