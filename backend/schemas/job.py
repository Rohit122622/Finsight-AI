"""
Pydantic API schemas for Job creation and status inspection.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from core.constants import AgentTaskType, JobStatus


class JobCreateRequest(BaseModel):
    """Payload for submitting an asynchronous agent job."""

    agent_name: str = Field(..., description="Target agent name (e.g. 'DummyAgent')")
    task_type: str = Field(
        default=AgentTaskType.DUMMY_TASK.value,
        description="Type of task to perform",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters for the agent",
    )
    session_id: Optional[str] = Field(
        None,
        description="Optional research session ID to bind this job to",
    )
    timeout_seconds: Optional[int] = Field(
        None,
        gt=0,
        description="Custom execution timeout in seconds (optional)",
    )
    max_retries: Optional[int] = Field(
        None,
        ge=0,
        description="Custom maximum retry attempts (optional)",
    )


class JobResponse(BaseModel):
    """Full details of a registered job."""

    job_id: str
    user_id: str
    session_id: Optional[str] = None
    agent_name: str
    task_type: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int
    max_retries: int
    timeout_seconds: int
    progress_percent: int = 0
    current_step: Optional[str] = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    result_summary: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Lightweight response for polling job status."""

    job_id: str
    status: JobStatus
    retry_count: int
    progress_percent: int = 0
    current_step: Optional[str] = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None
