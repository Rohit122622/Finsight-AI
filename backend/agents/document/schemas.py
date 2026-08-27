"""
Pydantic Schemas and Contracts for Document Agent in FinSentry AI.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentAgentPayload(BaseModel):
    """Execution input payload for DocumentAgent."""
    document_id: str = Field(..., description="Document ID to ingest and process")
    session_id: str = Field(..., description="Session ID owning this document")
    user_id: Optional[str] = Field(None, description="User ID for multi-tenant isolation")
    chunk_size_tokens: Optional[int] = Field(400, ge=50, le=2000, description="Target tokens per chunk (300-500)")
    chunk_overlap_tokens: Optional[int] = Field(50, ge=0, le=200, description="Token overlap between consecutive text chunks")
    force_ocr: Optional[bool] = Field(False, description="Force OCR execution regardless of text density")


class PDFDetectionResult(BaseModel):
    """Result of PDF inspection, validation, and OCR necessity determination."""
    is_valid_pdf: bool = Field(..., description="True if byte stream is a valid readable PDF")
    is_text_based: bool = Field(..., description="True if PDF has sufficient extractable text layer")
    text_density: float = Field(default=0.0, description="Average character density per page")
    page_count: int = Field(default=0, ge=0, description="Total number of pages")
    requires_ocr: bool = Field(default=False, description="True if OCR is strictly necessary")
    has_encryption: bool = Field(default=False, description="True if PDF is password-protected/encrypted")
    has_images: bool = Field(default=False, description="True if PDF contains image XObjects")
    error_message: Optional[str] = Field(None, description="Error explanation if invalid or unreadable")


class ExtractedTableRow(BaseModel):
    """Single row inside an extracted structured table."""
    label: str = Field(..., description="Row header or primary label (e.g. Total net sales)")
    values: List[str] = Field(default_factory=list, description="Column values corresponding to table headers")


class ExtractedTable(BaseModel):
    """Structured representation of an extracted financial table."""
    table_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID of the table")
    page_number: int = Field(..., description="Page where table is located")
    section: Optional[str] = Field(None, description="Classified financial section")
    headers: List[str] = Field(default_factory=list, description="Column headers (e.g. ['2025', '2024', '2023'])")
    rows: List[ExtractedTableRow] = Field(default_factory=list, description="Structured row entries")
    markdown: str = Field(..., description="Clean markdown representation of table with explicit headers")
    extraction_method: str = Field("pdfplumber", description="Method used to extract table")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional table coordinates or metadata")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ParsedChunk(BaseModel):
    """Normalized chunk representation ready for embedding and MongoDB persistence."""
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Deterministic or unique chunk identifier")
    document_id: str = Field(..., description="Parent document UUID")
    session_id: str = Field(..., description="Research session UUID")
    user_id: str = Field(..., description="Owner user UUID")
    chunk_index: int = Field(default=0, ge=0, description="0-indexed sequence number in document")
    text: str = Field(..., description="Text content of chunk for retrieval and embedding")
    source_text: str = Field(..., description="Exact raw text slice or table markdown")
    content_type: str = Field("text", description="Type of content: 'text' or 'table'")
    section: Optional[str] = Field(None, description="Classified financial section")
    page_number: Optional[int] = Field(None, description="Primary source page number (1-indexed)")
    page_start: Optional[int] = Field(None, description="Starting page number")
    page_end: Optional[int] = Field(None, description="Ending page number")
    source_pages: List[int] = Field(default_factory=list, description="All pages contributing to chunk")
    table_id: Optional[str] = Field(None, description="Referenced table ID if content_type is 'table'")
    token_estimate: int = Field(default=0, ge=0, description="Measured token count (300-500 target)")
    character_count: int = Field(default=0, ge=0, description="Character count")
    extraction_method: str = Field("native", description="Extraction engine used (native, pdfplumber, ocr)")
    embedding: Optional[List[float]] = Field(None, description="1024-dim BGE-large-en normalized vector")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible metadata dictionary")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class DocumentAgentResultSummary(BaseModel):
    """Structured summary returned in AgentResult."""
    document_id: str
    session_id: str
    status: str
    page_count: int
    chunk_count: int
    table_count: int
    token_count: int
    filename: str = ""
    word_count: int = 0
    character_count: int = 0
    section_breakdown: Dict[str, int] = Field(default_factory=dict)
    ocr_invoked: bool = False
    message: str = "Document processed, chunked, and indexed successfully"
