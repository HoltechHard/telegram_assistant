"""
LLM Client Module for Telegram Bot System.
This module handles all interactions with the LLM API, including:
- Loading system prompts
- Integrating context from the Telegram channel
- Managing query construction with question + prompt + context
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from openai import OpenAI

from config import get_config, BASE_DIR

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Represents a response from the LLM."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    success: bool = True
    error_message: Optional[str] = None


class SystemPromptManager:
    """Manages the loading and caching of system prompts."""
    
    def __init__(self, prompt_path: Optional[str] = None):
        """
        Initialize the SystemPromptManager.
        
        Args:
            prompt_path: Optional custom path to the system prompt file
        """
        self.prompt_path = prompt_path or str(BASE_DIR / "rag" / "instruct.md")
        self._cached_prompt: Optional[str] = None
    
    def load_prompt(self, force_reload: bool = False) -> str:
        """
        Load the system prompt from file.
        
        Args:
            force_reload: If True, reload from file even if cached
            
        Returns:
            str: The system prompt content
        """
        if not force_reload and self._cached_prompt:
            return self._cached_prompt
        
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                self._cached_prompt = f.read()
            logger.info(f"Loaded system prompt from {self.prompt_path}")
            return self._cached_prompt
        except FileNotFoundError:
            logger.warning(f"System prompt file not found: {self.prompt_path}")
            # Return default prompt
            default_prompt = self._get_default_prompt()
            self._cached_prompt = default_prompt
            return default_prompt
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Return a default system prompt if no file is found."""
        return """You are a helpful assistant for a Telegram channel community.
Your role is to answer user questions based on the context provided from recent channel messages.
Be helpful, accurate, and concise in your responses.
If you cannot find relevant information in the context, clearly state that and suggest the user contact the channel administrator for more specific information.
Always respond in a friendly and professional manner."""


class LLMClient:
    """
    Main LLM client for handling queries with context integration.
    This class manages the interaction with the LLM API, including
    the construction of prompts with context from the Telegram channel.
    """
    
    def __init__(self):
        """Initialize the LLM client with configuration."""
        self.config = get_config()
        self.llm_config = self.config.llm
        self.prompt_manager = SystemPromptManager()
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.llm_config.api_key,
            base_url=self.llm_config.base_url
        )
        
        logger.info(f"LLM Client initialized with model: {self.llm_config.model}")
    
    def _build_messages(
        self,
        user_question: str,
        context: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """
        Build the messages list for the LLM API call.
        
        Args:
            user_question: The user's question
            context: The context from the Telegram channel
            system_prompt: Optional custom system prompt
            conversation_history: Optional list of previous messages
            
        Returns:
            List[Dict[str, str]]: The messages list for the API call
        """
        # Load system prompt
        base_prompt = system_prompt or self.prompt_manager.load_prompt()
        
        # Enhance system prompt with context instructions
        enhanced_prompt = f"""{base_prompt}

=== CRITICAL INSTRUCTIONS ===
You MUST use the channel context provided below as your PRIMARY source of information.
The context contains REAL messages from the Telegram channel that are relevant to the user's question.

When answering:
1. FIRST check if the answer is in the channel context - if it is, USE IT!
2. Quote or reference specific information from the context
3. If you find relevant information in the context, START your answer with it
4. Only use general knowledge if the context truly doesn't contain the answer
5. Never say "no information" if the context contains relevant data

Format your response in clean Markdown when appropriate.
"""
        
        messages = [
            {"role": "system", "content": enhanced_prompt}
        ]
        
        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add context as a user message (or as part of the prompt)
        # Check if context is empty or just says "no messages"
        has_valid_context = context and "NO_CHANNEL_CONTEXT" not in context and "No recent messages" not in context
        
        if has_valid_context:
            context_message = f"""=== CHANNEL CONTEXT (READ THIS FIRST!) ===

{context}

=== END OF CHANNEL CONTEXT ===

USER QUESTION: {user_question}

INSTRUCTIONS: Look at the CHANNEL CONTEXT above. If the answer to the user's question is there, use it! Extract specific facts, prices, dates, or other details from the context."""
        else:
            logger.warning(f"No valid context available for query: {context[:100] if context else 'None'}")
            context_message = f"""No recent channel context is available.

USER QUESTION: {user_question}

Note: Answer based on your general knowledge, but suggest the user check the channel for the most recent updates."""
        
        messages.append({"role": "user", "content": context_message})
        
        return messages
    
    def query(
        self,
        user_question: str,
        context: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """
        Query the LLM with a question and context.
        
        Args:
            user_question: The user's question
            context: The context from the Telegram channel
            system_prompt: Optional custom system prompt
            conversation_history: Optional list of previous messages
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            
        Returns:
            LLMResponse: The response from the LLM
        """
        # Ensure context is not None
        if context is None:
            context = "No channel context available."
        
        try:
            messages = self._build_messages(
                user_question=user_question,
                context=context,
                system_prompt=system_prompt,
                conversation_history=conversation_history
            )
            
            # Use provided values or config defaults
            temp = temperature if temperature is not None else self.llm_config.temperature
            tokens = max_tokens if max_tokens is not None else self.llm_config.max_tokens
            
            logger.info(f"Querying LLM with {len(messages)} messages")
            logger.info(f"User question: {user_question[:100]}...")
            logger.info(f"Context length: {len(context)} chars, has_valid_context: {'NO_CHANNEL_CONTEXT' not in context and 'No recent messages' not in context}")
            
            response = self.client.chat.completions.create(
                model=self.llm_config.model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens
            )
            
            # Handle None content (some APIs return None for empty responses)
            content = response.choices[0].message.content
            if content is None:
                content = ""
                logger.warning("LLM returned None content - empty response")
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }
            
            logger.info(f"LLM response received: {len(content)} characters")
            logger.debug(f"Token usage: {usage}")
            
            # Check if response is empty
            if not content.strip():
                logger.warning("LLM returned empty content")
                return LLMResponse(
                    content="I apologize, but I couldn't generate a response. Please try asking your question differently.",
                    model=self.llm_config.model,
                    usage=usage,
                    success=True
                )
            
            return LLMResponse(
                content=content,
                model=self.llm_config.model,
                usage=usage,
                success=True
            )
            
        except Exception as e:
            logger.error(f"LLM API error: {e}", exc_info=True)
            return LLMResponse(
                content="",
                model=self.llm_config.model,
                success=False,
                error_message=str(e)
            )
    
    def query_simple(self, user_message: str) -> str:
        """
        Simple query without context (backward compatibility).
        
        Args:
            user_message: The user's message
            
        Returns:
            str: The LLM response content
        """
        system_prompt = self.prompt_manager.load_prompt()
        
        try:
            response = self.client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return f"Error: {str(e)}"


# Convenience function for backward compatibility
def query_llm(user_message: str) -> str:
    """
    Convenience function for simple LLM queries.
    This maintains backward compatibility with the original code.
    
    Args:
        user_message: The user's message
        
    Returns:
        str: The LLM response content
    """
    client = LLMClient()
    return client.query_simple(user_message)


def query_llm_with_context(user_question: str, context: str) -> LLMResponse:
    """
    Convenience function for LLM queries with context.
    
    Args:
        user_question: The user's question
        context: The context from the Telegram channel
        
    Returns:
        LLMResponse: The response from the LLM
    """
    client = LLMClient()
    return client.query(user_question=user_question, context=context)
