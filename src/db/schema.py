from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TtsRequestPayload(BaseModel):
    text: str
    voice: str = "Leo"
    speed: float = 1.0
    clean_text: bool = False


class Task(BaseModel):
    id: str
    status: TaskStatus
    payload: TtsRequestPayload
    result_path: Optional[str] = None
    error: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    
    @classmethod
    def from_row(cls, row: tuple) -> "Task":
        payload_data = json.loads(row[2])
        return cls(
            id=row[0],
            status=TaskStatus(row[1]),
            payload=TtsRequestPayload(**payload_data),
            result_path=row[3],
            error=row[4],
            progress=row[5],
            created_at=datetime.fromisoformat(row[6]) if row[6] else None,
            started_at=datetime.fromisoformat(row[7]) if row[7] else None,
            completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
            worker_id=row[9],
        )
    
    def to_insert_tuple(self) -> tuple:
        return (
            self.id,
            self.status.value,
            self.payload.model_dump_json(),
            self.result_path,
            self.error,
            self.progress,
            self.created_at.isoformat() if self.created_at else None,
            self.started_at.isoformat() if self.started_at else None,
            self.completed_at.isoformat() if self.completed_at else None,
            self.worker_id,
        )


class QueueStats(BaseModel):
    pending: int
    processing: int
    completed: int
    failed: int
    total: int