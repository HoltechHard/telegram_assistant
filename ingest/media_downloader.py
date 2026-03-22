import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class MediaDownloader:
    """
    Service responsible for downloading media from Telegram using python-telegram-bot
    and storing it locally using a deterministic filename.
    """

    def __init__(self, media_folder: str = "multimedia"):
        """
        Initialize the MediaDownloader.
        
        Args:
            media_folder: Directory where images will be stored.
        """
        self.base_folder = Path(media_folder)
        self.base_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"MediaDownloader initialized. Folder: {self.base_folder}")

    async def download(self, message) -> Optional[str]:
        """
        Downloads the highest resolution image from a python-telegram-bot Message.

        File name format:
            messageID + date + extension

        Example:
            1254_20260320_153045.jpg
            
        Args:
            message: The telegram.Message object (from python-telegram-bot)
            
        Returns:
            str: The local path to the downloaded image, or None if download fails.
        """

        if not message.photo:
            logger.warning(f"Message {message.message_id} does not contain a photo.")
            return None

        # message metadata
        msg_id = message.message_id
        # PTB dates are already datetime objects (usually UTC)
        msg_date = message.date.strftime("%Y%m%d_%H%M%S")

        # determine extension (default to .jpg for Telegram photos)
        extension = ".jpg"

        filename = f"{msg_id}_{msg_date}{extension}"
        file_path = self.base_folder / filename

        try:
            # Get the highest resolution photo
            photo = message.photo[-1]
            file = await photo.get_file()
            
            # download to drive
            await file.download_to_drive(custom_path=file_path)
            
            logger.info(f"Successfully downloaded image to: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error downloading media from message {msg_id}: {e}")
            return None
