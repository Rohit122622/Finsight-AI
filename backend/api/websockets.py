"""
FinSentry AI — WebSocket & Real-Time Chat API (Phase 2I).

Provides bidirectional WebSocket streaming for agent events and chat, plus
REST fallbacks for chat history management.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.chat import (
    ChatHistoryResponse,
    ChatMessageResponse,
    SendChatMessageRequest,
)
from services.chat_stream_service import chat_stream_service
from services.event_bus import event_bus
from services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


                                                                
                        
                                                                

@router.websocket("/sessions/{session_id}/ws")
async def websocket_session_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = Query(None),
):
    """
    Authenticated WebSocket endpoint for real-time session streaming.

    Query Parameters:
        token: JWT access token for authentication during handshake.

    Close Codes:
        4001: Missing or invalid authentication token
        4003: Forbidden — session does not belong to authenticated user
        4004: Session not found
    """
                               
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    payload = await ws_manager.authenticate_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token subject")
        return

                                                          
    is_owner = await ws_manager.verify_session_ownership(session_id, user_id)
    if not is_owner:
        await websocket.close(code=4003, reason="Access denied to session stream")
        return

                                       
    await ws_manager.connect(websocket, session_id, user_id)

                                                
    await websocket.send_json({
        "type": "connection_established",
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "status": "connected",
            "message": "Real-time stream connected to FinSentry AI",
        },
    })

    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
            except Exception:
                await websocket.send_json({
                    "type": "error",
                    "session_id": session_id,
                    "payload": {"error": "Invalid JSON format"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            action = msg.get("action", "")

                                
            if action == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"client_time": msg.get("payload", {}).get("client_time")},
                })

                                
            elif action == "chat":
                content = msg.get("payload", {}).get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "payload": {"error": "Chat content cannot be empty"},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                enable_rag = msg.get("payload", {}).get("enable_rag", True)
                req = SendChatMessageRequest(content=content, enable_rag=enable_rag)

                                                               
                asyncio.create_task(
                    chat_stream_service.send_message(
                        session_id=session_id,
                        user_id=user_id,
                        request=req,
                    )
                )

                                     
            elif action == "subscribe":
                channels = msg.get("payload", {}).get("channels", ["all"])
                await websocket.send_json({
                    "type": "subscribed",
                    "session_id": session_id,
                    "payload": {"channels": channels},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            else:
                await websocket.send_json({
                    "type": "unknown_action",
                    "session_id": session_id,
                    "payload": {"action": action},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id, user_id)
    except Exception as exc:
        logger.warning("WebSocket error in session %s: %s", session_id, exc)
        await ws_manager.disconnect(websocket, session_id, user_id)


                                                                
                         
                                                                

@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["chat"],
)
async def send_chat_message(
    session_id: str,
    request: SendChatMessageRequest,
    current_user: UserModel = Depends(get_current_user),
    _session: SessionModel = Depends(require_session_owner),
) -> ChatMessageResponse:
    """
    Submit a conversational query to research agents in the session.
    Retrieves grounded context from session documents and returns an answer with citations.
    """
    user_id = str(current_user.id)
    return await chat_stream_service.send_message(
        session_id=session_id,
        user_id=user_id,
        request=request,
    )


@router.get(
    "/sessions/{session_id}/chat",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
    tags=["chat"],
)
async def get_chat_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    _session: SessionModel = Depends(require_session_owner),
) -> ChatHistoryResponse:
    """
    Retrieve full multi-turn conversation history for the current session.
    """
    user_id = str(current_user.id)
    return await chat_stream_service.list_chat_history(
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        skip=skip,
    )


@router.delete(
    "/sessions/{session_id}/chat",
    status_code=status.HTTP_200_OK,
    tags=["chat"],
)
async def delete_chat_history(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    _session: SessionModel = Depends(require_session_owner),
) -> dict:
    """
    Clear all chat messages in the session.
    """
    user_id = str(current_user.id)
    deleted = await chat_stream_service.delete_chat_history(
        session_id=session_id,
        user_id=user_id,
    )
    return {
        "status": "success",
        "session_id": session_id,
        "deleted_count": deleted,
    }


                                                                
                                       
                                                                

@router.post(
    "/sessions/{session_id}/broadcast",
    status_code=status.HTTP_200_OK,
    tags=["realtime"],
)
async def broadcast_session_event(
    session_id: str,
    payload: Dict[str, Any],
    event_type: str = Query("custom_event"),
    current_user: UserModel = Depends(get_current_user),
    _session: SessionModel = Depends(require_session_owner),
) -> dict:
    """
    Trigger a real-time event broadcast to active WebSocket clients in the session.
    """
    user_id = str(current_user.id)
    sent_count = await ws_manager.broadcast_to_session(
        session_id=session_id,
        message={
            "type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "payload": payload,
        },
    )
                                   
    event_bus.publish_session_event(
        session_id=session_id,
        event_type=event_type,
        payload=payload,
        user_id=user_id,
    )
    return {
        "status": "broadcast_sent",
        "session_id": session_id,
        "event_type": event_type,
        "active_recipients": sent_count,
    }


@router.get(
    "/sessions/{session_id}/ws/status",
    status_code=status.HTTP_200_OK,
    tags=["realtime"],
)
async def get_websocket_session_status(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    _session: SessionModel = Depends(require_session_owner),
) -> dict:
    """
    Return active WebSocket connection count and health for the session.
    """
    count = ws_manager.get_session_connection_count(session_id)
    return {
        "session_id": session_id,
        "active_sockets": count,
        "streaming_available": True,
    }
