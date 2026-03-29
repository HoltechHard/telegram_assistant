import asyncio
import logging
import time
from ingest.speech.ai_audio_transcriber import WhisperTranscriber
from ingest.speech.grpc_client import WhisperGRPCClient
from queue_speech.async_worker import AsyncWorker
from queue_speech.redis_speech_queue import RedisSpeechQueue
from settings.config import get_config

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Coordinator for speech ingestion"""
    def __init__(self):
        logger.warning("?? AudioProcessor: Initializing...")
        self.config = get_config()
        logger.warning(f"?? AudioProcessor: Config loaded - speech_folder={self.config.speech_folder}")
        
        self.queue = RedisSpeechQueue()
        logger.warning(f"?? AudioProcessor: Redis Queue initialized - queue_name='{self.config.speech.redis_queue}'")
        
        self.grpc_client = WhisperGRPCClient()
        logger.warning(f"?? AudioProcessor: gRPC Client initialized")
        
        self.transcriber = WhisperTranscriber(self.grpc_client)
        logger.warning(f"?? AudioProcessor: Whisper Transcriber initialized")
        
        self.workers = []
        self._worker_tasks = []
        logger.info("? AudioProcessor initialized successfully")

    async def start(self):
        """Start the worker pool"""
        worker_count = self.config.speech.max_workers
        logger.warning(f"?? AudioProcessor: Starting {worker_count} speech transcription workers...")
        
        for i in range(worker_count):
            try:
                worker = AsyncWorker(
                    queue=self.queue,
                    transcriber=self.transcriber,
                    worker_id=i
                )
                self.workers.append(worker)
                task = asyncio.create_task(worker.run())
                self._worker_tasks.append(task)
                logger.warning(f"? AudioProcessor: Worker-{i} task created and scheduled")
            except Exception as e:
                logger.error(f"? AudioProcessor: Failed to create Worker-{i}: {e}", exc_info=True)
        
        logger.warning(f"? AudioProcessor: All {len(self.workers)} workers started")
        for i, task in enumerate(self._worker_tasks):
            logger.warning(f"   - Worker-{i} task: {task}")

    async def stop(self):
        """Stop all workers gracefully"""
        logger.warning(f"??  AudioProcessor: Stopping {len(self._worker_tasks)} workers...")
        for i, task in enumerate(self._worker_tasks):
            logger.warning(f"   - Cancelling Worker-{i} task")
            task.cancel()
        
        if self._worker_tasks:
            results = await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, asyncio.CancelledError):
                    logger.warning(f"   - Worker-{i} cancelled successfully")
                elif isinstance(result, Exception):
                    logger.error(f"   - Worker-{i} error during cancellation: {result}")
        
        await self.queue.close()
        logger.warning(f"? AudioProcessor: All workers stopped")

    async def submit_audio(self, audio_path: str, message_id: int) -> str:
        """Submit an audio file for transcription"""
        logger.warning(f"?? AudioProcessor: Submitting audio for transcription")
        logger.warning(f"   - Message ID: {message_id}")
        logger.warning(f"   - Audio path: {audio_path}")
        
        try:
            job_id = await self.queue.push(audio_path, message_id)
            logger.warning(f"? AudioProcessor: Audio queued successfully")
            logger.warning(f"   - Job ID: {job_id}")
            logger.warning(f"   - Queue name: {self.config.speech.redis_queue}")
            return job_id
        except Exception as e:
            logger.error(f"? AudioProcessor: Failed to queue audio: {e}", exc_info=True)
            raise
    
    async def wait_for_transcript(self, job_id: str, timeout: int = 60) -> str:
        """Poll redis for the completed transcript"""
        logger.warning(f"? AudioProcessor: Waiting for transcript (Job: {job_id})")
        logger.warning(f"   - Timeout: {timeout} seconds")
        logger.warning(f"   - Checking Redis key: 'speech_result:{job_id}'")
        
        start = time.time()
        poll_count = 0
        
        while time.time() - start < timeout:
            poll_count += 1
            elapsed = int(time.time() - start)
            
            # Log every 5 seconds
            if poll_count % 5 == 0:
                logger.debug(f"   - Polling ({elapsed}s elapsed, {poll_count} polls)...")
            
            try:
                result = await self.queue.redis.get(f"speech_result:{job_id}")
                
                if result:
                    elapsed = time.time() - start
                    
                    if result.startswith("__ERROR__"):
                        logger.error(f"? AudioProcessor: Transcription failed")
                        logger.error(f"   - Error from worker: {result}")
                        logger.error(f"   - Total time: {elapsed:.2f}s")
                        raise RuntimeError(f"Transcription failed in worker: {result}")
                    
                    logger.warning(f"? AudioProcessor: Transcript received in {elapsed:.2f}s")
                    logger.warning(f"   - Transcript length: {len(result)} chars")
                    logger.warning(f"   - Preview: {result[:150]}...")
                    return result
                
                await asyncio.sleep(1)
            
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"? AudioProcessor: Error checking Redis: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        elapsed = time.time() - start
        logger.error(f"? AudioProcessor: Transcription timeout after {elapsed:.2f}s ({poll_count} polls)")
        logger.error(f"   - Job ID: {job_id}")
        logger.error(f"   - Check if workers are running: 'python -c \"import redis; r = redis.Redis(...); print(r.llen('whisper_speech'))'\"")
        raise TimeoutError(f"Transcription timed out after {timeout}s")
