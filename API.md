# API Reference

Base URL: `http://localhost:8000/v1`

**Task IDs:** All task IDs are 64-character lowercase hex strings generated using a cryptographically secure random number generator (256 bits of entropy). They are not sequential and cannot be guessed.

---

## POST /tts

Synchronous TTS. Returns audio immediately.

**Request:**

```json
{
  "text": "Hello world",
  "voice": "Leo",
  "speed": 1.0,
  "clean_text": false
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | string | yes | — | Text to synthesize (max 64,000 chars) |
| `voice` | string | no | `"Leo"` | Voice name (see `/voices`) |
| `speed` | float | no | `1.0` | Playback speed (0.5–2.0) |
| `clean_text` | boolean | no | `false` | Expand numbers/dates |

**Response (200):** Binary audio stream (WAV, 24kHz)

**Errors:**

| Status | Meaning |
|--------|---------|
| 400 | Invalid voice |
| 413 | Text exceeds 64,000 chars |
| 503 | Service unavailable |

---

## POST /tts/async

Async TTS. Returns task ID for polling.

**Request:** Same as `POST /tts`

**Response (202):**

```json
{
  "task_id": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "status": "pending",
  "poll_url": "/v1/tts/async/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "download_url": "/v1/tts/async/a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1/download"
}
```

---

## GET /tts/async/{task_id}

Get async task status.

**Response (200):**

```json
{
  "task_id": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "status": "completed",
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

**Status values:** `pending` | `processing` | `completed` | `failed`

| Status | `result_path` | `error` |
|--------|---------------|---------|
| `completed` | Audio file path | `null` |
| `failed` | `null` | Error message |

**Errors:**

| Status | Meaning |
|--------|---------|
| 404 | Task not found |
| 503 | Service unavailable |

---

## POST /tts/async/{task_id}/cancel

Cancel a pending or processing task.

**Response (200):**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled"
}
```

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

---

## GET /voices

List available voices.

**Response (200):**

```json
{
  "voices": ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"],
  "default": "Leo"
}
```

---

## POST /cleanup

Delete completed/failed tasks older than N days.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | `7` | Retention period |

**Response (200):**

```json
{
  "message": "Cleaned up 42 old tasks",
  "days": 7
}
```

---

## GET /health

Health check endpoint.

**Response (200):**

```json
{
  "status": "healthy"
}
```

---

## GET /metrics

Prometheus metrics endpoint. Returns plain text in OpenMetrics format.

---

## GET /

AI agent discovery endpoint. Returns this entire API reference document as plain text, allowing agents to dynamically learn all available endpoints, request models, and response formats.

**Response (200):** `text/plain` — this document
