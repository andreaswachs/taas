import asyncio
import logging
import logging.config
import os
from contextlib import asynccontextmanager

from .api.config import get_settings

settings = get_settings()

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "%(message)s",
            "class": "pythonjsonlogger.json.JsonFormatter",
            "rename_fields": {"levelname": "level", "name": "logger"},
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["default"],
        "level": settings.log_level.upper(),
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": settings.log_level.upper(),
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

from fastapi import FastAPI  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
import uvicorn  # noqa: E402

from .api.config import get_settings  # noqa: E402
from .api.v1_routes import create_v1_router  # noqa: E402
from .monitoring import create_metrics_app  # noqa: E402
from scripts.workers import TaskQueueManagerWithWorkers  # noqa: E402

logger = logging.getLogger(__name__)


class JSONLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_start_time = asyncio.get_event_loop().time()
        
        response = await call_next(request)
        
        process_time = asyncio.get_event_loop().time() - request_start_time
        
        logger.info(
            "HTTP request",
            extra={
                "http_method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2),
                "user_agent": request.headers.get("user-agent", ""),
            },
        )
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    logger.info("Starting TTS Service", extra={"version": settings.api_version})
    
    # Initialize main task queue manager with workers
    task_queue_manager = TaskQueueManagerWithWorkers(
        db_path=settings.db_path,
        max_workers=settings.max_workers,
        max_queue_depth=settings.max_queue_depth,
        audio_output_dir=settings.audio_output_dir
    )
    
    await task_queue_manager.initialize()
    await task_queue_manager.start_workers()
    
    logger.info("Background workers started", extra={"worker_count": settings.max_workers})
    
    # Store in app state for easy access
    app.state.task_queue_manager = task_queue_manager
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down TTS Service")
    await task_queue_manager.stop_workers()
    logger.info("Service shutdown complete")


_api_docs_content: str | None = None


def _get_api_docs() -> str:
    global _api_docs_content
    if _api_docs_content is None:
        path = os.path.join(os.path.dirname(__file__), "..", "API.md")
        with open(path) as f:
            _api_docs_content = f.read()
    return _api_docs_content


def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title="KittenTTS Service",
        description="Text-to-Speech as a Service with SQLite-backed async queue and monitoring",
        version=settings.api_version,
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(JSONLogMiddleware)
    
    # CORS configuration for Kubernetes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    v1_router = create_v1_router()
    app.include_router(v1_router, prefix=f"/{settings.api_version}")
    
    # Metrics endpoint for Prometheus
    metrics_app = create_metrics_app()
    app.include_router(metrics_app.router, prefix="/metrics")
    
    # Health check endpoints for Kubernetes
    @app.get("/health", include_in_schema=False)
    async def health():
        """Liveness probe endpoint for Kubernetes"""
        return {"status": "healthy"}
    
    @app.get("/ready", include_in_schema=False)
    async def ready():
        """Readiness probe endpoint for Kubernetes"""
        queue_manager: TaskQueueManagerWithWorkers = getattr(app.state, "task_queue_manager", None)
        if not queue_manager:
            return {"status": "unavailable", "reason": "Task queue manager not initialized"}
        
        stats = await queue_manager.get_stats()
        return {
            "status": "ready",
            "queue_depth": stats["queue_stats"]["pending"],
            "processing": stats["queue_stats"]["processing"],
            "worker_count": stats["worker_stats"]["active_workers"],
            "max_workers": stats["worker_stats"]["max_workers"],
        }
    
    @app.get("/")
    async def api_docs():
        return PlainTextResponse(_get_api_docs())
    
    return app


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:create_app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.log_level == "DEBUG"
    )