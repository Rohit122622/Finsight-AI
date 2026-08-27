"""
Job document model for persistent asynchronous agent task execution.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from core.constants import AgentTaskType, JobStatus


class JobModel(BaseModel):
    """
    MongoDB persistence schema for asynchronous agent jobs.
    """

    job_id: str = Field(..., description="Unique UUID for the asynchronous job")
    user_id: str = Field(..., description="User ID owning this job")
    session_id: Optional[str] = Field(None, description="Associated research session ID if applicable")
    agent_name: str = Field(..., description="Registered agent assigned to this job")
    task_type: str = Field(default=AgentTaskType.DUMMY_TASK.value, description="Task categorization")
    status: str = Field(default=JobStatus.QUEUED.value, description="Current lifecycle state")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(None, description="Timestamp when worker began processing")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when job reached terminal state")

    @field_validator("created_at", "started_at", "completed_at", mode="before")
    @classmethod
    def ensure_utc_datetime(cls, v: Any) -> Optional[datetime]:
        """Normalize naive or string datetimes to timezone-aware UTC datetimes."""
        if v is None:
            return None
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
        return v
    retry_count: int = Field(default=0, ge=0, description="Number of retries attempted")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry limit before permanent failure")
    timeout_seconds: int = Field(default=300, gt=0, description="Maximum allowed execution window")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Execution progress percentage 0-100")
    current_step: Optional[str] = Field(None, description="Current workflow or agent execution step")
    events: list[dict[str, Any]] = Field(
        default_factory=list, description="Ordered audit log of live progress events"
    )
    error: Optional[str] = Field(None, description="Error message if job failed")
    result_summary: Optional[Dict[str, Any]] = Field(
        None, description="Lightweight summary of results (never large raw files)"
    )
    result_ref: Optional[str] = Field(
        None, description="Pointer/reference to stored artifact or output collection"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Arbitrary safe execution metadata"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dict format."""
        data = self.model_dump()
        return data

    @classmethod
    def from_mongo(cls, doc: Dict[str, Any]) -> "JobModel":
        """Reconstruct model from MongoDB document, removing Mongo ObjectId."""
        if not doc:
            raise ValueError("Empty document cannot be converted to JobModel")
        doc_copy = dict(doc)
        doc_copy.pop("_id", None)
        return cls(**doc_copy)
