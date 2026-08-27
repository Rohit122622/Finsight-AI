"""
Pydantic schemas for research-session request/response payloads.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Payload for creating a new research session."""

    session_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        examples=["Q2 2026 Market Analysis"],
    )


class UpdateSessionRequest(BaseModel):
    """Payload for updating a research session's name."""

    session_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        examples=["Updated Research Session Name"],
    )


class SessionResponse(BaseModel):
    """Public-facing representation of a research session."""

    id: str
    user_id: str
    session_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


class SessionListResponse(BaseModel):
    """Paginated list of research sessions with metadata."""

    sessions: List[SessionResponse]
    total: int
    page: int
    page_size: int
