import os
import asyncio
import logging
import riva.client
from settings.config import get_config
from datetime import datetime

logger = logging.getLogger(__name__)

class WhisperTranscriber:
    """Adapter that transcribes audio using a persistent gRPC client"""

    def __init__(self, grpc_client):
        logger.warning(f"?? WhisperTranscriber: Initializing...")
        self.config = get_config()
        self.grpc_client = grpc_client
        logger.warning(f"? WhisperTranscriber: Ready")
        logger.warning(f"   - Language: {self.config.speech.language}")
        logger.warning(f"   - gRPC Client: {grpc_client}")

    async def transcribe(self, audio_path: str):
        """Transcribe audio asynchronously"""
        logger.warning(f"???  WhisperTranscriber: Starting transcription")
        logger.warning(f"   - Audio file: {audio_path}")
        
        # Verify file exists
        if not os.path.exists(audio_path):
            logger.error(f"? WhisperTranscriber: File not found: {audio_path}")
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size = os.path.getsize(audio_path)
        logger.warning(f"   - File size: {file_size} bytes")
        
        try:
            start_time = datetime.now()
            result = await asyncio.to_thread(self._sync_transcribe, audio_path)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.warning(f"? WhisperTranscriber: Transcription complete in {elapsed:.2f}s")
            logger.warning(f"   - Result length: {len(result)} chars")
            logger.warning(f"   - Preview: {result[:200] if result else '(empty result)'}...")
            
            return result
            
        except Exception as e:
            logger.error(f"? WhisperTranscriber: Transcription failed")
            logger.error(f"   - Error type: {type(e).__name__}")
            logger.error(f"   - Error message: {str(e)}", exc_info=True)
            raise

    def _sync_transcribe(self, audio_path: str):
        """Synchronous transcription (runs in thread pool)"""
        logger.warning(f"???  WhisperTranscriber._sync_transcribe: Starting Whisper model")
        logger.warning(f"   - File: {audio_path}")
        logger.warning(f"   - Language: {self.config.speech.language}")
        
        try:
            # Create config
            config = riva.client.RecognitionConfig(
                language_code=self.config.speech.language,
                max_alternatives=1,
                enable_automatic_punctuation=True,
                verbatim_transcripts=True,
                enable_word_time_offsets=False
            )
            logger.warning(f"   - Config created: language={self.config.speech.language}")

            # Read audio file
            logger.warning(f"   - Reading audio file...")
            with open(audio_path, 'rb') as fh:
                audio_data = fh.read()
                audio_size = len(audio_data)
            logger.warning(f"   - Audio data loaded: {audio_size} bytes")

            # Call Whisper via gRPC
            logger.warning(f"   - Calling Whisper gRPC service...")
            response = self.grpc_client.transcribe_bytes(audio_data, config)
            logger.warning(f"   - gRPC response received")
            
            # Extract transcript
            if not response.results:
                logger.warning(f"   - ??  Whisper returned no results (empty audio?)")
                return ""
            
            logger.warning(f"   - Results count: {len(response.results)}")
            
            # Join alternatives across all results
            transcript = []
            for i, result in enumerate(response.results):
                logger.debug(f"   - Result {i}: {len(result.alternatives)} alternatives")
                if result.alternatives:
                    alt_text = result.alternatives[0].transcript
                    transcript.append(alt_text)
                    logger.debug(f"     - Text: {alt_text[:100]}...")
                    
            final_transcript = " ".join(transcript).strip()
            logger.warning(f"? WhisperTranscriber._sync_transcribe: Complete")
            logger.warning(f"   - Final transcript length: {len(final_transcript)} chars")
            
            return final_transcript
            
        except Exception as e:
            logger.error(f"? WhisperTranscriber._sync_transcribe: Error")
            logger.error(f"   - Error type: {type(e).__name__}")
            logger.error(f"   - Error message: {str(e)}", exc_info=True)
            raise
