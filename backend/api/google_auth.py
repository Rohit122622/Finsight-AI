"""
Google OAuth2 API routes.

Endpoints:
    GET /api/v1/auth/google/login    – redirect user to Google OAuth authorization server
    GET /api/v1/auth/google/callback – handle Google OAuth redirect, exchange code, authenticate/create user, return JWT tokens
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.connection import get_database
from schemas.auth import TokenResponse
from services.google_auth_service import (
    get_google_auth_url,
    process_google_oauth_callback,
)

logger = logging.getLogger(__name__)

router = APIRouter()





@router.get(
    "/login",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Google OAuth Login",
    description=(
        "Redirects the client to Google's OAuth2 authorization page. "
        "Includes a signed CSRF state token in the authorization request."
    ),
)
async def google_login() -> RedirectResponse:
    auth_url, _ = get_google_auth_url()
    logger.info("Redirecting client to Google OAuth login")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)





@router.get(
    "/callback",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Google OAuth Callback",
    description=(
        "Handles the OAuth redirect from Google. Validates state token, "
        "exchanges authorization code for verified Google user profile, "
        "creates user if not present, and returns a JWT access and refresh token pair."
    ),
)
async def google_callback(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    code: Annotated[Optional[str], Query(description="Authorization code from Google")] = None,
    state: Annotated[Optional[str], Query(description="OAuth state token")] = None,
    error: Annotated[Optional[str], Query(description="OAuth error code if any")] = None,
) -> TokenResponse:
    if error:
        logger.warning("Google OAuth callback received error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth authorization failed: {error}",
        )

    if not code:
        logger.warning("Google OAuth callback missing 'code' parameter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code from Google",
        )

    if not state:
        logger.warning("Google OAuth callback missing 'state' parameter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter",
        )

    try:
        token_response = await process_google_oauth_callback(db, code, state)
        return token_response
    except ValueError as exc:
        logger.warning("Google OAuth processing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
