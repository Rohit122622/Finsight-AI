"""
FinSentry AI — Phase 3C Context Building Result Contract.

Strongly typed Pydantic schemas for the Context Building layer:
  - Document evidence (preserving full citation metadata)
  - Financial metric evidence
  - Red flag evidence
  - Comparison evidence
  - Conversation context
  - Session memory
  - Categorization (SOURCE_EVIDENCE, CONVERSATION_CONTEXT, SESSION_MEMORY)
  - Research context envelope with compression and truncation metadata
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from schemas.query_understanding import QueryUnderstandingResult
from schemas.retrieval import RetrievalMode, RetrievalResult


                                                                       

class ContextSourceType(str, Enum):
    """Specific type of context item."""

    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"
    FINANCIAL_METRIC = "FINANCIAL_METRIC"
    RED_FLAG = "RED_FLAG"
    COMPARISON = "COMPARISON"
    CHAT_HISTORY = "CHAT_HISTORY"
    SESSION_MEMORY = "SESSION_MEMORY"


class ContextCategory(str, Enum):
    """
    High-level authoritative tier of context evidence.

    Crucial for Phase 3E evidence-based reasoning:
    - SOURCE_EVIDENCE: Verified document chunks, structured metrics, comparisons, red flags.
    - CONVERSATION_CONTEXT: Prior user/assistant chat turns (not authoritative source evidence).
    - SESSION_MEMORY: Prior topics, entities, and periods discussed in this research session.
    """

    SOURCE_EVIDENCE = "SOURCE_EVIDENCE"
    CONVERSATION_CONTEXT = "CONVERSATION_CONTEXT"
    SESSION_MEMORY = "SESSION_MEMORY"


                                                                       

class DocumentEvidence(BaseModel):
    """
    Direct document chunk evidence with preserved citation metadata.
    Does NOT modify the original retrieved text.
    """

    document_id: str = Field(..., description="Parent document identifier")
    chunk_id: str = Field(..., description="Unique chunk identifier")
    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="Owning user identifier")
    source_text: str = Field(..., description="Verbatim chunk text content")
    page_number: Optional[int] = Field(None, description="Page number in source document")
    section: Optional[str] = Field(None, description="Section identifier in source document")
    chunk_index: int = Field(default=0, description="Sequential index within document")
    score: float = Field(..., ge=0.0, le=1.0, description="Retrieval relevance score")
    retrieval_method: RetrievalMode = Field(..., description="Retrieval method (vector, keyword, hybrid)")
    document_filename: Optional[str] = Field(None, description="Original document filename")
    token_estimate: int = Field(default=0, description="Estimated token count")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional chunk metadata")
    category: ContextCategory = Field(default=ContextCategory.SOURCE_EVIDENCE)
    source_type: ContextSourceType = Field(default=ContextSourceType.DOCUMENT_CHUNK)


class MetricEvidence(BaseModel):
    """Structured financial metric evidence."""

    metric_name: str = Field(..., description="Canonical metric name (e.g., revenue, net_income)")
    value: Any = Field(..., description="Extracted metric value (number or formatted string)")
    unit_or_currency: Optional[str] = Field(None, description="Currency or unit (e.g., USD, %, millions)")
    period: Optional[str] = Field(None, description="Fiscal or calendar period (e.g., 2024, Q1 2024, FY23)")
    document_reference: Optional[str] = Field(None, description="Document ID or section reference")
    page_number: Optional[int] = Field(None, description="Page number where metric was identified")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Extraction confidence score")
    category: ContextCategory = Field(default=ContextCategory.SOURCE_EVIDENCE)
    source_type: ContextSourceType = Field(default=ContextSourceType.FINANCIAL_METRIC)


class RedFlagEvidence(BaseModel):
    """Identified financial risk or red-flag evidence."""

    flag_id: str = Field(..., description="Unique red flag identifier")
    title: str = Field(..., description="Title or classification of the red flag")
    severity: str = Field(..., description="Severity level (e.g., HIGH, MEDIUM, LOW, CRITICAL)")
    description: str = Field(..., description="Detailed description of the financial anomaly or risk")
    source_reference: Optional[str] = Field(None, description="Document or metric citation")
    score: Optional[float] = Field(None, description="Anomaly or risk score")
    category: ContextCategory = Field(default=ContextCategory.SOURCE_EVIDENCE)
    source_type: ContextSourceType = Field(default=ContextSourceType.RED_FLAG)


class ComparisonEvidence(BaseModel):
    """Period-over-period or cross-metric comparison evidence."""

    metric_name: str = Field(..., description="Metric being compared")
    base_period: str = Field(..., description="Baseline period (e.g., 2023, Q1 2023)")
    target_period: str = Field(..., description="Target period (e.g., 2024, Q1 2024)")
    base_value: Any = Field(..., description="Base period value")
    target_value: Any = Field(..., description="Target period value")
    absolute_change: Optional[Any] = Field(None, description="Absolute difference")
    percentage_change: Optional[str] = Field(None, description="Percentage change (e.g., +15.2%, -3.4%)")
    trend: Optional[str] = Field(None, description="Trend direction (e.g., INCREASE, DECREASE, STABLE)")
    source_reference: Optional[str] = Field(None, description="Document reference citation")
    category: ContextCategory = Field(default=ContextCategory.SOURCE_EVIDENCE)
    source_type: ContextSourceType = Field(default=ContextSourceType.COMPARISON)


class ConversationMessage(BaseModel):
    """A prior conversation message turn."""

    role: str = Field(..., description="Role of message sender (user, assistant)")
    content: str = Field(..., description="Message text content")
    timestamp: Optional[str] = Field(None, description="ISO timestamp or sequence index")
    category: ContextCategory = Field(default=ContextCategory.CONVERSATION_CONTEXT)
    source_type: ContextSourceType = Field(default=ContextSourceType.CHAT_HISTORY)


class SessionMemoryItem(BaseModel):
    """A key entity, topic, or parameter preserved in session research memory."""

    topic: Optional[str] = Field(None, description="Primary research subject or company")
    entities: List[str] = Field(default_factory=list, description="Identified companies/tickers")
    metrics_discussed: List[str] = Field(default_factory=list, description="Metrics previously queried")
    periods_discussed: List[str] = Field(default_factory=list, description="Periods previously queried")
    prior_queries: List[str] = Field(default_factory=list, description="Recent user query strings")
    document_ids: List[str] = Field(default_factory=list, description="Referenced document IDs")
    category: ContextCategory = Field(default=ContextCategory.SESSION_MEMORY)
    source_type: ContextSourceType = Field(default=ContextSourceType.SESSION_MEMORY)


                                                                       

class ContextLimitsConfig(BaseModel):
    """Configurable limits for context window assembly."""

    max_chunks: int = Field(default=10, ge=1, le=50, description="Maximum document chunks to include")
    max_characters: int = Field(default=8000, ge=500, le=50000, description="Maximum character budget")
    max_tokens: int = Field(default=2000, ge=100, le=12000, description="Maximum estimated token budget")
    max_history_messages: int = Field(default=5, ge=0, le=30, description="Maximum chat history messages")
    max_metrics: int = Field(default=10, ge=0, le=50, description="Maximum financial metrics")
    max_red_flags: int = Field(default=5, ge=0, le=20, description="Maximum red flags")
    max_comparisons: int = Field(default=5, ge=0, le=20, description="Maximum comparison records")


class ContextMetadata(BaseModel):
    """Operational metadata regarding context assembly, ranking, and compression."""

    total_chunks_retrieved: int = Field(default=0)
    chunks_selected: int = Field(default=0)
    metrics_selected: int = Field(default=0)
    red_flags_selected: int = Field(default=0)
    comparisons_selected: int = Field(default=0)
    history_messages_selected: int = Field(default=0)
    has_session_memory: bool = Field(default=False)
    total_character_count: int = Field(default=0)
    total_token_estimate: int = Field(default=0)
    is_truncated: bool = Field(default=False, description="Whether limits caused truncation")
    truncated_sources: List[str] = Field(default_factory=list, description="List of source types truncated")
    available_sources: List[ContextSourceType] = Field(default_factory=list)
    missing_sources: List[ContextSourceType] = Field(default_factory=list)


                                                                       

class ResearchContext(BaseModel):
    """
    Complete structured context package ready for Research Agent reasoning (Phase 3D/3E).
    Does NOT generate the final financial answer.
    """

    session_id: str = Field(..., description="Owning research session ID")
    user_id: str = Field(..., description="Owning user ID")
    query: str = Field(..., description="User question")
    query_understanding: Optional[QueryUnderstandingResult] = Field(
        None, description="Structured query understanding analysis from Phase 3B"
    )
    documents: List[DocumentEvidence] = Field(
        default_factory=list, description="Selected ranked document chunks (SOURCE_EVIDENCE)"
    )
    metrics: List[MetricEvidence] = Field(
        default_factory=list, description="Selected financial metrics (SOURCE_EVIDENCE)"
    )
    red_flags: List[RedFlagEvidence] = Field(
        default_factory=list, description="Selected red flag risks (SOURCE_EVIDENCE)"
    )
    comparisons: List[ComparisonEvidence] = Field(
        default_factory=list, description="Selected comparison data (SOURCE_EVIDENCE)"
    )
    chat_history: List[ConversationMessage] = Field(
        default_factory=list, description="Recent conversation turns (CONVERSATION_CONTEXT)"
    )
    session_memory: Optional[SessionMemoryItem] = Field(
        None, description="Session research memory (SESSION_MEMORY)"
    )
    metadata: ContextMetadata = Field(..., description="Context assembly metadata")


                                                                       

class ContextBuildingRequest(BaseModel):
    """Request payload to assemble structured research context."""

    query: str = Field(..., min_length=1, description="User question")
    retrieved_results: Optional[List[RetrievalResult]] = Field(
        default=None, description="Pre-retrieved Phase 3A chunks"
    )
    financial_metrics: Optional[List[MetricEvidence]] = Field(
        default=None, description="Pre-extracted financial metrics"
    )
    red_flags: Optional[List[RedFlagEvidence]] = Field(
        default=None, description="Pre-identified red flags"
    )
    comparisons: Optional[List[ComparisonEvidence]] = Field(
        default=None, description="Pre-computed comparisons"
    )
    chat_history: Optional[List[ConversationMessage]] = Field(
        default=None, description="Recent conversation turns"
    )
    session_memory: Optional[SessionMemoryItem] = Field(
        default=None, description="Session memory"
    )
    limits: Optional[ContextLimitsConfig] = Field(
        default=None, description="Custom context window limits"
    )
    auto_retrieve: bool = Field(
        default=True,
        description="Whether to automatically execute Phase 3B query understanding and Phase 3A retrieval if results not supplied",
    )
