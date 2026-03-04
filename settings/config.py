"""
Configuration module for the Telegram Bot System.
This module manages all environment variables, constants, and configuration settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

# Get the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / "settings" / ".env")


@dataclass
class TelegramConfig:
    """Telegram-specific configuration settings."""
    bot_token: str
    channel_id: str
    owner_username: str
    owner_chat_id: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "TelegramConfig":
        """Load Telegram configuration from environment variables."""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
        owner_username = os.getenv("OWNER_USERNAME")
        owner_chat_id = os.getenv("OWNER_CHAT_ID")
        
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables.")
        if not channel_id:
            raise ValueError("TELEGRAM_CHANNEL_ID not found in environment variables.")
        
        # Normalize owner username (ensure it starts with @)
        if owner_username and not owner_username.startswith("@"):
            owner_username = f"@{owner_username}"
        
        return cls(
            bot_token=bot_token,
            channel_id=channel_id,
            owner_username=owner_username,
            owner_chat_id=owner_chat_id
        )


@dataclass
class LLMConfig:
    """LLM API configuration settings."""
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load LLM configuration from environment variables."""
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        temperature = float(os.getenv("LLM_TEMPERATURE"))
        max_tokens = int(os.getenv("LLM_MAX_TOKENS"))
        
        if not api_key:
            raise ValueError("LLM_API_KEY not found in environment variables.")
        
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )


@dataclass
class BroadcastConfig:
    """Broadcast-related configuration settings."""
    delay_hours: int
    enabled: bool
    
    @classmethod
    def from_env(cls) -> "BroadcastConfig":
        """Load broadcast configuration from environment variables."""
        delay_hours = int(os.getenv("BROADCAST_DELAY_HOURS"))
        enabled = os.getenv("BROADCAST_ENABLED").lower() == "true"
        
        return cls(delay_hours=delay_hours, 
                   enabled=enabled)


@dataclass
class ContextConfig:
    """Context collection configuration settings."""
    context_hours: int
    max_messages: int
    
    @classmethod
    def from_env(cls) -> "ContextConfig":
        """Load context configuration from environment variables."""
        context_hours = int(os.getenv("CONTEXT_HOURS"))
        max_messages = int(os.getenv("MAX_CONTEXT_MESSAGES"))
        
        return cls(context_hours=context_hours, 
                   max_messages=max_messages)


@dataclass
class AppConfig:
    """Main application configuration container."""
    telegram: TelegramConfig
    llm: LLMConfig
    broadcast: BroadcastConfig
    context: ContextConfig
    log_level: str
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load all configuration from environment variables."""
        return cls(
            telegram=TelegramConfig.from_env(),
            llm=LLMConfig.from_env(),
            broadcast=BroadcastConfig.from_env(),
            context=ContextConfig.from_env(),
            log_level=os.getenv("LOG_LEVEL")
        )


# Global configuration instance
config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get or create the global configuration instance."""
    global config
    if config is None:
        config = AppConfig.from_env()
    return config


def reload_config() -> AppConfig:
    """Reload configuration from environment variables."""
    global config
    load_dotenv(BASE_DIR / "settings" / ".env", override=True)
    config = AppConfig.from_env()
    return config
