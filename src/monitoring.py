from fastapi import FastAPI, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.core import CollectorRegistry
import logging


logger = logging.getLogger(__name__)

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


def create_metrics_app() -> FastAPI:
    app = FastAPI(
        title="KittenTTS Metrics",
        description="Prometheus metrics endpoint",
        version="1.0.0"
    )
    
    @app.get("/metrics")
    async def get_metrics():
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")
    
    return app


def update_metrics_from_queue(queue_manager):
    try:
        stats = queue_manager.get_stats()
        
        queue_size.set(stats['queue_stats']['pending'])
        active_workers.set(stats['worker_stats']['active_workers'])
        
        worker_usage.set(stats['worker_stats']['active_workers'] / stats['worker_stats']['max_workers'] * 100)
        
    except Exception as e:
        logger.exception("Error updating metrics", extra={"error": str(e)})