"""
Google OAuth2 authentication service layer.

Handles Google OAuth2 state management, authorization URL construction,
token exchange, and user profile retrieval using Authlib. Reuses existing
authentication helpers for user creation and JWT token issuance.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from authlib.integrations.httpx_client import AsyncOAuth2Client
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import get_settings
from schemas.auth import TokenResponse
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_or_create_google_user,
    store_refresh_token,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


                                                                        


def generate_oauth_state() -> str:
    """
    Generate a cryptographically signed OAuth state token.

    Contains a random nonce, action type, and expiry window (10 minutes).
    Statelessly prevents CSRF and state tampering without server-side storage.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "type": "google_oauth_state",
        "nonce": secrets.token_hex(16),
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_oauth_state(state: str) -> bool:
    """
    Verify the validity and integrity of a returned OAuth state token.

    Returns ``True`` if valid and unexpired; ``False`` otherwise.
    """
    if not state:
        logger.warning("OAuth state verification failed: empty state")
        return False

    settings = get_settings()
    try:
        payload = jwt.decode(
            state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "google_oauth_state":
            logger.warning(
                "OAuth state verification failed: invalid state type '%s'",
                payload.get("type"),
            )
            return False
        return True
    except JWTError as exc:
        logger.warning("OAuth state verification failed: %s", exc)
        return False


                                                                       


from urllib.parse import parse_qs, urlparse


def get_google_auth_url(redirect_uri: Optional[str] = None) -> Tuple[str, str]:
    """
    Construct the Google OAuth authorization redirect URL and state token.

    Uses Authlib's ``AsyncOAuth2Client`` to build the URL cleanly.
    Returns a tuple of ``(authorization_url, state)``.
    """
    settings = get_settings()
    target_redirect_uri = (redirect_uri or settings.GOOGLE_REDIRECT_URI).strip().rstrip("/")
    state = generate_oauth_state()

    client = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID.strip(),
        client_secret=settings.GOOGLE_CLIENT_SECRET.strip(),
        scope="openid email profile",
    )

    url, _ = client.create_authorization_url(
        GOOGLE_AUTHORIZATION_ENDPOINT,
        redirect_uri=target_redirect_uri,
        state=state,
        access_type="offline",
        prompt="select_account",
    )

                               
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    decoded_redirect_uri = query_params.get("redirect_uri", [""])[0]

    logger.info("=== GOOGLE OAUTH DEBUG ===")
    logger.info("Loaded Client ID: %s", settings.GOOGLE_CLIENT_ID)
    logger.info("Loaded Redirect URI: %s", settings.GOOGLE_REDIRECT_URI)
    logger.info("Target Redirect URI: %s", target_redirect_uri)
    logger.info("Decoded redirect_uri parameter: %s", decoded_redirect_uri)
    logger.info("State parameter: %s", state)
    logger.info("Generated Auth URL: %s", url)
    logger.info("===========================")

    return url, state


async def fetch_google_user_profile(
    code: str, redirect_uri: Optional[str] = None
) -> dict:
    """
    Exchange authorization code for tokens and retrieve verified Google user profile.

    Raises ``ValueError`` if token exchange fails or if the Google email is
    missing / unverified.
    """
    settings = get_settings()
    target_redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI

    async with AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    ) as client:
        try:
            token = await client.fetch_token(
                GOOGLE_TOKEN_ENDPOINT,
                code=code,
                redirect_uri=target_redirect_uri,
                grant_type="authorization_code",
            )
        except Exception as exc:
            logger.error("Failed to exchange code for Google token: %s", exc)
            raise ValueError("Failed to exchange authorization code with Google") from exc

        access_token = token.get("access_token")
        if not access_token:
            logger.error("Google token response did not contain access_token")
            raise ValueError("Google OAuth token response missing access_token")

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = await client.get(GOOGLE_USERINFO_ENDPOINT, headers=headers)
            profile = resp.json()
        except Exception as exc:
            logger.error("Failed to fetch Google user profile: %s", exc)
            raise ValueError("Failed to fetch user profile from Google") from exc

    email = profile.get("email")
    email_verified = profile.get("email_verified", False)

    if not email:
        logger.error("Google user profile missing email field")
        raise ValueError("Google account email is missing")

    if not email_verified:
        logger.error("Google user email %s is not verified", email)
        raise ValueError("Google account email is not verified")

    return profile


async def process_google_oauth_callback(
    db: AsyncIOMotorDatabase,
    code: str,
    state: str,
    redirect_uri: Optional[str] = None,
) -> TokenResponse:
    """
    Process the Google OAuth callback end-to-end.

    Steps:
        1. Validate state parameter.
        2. Exchange code for Google user profile.
        3. Find existing user or create a new Google-authenticated user.
        4. Issue JWT access and refresh token pair.
        5. Store refresh token JTI for server-side revocation tracking.

    Raises ``ValueError`` on state or token validation errors.
    """
    if not verify_oauth_state(state):
        raise ValueError("Invalid or expired OAuth state parameter")

    profile = await fetch_google_user_profile(code, redirect_uri=redirect_uri)

    email = profile["email"]
    full_name = profile.get("name") or email.split("@")[0]
    google_id = profile.get("sub", "")

    user = await get_or_create_google_user(
        db,
        google_id=google_id,
        email=email,
        full_name=full_name,
    )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)

                                                                 
    refresh_payload = decode_token(refresh_token)
    jti = refresh_payload.get("jti", "")
    if jti:
        await store_refresh_token(db, user.id, jti)

    logger.info("Google OAuth login successful for user %s (%s)", user.id, user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
