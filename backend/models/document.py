"""
Document persistence models for FinSentry AI (Phase 2B).
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.constants import DocumentStatus


class DocumentChunk(BaseModel):
    """A segment of extracted document text for downstream analysis and RAG."""

    chunk_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the chunk",
    )
    document_id: Optional[str] = Field(None, description="Parent document identifier")
    user_id: Optional[str] = Field(None, description="Owning user identifier")
    chunk_index: int = Field(default=0, ge=0, description="Sequential index within document")
    text: str = Field(..., description="Raw text slice")
    source_text: Optional[str] = Field(None, description="Unprocessed source text segment")
    section: Optional[str] = Field(None, description="Identified financial section")
    token_estimate: int = Field(default=0, ge=0, description="Estimated token count")
    character_count: int = Field(default=0, ge=0, description="Character count")
    page_number: Optional[int] = Field(None, description="Source page number if applicable")
    embedding: Optional[List[float]] = Field(default=None, description="Vector embedding representation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom chunk metadata")


class DocumentMetadata(BaseModel):
    """Statistical and structural metadata for an ingested document."""

    page_count: Optional[int] = Field(None, description="Total pages if paginated (e.g. PDF)")
    word_count: int = Field(default=0, ge=0, description="Total extracted word count")
    character_count: int = Field(default=0, ge=0, description="Total extracted character count")
    token_estimate: int = Field(default=0, ge=0, description="Estimated total tokens")
    sha256: str = Field(default="", description="SHA-256 hash of original file content")
    chunk_count: int = Field(default=0, ge=0, description="Total chunks generated")
    extracted_summary: Optional[str] = Field(None, description="High-level text preview/summary")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary safe file metadata")


class DocumentModel(BaseModel):
    """
    MongoDB persistence document for an ingested research document.
    """

    id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId string")
    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique UUID for the document",
    )
    session_id: str = Field(..., description="ID of the research session this document belongs to")
    user_id: str = Field(..., description="ID of the owning user")
    filename: str = Field(..., description="Original name of the uploaded file")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    mime_type: str = Field(..., description="MIME content type")
    storage_path: str = Field(..., description="Relative or absolute path in the storage service")
    status: str = Field(
        default=DocumentStatus.UPLOADED.value,
        description="Current processing lifecycle status",
    )
    error_message: Optional[str] = Field(None, description="Error message if processing failed")
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    chunks: List[DocumentChunk] = Field(default_factory=list, description="Extracted text chunks")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dict."""
        data = self.model_dump(by_alias=False)
        if "id" in data and data["id"] is None:
            data.pop("id", None)
        return data

    @classmethod
    def from_mongo(cls, doc: Dict[str, Any]) -> "DocumentModel":
        """Reconstruct model from MongoDB document."""
        if not doc:
            raise ValueError("Empty document cannot be converted to DocumentModel")
        doc_copy = dict(doc)
        if "_id" in doc_copy:
            doc_copy["_id"] = str(doc_copy["_id"])

                                                                                                       
        chunks_list = doc_copy.get("chunks") or []
        meta_dict = doc_copy.get("metadata")
        if isinstance(meta_dict, dict):
            if (not meta_dict.get("chunk_count") or meta_dict.get("chunk_count") <= 0) and chunks_list:
                meta_dict["chunk_count"] = len(chunks_list)
        elif not meta_dict and chunks_list:
            doc_copy["metadata"] = {"chunk_count": len(chunks_list)}

        return cls(**doc_copy)
