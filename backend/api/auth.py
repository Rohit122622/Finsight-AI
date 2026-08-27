"""
Authentication API routes.

Endpoints:
    POST /register  – create a new local account
    POST /login     – authenticate with email + password
    POST /refresh   – exchange a refresh token for a new token pair
    GET  /me        – return the authenticated user's profile
    POST /logout    – revoke all refresh tokens for the user
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database
from middleware.auth_middleware import get_current_user
from middleware.rate_limiter import login_rate_limiter
from models.user import UserModel
from schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    create_user,
    decode_token,
    get_user_by_email,
    is_refresh_token_revoked,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token,
    store_refresh_token,
    verify_password,
    verify_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()





def _extract_jti(token: str) -> str:
    """Extract the JTI claim from a refresh token (already validated)."""
    payload = decode_token(token)
    return payload.get("jti", "")





@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a local account and return a JWT token pair.",
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> TokenResponse:
    existing = await get_user_by_email(db, body.email)
    if existing is not None:
        logger.warning("Registration attempt with existing email: %s", body.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = await create_user(
        db,
        full_name=body.full_name,
        email=body.email,
        password=body.password,
    )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)


    jti = _extract_jti(refresh_token)
    await store_refresh_token(db, user.id, jti)

    logger.info("User registered: %s", user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )





@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description="Authenticate with email and password. Returns a JWT token pair.",
)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> TokenResponse:

    client_ip = request.client.host if request.client else "unknown"
    if not login_rate_limiter.check_rate_limit(client_ip):
        logger.warning("Login rate limit exceeded for IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    user = await get_user_by_email(db, body.email)

    if user is None or not verify_password(body.password, user.password_hash):

        login_rate_limiter.record_attempt(client_ip)
        logger.warning("Failed login attempt for: %s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


    login_rate_limiter.reset(client_ip)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)


    jti = _extract_jti(refresh_token)
    await store_refresh_token(db, user.id, jti)

    logger.info("User logged in: %s", user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )





@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh tokens",
    description="Exchange a valid refresh token for a new access/refresh token pair.",
)
async def refresh(
    body: dict,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> TokenResponse:
    token = body.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token is required",
        )

    payload = verify_refresh_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


    old_jti = payload.get("jti", "")
    if old_jti:
        revoked = await is_refresh_token_revoked(db, old_jti)
        if revoked:
            logger.warning("Attempt to use revoked refresh token: %s", old_jti)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked",
            )

    user_id: str = payload["sub"]
    email: str = payload["email"]


    if old_jti:
        await revoke_refresh_token(db, old_jti)

    access_token = create_access_token(user_id, email)
    new_refresh_token = create_refresh_token(user_id, email)


    new_jti = _extract_jti(new_refresh_token)
    await store_refresh_token(db, user_id, new_jti)

    logger.info("Tokens refreshed for user %s", user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )





@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current user profile",
    description="Return the authenticated user's public profile.",
)
async def me(
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        provider=current_user.provider,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )





@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out",
    description=(
        "Revoke all active refresh tokens for the authenticated user. "
        "The client must also discard its stored tokens."
    ),
)
async def logout(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> dict:

    revoked_count = await revoke_all_user_refresh_tokens(db, current_user.id)
    logger.info(
        "User logged out: %s (revoked %d tokens)", current_user.email, revoked_count
    )
    return {"message": "Successfully logged out"}
