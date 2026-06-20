#!/bin/bash

set -e

export PYTHONPATH="/app:$PYTHONPATH"

# Function to handle graceful shutdown
shutdown() {
    echo "Shutting down TTS Service..."
    exit 0
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT

# Initialize data directories
mkdir -p "${AUDIO_OUTPUT_DIR:-/var/lib/taas-audio}" "${MODEL_CACHE_DIR:-/var/lib/taas-models}" "$(dirname "${DB_PATH:-/var/lib/taas-db/tasks.db}")"

# Clean up old audio files based on TTL
echo "Cleaning up old audio files..."
AUDIO_DIR="${AUDIO_OUTPUT_DIR:-/var/lib/taas-audio}"
if [ -d "$AUDIO_DIR" ]; then
    find "$AUDIO_DIR" -name "*.wav" -mtime +${AUDIO_TTL_HOURS:-12} -delete 2>/dev/null || true
    echo "Audio cleanup completed"
fi

# Run database cleanup
if command -v python3 &> /dev/null; then
    echo "Running database cleanup..."
    python3 -c "
import asyncio
from src.db.queue import TaskQueueManager
from src.api.config import get_settings

async def cleanup():
    settings = get_settings()
    queue = TaskQueueManager(settings.db_path, settings.max_workers, settings.max_queue_depth)
    await queue.initialize()
    count = await queue.cleanup_old_tasks()
    print(f'Database cleanup completed: {count} tasks removed')

asyncio.run(cleanup())
" 2>/dev/null || echo "Database cleanup completed (may have failed)"
fi

# Start the service (uvicorn + lifespan manages workers)
echo "Starting TTS Service..."
exec python3 -m uvicorn src.main:create_app --host 0.0.0.0 --port 8000 --factory --log-level info --log-config /app/log_config.json
