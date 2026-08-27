"""
FinSentry AI — Phase 3H Research Chat & API Router.

Exposes REST endpoints for:
  - POST /api/v1/research/chat (streaming and non-streaming)
  - GET /api/v1/research/conversations/{conversation_id}
  - GET /api/v1/research/conversations/{conversation_id}/messages
  - GET /api/v1/research/sessions/{session_id}/history
  - GET /api/v1/research/sessions/{session_id}/memory
  - DELETE /api/v1/research/conversations/{conversation_id}
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database, mongodb
from middleware.auth_middleware import get_current_user
from models.user import UserModel
from schemas.observability import TraceDetailResponse, TraceListResponse
from schemas.research_api import (
    ResearchChatRequest,
    ResearchChatResponse,
    ResearchConversation,
    ResearchHistoryResponse,
    ResearchMessage,
    SessionMemoryResponse,
)
from services.observability_service import observability_service
from services.research_chat_service import research_chat_service
from services.session_service import verify_session_ownership

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/chat",
    response_model=ResearchChatResponse,
    responses={
        200: {
            "description": "Validated research response or Server-Sent Events stream",
            "content": {
                "application/json": {},
                "text/event-stream": {},
            },
        }
    },
    summary="Execute research chat (streaming or non-streaming)",
)
async def research_chat(
    request: ResearchChatRequest,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Execute evidence-grounded research chat turn with multi-tenant session isolation.

    Supports:
      - Multi-turn research conversations
      - Session research memory
      - Hybrid retrieval (Phase 3A)
      - Query understanding (Phase 3B)
      - Multi-source context building (Phase 3C)
      - Prompt engineering (Phase 3D)
      - LLM Fallback (Phase 3F)
      - Evidence reasoning & claim extraction (Phase 3E)
      - Strict multi-tenant output validation (Phase 3G)
      - Real-time Server-Sent Events (SSE) streaming (Phase 3H)
    """
    user_id = str(current_user.id)
    session_id = request.session_id


    try:
        session = await verify_session_ownership(db, session_id, user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Database error verifying session ownership: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service unavailable.",
        )

    if session is None:
        logger.warning(
            "Research chat unauthorized: session %s not found or not owned by user %s",
            session_id,
            user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )


    if request.stream:
        return StreamingResponse(
            research_chat_service.stream_chat(
                session_id=session_id,
                user_id=user_id,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


    try:
        response = await research_chat_service.execute_chat(
            session_id=session_id,
            user_id=user_id,
            request=request,
        )
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error executing research chat: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during research analysis.",
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ResearchConversation,
    summary="Get research conversation details",
)
async def get_conversation(
    conversation_id: str = Path(..., description="Conversation UUID"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve research conversation metadata ensuring user tenant isolation.
    """
    user_id = str(current_user.id)
    conv = await research_chat_service.get_conversation(conversation_id, user_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    return ResearchConversation(
        conversation_id=conv["conversation_id"],
        session_id=conv["session_id"],
        user_id=conv["user_id"],
        title=conv.get("title"),
        message_count=conv.get("message_count", 0),
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[ResearchMessage],
    summary="Get conversation message history",
)
async def get_conversation_messages(
    conversation_id: str = Path(..., description="Conversation UUID"),
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve all messages for a conversation ensuring tenant isolation.
    """
    user_id = str(current_user.id)
    conv = await research_chat_service.get_conversation(conversation_id, user_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    api_messages, _ = await research_chat_service.load_conversation_history(
        session_id=conv["session_id"],
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return api_messages


@router.get(
    "/sessions/{session_id}/conversations",
    response_model=List[ResearchConversation],
    summary="List all research conversations in a session",
)
async def list_session_conversations(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve all conversation threads in a session with full tenant isolation.
    """
    user_id = str(current_user.id)
    session = await verify_session_ownership(db, session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )

    raw_convs = await research_chat_service.list_conversations(session_id, user_id)
    return [
        ResearchConversation(
            conversation_id=c["conversation_id"],
            session_id=c["session_id"],
            user_id=c["user_id"],
            title=c.get("title") or "Financial Research Conversation",
            message_count=c.get("message_count", 0),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in raw_convs
    ]


@router.get(
    "/sessions/{session_id}/history",
    response_model=ResearchHistoryResponse,
    summary="Get session research history across all conversations",
)
async def get_session_research_history(
    session_id: str = Path(..., description="Research session ID"),
    conversation_id: Optional[str] = Query(None, description="Optional conversation filter"),
    limit: int = Query(default=100, ge=1, le=200, description="Max messages to return"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve all research messages in a session.
    """
    user_id = str(current_user.id)
    session = await verify_session_ownership(db, session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )

    api_messages, _ = await research_chat_service.load_conversation_history(
        session_id=session_id,
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return ResearchHistoryResponse(
        session_id=session_id,
        conversation_id=conversation_id,
        messages=api_messages,
        total_messages=len(api_messages),
    )


@router.get(
    "/sessions/{session_id}/memory",
    response_model=SessionMemoryResponse,
    summary="Get session research memory",
)
async def get_session_memory(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve session research memory (entities, topics, discussed metrics, periods).
    """
    user_id = str(current_user.id)
    session = await verify_session_ownership(db, session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )

    memory = await research_chat_service.load_session_memory(session_id=session_id, user_id=user_id)
    db = mongodb.get_db()
    raw_doc = await db.research_session_memory.find_one(
        {"session_id": session_id, "user_id": user_id}
    )

    return SessionMemoryResponse(
        session_id=session_id,
        user_id=user_id,
        topic=memory.topic if memory else None,
        entities=memory.entities if memory else [],
        metrics_discussed=memory.metrics_discussed if memory else [],
        periods_discussed=memory.periods_discussed if memory else [],
        prior_queries=memory.prior_queries if memory else [],
        document_ids=memory.document_ids if memory else [],
        updated_at=raw_doc.get("updated_at") if raw_doc else datetime.now(timezone.utc),
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete research conversation and associated messages",
)
async def delete_conversation(
    conversation_id: str = Path(..., description="Conversation UUID"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Delete a conversation and its messages ensuring tenant isolation.
    """
    user_id = str(current_user.id)
    conv = await research_chat_service.get_conversation(conversation_id, user_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    await db.research_conversations.delete_one(
        {"conversation_id": conversation_id, "user_id": user_id}
    )
    delete_result = await db.research_messages.delete_many(
        {"conversation_id": conversation_id, "user_id": user_id}
    )

    return {
        "status": "deleted",
        "conversation_id": conversation_id,
        "messages_deleted": delete_result.deleted_count,
    }




@router.get(
    "/sessions/{session_id}/traces",
    response_model=TraceListResponse,
    summary="Get research telemetry traces for session",
)
async def get_session_traces(
    session_id: str = Path(..., description="Research session ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Max traces to return"),
    skip: int = Query(default=0, ge=0, description="Traces offset"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve telemetry traces for a research session with strict tenant isolation.
    """
    user_id = str(current_user.id)
    session = await verify_session_ownership(db, session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )

    return await observability_service.get_session_traces(
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        skip=skip,
    )


@router.get(
    "/traces/{trace_id}",
    response_model=TraceDetailResponse,
    summary="Get full trace detail by trace_id",
)
async def get_trace_detail(
    trace_id: str = Path(..., description="Unique trace UUID"),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    """
    Retrieve detailed trace execution hierarchy and metrics for an authorized user.
    """
    user_id = str(current_user.id)
    trace = await observability_service.get_trace_detail(trace_id=trace_id, user_id=user_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found or access denied.",
        )

    return TraceDetailResponse(trace=trace)

