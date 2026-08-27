"""
Authentication service layer.

Encapsulates all auth business logic: password hashing, JWT management,
user CRUD against MongoDB, and Google OAuth helpers.  No FastAPI-specific
code lives here — the module depends only on Motor, bcrypt, python-jose
and the project's own config/models/schemas.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import get_settings
from models.user import AuthProvider, UserModel

logger = logging.getLogger(__name__)


                                                                       


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*."""
    return bcrypt.checkpw(
        plain.encode("utf-8"), hashed.encode("utf-8")
    )


                                                                       


def create_access_token(user_id: str, email: str) -> str:
    """
    Create a short-lived access token.

    Claims:
        sub  – user ID (string form of MongoDB ObjectId)
        email – user email (convenience claim)
        type – ``access``
        exp  – expiry timestamp
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(user_id: str, email: str) -> str:
    """
    Create a long-lived refresh token.

    Each refresh token includes a unique JTI (JWT ID) claim that is
    stored in MongoDB for server-side revocation tracking.

    Claims mirror the access token but with ``type=refresh``, a unique
    ``jti``, and a longer expiry window.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "email": email,
        "type": "refresh",
        "jti": jti,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.

    Returns the full claims dict on success.
    Raises ``JWTError`` on invalid/expired tokens.
    """
    settings = get_settings()
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def verify_access_token(token: str) -> Optional[dict]:
    """
    Verify an access token and return its claims.

    Returns ``None`` for any invalid, expired, or non-access token.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            logger.warning("Token type mismatch: expected 'access', got '%s'", payload.get("type"))
            return None
        if payload.get("sub") is None:
            logger.warning("Access token missing 'sub' claim")
            return None
        return payload
    except JWTError as exc:
        logger.warning("Access token verification failed: %s", exc)
        return None


def verify_refresh_token(token: str) -> Optional[dict]:
    """
    Verify a refresh token and return its claims.

    Returns ``None`` for any invalid, expired, or non-refresh token.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            logger.warning("Token type mismatch: expected 'refresh', got '%s'", payload.get("type"))
            return None
        if payload.get("sub") is None:
            logger.warning("Refresh token missing 'sub' claim")
            return None
        return payload
    except JWTError as exc:
        logger.warning("Refresh token verification failed: %s", exc)
        return None


                                                                       
 
                                                                          
                                                                       
                                                         
 
                                                                   
                                                                    
                       
                                                                       


async def store_refresh_token(
    db: AsyncIOMotorDatabase,
    user_id: str,
    jti: str,
) -> None:
    """
    Record a newly issued refresh token in MongoDB.

    The document tracks the JTI, owning user, creation timestamp, and
    revocation status.
    """
    await db.refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user_id,
        "revoked": False,
        "created_at": datetime.now(timezone.utc),
    })
    logger.info("Stored refresh token %s for user %s", jti, user_id)


async def is_refresh_token_revoked(
    db: AsyncIOMotorDatabase,
    jti: str,
) -> bool:
    """
    Check whether a refresh token has been revoked.

    Returns ``True`` if revoked **or** if the JTI is not found in the
    database (tokens issued before revocation tracking was added are
    treated as revoked for security).
    """
    doc = await db.refresh_tokens.find_one({"jti": jti})
    if doc is None:
                                                                        
        logger.warning("Refresh token JTI %s not found in database", jti)
        return True
    return doc.get("revoked", True)


async def revoke_refresh_token(
    db: AsyncIOMotorDatabase,
    jti: str,
) -> None:
    """Revoke a single refresh token by its JTI."""
    await db.refresh_tokens.update_one(
        {"jti": jti},
        {"$set": {"revoked": True}},
    )
    logger.info("Revoked refresh token %s", jti)


async def revoke_all_user_refresh_tokens(
    db: AsyncIOMotorDatabase,
    user_id: str,
) -> int:
    """
    Revoke ALL active refresh tokens for a user.

    Called on logout to invalidate every device/session.
    Returns the number of tokens revoked.
    """
    result = await db.refresh_tokens.update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True}},
    )
    count = result.modified_count
    logger.info("Revoked %d refresh token(s) for user %s", count, user_id)
    return count


                                                                       


async def get_user_by_email(
    db: AsyncIOMotorDatabase, email: str
) -> Optional[UserModel]:
    """Look up a user by email address (case-insensitive normalized). Returns ``None`` if not found."""
    normalized_email = email.lower().strip()
    doc = await db.users.find_one({"email": normalized_email})
    if doc is None:
        return None
    return UserModel.from_mongo(doc)


async def get_user_by_id(
    db: AsyncIOMotorDatabase, user_id: str
) -> Optional[UserModel]:
    """Look up a user by their string ID. Returns ``None`` if not found."""
    from bson import ObjectId

    if not ObjectId.is_valid(user_id):
        return None
    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if doc is None:
        return None
    return UserModel.from_mongo(doc)


async def create_user(
    db: AsyncIOMotorDatabase,
    full_name: str,
    email: str,
    password: str,
    provider: AuthProvider = AuthProvider.LOCAL,
) -> UserModel:
    """
    Insert a new user document and return the hydrated model.

    The caller is responsible for checking duplicate emails before
    invoking this function.
    """
    normalized_email = email.lower().strip()
    user = UserModel(
        full_name=full_name.strip(),
        email=normalized_email,
        password_hash=hash_password(password) if password else "",
        provider=provider,
    )
    result = await db.users.insert_one(user.to_mongo())
    user.id = str(result.inserted_id)
    logger.info("Created user %s (%s)", user.id, normalized_email)
    return user


                                                                       


async def get_or_create_google_user(
    db: AsyncIOMotorDatabase,
    google_id: str,
    email: str,
    full_name: str,
) -> UserModel:
    """
    Find an existing user by email or create a new Google-linked account.

    Always reuses the existing user account with the same email address so
    sessions, documents, and research conversations remain persistent across logins.
    """
    normalized_email = email.lower().strip()
    existing = await get_user_by_email(db, normalized_email)
    if existing is not None:
        return existing

    user = UserModel(
        full_name=full_name.strip() or normalized_email.split("@")[0],
        email=normalized_email,
        password_hash="",
        provider=AuthProvider.GOOGLE,
    )
    result = await db.users.insert_one(user.to_mongo())
    user.id = str(result.inserted_id)
    logger.info("Created Google user %s (%s)", user.id, normalized_email)
    return user


def build_google_auth_url(redirect_uri: str) -> str:
    """
    Build the Google OAuth2 authorization URL.

    This is a convenience helper; the actual redirect is handled
    by the caller (an API endpoint added in a later phase).
    """
    settings = get_settings()
    params = (
        f"client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
