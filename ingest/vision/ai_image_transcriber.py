import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class AIImageTranscriber:
    """
    Wrapper around AIClient that handles image encoding
    and prepares the transcription request.
    """

    def __init__(self, api_client):
        """
        Initialize the transcriber.
        
        Args:
            api_client: An initialized AIClient instance.
        """
        self.api_client = api_client
        logger.info("AIImageTranscriber initialized.")

    def _encode_image(self, image_path: str) -> str:
        """
        Encodes image file to Base64 string.
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def transcribe(self, image_path: str) -> str:
        """
        Transcribes the image at the given path using the AI system.
        
        Args:
            image_path: Local path to the image file.
            
        Returns:
            str: AI generated transcription text.
        """
        if not Path(image_path).exists():
            logger.error(f"Image not found at path: {image_path}")
            return "Error: Image file not found."

        try:
            encoded_image = self._encode_image(image_path)
            # Call the AI model
            response = await self.api_client.describe_image(encoded_image)
            return response
            
        except Exception as e:
            logger.error(f"Error during transcription of {image_path}: {e}")
            return f"Transcription error: {str(e)}"
