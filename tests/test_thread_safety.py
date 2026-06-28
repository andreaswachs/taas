"""Tests for KittenTTS thread-safety fix.

KittenTTS's internal espeak-ng phonemizer is not thread-safe. These tests
verify that the KittenTTSModelWrapper serializes concurrent inference calls
via a threading.Lock.
"""
import asyncio
import threading
import time
from unittest.mock import MagicMock

import pytest

from src.tts.engine import KittenTTSModelWrapper


@pytest.fixture
def mock_model():
    """Return a mock KittenTTS model that tracks concurrent access."""
    model = MagicMock()
    model.generate.return_value = [0.0, 0.1, 0.2]  # fake audio array
    return model


@pytest.fixture
def engine(mock_model):
    """Return a KittenTTSModelWrapper with a pre-loaded mock model."""
    wrapper = KittenTTSModelWrapper()
    wrapper._model = mock_model
    return wrapper


class TestInferenceLock:
    """Tests that verify inference calls are serialized."""

    def test_generate_locked_acquires_lock(self, engine, mock_model):
        """_generate_locked must acquire the inference lock during generation."""
        assert not engine._inference_lock.locked()

        engine._generate_locked("hello", "Luna", 1.0, False)

        mock_model.generate.assert_called_once_with(
            "hello", voice="Luna", speed=1.0, clean_text=False
        )
        assert not engine._inference_lock.locked()

    def test_generate_locked_is_not_reentrant(self, engine):
        """The inference lock must block a second call until the first finishes."""
        inside_event = threading.Event()
        release_event = threading.Event()
        call_count = 0

        def slow_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            inside_event.set()    # signal we are inside generate
            release_event.wait()  # hold the lock until told to release
            return [0.0]

        engine._model.generate = slow_generate

        def caller():
            engine._generate_locked("text", "Luna", 1.0, False)

        t1 = threading.Thread(target=caller)
        t1.start()

        # Wait until t1 is definitely inside the locked section
        inside_event.wait(timeout=2)
        assert inside_event.is_set(), "Thread 1 never entered generate"

        # Now t2 should block trying to acquire the lock
        t2 = threading.Thread(target=caller)
        t2.start()
        t2.join(timeout=0.1)
        assert t2.is_alive(), "Thread 2 should be blocked waiting for the lock"

        # Let t1 finish so t2 can proceed
        release_event.set()
        t1.join(timeout=2)
        t2.join(timeout=2)

        assert call_count == 2, "Both calls should eventually complete"

    def test_concurrent_generate_locked_serializes_access(self, engine):
        """Multiple concurrent threads must never overlap inside generate."""
        overlap_detected = False
        active_count = 0
        count_lock = threading.Lock()
        max_concurrent = 0

        def instrumented_generate(*args, **kwargs):
            nonlocal overlap_detected, active_count, max_concurrent
            with count_lock:
                active_count += 1
                if active_count > max_concurrent:
                    max_concurrent = active_count
                if active_count > 1:
                    overlap_detected = True
            time.sleep(0.03)  # simulate work
            with count_lock:
                active_count -= 1
            return [0.0]

        engine._model.generate = instrumented_generate

        threads = [
            threading.Thread(target=engine._generate_locked, args=(f"text{i}", "Luna", 1.0, False))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not overlap_detected, (
            "Concurrent calls overlapped inside generate — lock is not working"
        )
        assert max_concurrent == 1, (
            f"Expected max concurrent access = 1, got {max_concurrent}"
        )


class TestAsyncGenerateMethods:
    """Tests for the async public methods that delegate to _generate_locked."""

    @pytest.mark.asyncio
    async def test_generate_with_format_uses_lock(self, engine, mock_model, monkeypatch):
        """generate_with_format should delegate to _generate_locked."""
        from src.db.schema import TtsRequestPayload

        # Bypass soundfile by mocking the bytes conversion
        async def fake_bytes(audio_array, fmt):
            return b"FAKE_AUDIO"
        monkeypatch.setattr(engine, "_audio_array_to_bytes", fake_bytes)

        payload = TtsRequestPayload(
            text="Hello world",
            voice="Luna",
            speed=1.0,
            clean_text=False,
        )

        result = await engine.generate_with_format(payload)

        assert result.task_id is not None
        assert result.format.value == "wav"
        mock_model.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_to_file_uses_lock(self, engine, mock_model, tmp_path):
        """generate_to_file should delegate to _generate_locked."""
        from src.db.schema import TtsRequestPayload

        payload = TtsRequestPayload(
            text="Hello world",
            voice="Luna",
            speed=1.0,
            clean_text=False,
        )
        output_file = tmp_path / "test.wav"

        result_path = await engine.generate_to_file(
            "task-123", payload, output_file
        )

        assert result_path == str(output_file)
        mock_model.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_async_calls_are_serialized(self, mock_model):
        """Multiple asyncio tasks must not overlap inside model.generate."""
        engine = KittenTTSModelWrapper()
        engine._model = mock_model

        overlap_detected = False
        active_count = 0
        count_lock = threading.Lock()

        def instrumented_generate(*args, **kwargs):
            nonlocal overlap_detected, active_count
            with count_lock:
                active_count += 1
                if active_count > 1:
                    overlap_detected = True
            time.sleep(0.04)
            with count_lock:
                active_count -= 1
            return [0.0]

        mock_model.generate = instrumented_generate

        from src.db.schema import TtsRequestPayload

        payloads = [
            TtsRequestPayload(text=f"text{i}", voice="Luna", speed=1.0, clean_text=False)
            for i in range(5)
        ]

        tasks = [asyncio.create_task(engine.generate_with_format(p)) for p in payloads]
        await asyncio.gather(*tasks, return_exceptions=True)

        assert not overlap_detected, (
            "Concurrent async tasks overlapped inside generate — inference lock is broken"
        )
