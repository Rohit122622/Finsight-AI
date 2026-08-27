"""
FinSentry AI — Chat & Real-Time Event Persistence Models (Phase 2I).
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRole(str, Enum):
    """Role of a message participant."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"


class CitationSource(BaseModel):
    """Source citation referencing an ingested document chunk."""
    document_id: str = Field(..., description="ID of source document")
    chunk_id: Optional[str] = Field(None, description="ID of specific source chunk")
    chunk_index: Optional[int] = Field(None, description="Index of chunk in document")
    snippet: str = Field(..., description="Relevant extracted snippet")
    page_number: Optional[int] = Field(None, description="Page number if available")
    similarity_score: Optional[float] = Field(None, description="Vector similarity score")


class ChatMessageModel(BaseModel):
    """
    MongoDB persistence document for an interactive research session chat message.
    """

    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId string")
    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for the chat message",
    )
    session_id: str = Field(..., description="ID of the research session")
    user_id: str = Field(..., description="Owner user ID for tenant isolation")
    role: ChatRole = Field(default=ChatRole.USER, description="Message sender role")
    content: str = Field(..., description="Text content of the message")
    agent_name: Optional[str] = Field(None, description="Name of generating agent if applicable")
    sources: List[CitationSource] = Field(
        default_factory=list, description="Citations and evidence grounding the message"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary safe metadata"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp",
    )

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda dt: dt.isoformat()},
    }

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dict, excluding empty id."""
        data = self.model_dump(by_alias=False)
        if "id" in data and data["id"] is None:
            data.pop("id", None)
        return data


class RealTimeEventModel(BaseModel):
    """
    Schema for real-time WebSocket and Redis Pub/Sub events.
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event ID",
    )
    event_type: str = Field(..., description="e.g. job_progress, agent_milestone, chat_token, notification")
    session_id: str = Field(..., description="Target session ID")
    user_id: Optional[str] = Field(None, description="Target user ID or broadcast")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO UTC timestamp",
    )
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
