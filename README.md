# TTS Service

Text-to-Speech as a Service using KittenTTS with SQLite-backed async queue.

## Quick Start

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn src.main:create_app --host 0.0.0.0 --port 8000 --reload
```

## Docker

```bash
# Build
docker build -t tts-service .

# Run
docker run -p 8000:8000 tts-service
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tts` | POST | Synchronous TTS (returns audio) |
| `/v1/tts/async` | POST | Async TTS (returns task ID) |
| `/v1/tts/async/{task_id}` | GET | Check async task status |
| `/v1/tts/async/{task_id}/download` | GET | Download completed audio file |
| `/v1/tts/async/{task_id}/cancel` | POST | Cancel a pending/processing task |
| `/v1/voices` | GET | List available voices |
| `/v1/health` | GET | Health check |
| `/v1/metrics` | GET | Prometheus metrics |

### Example

```bash
curl -X POST http://localhost:8000/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "Bella"}'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `/var/lib/taas-db/tasks.db` | SQLite database location |
| `AUDIO_OUTPUT_DIR` | `/var/lib/taas-audio` | Generated audio file directory |
| `MODEL_CACHE_DIR` | `/var/lib/taas-models` | KittenTTS model cache |
| `MAX_WORKERS` | `5` | Background worker count |
| `MAX_QUEUE_DEPTH` | `1000` | Max queued tasks |
| `AUDIO_TTL_HOURS` | `12` | Audio file retention |
| `LOG_LEVEL` | `INFO` | Log level |

Default paths are sibling directories under `/var/lib/taas-*` so each can be backed by a separate PVC in Kubernetes with `readOnlyRootFilesystem: true`. Set via environment variables or `.env` file.

## License

MIT
