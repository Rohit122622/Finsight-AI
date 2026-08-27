"""
Pydantic schemas for authentication request/response payloads.

These schemas are used exclusively at the API boundary — they are
distinct from the internal ``UserModel`` stored in MongoDB.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    full_name: str = Field(..., min_length=1, max_length=128, examples=["Rohit Kumar"])
    email: EmailStr = Field(..., examples=["rohit@example.com"])
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Payload for email + password authentication."""

    email: EmailStr = Field(..., examples=["rohit@example.com"])
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public-facing user representation (never includes password_hash)."""

    id: str
    full_name: str
    email: EmailStr
    provider: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }
