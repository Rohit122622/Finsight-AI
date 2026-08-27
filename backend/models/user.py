"""
User document model for MongoDB.

Defines the canonical shape of a document in the ``users`` collection,
along with helpers for serialisation and factory construction.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class AuthProvider(str, Enum):
    """Supported authentication providers."""

    LOCAL = "local"
    GOOGLE = "google"


class UserModel(BaseModel):
    """
    Domain model for a user stored in MongoDB.

    The ``id`` field maps to MongoDB's ``_id`` as a string to
    simplify JSON serialisation across the API boundary.
    """

    id: Optional[str] = Field(default=None, alias="_id")
    full_name: str = Field(..., min_length=1, max_length=128)
    email: EmailStr
    password_hash: str = Field(default="")
    provider: AuthProvider = Field(default=AuthProvider.LOCAL)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }

    def to_mongo(self) -> dict:
        """
        Convert the model to a MongoDB-ready dict.

        Strips ``id`` (None on insert) and ``_id`` so that Mongo
        can assign its own ObjectId.
        """
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, doc: dict) -> "UserModel":
        """
        Construct a UserModel from a raw MongoDB document.

        Converts the ObjectId ``_id`` to a plain string.
        """
        if doc is None:
            raise ValueError("Cannot construct UserModel from None")
        doc["_id"] = str(doc["_id"])
        return cls(**doc)
