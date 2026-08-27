"""
Research session document model for MongoDB.

Defines the canonical shape of a document in the ``research_sessions``
collection, along with helpers for serialisation and factory construction.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class SessionModel(BaseModel):
    """
    Domain model for a research session stored in MongoDB.

    Each session belongs to exactly one user (referenced by ``user_id``).
    """

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str = Field(..., min_length=1)
    session_name: str = Field(..., min_length=1, max_length=256)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }

    def to_mongo(self) -> dict:
        """
        Convert the model to a MongoDB-ready dict.

        Strips ``id`` / ``_id`` so that Mongo assigns its own ObjectId.
        """
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, doc: dict) -> "SessionModel":
        """
        Construct a SessionModel from a raw MongoDB document.

        Converts the ObjectId ``_id`` to a plain string.
        """
        if doc is None:
            raise ValueError("Cannot construct SessionModel from None")
        doc["_id"] = str(doc["_id"])
        return cls(**doc)
