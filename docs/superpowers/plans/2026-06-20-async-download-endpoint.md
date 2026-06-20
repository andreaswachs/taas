# Async TTS Audio Download Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a download endpoint for async TTS audio and replace UUID task IDs with cryptographically secure random tokens to prevent enumeration attacks.

**Architecture:** Replace `uuid.uuid4()` with `secrets.token_hex(32)` for task ID generation. Add `GET /v1/tts/async/{task_id}/download` endpoint that serves WAV files via `FileResponse`. Add `download_url` field to async submit and status poll responses.

**Tech Stack:** Python, FastAPI, aiosqlite, secrets module

---

## File Structure

| File | Change |
|------|--------|
| `src/db/queue.py` | Replace `uuid` import with `secrets`, change ID generation |
| `src/api/v1_routes.py` | Add download endpoint, add `download_url` to responses |
| `scripts/workers.py` | Add `download_url` to `get_task_status` response dict |
| `API.md` | Document new endpoint, update ID format, update response schemas |

---

### Task 1: Replace UUID with secure random token

**Files:**
- Modify: `src/db/queue.py:3,85`

- [ ] **Step 1: Update import**

Replace `import uuid` with `import secrets` at line 3 of `src/db/queue.py`.

```python
import secrets
```

- [ ] **Step 2: Update ID generation**

Replace line 85 of `src/db/queue.py`:

```python
# Before:
task_id = str(uuid.uuid4())

# After:
task_id = secrets.token_hex(32)
```

- [ ] **Step 3: Verify no other uuid references remain**

Run: `grep -n 'uuid' src/db/queue.py`
Expected: No output (uuid import and usage removed)

- [ ] **Step 4: Commit**

```bash
git add src/db/queue.py
git commit -m "feat: replace UUID with cryptographically secure random token for task IDs"
```

---

### Task 2: Add download_url to get_task_status response

**Files:**
- Modify: `scripts/workers.py:181-195`

- [ ] **Step 1: Add download_url to status dict**

In `scripts/workers.py`, update the `get_task_status` method (lines 181-195) to include `download_url`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add scripts/workers.py
git commit -m "feat: add download_url to task status response"
```

---

### Task 3: Add download endpoint and update async submit response

**Files:**
- Modify: `src/api/v1_routes.py:87-128`

- [ ] **Step 1: Add download endpoint**

In `src/api/v1_routes.py`, add the following endpoint after the `get_async_status` endpoint (after line 128), before the cancel endpoint:

```python
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
```

- [ ] **Step 2: Update async_tts response to include download_url**

Replace lines 108-114 in `src/api/v1_routes.py`:

```python
        return JSONResponse(
            {
                "task_id": task_id,
                "status": "pending",
                "poll_url": f"/v1/tts/async/{task_id}",
                "download_url": f"/v1/tts/async/{task_id}/download",
            }
        )
```

- [ ] **Step 3: Fix poll_url bug**

The existing `poll_url` at line 112 uses `/v1/status/{task_id}` which is incorrect — the actual endpoint is `/v1/tts/async/{task_id}`. The updated code in Step 2 fixes this.

- [ ] **Step 4: Commit**

```bash
git add src/api/v1_routes.py
git commit -m "feat: add GET /v1/tts/async/{task_id}/download endpoint for audio file retrieval"
```

---

### Task 4: Update API documentation

**Files:**
- Modify: `API.md`

- [ ] **Step 1: Update task ID description**

In `API.md`, add a note after the base URL section (after line 3) explaining the ID format:

```markdown
**Task IDs:** All task IDs are 64-character lowercase hex strings generated using a cryptographically secure random number generator (256 bits of entropy). They are not sequential and cannot be guessed.
```

- [ ] **Step 2: Update POST /tts/async response**

Replace the response section of `POST /tts/async` (lines 47-55) with:

```json
{
  "task_id": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "status": "pending",
  "poll_url": "/v1/tts/async/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "download_url": "/v1/tts/async/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1/download"
}
```

- [ ] **Step 3: Update GET /tts/async/{task_id} response**

Add `download_url` field to the status response example (around line 66):

```json
{
  "id": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "status": "completed",
  "payload": {
    "text": "Hello world",
    "voice": "Leo",
    "speed": 1.0,
    "clean_text": false
  },
  "result_path": "/data/audio/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1.wav",
  "download_url": "/v1/tts/async/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1/download",
  "error": null,
  "progress": 100,
  "created_at": "2026-06-20T12:00:00",
  "started_at": "2026-06-20T12:00:01",
  "completed_at": "2026-06-20T12:00:05",
  "worker_id": "worker-1"
}
```

- [ ] **Step 4: Add new download endpoint section**

After the `POST /tts/async/{task_id}/cancel` section (after line 113), add:

```markdown
---

## GET /tts/async/{task_id}/download

Download the audio file for a completed async TTS task.

**Response (200):** Binary audio stream (WAV, 24kHz)

**Response headers:**
```
Content-Type: audio/wav
Content-Disposition: attachment; filename="{task_id}.wav"
```

**Errors:**

| Status | Meaning |
|--------|---------|
| 404 | Task not found |
| 409 | Task not completed (pending, processing, or failed) |
| 503 | Service unavailable |
```

- [ ] **Step 5: Commit**

```bash
git add API.md
git commit -m "docs: document async download endpoint and secure task ID format"
```

---

### Task 5: Verify changes end-to-end

- [ ] **Step 1: Run linter**

Run: `uv run ruff check src/ scripts/`
Expected: No errors

- [ ] **Step 2: Verify imports are clean**

Run: `python3 -c "from src.db.queue import TaskQueueManager; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Check for any remaining uuid4 references**

Run: `grep -rn 'uuid' src/ scripts/`
Expected: No output

- [ ] **Step 4: Final commit if needed**

If any fixes were required, commit them:

```bash
git add -A
git commit -m "fix: clean up remaining uuid references"
```
