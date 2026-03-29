import os
from datetime import datetime
from telegram import Message
import logging
from settings.config import get_config

logger = logging.getLogger(__name__)

class SpeechMediaDownloader:
    def __init__(self):
        config = get_config()
        # Normalize path and fallback to default multimedia/audio
        speech_folder = config.speech_folder or "multimedia/audio"
        self.audio_dir = os.path.normpath(speech_folder)

        logger.warning(f"? SpeechMediaDownloader: Initializing...")
        logger.warning(f"   - Audio directory: {self.audio_dir}")
        
        # Create directory
        try:
            os.makedirs(self.audio_dir, exist_ok=True)
            logger.warning(f"? SpeechMediaDownloader: Audio directory ready")
            
            # Verify write permissions
            test_file = os.path.join(self.audio_dir, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            logger.warning(f"? SpeechMediaDownloader: Directory has write permissions")
            
        except Exception as e:
            logger.error(f"? SpeechMediaDownloader: Cannot create/access directory: {e}", exc_info=True)

    async def download(self, message: Message) -> str:
        """Downloads an audio/voice file and returns the path."""
        logger.warning(f"?? SpeechMediaDownloader: Starting download")
        logger.warning(f"   - Message ID: {message.message_id}")
        logger.warning(f"   - Has voice: {bool(message.voice)}")
        logger.warning(f"   - Has audio: {bool(message.audio)}")
        
        audio_obj = message.voice or message.audio
        if not audio_obj:
            logger.error(f"? SpeechMediaDownloader: No voice or audio object found")
            return None

        try:
            logger.warning(f"   - Audio object type: {type(audio_obj).__name__}")
            logger.warning(f"   - File ID: {audio_obj.file_id}")
            logger.warning(f"   - File unique ID: {audio_obj.file_unique_id}")
            logger.warning(f"   - MIME type: {audio_obj.mime_type}")
            logger.warning(f"   - Duration: {audio_obj.duration}s")
            
            # Get file from Telegram
            logger.warning(f"   - Downloading from Telegram...")
            file = await audio_obj.get_file()
            logger.warning(f"   ? File object obtained from Telegram")
            
            # Construct filename
            date_str = message.date.strftime("%Y%m%d_%H%M%S") if message.date else datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{message.message_id}_{date_str}.ogg"
            file_path = os.path.join(self.audio_dir, filename)
            
            logger.warning(f"   - Target path: {file_path}")
            logger.warning(f"   - Filename: {filename}")
            
            # Download to disk
            logger.warning(f"   - Downloading to disk...")
            await file.download_to_drive(file_path)
            
            # Verify file was created
            if not os.path.exists(file_path):
                logger.error(f"? SpeechMediaDownloader: File was not created at {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            logger.warning(f"? SpeechMediaDownloader: Download complete")
            logger.warning(f"   - File path: {file_path}")
            logger.warning(f"   - File size: {file_size} bytes")
            
            if file_size == 0:
                logger.error(f"? SpeechMediaDownloader: Downloaded file is empty (0 bytes)")
                return None
            
            logger.warning(f"   - File created successfully!")
            return file_path
            
        except Exception as e:
            logger.error(f"? SpeechMediaDownloader: Failed to download audio from message {message.message_id}")
            logger.error(f"   - Error type: {type(e).__name__}")
            logger.error(f"   - Error details: {str(e)}", exc_info=True)
            return None
