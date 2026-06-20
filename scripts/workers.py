import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import threading

from src.db.queue import TaskQueueManager, TtsRequestPayload
from src.tts.engine import KittenTTSModelWrapper
from src.api.config import get_settings

logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(
        self,
        worker_id: str,
        task_queue: TaskQueueManager,
        tts_engine: KittenTTSModelWrapper,
        audio_output_dir: Path
    ):
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.tts_engine = tts_engine
        self.audio_output_dir = audio_output_dir
        self.is_running = False
    
    async def process_task(self, task_id: str) -> tuple[bool, Optional[str]]:
        logger.info("Worker processing task", extra={"worker_id": self.worker_id, "task_id": task_id})
        
        task = await self.task_queue.get_task(task_id)
        if not task:
            logger.error("Task not found", extra={"worker_id": self.worker_id, "task_id": task_id})
            return False, "Task not found"
        
        payload = task.payload
        
        try:
            await self.task_queue.update_task(
                task_id,
                status="processing",
                progress=10,
                worker_id=self.worker_id
            )
            
            await self.task_queue.update_task(
                task_id,
                progress=30
            )
            
            output_file = self.audio_output_dir / f"{task_id}.wav"
            result_path = await self.tts_engine.generate_to_file(
                task_id,
                payload,
                output_file
            )
            
            await asyncio.sleep(0.1)
            await self.task_queue.update_task(
                task_id,
                status="completed",
                result_path=result_path,
                progress=100
            )
            
            logger.info("Task completed successfully", extra={"worker_id": self.worker_id, "task_id": task_id})
            return True, None
            
        except Exception as e:
            error_msg = f"Failed to process task: {str(e)}"
            logger.error("Task processing failed", extra={"worker_id": self.worker_id, "task_id": task_id, "error": error_msg})
            await self.task_queue.update_task(
                task_id,
                status="failed",
                error=error_msg,
                progress=0
            )
            return False, error_msg


class TaskQueueManagerWithWorkers:
    def __init__(
        self,
        db_path: str,
        max_workers: int = 5,
        max_queue_depth: int = 1000,
        audio_output_dir: str = "/var/lib/taas-audio"
    ):
        self.task_queue = TaskQueueManager(db_path, max_workers, max_queue_depth)
        self.tts_engine = KittenTTSModelWrapper()
        self.audio_output_dir = Path(audio_output_dir)
        self.max_workers = max_workers
        
        self.workers: List[BackgroundWorker] = []
        self.worker_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        self.worker_id = f"{threading.current_thread().name}-{id(self)}"
    
    async def initialize(self) -> None:
        logger.info("Initializing task queue manager", extra={"max_workers": self.max_workers})
        await self.task_queue.initialize()
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)
    
    async def start_workers(self) -> None:
        if self.is_running:
            logger.warning("Workers are already running")
            return
        
        self.is_running = True
        logger.info("Starting background workers", extra={"max_workers": self.max_workers})
        
        for i in range(self.max_workers):
            worker = BackgroundWorker(
                f"worker-{i + 1}",
                self.task_queue,
                self.tts_engine,
                self.audio_output_dir
            )
            self.workers.append(worker)
            task = asyncio.create_task(self._worker_loop(worker))
            self.worker_tasks.append(task)
        
        cleanup_task = asyncio.create_task(self._background_cleanup_loop())
        self.worker_tasks.append(cleanup_task)
        
        logger.info("All workers started", extra={"worker_count": len(self.workers)})
    
    async def _worker_loop(self, worker: BackgroundWorker) -> None:
        logger.info("Worker loop started", extra={"worker_id": worker.worker_id})
        
        while self.is_running:
            try:
                task = await self.task_queue.claim_next_task(worker.worker_id)
                
                if task:
                    logger.info("Worker claimed task", extra={"worker_id": worker.worker_id, "task_id": task.id})
                    success, error = await worker.process_task(task.id)
                    status = "completed" if success else "failed"
                    
                    if success:
                        logger.info("Worker task result", extra={"worker_id": worker.worker_id, "task_id": task.id, "status": status})
                    else:
                        logger.warning("Worker task result", extra={"worker_id": worker.worker_id, "task_id": task.id, "status": status, "error": error})
                else:
                    await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.exception("Worker loop error", extra={"worker_id": worker.worker_id, "error": str(e)})
                await asyncio.sleep(1)
        
        logger.info("Worker loop stopped", extra={"worker_id": worker.worker_id})
    
    async def stop_workers(self) -> None:
        if not self.is_running:
            return
        
        logger.info("Stopping background workers")
        self.is_running = False
        
        for task in self.worker_tasks:
            task.cancel()
        
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        self.worker_tasks.clear()
        self.workers.clear()
        
        await self.task_queue.close()
        logger.info("All workers stopped")
    
    async def enqueue_task(self, payload: TtsRequestPayload) -> str:
        task = await self.task_queue.enqueue_task(payload)
        logger.info("Task enqueued", extra={"task_id": task.id})
        return task.id
    
    async def get_task_status(self, task_id: str) -> Optional[dict]:
        task = await self.task_queue.get_task(task_id)
        if task:
            return {
                "task_id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "worker_id": task.worker_id,
                "error": task.error,
                "result_path": task.result_path,
                "download_url": f"/v1/tts/async/{task.id}/download",
            }
        return None
    
    async def get_stats(self) -> dict:
        queue_stats = await self.task_queue.get_stats()
        
        return {
            "queue_stats": {
                "pending": queue_stats.pending,
                "processing": queue_stats.processing,
                "completed": queue_stats.completed,
                "failed": queue_stats.failed,
                "total": queue_stats.total,
            },
            "worker_stats": {
                "max_workers": self.max_workers,
                "active_workers": len([w for w in self.workers if w.is_running]),
            }
        }
    
    async def cleanup_audio_files(self) -> int:
        logger.info("Starting audio file cleanup")
        settings = get_settings()
        cutoff_time = datetime.now() - timedelta(hours=settings.audio_ttl_hours)
        
        deleted_count = 0
        for audio_file in self.audio_output_dir.glob("*.wav"):
            if audio_file.stat().st_mtime < cutoff_time.timestamp():
                try:
                    audio_file.unlink()
                    logger.info("Deleted old audio file", extra={"file": str(audio_file)})
                    deleted_count += 1
                except Exception as e:
                    logger.error("Failed to delete audio file", extra={"file": str(audio_file), "error": str(e)})
        
        logger.info("Audio file cleanup completed", extra={"deleted_count": deleted_count})
        return deleted_count

    async def _background_cleanup_loop(self) -> None:
        while self.is_running:
            try:
                await self.cleanup_audio_files()
                await asyncio.sleep(3600)
            except Exception as e:
                logger.exception("Background cleanup job error", extra={"error": str(e)})
                await asyncio.sleep(3600)
