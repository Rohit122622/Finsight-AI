"""
Pydantic API schemas for document ingestion and inspection (Phase 2B).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.constants import DocumentStatus


class DocumentChunkResponse(BaseModel):
    """Schema for individual document text chunk."""

    chunk_id: str
    chunk_index: int
    text: str
    token_estimate: int
    character_count: int
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentMetadataResponse(BaseModel):
    """Schema for document statistical and structural metadata."""

    page_count: Optional[int] = None
    word_count: int = 0
    character_count: int = 0
    token_estimate: int = 0
    sha256: str = ""
    chunk_count: int = 0
    extracted_summary: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    """Summary representation of an ingested document."""

    document_id: str
    session_id: str
    user_id: str
    filename: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    error_message: Optional[str] = None
    metadata: DocumentMetadataResponse
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """Detailed document representation including full chunk list."""

    chunks: List[DocumentChunkResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    """Paginated list of documents belonging to a session."""

    documents: List[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentProcessRequest(BaseModel):
    """Optional parameters for document text extraction and chunking."""

    chunk_size: Optional[int] = Field(None, gt=50, le=10000, description="Target chunk size in characters")
    chunk_overlap: Optional[int] = Field(None, ge=0, le=2000, description="Overlap between consecutive chunks")
    async_mode: bool = Field(default=True, description="Process asynchronously via Celery job queue")


class SecureUploadResponse(BaseModel):
    """Response returned upon secure upload and background job dispatch (Phase 2D)."""

    document_id: str
    session_id: str
    user_id: str
    filename: str
    file_size: int
    mime_type: str
    sha256: str
    storage_key: str
    status: str
    job_id: Optional[str] = None
    created_at: datetime
    message: str = "Document uploaded securely and queued for background processing."
