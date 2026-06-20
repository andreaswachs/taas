# Design: Async TTS Audio Download Endpoint

## Problem

After submitting an async TTS job via `POST /v1/tts/async` and polling `GET /v1/tts/async/{task_id}` until completion, users receive a `result_path` field containing a server-side filesystem path (e.g., `/data/audio/abc.wav`). There is no HTTP endpoint to download the generated audio file.

Additionally, task IDs are currently UUID v4 strings, which are predictable enough to allow enumeration attacks if exposed in download URLs.

## Solution

### 1. Secure Task ID Generation

Replace `uuid.uuid4()` with `secrets.token_hex(32)` in `src/db/queue.py`.

- **Before:** `550e8400-e29b-41d4-a716-446655440000` (UUID v4, ~122 bits entropy)
- **After:** `a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1` (256 bits entropy)

This eliminates enumeration risk: with 2^256 possible IDs, brute-force guessing is computationally infeasible.

### 2. New Download Endpoint

**Route:** `GET /v1/tts/async/{task_id}/download`

**Behavior by task status:**

| Status | Response |
|--------|----------|
| Not found | 404 Not Found |
| `pending` | 409 Conflict |
| `processing` | 409 Conflict |
| `failed` | 409 Conflict |
| `completed` | 200 OK, binary WAV stream |

**Response headers on success:**
```
Content-Type: audio/wav
Content-Disposition: attachment; filename="{task_id}.wav"
```

**Error response body (409):**
```json
{
  "detail": "Task is not completed. Current status: processing"
}
```

### 3. Updated API Responses

Add `download_url` field to the async submit response and the status poll response.

**POST /v1/tts/async response (202):**
```json
{
  "task_id": "a3f8b2c1...",
  "status": "pending",
  "poll_url": "/v1/tts/async/a3f8b2c1...",
  "download_url": "/v1/tts/async/a3f8b2c1.../download"
}
```

**GET /v1/tts/async/{task_id} response (200):**
```json
{
  "id": "a3f8b2c1...",
  "status": "completed",
  "payload": { ... },
  "result_path": "/data/audio/a3f8b2c1....wav",
  "download_url": "/v1/tts/async/a3f8b2c1.../download",
  "error": null,
  "progress": 100,
  "created_at": "2026-06-20T12:00:00",
  "started_at": "2026-06-20T12:00:01",
  "completed_at": "2026-06-20T12:00:05",
  "worker_id": "worker-1"
}
```

### 4. Files to Modify

| File | Change |
|------|--------|
| `src/db/queue.py:85` | Replace `str(uuid.uuid4())` with `secrets.token_hex(32)` |
| `src/api/v1_routes.py` | Add new `GET /tts/async/{task_id}/download` endpoint; add `download_url` to async submit and status responses |
| `API.md` | Document new endpoint, update response schemas, update ID format description |

### 5. Out of Scope

- Authentication/authorization on the download endpoint (future work)
- Streaming/range requests for large files
- Signed URLs or expiring download links
- Migration of existing UUID-format task IDs in the database

## Testing

1. Submit an async TTS job, verify `download_url` is present in the response
2. Poll status, verify `download_url` is present while task is pending/processing
3. Attempt download before completion, verify 409 response
4. Download after completion, verify valid WAV file returned with correct headers
5. Download with nonexistent task ID, verify 404 response
6. Verify new task IDs are 64-char hex strings (not UUID format)
