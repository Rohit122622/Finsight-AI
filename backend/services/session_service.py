"""
Research session service layer.

Encapsulates all session business logic: CRUD operations, ownership
validation, and pagination against MongoDB.  No FastAPI-specific code
lives here — the module depends only on Motor, bson, and the project's
own models.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.session import SessionModel

logger = logging.getLogger(__name__)


                                                                       


async def verify_session_ownership(
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
) -> Optional[SessionModel]:
    """
    Verify that a session exists AND belongs to the given user.

    Returns the ``SessionModel`` if the session belongs to the user,
    or ``None`` if the session does not exist or belongs to someone else.

    Every lookup filters by **both** ``_id`` and ``user_id`` to prevent
    any cross-tenant data leakage at the database level.
    """
    if not ObjectId.is_valid(session_id):
        logger.warning("Invalid ObjectId format: %s", session_id)
        return None

    doc = await db.research_sessions.find_one(
        {"_id": ObjectId(session_id), "user_id": user_id}
    )
    if doc is None:
        return None

    return SessionModel.from_mongo(doc)


                                                                       


async def create_session(
    db: AsyncIOMotorDatabase,
    user_id: str,
    session_name: str,
) -> SessionModel:
    """
    Insert a new research session owned by *user_id*.

    Returns the hydrated ``SessionModel`` with the generated ``_id``.
    """
    session = SessionModel(
        user_id=user_id,
        session_name=session_name,
    )
    result = await db.research_sessions.insert_one(session.to_mongo())
    session.id = str(result.inserted_id)
    logger.info(
        "Created session %s for user %s (name=%r)",
        session.id,
        user_id,
        session_name,
    )
    return session


                                                                       


async def list_sessions(
    db: AsyncIOMotorDatabase,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[SessionModel], int]:
    """
    Return a paginated list of sessions belonging to *user_id*.

    Results are sorted by ``created_at`` descending (newest first).
    Returns a tuple of ``(sessions, total_count)``.
    """
    query_filter = {"user_id": user_id}

    total = await db.research_sessions.count_documents(query_filter)

    skip = (page - 1) * page_size
    cursor = (
        db.research_sessions
        .find(query_filter)
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )

    sessions: List[SessionModel] = []
    async for doc in cursor:
        sessions.append(SessionModel.from_mongo(doc))

    logger.info(
        "Listed %d/%d sessions for user %s (page=%d)",
        len(sessions),
        total,
        user_id,
        page,
    )
    return sessions, total


                                                                       


async def get_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
) -> Optional[SessionModel]:
    """
    Retrieve a single session by ID, scoped to *user_id*.

    Returns ``None`` if the session does not exist or belongs to
    another user.  Uses ``verify_session_ownership`` internally to
    ensure the compound filter is always applied.
    """
    session = await verify_session_ownership(db, session_id, user_id)
    if session is not None:
        logger.info("Retrieved session %s for user %s", session_id, user_id)
    else:
        logger.warning(
            "Session %s not found or not owned by user %s",
            session_id,
            user_id,
        )
    return session


                                                                       


async def update_session_name(
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
    new_name: str,
) -> Optional[SessionModel]:
    """
    Update the name of a session, scoped to *user_id*.

    The MongoDB ``update_one`` filter includes both ``_id`` and
    ``user_id`` so that a user can never rename another user's session.

    Returns the updated ``SessionModel`` or ``None`` if the session
    does not exist / is not owned by the caller.
    """
    if not ObjectId.is_valid(session_id):
        logger.warning("Invalid ObjectId format for update: %s", session_id)
        return None

    now = datetime.now(timezone.utc)
    result = await db.research_sessions.update_one(
        {"_id": ObjectId(session_id), "user_id": user_id},
        {"$set": {"session_name": new_name, "updated_at": now}},
    )

    if result.matched_count == 0:
        logger.warning(
            "Update failed — session %s not found or not owned by user %s",
            session_id,
            user_id,
        )
        return None

                                             
    updated = await verify_session_ownership(db, session_id, user_id)
    logger.info(
        "Updated session %s name to %r for user %s",
        session_id,
        new_name,
        user_id,
    )
    return updated


                                                                       


async def delete_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
) -> bool:
    """
    Delete a session, scoped to *user_id*.

    The delete filter includes both ``_id`` and ``user_id`` so that
    a user can never delete another user's session.

    Returns ``True`` if a document was deleted, ``False`` otherwise.
    """
    if not ObjectId.is_valid(session_id):
        logger.warning("Invalid ObjectId format for delete: %s", session_id)
        return False

    result = await db.research_sessions.delete_one(
        {"_id": ObjectId(session_id), "user_id": user_id}
    )

    if result.deleted_count == 0:
        logger.warning(
            "Delete failed — session %s not found or not owned by user %s",
            session_id,
            user_id,
        )
        return False

    logger.info("Deleted session %s for user %s", session_id, user_id)
    return True
