import logging
import requests
import json
from typing import Optional

logger = logging.getLogger(__name__)

class AIClient:
    """
    Service for connecting to the AI API (NVIDIA/OpenAI compatible),
    with support for vision tasks (image analysis).
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        """
        Initialize the AIClient.
        
        Args:
            api_key: AI API Key
            base_url: API Base URL
            model: Model name for vision tasks
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        
        # Determine the full invoke URL
        if "/chat/completions" in self.base_url:
            self.invoke_url = self.base_url
        else:
            self.invoke_url = f"{self.base_url}/chat/completions"
            
        logger.info(f"AIClient (Vision) initialized with URL: {self.invoke_url} and model: {self.model}")

    async def describe_image(self, image_b64: str) -> str:
        """
        Sends image to the API and returns description/transcription.
        
        Args:
            image_b64: Base64 encoded image content
            
        Returns:
            str: The AI-generated transcription or an error message.
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        # Payload for multimodal model
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe the text and describe the content of this image accurately."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.2,
            "top_p": 0.7,
            "stream": False
        }

        try:
            logger.info(f"Sending image to AI vision API ({self.model})...")
            # Using synchronous requests to match the provided logic
            response = requests.post(self.invoke_url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            description = result['choices'][0]['message']['content']
            
            logger.info("Successfully received transcription from AI.")
            return description

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error connecting to AI API: {e.response.text}"
            logger.error(error_msg)
            return f"Error connecting to AI API: HTTP {e.response.status_code}"
            
        except Exception as e:
            error_msg = f"Unexpected error connecting to AI API: {str(e)}"
            logger.error(error_msg)
            return f"Error: {str(e)}"
