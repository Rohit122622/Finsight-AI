"""
Reusable ownership verification dependency.

Provides a FastAPI dependency that ensures the authenticated user
owns the resource identified by ``session_id`` in the URL path.

This is a *dependency*, not ASGI middleware, so it participates in
FastAPI's dependency-injection graph and has access to path params,
the database handle, and the current user.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database
from middleware.auth_middleware import get_current_user
from models.session import SessionModel
from models.user import UserModel
from services.session_service import verify_session_ownership

logger = logging.getLogger(__name__)


async def require_session_owner(
    session_id: Annotated[str, Path(description="Research session ID")],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> SessionModel:
    """
    FastAPI dependency that verifies the current user owns the session.

    Resolves to the ``SessionModel`` if ownership is confirmed.
    Raises:
        HTTP 404 – session does not exist (for the requesting user)
        HTTP 403 – the session exists but is not owned by the caller

    Design note:
        Because ``verify_session_ownership`` always queries with both
        ``_id`` and ``user_id``, a non-owner receives a 404 rather
        than a 403 (no information leakage about other users' data).
        A 403 is raised only when the ObjectId is invalid, which is a
        client error rather than an ownership violation.

    Usage::

        @router.get("/sessions/{session_id}")
        async def get_session(
            session: SessionModel = Depends(require_session_owner),
        ):
            ...
    """
    session = await verify_session_ownership(db, session_id, current_user.id)

    if session is None:
        logger.warning(
            "Ownership check failed — session %s not found for user %s",
            session_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return session
