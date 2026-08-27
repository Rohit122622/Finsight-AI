"""
FinSentry AI — Redis Pub/Sub Event Bus (Phase 2I).

Enables distributed real-time event broadcasting across Celery workers and
FastAPI WebSocket listeners.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

from database.redis_client import redis_manager

logger = logging.getLogger(__name__)

                                                              
CHANNEL_PREFIX = "finsentry:events:session"


class EventBus:
    """
    Redis Pub/Sub event bus for multi-tenant real-time updates.
    """

    def __init__(self) -> None:
        self._pubsub: Optional[Any] = None

    def publish_session_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> int:
        """
        Publish a real-time event to a session-scoped Redis Pub/Sub channel.

        Returns the number of subscribers that received the message.
        """
        channel = f"{CHANNEL_PREFIX}:{session_id}"
        message_dict = {
            "type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "payload": payload,
        }
        try:
            client = redis_manager.get_client()
            message_json = json.dumps(message_dict)
            subscribers = client.publish(channel, message_json)
            logger.debug(
                "Published event '%s' to %s (subscribers: %d)",
                event_type,
                channel,
                subscribers,
            )
            return subscribers
        except Exception as exc:
            logger.warning("Failed to publish event to Redis Pub/Sub: %s", exc)
            return 0

    def publish_job_progress(
        self,
        session_id: str,
        job_id: str,
        progress_percent: int,
        current_step: str,
        status: str,
        events: Optional[list] = None,
    ) -> int:
        """Helper to publish job progress updates."""
        return self.publish_session_event(
            session_id=session_id,
            event_type="job_progress",
            payload={
                "job_id": job_id,
                "progress_percent": progress_percent,
                "current_step": current_step,
                "status": status,
                "events": events or [],
            },
        )

    def publish_agent_milestone(
        self,
        session_id: str,
        agent_name: str,
        milestone: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Helper to publish agent execution milestones."""
        return self.publish_session_event(
            session_id=session_id,
            event_type="agent_milestone",
            payload={
                "agent_name": agent_name,
                "milestone": milestone,
                "details": details or {},
            },
        )


event_bus = EventBus()
