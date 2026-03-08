"""
Question Store Module.
Persists all questions to a JSON file for history and auditing.
Each question has: question_id, question_description, category, status.
"""

import json
import shutil
import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

from settings.config import BASE_DIR

logger = logging.getLogger(__name__)

# Default storage path
QUESTIONS_FILE = BASE_DIR / "data" / "questions.json"


class QuestionStore:
    """
    JSON file-based persistence for question history.
    
    Stores all questions with their metadata and processing status.
    Thread-safe via asyncio.Lock.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the question store.
        
        Args:
            storage_path: Optional custom path to the JSON file
        """
        self.storage_path = Path(storage_path) if storage_path else QUESTIONS_FILE
        self._questions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        
        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self._load_from_file()
        
        logger.info(
            f"QuestionStore initialized: {len(self._questions)} questions loaded "
            f"from {self.storage_path}"
        )
    
    def _load_from_file(self) -> None:
        """Load questions from the JSON file."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for q in data.get("questions", []):
                self._questions[q["question_id"]] = q
                
        except Exception as e:
            logger.error(f"Failed to load questions file: {e}")
    
    async def _save_to_file(self) -> None:
        """Save questions to the JSON file."""
        try:
            data = {
                "version": 1,
                "total_questions": len(self._questions),
                "questions": list(self._questions.values())
            }
            
            # Write to temp file, then move for atomicity
            temp_path = self.storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            shutil.move(str(temp_path), str(self.storage_path))
            
        except Exception as e:
            logger.error(f"Failed to save questions file: {e}", exc_info=True)
    
    async def add_question(
        self,
        question_id: str,
        question_description: str,
        category: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Add a new question to the store.
        
        Args:
            question_id: Unique question identifier
            question_description: The user's question text
            category: Question category
            user_id: Telegram user ID
            
        Returns:
            Dict[str, Any]: The stored question record
        """
        question = {
            "question_id": question_id,
            "question_description": question_description,
            "category": category,
            "status": False,  # False = not yet attended
            "user_id": user_id,
        }
        
        async with self._lock:
            self._questions[question_id] = question
            await self._save_to_file()
        
        logger.info(f"Question {question_id} added to store (category={category})")
        return question
    
    async def mark_completed(self, question_id: str) -> None:
        """
        Mark a question as completed (attended).
        
        Args:
            question_id: The question ID to mark
        """
        async with self._lock:
            if question_id in self._questions:
                self._questions[question_id]["status"] = True
                await self._save_to_file()
                logger.info(f"Question {question_id} marked as completed in store")
    
    async def mark_failed(self, question_id: str) -> None:
        """
        Mark a question as failed.
        
        Args:
            question_id: The question ID
        """
        async with self._lock:
            if question_id in self._questions:
                self._questions[question_id]["status"] = "failed"
                await self._save_to_file()
                logger.info(f"Question {question_id} marked as failed in store")
    
    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending (not yet attended) questions."""
        return [q for q in self._questions.values() if q["status"] is False]
    
    def get_completed(self) -> List[Dict[str, Any]]:
        """Get all completed questions."""
        return [q for q in self._questions.values() if q["status"] is True]
    
    def get_question(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific question by ID."""
        return self._questions.get(question_id)
    
    def get_total_count(self) -> int:
        """Get total number of questions."""
        return len(self._questions)
