# Agent Instructions

## Before Any Commit

**Validate everything first.** Never commit without confirming:

1. `make lint` passes
2. `make test` passes
3. `docker compose up --build` builds and starts successfully

The container build is the final gate — it catches missing files, broken imports, and dependency issues that local checks miss. If the image doesn't build, don't commit.

## Quick Commands

```bash
make setup          # Install deps (uv sync)
make test           # Run tests (pytest)
make lint           # Lint with ruff
make format         # Format with ruff
make dev            # Docker compose up --build
```

## Gotchas

- **PYTHONPATH required**: Some scripts need `PYTHONPATH=src` (see `make workers`).
- **Tests are in root**: `test_comprehensive.py` at repo root, not in `tests/` (which is empty). CI runs: `python3 -m pytest test_comprehensive.py -v`.
- **KittenTTS wheel**: Installed from GitHub release URL, not PyPI. Check `pyproject.toml` for version.
- **Docker build uses `Containerfile`**, not `Dockerfile`. The `compose.yaml` references it.
- **Entrypoint runs workers via lifespan**: Don't start workers separately in Docker; `src/main.py` handles it via `TaskQueueManagerWithWorkers`.

## Architecture

- **`src/main.py`**: FastAPI app factory. Wires up routes, middleware, workers.
- **`src/api/v1_routes.py`**: All API endpoints.
- **`src/api/config.py`**: Settings via pydantic-settings. Env vars override `.env`.
- **`src/tts/engine.py`**: KittenTTS model wrapper.
- **`src/db/queue.py`**: SQLite async task queue.
- **`scripts/workers.py`**: Background worker classes (used by `main.py` lifespan).
- **`data/`**: Runtime data (SQLite DB, audio files, model cache). Gitignored.

## Dev Workflow

- Dev server with reload: `uv run uvicorn src.main:create_app --host 0.0.0.0 --port 8000 --reload`
- Or just: `make dev` (Docker)
- Run single test: `pytest test_comprehensive.py -k "test_name" -v`
