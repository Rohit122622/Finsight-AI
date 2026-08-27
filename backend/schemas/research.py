"""
Pydantic API schemas for Semantic Search, Financial Research, and Metric Extraction (Phase 2C).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    """Payload for querying session document chunks using semantic similarity."""

    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum chunks to retrieve")
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity cutoff")
    document_ids: Optional[List[str]] = Field(None, description="Optional list of document IDs to restrict search to")


class SemanticSearchResultChunk(BaseModel):
    """Ranked document chunk returned from semantic vector retrieval."""

    chunk_id: str
    chunk_index: int
    document_id: str
    document_filename: str
    text: str
    score: float
    token_estimate: int
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SemanticSearchResponse(BaseModel):
    """Response containing semantic search matches."""

    query: str
    session_id: str
    results: List[SemanticSearchResultChunk]
    total_results: int


class CitationItem(BaseModel):
    """Source reference supporting a grounded research finding."""

    citation_id: int
    document_id: str
    document_filename: str
    chunk_id: str
    chunk_index: int
    page_number: Optional[int] = None
    relevance_score: float
    snippet: str


class ResearchQueryRequest(BaseModel):
    """Request payload for executing financial research / Q&A."""

    query: str = Field(..., min_length=1, description="Financial question or research task")
    document_ids: Optional[List[str]] = Field(None, description="Optional list of document IDs to filter by")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of evidence chunks to retrieve")
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity threshold")
    async_mode: bool = Field(default=True, description="Process in background via Celery worker")


class ResearchResultResponse(BaseModel):
    """Synchronous or retrieved result of financial research."""

    query: str
    session_id: str
    answer: str
    citations: List[CitationItem] = Field(default_factory=list)
    chunks_retrieved: int = 0


class ExtractionQueryRequest(BaseModel):
    """Request payload for structured financial data extraction."""

    document_id: Optional[str] = Field(None, description="Optional document ID to restrict extraction to")
    target_fields: Optional[List[str]] = Field(
        None, description="List of target attributes (e.g. revenue, EBITDA, net_income, risks)"
    )
    async_mode: bool = Field(default=True, description="Process in background via Celery worker")


class ExtractionResultResponse(BaseModel):
    """Structured financial data extracted from session documents."""

    session_id: str
    document_id: Optional[str] = None
    target_fields: List[str] = Field(default_factory=list)
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    chunks_analyzed: int = 0
