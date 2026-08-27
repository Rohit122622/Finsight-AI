"""
Research session API routes.

Endpoints:
    POST   /sessions              – create a new research session
    GET    /sessions              – list the current user's sessions
    GET    /sessions/{session_id} – retrieve a single session
    PATCH  /sessions/{session_id} – rename a session
    DELETE /sessions/{session_id} – delete a session

Every endpoint requires a valid JWT (``Authorization: Bearer <token>``).
All queries are scoped to the authenticated user — no cross-tenant
access is possible.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.session import (
    CreateSessionRequest,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from services.session_service import (
    create_session,
    delete_session,
    list_sessions,
    update_session_name,
)

logger = logging.getLogger(__name__)

router = APIRouter()


                                                                       


def _session_to_response(session: SessionModel) -> SessionResponse:
    """Map a domain model to the API response schema."""
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        session_name=session.session_name,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


                                                                      


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a research session",
    description=(
        "Create a new research session owned by the authenticated user. "
        "Returns the created session with its generated ID."
    ),
)
async def create_session_endpoint(
    body: CreateSessionRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> SessionResponse:
    session = await create_session(db, current_user.id, body.session_name)
    logger.info("User %s created session %s", current_user.id, session.id)
    return _session_to_response(session)


                                                                      


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List research sessions",
    description=(
        "Return a paginated list of the authenticated user's research sessions, "
        "sorted by creation date (newest first)."
    ),
)
async def list_sessions_endpoint(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page")
    ] = 20,
) -> SessionListResponse:
    sessions, total = await list_sessions(db, current_user.id, page, page_size)
    return SessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
        total=total,
        page=page,
        page_size=page_size,
    )


                                                                      


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get a research session",
    description=(
        "Retrieve a single research session by ID. "
        "Returns 404 if the session does not exist or belongs to another user."
    ),
)
async def get_session_endpoint(
    session: Annotated[SessionModel, Depends(require_session_owner)],
) -> SessionResponse:
    return _session_to_response(session)


                                                                      


@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Rename a research session",
    description=(
        "Update the name of an existing research session. "
        "Returns 404 if the session does not exist or belongs to another user."
    ),
)
async def update_session_endpoint(
    body: UpdateSessionRequest,
    session: Annotated[SessionModel, Depends(require_session_owner)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> SessionResponse:
    updated = await update_session_name(
        db, session.id, current_user.id, body.session_name
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    logger.info(
        "User %s renamed session %s to %r",
        current_user.id,
        session.id,
        body.session_name,
    )
    return _session_to_response(updated)


                                                                      


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a research session",
    description=(
        "Permanently delete a research session. "
        "Returns 404 if the session does not exist or belongs to another user."
    ),
)
async def delete_session_endpoint(
    session: Annotated[SessionModel, Depends(require_session_owner)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> dict:
    deleted = await delete_session(db, session.id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    logger.info("User %s deleted session %s", current_user.id, session.id)
    return {"message": "Session deleted successfully", "session_id": session.id}
