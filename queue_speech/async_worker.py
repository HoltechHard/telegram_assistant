import asyncio
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class AsyncWorker:
    """Worker that consumes transcription jobs from Redis and uses WhisperTranscriber."""

    def __init__(self, queue, transcriber, worker_id=0):
        self.queue = queue
        self.transcriber = transcriber
        self.worker_id = worker_id
        self.processed_count = 0
        self.error_count = 0

    async def run(self):
        logger.info(f"[SpeechWorker-{self.worker_id}] ? STARTED - Waiting for jobs on queue: {self.queue.queue}")
        logger.info(f"[SpeechWorker-{self.worker_id}] Redis connection: {self.queue.redis}")
        logger.info(f"[SpeechWorker-{self.worker_id}] Transcriber: {self.transcriber.__class__.__name__}")
        
        while True:
            try:
                logger.debug(f"[SpeechWorker-{self.worker_id}] Polling queue (processed: {self.processed_count}, failed: {self.error_count})")
                job = await self.queue.pop()
                
                if not job:
                    # Queue empty, sleep briefly
                    await asyncio.sleep(0.1)
                    continue

                job_id = job.get("id")
                audio_path = job.get("audio_path")
                message_id = job.get("message_id")

                logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? DEQUEUED")
                logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Message ID: {message_id}")
                logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Audio Path: {audio_path}")
                
                # Verify file exists
                if not os.path.exists(audio_path):
                    logger.error(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? CRITICAL: Audio file not found at {audio_path}")
                    self.error_count += 1
                    await self.queue.redis.setex(f"speech_result:{job_id}", 3600, "__ERROR__:FILE_NOT_FOUND")
                    continue
                
                file_size = os.path.getsize(audio_path)
                logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] File size: {file_size} bytes")
                
                if file_size == 0:
                    logger.error(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? CRITICAL: Audio file is empty (0 bytes)")
                    self.error_count += 1
                    await self.queue.redis.setex(f"speech_result:{job_id}", 3600, "__ERROR__:EMPTY_FILE")
                    continue

                logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? TRANSCRIBING... (Starting Whisper model)")
                start_time = datetime.now()
                
                try:
                    transcript = await self.transcriber.transcribe(audio_path)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? TRANSCRIPTION COMPLETE in {elapsed:.2f}s")
                    logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Transcript length: {len(transcript)} chars")
                    logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Preview: {transcript[:200]}...")
                    
                    # Store result in Redis
                    await self.queue.redis.setex(f"speech_result:{job_id}", 3600, transcript)
                    logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? STORED in Redis with key: speech_result:{job_id}")
                    
                    self.processed_count += 1

                except Exception as proc_error:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    logger.error(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] ? TRANSCRIPTION FAILED after {elapsed:.2f}s")
                    logger.error(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Error type: {type(proc_error).__name__}")
                    logger.error(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Error details: {str(proc_error)}", exc_info=True)
                    
                    self.error_count += 1
                    error_msg = f"__ERROR__:{type(proc_error).__name__}:{str(proc_error)[:100]}"
                    await self.queue.redis.setex(f"speech_result:{job_id}", 3600, error_msg)
                    logger.warning(f"[SpeechWorker-{self.worker_id}] [JOB-{job_id}] Error flag stored in Redis")

            except Exception as e:
                logger.error(f"[SpeechWorker-{self.worker_id}] ? CRITICAL ERROR in worker loop: {str(e)}", exc_info=True)
                logger.error(f"[SpeechWorker-{self.worker_id}] Sleeping 5 seconds before retry...")
                await asyncio.sleep(5)
