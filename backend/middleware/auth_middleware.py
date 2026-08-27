"""
JWT authentication middleware.

Provides FastAPI dependencies for extracting and validating the
current user from an ``Authorization: Bearer <token>`` header.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database
from models.user import UserModel
from services.auth_service import get_user_by_id, verify_access_token

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> UserModel:
    """
    FastAPI dependency that resolves the authenticated user.

    Steps:
        1. Extract the Bearer token from the Authorization header.
        2. Decode and verify the JWT (must be an ``access`` token).
        3. Load the user from MongoDB by the ``sub`` claim.
        4. Return the ``UserModel`` or raise 401.

    Usage::

        @router.get("/me")
        async def me(user: UserModel = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_access_token(token)

    if payload is None:
        logger.warning("Invalid or expired access token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload["sub"]
    user = await get_user_by_id(db, user_id)

    if user is None:
        logger.warning("Token references non-existent user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
