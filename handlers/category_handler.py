"""
Category Handler Module for Telegram Bot System.
Handles the question categorization flow with inline buttons.

Categories and their priority scores:
    Notas        = 1 (highest)
    Evaluaciones = 2
    Tareas       = 3
    Otros        = 4 (lowest)
"""

import logging
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Category definitions
CATEGORIES = {
    "notas": "Notas",
    "evaluaciones": "Evaluaciones",
    "tareas": "Tareas",
    "otros": "Otros",
}

# Callback data prefix
CATEGORY_CALLBACK_PREFIX = "cat:"


def create_category_keyboard() -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with category selection buttons.
    
    Layout: 2x2 grid of category buttons
    
    Returns:
        InlineKeyboardMarkup: The category selection keyboard
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "+ Notas", callback_data=f"{CATEGORY_CALLBACK_PREFIX}notas"
            ),
            InlineKeyboardButton(
                "+ Evaluaciones", callback_data=f"{CATEGORY_CALLBACK_PREFIX}evaluaciones"
            ),
        ],
        [
            InlineKeyboardButton(
                "+ Tareas", callback_data=f"{CATEGORY_CALLBACK_PREFIX}tareas"
            ),
            InlineKeyboardButton(
                "+ Otros", callback_data=f"{CATEGORY_CALLBACK_PREFIX}otros"
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def parse_category_callback(callback_data: str) -> Optional[str]:
    """
    Parse the callback data from category buttons.
    
    Args:
        callback_data: The callback data string (e.g., "cat:notas")
        
    Returns:
        Optional[str]: The category name, or None if invalid
    """
    if not callback_data.startswith(CATEGORY_CALLBACK_PREFIX):
        return None
    
    category = callback_data[len(CATEGORY_CALLBACK_PREFIX):]
    
    if category in CATEGORIES:
        return category
    
    logger.warning(f"Unknown category in callback: {category}")
    return None


def get_category_display_name(category: str) -> str:
    """
    Get the display name for a category.
    
    Args:
        category: The category key (e.g., "notas")
        
    Returns:
        str: The display name (e.g., "Notas")
    """
    return CATEGORIES.get(category, category.capitalize())
