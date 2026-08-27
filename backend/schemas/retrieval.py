"""
FinSentry AI — Phase 3A Retrieval Result Contract.

Strongly typed Pydantic schemas for the hybrid retrieval pipeline, providing
structured results with full citation metadata for downstream Research Agent
consumption (Phase 3C/3E).
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


from schemas.query_understanding import QueryUnderstandingResult


                                                                       

class RetrievalMode(str, Enum):
    """Supported retrieval strategies."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


                                                                       

class MetadataFilter(BaseModel):
    """
    A single metadata filter clause for retrieval narrowing.

    Designed to be extensible — additional financial metadata fields can be
    added without modifying the retrieval engine.
    """

    document_id: Optional[str] = Field(None, description="Filter by specific document ID")
    document_ids: Optional[List[str]] = Field(None, description="Filter by list of document IDs")
    page_number: Optional[int] = Field(None, ge=1, description="Filter by specific page number")
    page_range: Optional[List[int]] = Field(
        None,
        min_length=2,
        max_length=2,
        description="Filter by page range [start, end] inclusive",
    )
    section: Optional[str] = Field(None, description="Filter by document section identifier")
    status: Optional[str] = Field(None, description="Filter by document processing status")
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata filters for future extensibility",
    )

    @field_validator("page_range")
    @classmethod
    def validate_page_range(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is not None and len(v) == 2 and v[0] > v[1]:
            raise ValueError("page_range start must be <= end")
        return v


                                                                       

class RetrievalRequest(BaseModel):
    """Request payload for Phase 3A retrieval operations."""

    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=100, description="Maximum chunks to retrieve")
    score_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum relevance score cutoff",
    )
    mode: RetrievalMode = Field(
        default=RetrievalMode.HYBRID,
        description="Retrieval strategy: vector, keyword, or hybrid",
    )
    filters: Optional[MetadataFilter] = Field(
        None,
        description="Optional metadata filters to narrow retrieval scope",
    )
    vector_weight: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Weight for vector/semantic score in hybrid ranking (keyword weight = 1 - vector_weight)",
    )
    enable_query_understanding: bool = Field(
        default=True,
        description="Whether to run Phase 3B query understanding to extract signals and expand queries",
    )

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if v < 1:
            raise ValueError("top_k must be at least 1")
        if v > 100:
            raise ValueError("top_k must not exceed 100")
        return v


                                                                       

class RetrievalResult(BaseModel):
    """
    A single ranked retrieval result with full citation metadata.

    Retains all information required for Phase 3C citation generation
    and Phase 3E validation.
    """

    document_id: str = Field(..., description="Parent document identifier")
    chunk_id: str = Field(..., description="Unique chunk identifier")
    session_id: str = Field(..., description="Owning session identifier")
    user_id: str = Field(..., description="Owning user identifier")
    source_text: str = Field(..., description="Raw chunk text content")
    page_number: Optional[int] = Field(None, description="Source page number if applicable")
    section: Optional[str] = Field(None, description="Document section identifier")
    chunk_index: int = Field(default=0, description="Sequential index within document")
    score: float = Field(..., ge=0.0, le=1.0, description="Combined relevance score")
    vector_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Semantic similarity score")
    keyword_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Lexical match score")
    retrieval_method: RetrievalMode = Field(..., description="Method used to retrieve this result")
    document_filename: Optional[str] = Field(None, description="Original document filename")
    token_estimate: int = Field(default=0, description="Estimated token count for the chunk")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional chunk metadata for downstream processing",
    )


                                                                       

class RetrievalMetadata(BaseModel):
    """Operational metadata about the retrieval operation itself."""

    mode: RetrievalMode = Field(..., description="Retrieval mode used")
    vector_weight: float = Field(default=0.7, description="Vector weight in hybrid scoring")
    keyword_weight: float = Field(default=0.3, description="Keyword weight in hybrid scoring")
    score_threshold: float = Field(default=0.0, description="Minimum score threshold applied")
    total_candidates: int = Field(default=0, description="Total candidates before top-K truncation")
    cache_hit: bool = Field(default=False, description="Whether result was served from cache")
    cache_key: Optional[str] = Field(None, description="Cache key used (sanitized, no secrets)")
    filters_applied: Optional[MetadataFilter] = Field(None, description="Filters that were applied")
    query_understanding: Optional[QueryUnderstandingResult] = Field(
        None,
        description="Structured query understanding analysis (Phase 3B)",
    )


                                                                       

class RetrievalResponse(BaseModel):
    """
    Complete response envelope for a Phase 3A retrieval operation.

    Consumed by the Research Agent in Phase 3C+.
    """

    query: str = Field(..., description="Original query string")
    session_id: str = Field(..., description="Session the retrieval was scoped to")
    results: List[RetrievalResult] = Field(default_factory=list, description="Ranked retrieval results")
    total: int = Field(default=0, description="Number of results returned")
    retrieval_metadata: RetrievalMetadata = Field(..., description="Operational metadata")
