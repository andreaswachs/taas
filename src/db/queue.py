import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import aiosqlite
import logging

from .schema import Task, TaskStatus, TtsRequestPayload, QueueStats

logger = logging.getLogger(__name__)


class TaskQueueManager:
    def __init__(self, db_path: str, max_workers: int, max_queue_depth: int):
        self.db_path = db_path
        self.max_workers = max_workers
        self.max_queue_depth = max_queue_depth
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        await self._create_schema()
        await self._enable_wal_mode()
        await self._db.commit()
        await self._reset_stale_processing_tasks()
    
    async def _reset_stale_processing_tasks(self) -> None:
        cursor = await self._db.execute(
            "UPDATE tasks SET status = 'pending', worker_id = NULL, started_at = NULL "
            "WHERE status = 'processing'"
        )
        await self._db.commit()
        if cursor.rowcount > 0:
            logger.info("Reset stale processing tasks", extra={"count": cursor.rowcount})
    
    async def _create_schema(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                payload TEXT NOT NULL,
                result_path TEXT,
                error TEXT,
                progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                worker_id TEXT
            )
        """)
        
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_queue 
            ON tasks(status, created_at) 
            WHERE status IN ('pending', 'processing')
        """)
        
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_worker 
            ON tasks(worker_id) 
            WHERE status = 'processing'
        """)
    
    async def _enable_wal_mode(self) -> None:
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA synchronous=NORMAL")
    
    @asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            async with self._db.execute("BEGIN IMMEDIATE"):
                try:
                    yield
                    await self._db.commit()
                except Exception:
                    await self._db.rollback()
                    raise
    
    async def enqueue_task(self, payload: TtsRequestPayload) -> Task:
        task_id = secrets.token_hex(32)
        task = Task(
            id=task_id,
            status=TaskStatus.PENDING,
            payload=payload,
            created_at=datetime.utcnow(),
        )
        
        async with self._transaction():
            pending_count = await self.get_pending_count()
            if pending_count >= self.max_queue_depth:
                raise QueueFullError(f"Queue is full (max {self.max_queue_depth} pending tasks)")
            
            await self._db.execute(
                """INSERT INTO tasks (id, status, payload, progress, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task.id, task.status.value, task.payload.model_dump_json(), 0, task.created_at.isoformat())
            )
        
        return task
    
    async def get_pending_count(self) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    
    async def get_processing_count(self) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'processing'"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    
    async def get_queue_depth(self) -> int:
        return await self.get_pending_count()
    
    async def claim_next_task(self, worker_id: str) -> Optional[Task]:
        async with self._lock:
            processing_count = await self.get_processing_count()
            if processing_count >= self.max_workers:
                return None
            
            cursor = await self._db.execute(
                "SELECT id FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1"
            )
            row = await cursor.fetchone()
            if not row:
                return None
            
            task_id = row[0]
            await self._db.execute(
                """UPDATE tasks 
                   SET status = 'processing', started_at = ?, worker_id = ?
                   WHERE id = ?""",
                (datetime.utcnow().isoformat(), worker_id, task_id)
            )
            await self._db.commit()
            
            return await self.get_task(task_id)
    
    async def update_task(
        self, 
        task_id: str, 
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        result_path: Optional[str] = None,
        error: Optional[str] = None,
        worker_id: Optional[str] = None
    ) -> bool:
        updates = []
        params = []
        
        if status is not None:
            updates.append("status = ?")
            params.append(status.value if hasattr(status, 'value') else status)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                updates.append("completed_at = ?")
                params.append(datetime.utcnow().isoformat())
        
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        
        if result_path is not None:
            updates.append("result_path = ?")
            params.append(result_path)
        
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        
        if worker_id is not None:
            updates.append("worker_id = ?")
            params.append(worker_id)
        
        if not updates:
            return False
        
        params.append(task_id)
        
        async with self._transaction():
            cursor = await self._db.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cursor.rowcount > 0
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        cursor = await self._db.execute(
            "SELECT id, status, payload, result_path, error, progress, "
            "created_at, started_at, completed_at, worker_id "
            "FROM tasks WHERE id = ?",
            (task_id,)
        )
        row = await cursor.fetchone()
        if row:
            return Task.from_row(row)
        return None
    
    async def get_stats(self) -> QueueStats:
        cursor = await self._db.execute("""
            SELECT 
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                COUNT(*) as total
            FROM tasks
        """)
        row = await cursor.fetchone()
        if row:
            return QueueStats(
                pending=row[0] or 0,
                processing=row[1] or 0,
                completed=row[2] or 0,
                failed=row[3] or 0,
                total=row[4] or 0,
            )
        return QueueStats(pending=0, processing=0, completed=0, failed=0, total=0)
    
    async def cleanup_old_tasks(self, days: int = 7) -> int:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        async with self._transaction():
            cursor = await self._db.execute(
                "DELETE FROM tasks WHERE status IN ('completed', 'failed') "
                "AND completed_at < ?",
                (cutoff.isoformat(),)
            )
            return cursor.rowcount
    
    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None


class QueueFullError(Exception):
    pass