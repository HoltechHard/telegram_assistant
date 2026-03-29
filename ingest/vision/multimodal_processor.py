import logging

logger = logging.getLogger(__name__)

class MultimodalProcessor:
    """
    Processor responsible for combining AI transcription results
    with original message captions.
    """

    def __init__(self, transcriber):
        """
        Initialize the MultimodalProcessor.
        
        Args:
            transcriber: An initialized AIImageTranscriber instance.
        """
        self.transcriber = transcriber
        logger.info("MultimodalProcessor initialized.")

    async def build_multimodal_caption(self, image_path: str, caption: str) -> str:
        """
        Takes the AI transcription result and concatenates it with the 
        original Telegram post caption.
        
        Args:
            image_path: Local path to the image file.
            caption: Original caption text from the Telegram message.
            
        Returns:
            str: Combined multimodal caption text.
        """

        # 1. Get transcription from AI
        logger.info(f"Requesting transcription for image: {image_path}")
        ai_text = await self.transcriber.transcribe(image_path)

        # 2. Handle empty caption
        original_caption = caption or "(No original caption provided)"

        # 3. Concatenate (AI transcription first, then original caption)
        # As requested: "the multimodal caption need to return the image transcription text 
        # together with the caption text in the same variable."
        
        # We'll use a clear separator for readability, but keep them in the same variable.
        multimodal_result = f"[AI TRANSCRIPTION]: {ai_text}\n\n[ORIGINAL CAPTION]: {original_caption}"

        logger.info("Multimodal caption built successfully.")
        return multimodal_result.strip()
