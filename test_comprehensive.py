#!/usr/bin/env python3
"""
Simple test to verify the KittenTTS service can be imported and initialized correctly.
This test can be run after building the container to verify basic functionality.
"""
import asyncio
import tempfile
import os
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    # Test core imports
    from src.api.config import get_settings
    from src.db.schema import TtsRequestPayload, TaskStatus
    from src.db.queue import TaskQueueManager, QueueFullError
    from src.tts.engine import KittenTTSModelWrapper, AudioFormat
    from src.api.v1_routes import create_v1_router
    from src.monitoring import create_metrics_app
    from scripts.workers import BackgroundWorker, TaskQueueManagerWithWorkers
    
    print("✅ All imports successful")


def test_settings():
    """Test that settings can be loaded."""
    print("Testing settings...")
    
    from src.api.config import get_settings
    
    settings = get_settings()
    
    assert settings.db_path.endswith("tasks.db"), f"Expected tasks.db, got {settings.db_path}"
    assert settings.max_workers == 5, f"Expected 5 max workers, got {settings.max_workers}"
    assert settings.max_text_length == 64000, f"Expected 64000 max text length, got {settings.max_text_length}"
    assert settings.default_voice == "Leo", f"Expected Leo as default voice, got {settings.default_voice}"
    assert len(settings.available_voices) == 8, f"Expected 8 voices, got {len(settings.available_voices)}"
    
    print(f"✅ Settings loaded correctly")
    print(f"   Database path: {settings.db_path}")
    print(f"   Max workers: {settings.max_workers}")
    print(f"   Max text length: {settings.max_text_length}")
    print(f"   Available voices: {len(settings.available_voices)}")


async def test_database_layer():
    """Test the SQLite database layer."""
    print("Testing database layer...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_tasks.db")
        
        from src.db.queue import TaskQueueManager, TtsRequestPayload
        from src.db.schema import TaskStatus
        
        queue = TaskQueueManager(db_path, max_workers=2, max_queue_depth=100)
        await queue.initialize()
        
        # Test enqueue
        payload = TtsRequestPayload(
            text="Hello world test",
            voice="Bella",
            speed=1.0,
            clean_text=False
        )
        
        task = await queue.enqueue_task(payload)
        assert task.id is not None, "Task should have an ID"
        assert task.status == TaskStatus.PENDING, "Task should be pending"
        assert task.payload.text == "Hello world test", "Task payload should match"
        
        # Test get task
        retrieved_task = await queue.get_task(task.id)
        assert retrieved_task is not None, "Task should be retrievable"
        assert retrieved_task.id == task.id, "Task ID should match"
        
        # Test stats
        stats = await queue.get_stats()
        assert stats.pending == 1, f"Expected 1 pending task, got {stats.pending}"
        
        # Test claim task
        worker_id = "test-worker"
        claimed_task = await queue.claim_next_task(worker_id)
        assert claimed_task is not None, "Task should be claimable"
        assert claimed_task.id == task.id, "Claimed task ID should match"
        
        # Test update task
        updated = await queue.update_task(
            task.id,
            status="processing",
            progress=50,
            worker_id=worker_id
        )
        assert updated, "Task update should succeed"
        
        # Verify update
        updated_task = await queue.get_task(task.id)
        assert updated_task.status == "processing", "Task status should be processing"
        assert updated_task.progress == 50, "Task progress should be 50"
        
        # Test cleanup
        cleanup_count = await queue.cleanup_old_tasks(days=0)
        assert cleanup_count == 0, f"Expected 0 tasks to cleanup (none are old), got {cleanup_count}"
        
        await queue.close()
        
    print("✅ Database layer tests passed")


async def test_tts_engine():
    """Test the TTS engine (without actual model loading)."""
    print("Testing TTS engine...")
    
    from src.tts.engine import KittenTTSModelWrapper, AudioFormat
    from src.db.schema import TtsRequestPayload
    
    engine = KittenTTSModelWrapper()
    
    # Test enum values
    assert AudioFormat.WAV == "wav", "WAV enum should be 'wav'"
    assert AudioFormat.FLAC == "flac", "FLAC enum should be 'flac'"
    
    # Test request payload creation
    payload = TtsRequestPayload(
        text="Test text",
        voice="Jasper",
        speed=1.2,
        clean_text=True
    )
    
    assert payload.text == "Test text", "Payload text should match"
    assert payload.voice == "Jasper", "Payload voice should match"
    assert payload.speed == 1.2, "Payload speed should match"
    assert payload.clean_text == True, "Payload clean_text should be True"
    
    print("✅ TTS engine tests passed")


async def test_task_queue_manager():
    """Test the task queue manager with workers."""
    print("Testing TaskQueueManagerWithWorkers...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_tasks.db")
        audio_dir = os.path.join(temp_dir, "audio")
        
        from scripts.workers import TaskQueueManagerWithWorkers
        from src.db.schema import TtsRequestPayload
        
        manager = TaskQueueManagerWithWorkers(
            db_path=db_path,
            max_workers=2,
            max_queue_depth=100,
            audio_output_dir=audio_dir
        )
        
        await manager.initialize()
        await manager.start_workers()
        
        # Give workers time to start
        await asyncio.sleep(0.5)
        
        # Test enqueue
        payload = TtsRequestPayload(
            text="Test message for async queue",
            voice="Luna",
            speed=0.8,
            clean_text=False
        )
        
        task_id = await manager.enqueue_task(payload)
        assert task_id is not None, "Task ID should be generated"
        
        # Test get task status
        task_status = await manager.get_task_status(task_id)
        assert task_status is not None, "Task status should be retrievable"
        assert task_status["task_id"] == task_id, "Task ID should match"
        assert task_status["status"] == "pending", "Task should be pending"
        
        # Test stats
        stats = await manager.get_stats()
        assert stats["queue_stats"]["pending"] == 1, f"Expected 1 pending task, got {stats['queue_stats']['pending']}"
        assert stats["worker_stats"]["max_workers"] == 2, f"Expected 2 max workers, got {stats['worker_stats']['max_workers']}"
        
        # Test cleanup
        cleanup_count = await manager.cleanup_audio_files()
        assert cleanup_count == 0, f"Expected 0 tasks to cleanup, got {cleanup_count}"
        
        # Stop workers
        await manager.stop_workers()
        
    print("✅ TaskQueueManagerWithWorkers tests passed")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("KittenTTS Service - Comprehensive Test Suite")
    print("=" * 60)
    
    try:
        test_imports()
        test_settings()
        await test_database_layer()
        await test_tts_engine()
        await test_task_queue_manager()
        
        print("=" * 60)
        print("✅ All tests passed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print("=" * 60)
        print(f"❌ Test failed: {str(e)}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())