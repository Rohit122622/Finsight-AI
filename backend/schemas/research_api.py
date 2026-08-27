"""
FinSentry AI — Phase 3H Research API Schemas.

Pydantic schemas for the Research API layer:
  - ResearchChatRequest
  - ResearchChatResponse
  - ResearchConversation
  - ResearchMessage
  - StreamEventType & StreamEvent
  - ResearchHistoryResponse
  - SessionMemoryResponse
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from schemas.reasoning import (
    ConfidenceLevel,
    ResearchCitation,
    ResearchClaim,
    ResearchResponse,
)
from schemas.output_validation import ValidationResult, ValidationStatus
from schemas.retrieval import RetrievalMode


class StreamEventType(str, Enum):
    """Event types emitted during streaming research execution."""

    STARTED = "started"
    QUERY_UNDERSTANDING = "query_understanding"
    RETRIEVAL = "retrieval"
    CONTEXT = "context"
    GENERATION = "generation"
    CITATION = "citation"
    VALIDATION = "validation"
    TOKEN = "token"
    CONTENT_DELTA = "content_delta"
    COMPLETED = "completed"
    REFUSED = "refused"
    ERROR = "error"


class ResearchChatRequest(BaseModel):
    """
    Request model for the Research Chat API (POST /api/v1/research/chat).
    """

    session_id: str = Field(..., description="ID of the owning research session")
    message: str = Field(..., description="Research question or user query prompt")
    conversation_id: Optional[str] = Field(
        None, description="Optional conversation UUID to continue multi-turn research"
    )
    stream: bool = Field(
        default=False, description="Whether to stream response via Server-Sent Events"
    )
    top_k: int = Field(
        default=5, ge=1, le=50, description="Maximum evidence chunks to retrieve"
    )
    mode: RetrievalMode = Field(
        default=RetrievalMode.HYBRID, description="Retrieval mode (hybrid, vector, keyword)"
    )
    score_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum retrieval similarity score"
    )
    document_ids: Optional[List[str]] = Field(
        None, description="Optional document ID filter"
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query/message cannot be empty or whitespace only.")
        if len(v) > 10000:
            raise ValueError("Query/message exceeds maximum allowed length (10,000 characters).")
        return v.strip()


class ResearchMessage(BaseModel):
    """
    Structured model for a single research conversation turn.
    """

    message_id: str = Field(..., description="Unique UUID of the message")
    conversation_id: str = Field(..., description="Conversation UUID")
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="Owning user ID")
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")
    claims: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="Validated claims for assistant messages"
    )
    citations: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="Validated source citations"
    )
    confidence_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confidence score"
    )
    confidence_tier: Optional[str] = Field(
        None, description="Confidence level (HIGH, MEDIUM, LOW, REFUSAL)"
    )
    validation_status: Optional[str] = Field(
        None, description="Validation status (VALID, DEGRADED, REFUSED)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp message was created",
    )


class ResearchConversation(BaseModel):
    """
    Research conversation summary model.
    """

    conversation_id: str = Field(..., description="Unique conversation UUID")
    session_id: str = Field(..., description="Research session ID")
    user_id: str = Field(..., description="Owning user ID")
    title: Optional[str] = Field(None, description="Conversation title or initial query")
    message_count: int = Field(default=0, description="Total messages in conversation")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last updated timestamp",
    )


class ResearchChatResponse(BaseModel):
    """
    Response model for non-streaming research chat.
    """

    conversation_id: str = Field(..., description="Conversation UUID")
    message_id: str = Field(..., description="Generated assistant message UUID")
    session_id: str = Field(..., description="Research session ID")
    user_id: str = Field(..., description="Owning user ID")
    trace_id: Optional[str] = Field(None, description="Phase 3J observability trace UUID")
    response: ResearchResponse = Field(
        ..., description="Validated Phase 3E/3G research response"
    )
    validation: ValidationResult = Field(
        ..., description="Complete Phase 3G output validation audit result"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Response timestamp",
    )


class StreamEvent(BaseModel):
    """
    Structured event payload emitted during streaming.
    """

    event: StreamEventType = Field(..., description="Event type name")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp",
    )

    def to_sse(self) -> str:
        """Format as Server-Sent Event string."""
        import json
        return f"event: {self.event.value}\ndata: {json.dumps(self.data)}\n\n"


class ResearchHistoryResponse(BaseModel):
    """
    Response model for retrieving conversation research history.
    """

    session_id: str = Field(..., description="Session ID")
    conversation_id: Optional[str] = Field(None, description="Conversation ID if filtered")
    messages: List[ResearchMessage] = Field(
        default_factory=list, description="Ordered conversation messages"
    )
    total_messages: int = Field(default=0, description="Count of returned messages")


class SessionMemoryResponse(BaseModel):
    """
    Response model for session research memory.
    """

    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="User ID")
    topic: Optional[str] = Field(None, description="Primary research topic")
    entities: List[str] = Field(default_factory=list, description="Identified companies/entities")
    metrics_discussed: List[str] = Field(default_factory=list, description="Financial metrics discussed")
    periods_discussed: List[str] = Field(default_factory=list, description="Periods discussed")
    prior_queries: List[str] = Field(default_factory=list, description="Prior research queries")
    document_ids: List[str] = Field(default_factory=list, description="Referenced document IDs")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp memory was last updated",
    )
