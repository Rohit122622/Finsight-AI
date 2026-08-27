"""
FinSentry AI — Chat & WebSocket API Schemas (Phase 2I).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models.chat import ChatRole, CitationSource


class SendChatMessageRequest(BaseModel):
    """Payload for submitting a chat query to research agents in a session."""
    content: str = Field(..., min_length=1, max_length=4000, description="User prompt or question")
    enable_rag: bool = Field(default=True, description="Whether to ground answer in session documents")
    top_k: int = Field(default=5, ge=1, le=20, description="Max citation chunks to retrieve")
    stream: bool = Field(default=False, description="Whether caller requests WebSocket stream vs REST response")


class ChatMessageResponse(BaseModel):
    """Response representation of a single chat message."""
    message_id: str
    session_id: str
    user_id: str
    role: ChatRole
    content: str
    agent_name: Optional[str] = None
    sources: List[CitationSource] = []
    metadata: Dict[str, Any] = {}
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """Paginated or complete chat history list."""
    session_id: str
    total: int
    messages: List[ChatMessageResponse]


class WebSocketClientMessage(BaseModel):
    """Inbound message from WebSocket client."""
    action: str = Field(..., description="Action type: 'chat', 'subscribe', 'ping', 'cancel'")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Action arguments")


class WebSocketServerMessage(BaseModel):
    """Outbound message emitted by the WebSocket server."""
    type: str = Field(..., description="Message type: 'chat_delta', 'chat_complete', 'job_progress', 'agent_status', 'pong', 'error'")
    session_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
