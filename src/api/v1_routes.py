from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.core import CollectorRegistry
from typing import Optional
import asyncio
import time
import os

from ..db.queue import TtsRequestPayload
from ..api.config import get_settings

registry = CollectorRegistry()

# Prometheus metrics
request_count = Counter('tts_requests_total', 'Total TTS requests', ['method', 'endpoint', 'status'], registry=registry)
request_duration = Histogram('tts_request_duration_seconds', 'Request duration', registry=registry)
queue_size = Gauge('tts_queue_depth', 'Current queue depth', registry=registry)
active_workers = Gauge('tts_active_workers', 'Number of active workers', registry=registry)
text_length_distribution = Histogram('tts_text_length_chars', 'Text length distribution', buckets=[0, 100, 500, 1000, 5000, 10000, 32000, 64000, float('inf')], registry=registry)
voice_usage = Counter('tts_voice_usage_total', 'Voice usage count', ['voice'], registry=registry)
speed_distribution = Histogram('tts_speed_seconds', 'Speech speed distribution', buckets=[0.1, 0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0], registry=registry)
worker_usage = Gauge('tts_worker_usage', 'Worker usage percentage', registry=registry)


def create_v1_router() -> APIRouter:
    router = APIRouter()
    settings = get_settings()
    
    @router.post("/tts", status_code=200)
    @request_duration.time()
    async def sync_tts(
        request: Request,
        tts_request: TtsRequestPayload = None
    ):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        # Validate text length
        if len(tts_request.text) > settings.max_text_length:
            raise HTTPException(
                status_code=413,
                detail=f"Text exceeds maximum {settings.max_text_length} characters limit"
            )
        
        # Validate voice
        if tts_request.voice not in settings.available_voices:
            raise HTTPException(
                status_code=400,
                detail=f"Voice '{tts_request.voice}' not available. Choose from: {', '.join(settings.available_voices)}"
            )
        
        task_id = await queue_manager.enqueue_task(tts_request)
        
        # Poll until task completes or fails
        start = time.monotonic()
        timeout = 300  # 5 minute max wait
        while time.monotonic() - start < timeout:
            status = await queue_manager.get_task_status(task_id)
            if not status:
                raise HTTPException(status_code=500, detail="Task disappeared")
            
            if status["status"] == "completed":
                result_path = status.get("result_path")
                if result_path and os.path.exists(result_path):
                    return FileResponse(
                        path=result_path,
                        media_type="audio/wav",
                        filename=f"{task_id}.wav"
                    )
                raise HTTPException(status_code=500, detail="Task completed but audio file not found")
            
            if status["status"] == "failed":
                raise HTTPException(
                    status_code=500,
                    detail=f"TTS generation failed: {status.get('error', 'Unknown error')}"
                )
            
            await asyncio.sleep(0.2)
        
        raise HTTPException(status_code=504, detail="TTS generation timed out")
    
    @router.post("/tts/async", status_code=202)
    @request_duration.time()
    async def async_tts(
        request: Request,
        tts_request: TtsRequestPayload = None
    ):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        # Validate text length
        if len(tts_request.text) > settings.max_text_length:
            raise HTTPException(
                status_code=413,
                detail=f"Text exceeds maximum {settings.max_text_length} characters limit"
            )
        
        task_id = await queue_manager.enqueue_task(tts_request)
        
        return JSONResponse(
            {
                "task_id": task_id,
                "status": "pending",
                "poll_url": f"/v1/tts/async/{task_id}",
                "download_url": f"/v1/tts/async/{task_id}/download",
            }
        )
    
    @router.get("/tts/async/{task_id}")
    async def get_async_status(task_id: str, request: Request):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        task_status = await queue_manager.get_task_status(task_id)
        if not task_status:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        return task_status
    
    @router.get("/tts/async/{task_id}/download")
    async def download_async_tts(task_id: str, request: Request):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        task_status = await queue_manager.get_task_status(task_id)
        if not task_status:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        status = task_status["status"]
        if status == "completed":
            result_path = task_status.get("result_path")
            if result_path and os.path.exists(result_path):
                return FileResponse(
                    path=result_path,
                    media_type="audio/wav",
                    filename=f"{task_id}.wav"
                )
            raise HTTPException(status_code=500, detail="Task completed but audio file not found")
        
        raise HTTPException(
            status_code=409,
            detail=f"Task is not completed. Current status: {status}"
        )
    
    @router.post("/tts/async/{task_id}/cancel")
    async def cancel_task(task_id: str, request: Request):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        queue_manager.task_queue.update_task(task_id, status="cancelled")
        return {"task_id": task_id, "status": "cancelled"}
    
    @router.get("/voices")
    async def get_voices():
        settings = get_settings()
        return {
            "voices": settings.available_voices,
            "default": settings.default_voice
        }
    
    @router.post("/cleanup")
    async def cleanup_tasks(days: Optional[int] = 7, request: Request = None):
        from scripts.workers import TaskQueueManagerWithWorkers
        
        if request:
            queue_manager: TaskQueueManagerWithWorkers = request.app.state.task_queue_manager
        else:
            # Fallback for direct calls
            raise HTTPException(status_code=503, detail="Service not available")
        
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Service not available")
        
        count = await queue_manager.cleanup_old_tasks(days)
        return {"message": f"Cleaned up {count} old tasks", "days": days}
    
    @router.get("/health")
    async def health():
        return {"status": "healthy"}
    
    @router.get("/metrics")
    async def metrics():
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")
    
    return router