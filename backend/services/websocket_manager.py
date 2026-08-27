"""
FinSentry AI — WebSocket Connection Manager (Phase 2I).

Manages active WebSocket connections per session and user, handles JWT
handshake authentication, and coordinates event broadcasts.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from core.config import get_settings
from database.connection import mongodb
from database.redis_client import redis_manager

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """
    Manages active WebSocket client connections segmented by session and user.
    """

    def __init__(self) -> None:
                                                            
        self._active_connections: Dict[str, Dict[str, Set[WebSocket]]] = {}
        self._lock = asyncio.Lock()
        self._pubsub_task: Optional[asyncio.Task] = None
        self._running = False

    async def authenticate_token(self, token: str) -> Optional[dict]:
        """
        Verify JWT access token from WebSocket handshake.

        Returns decoded payload dict containing 'sub' (user_id) if valid,
        or None if token is missing, expired, or invalid.
        """
        if not token:
            return None
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
                                          
            if payload.get("type") != "access":
                return None
            user_id = payload.get("sub")
            if not user_id:
                return None
            return payload
        except JWTError as exc:
            logger.debug("WebSocket JWT validation failed: %s", exc)
            return None

    async def verify_session_ownership(self, session_id: str, user_id: str) -> bool:
        """
        Verify that user owns the research session before accepting connection.
        """
        from bson import ObjectId
        from database.connection import get_sync_db
        try:
            db = mongodb.get_db()
            session = await db.research_sessions.find_one({
                "_id": ObjectId(session_id),
                "user_id": user_id,
            })
            return session is not None
        except Exception:
            try:
                sync_db = get_sync_db()
                doc = sync_db.research_sessions.find_one({
                    "_id": ObjectId(session_id),
                    "user_id": user_id,
                })
                return doc is not None
            except Exception as exc:
                logger.warning("verify_session_ownership failed: %s", exc)
                return False

    async def connect(self, websocket: WebSocket, session_id: str, user_id: str) -> None:
        """Accept connection and register under session and user map."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._active_connections:
                self._active_connections[session_id] = {}
            if user_id not in self._active_connections[session_id]:
                self._active_connections[session_id][user_id] = set()
            self._active_connections[session_id][user_id].add(websocket)
        logger.info(
            "WebSocket client connected — session: %s, user: %s (active: %d)",
            session_id,
            user_id,
            self.get_session_connection_count(session_id),
        )

    async def disconnect(self, websocket: WebSocket, session_id: str, user_id: str) -> None:
        """Remove connection from active maps."""
        async with self._lock:
            if session_id in self._active_connections:
                if user_id in self._active_connections[session_id]:
                    self._active_connections[session_id][user_id].discard(websocket)
                    if not self._active_connections[session_id][user_id]:
                        del self._active_connections[session_id][user_id]
                if not self._active_connections[session_id]:
                    del self._active_connections[session_id]
        logger.info(
            "WebSocket client disconnected — session: %s, user: %s",
            session_id,
            user_id,
        )

    def get_session_connection_count(self, session_id: str) -> int:
        """Return total active sockets in a given session."""
        if session_id not in self._active_connections:
            return 0
        return sum(len(sockets) for sockets in self._active_connections[session_id].values())

    async def broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any],
        exclude_socket: Optional[WebSocket] = None,
    ) -> int:
        """
        Send a JSON message to all active WebSocket clients in a session.
        """
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        if "session_id" not in message:
            message["session_id"] = session_id

        sent_count = 0
        dead_sockets: List[tuple] = []

        async with self._lock:
            session_users = self._active_connections.get(session_id, {})
            for user_id, sockets in session_users.items():
                for socket in list(sockets):
                    if socket == exclude_socket:
                        continue
                    try:
                        await socket.send_json(message)
                        sent_count += 1
                    except Exception as exc:
                        logger.debug("Failed sending to socket, queueing cleanup: %s", exc)
                        dead_sockets.append((session_id, user_id, socket))

            for s_id, u_id, dead_ws in dead_sockets:
                if s_id in self._active_connections and u_id in self._active_connections[s_id]:
                    self._active_connections[s_id][u_id].discard(dead_ws)

        return sent_count

    async def send_to_user(
        self,
        session_id: str,
        user_id: str,
        message: Dict[str, Any],
    ) -> int:
        """Send message specifically to a user's active sockets in a session."""
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        if "session_id" not in message:
            message["session_id"] = session_id

        sent_count = 0
        async with self._lock:
            session_users = self._active_connections.get(session_id, {})
            sockets = session_users.get(user_id, set())
            for socket in list(sockets):
                try:
                    await socket.send_json(message)
                    sent_count += 1
                except Exception:
                    pass
        return sent_count


ws_manager = WebSocketConnectionManager()
