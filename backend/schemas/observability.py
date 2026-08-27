"""
FinSentry AI — Phase 3J Research Observability & Telemetry Schemas.

Defines strongly typed Pydantic contracts for:
- Traces, Runs, and Stages
- Token Usage (Actual & Estimated)
- Latency & Stage Timings
- Failure & Error Categories
- Retrieval, Fallback, Grounding, and Validation Metrics
- Prompt Execution Telemetry
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    """Normalized categories for telemetry failure tracking."""
    RETRIEVAL_FAILURE = "retrieval_failure"
    CONTEXT_FAILURE = "context_failure"
    PROMPT_FAILURE = "prompt_failure"
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_PROVIDER_FAILURE = "llm_provider_failure"
    FALLBACK_FAILURE = "fallback_failure"
    VALIDATION_FAILURE = "validation_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    MALFORMED_REQUEST = "malformed_request"
    INTERNAL_ERROR = "internal_error"


class StageStatus(str, Enum):
    """Status of an individual pipeline stage or trace."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUSED = "REFUSED"
    SKIPPED = "SKIPPED"


class TokenUsage(BaseModel):
    """
    Token usage telemetry.
    Distinguishes actual provider reported tokens from marked estimates.
    """
    input_tokens: int = Field(default=0, ge=0, description="Number of prompt/input tokens.")
    output_tokens: int = Field(default=0, ge=0, description="Number of completion/output tokens.")
    total_tokens: int = Field(default=0, ge=0, description="Total tokens used.")
    is_estimated: bool = Field(
        default=False,
        description="True if provider usage was unavailable and tokens were estimated."
    )
    provider: Optional[str] = Field(default=None, description="LLM provider name.")
    model: Optional[str] = Field(default=None, description="LLM model identifier.")


class StageTiming(BaseModel):
    """Latency and execution metadata for a single research stage."""
    stage_name: str = Field(..., description="Name of the research stage.")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Stage start timestamp (UTC)."
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Stage completion timestamp (UTC)."
    )
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds.")
    status: str = Field(default=StageStatus.SUCCESS.value, description="Execution status.")
    error: Optional[str] = Field(default=None, description="Sanitized error description if failed.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Stage-specific metadata.")


class RetrievalMetrics(BaseModel):
    """Retrieval stage metrics and telemetry."""
    retrieval_mode: str = Field(default="hybrid", description="Retrieval mode used (hybrid/vector/keyword).")
    query_classification: str = Field(default="FACTUAL", description="Classified intent.")
    top_k: int = Field(default=5, ge=1, description="Requested top_k chunks.")
    candidates_examined: int = Field(default=0, ge=0, description="Number of candidate chunks evaluated.")
    results_returned: int = Field(default=0, ge=0, description="Number of top chunks returned.")
    cache_hit: bool = Field(default=False, description="Whether retrieval was served from cache.")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Retrieval stage duration in ms.")
    score_threshold: float = Field(default=0.0, ge=0.0, description="Applied similarity threshold.")
    avg_score: Optional[float] = Field(default=None, description="Average similarity score of results.")
    max_score: Optional[float] = Field(default=None, description="Max similarity score of results.")
    min_score: Optional[float] = Field(default=None, description="Min similarity score of results.")


class GroundingMetrics(BaseModel):
    """Safe citation and evidence grounding metrics."""
    citations_generated: int = Field(default=0, ge=0, description="Total citations extracted.")
    citations_validated: int = Field(default=0, ge=0, description="Citations verified against chunks.")
    invalid_citations: int = Field(default=0, ge=0, description="Invalid or hallucinated citations.")
    supported_claims: int = Field(default=0, ge=0, description="Claims supported by evidence.")
    unsupported_claims: int = Field(default=0, ge=0, description="Claims unsupported by evidence.")
    partially_supported_claims: int = Field(default=0, ge=0, description="Partially supported claims.")
    grounding_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Supported / total claims ratio.")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Calculated confidence score.")
    confidence_level: str = Field(default="HIGH", description="Confidence tier (HIGH, MEDIUM, LOW).")
    refusal_status: bool = Field(default=False, description="Whether inquiry was safely refused.")
    refusal_reason: Optional[str] = Field(default=None, description="Refusal rationale if applicable.")


class ValidationMetrics(BaseModel):
    """Output validation telemetry from Phase 3G."""
    validation_status: str = Field(default="VALID", description="Validation status (VALID/MODIFIED/REFUSED/INVALID).")
    is_valid: bool = Field(default=True, description="Whether response passed validation.")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Validation duration in ms.")
    invalid_citation_count: int = Field(default=0, ge=0, description="Number of invalid citations.")
    unsupported_claim_count: int = Field(default=0, ge=0, description="Number of unsupported claims.")
    conflict_count: int = Field(default=0, ge=0, description="Number of evidence conflicts detected.")
    confidence_before: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence before validation.")
    confidence_after: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence after validation.")
    refusal_decision: bool = Field(default=False, description="Whether validation triggered refusal.")
    validation_errors: List[str] = Field(default_factory=list, description="Sanitized validation errors.")
    validation_warnings: List[str] = Field(default_factory=list, description="Sanitized validation warnings.")


class FallbackMetrics(BaseModel):
    """Phase 3F multi-provider LLM fallback telemetry."""
    fallback_occurred: bool = Field(default=False, description="Whether fallback was triggered.")
    primary_provider: str = Field(default="", description="Configured primary provider.")
    primary_model: str = Field(default="", description="Configured primary model.")
    failed_attempts: int = Field(default=0, ge=0, description="Total failed attempts.")
    error_categories: List[str] = Field(default_factory=list, description="Error categories encountered.")
    fallback_provider: Optional[str] = Field(default=None, description="First successful fallback provider.")
    fallback_model: Optional[str] = Field(default=None, description="First successful fallback model.")
    final_provider: str = Field(default="", description="Provider that produced final response.")
    final_model: str = Field(default="", description="Model that produced final response.")
    fallback_attempt_count: int = Field(default=0, ge=0, description="Total provider hops.")
    total_fallback_latency_ms: float = Field(default=0.0, ge=0.0, description="Total fallback latency in ms.")
    chain_summary: str = Field(
        default="PRIMARY_SUCCESS",
        description="Summary of chain progression (e.g. PRIMARY_SUCCESS, PRIMARY_FAILED_CLAUDE_SUCCESS, ALL_FAILED)."
    )


class PromptExecutionMetadata(BaseModel):
    """Prompt construction and execution metadata."""
    prompt_version: str = Field(default="1.0.0", description="Prompt template version.")
    prompt_sections: List[str] = Field(default_factory=list, description="Included prompt sections.")
    prompt_character_count: int = Field(default=0, ge=0, description="Total character count.")
    estimated_tokens: int = Field(default=0, ge=0, description="Estimated prompt tokens.")
    model: str = Field(default="", description="Target model.")
    provider: str = Field(default="", description="Target provider.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Execution timestamp (UTC)."
    )
    duration_ms: float = Field(default=0.0, ge=0.0, description="Prompt build duration in ms.")
    success: bool = Field(default=True, description="Whether prompt build succeeded.")
    error: Optional[str] = Field(default=None, description="Error message if prompt construction failed.")


class ErrorEvent(BaseModel):
    """Structured error event captured during research pipeline."""
    category: str = Field(..., description="FailureCategory value.")
    stage: str = Field(..., description="Pipeline stage where error occurred.")
    error_message: str = Field(..., description="Sanitized user-safe error message.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Error occurrence timestamp (UTC)."
    )
    retry_count: int = Field(default=0, ge=0, description="Retry attempt count when error occurred.")
    provider: Optional[str] = Field(default=None, description="Associated provider if LLM error.")


class ResearchRun(BaseModel):
    """
    Represents an individual nested execution run (e.g. LangSmith compatible run).
    """
    run_id: str = Field(..., description="Unique run UUID.")
    parent_run_id: Optional[str] = Field(default=None, description="Parent run UUID if nested.")
    run_type: str = Field(default="chain", description="Run type (chain, tool, llm, retriever).")
    name: str = Field(..., description="Human-readable run name.")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Sanitized run inputs.")
    outputs: Optional[Dict[str, Any]] = Field(default=None, description="Sanitized run outputs.")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Run start timestamp (UTC)."
    )
    completed_at: Optional[datetime] = Field(default=None, description="Run completion timestamp (UTC).")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Run duration in ms.")
    status: str = Field(default=StageStatus.SUCCESS.value, description="Run status.")
    error: Optional[str] = Field(default=None, description="Sanitized error if failed.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Sanitized run metadata.")


class ResearchTrace(BaseModel):
    """
    Root telemetry record for a complete Research Agent query execution.
    """
    trace_id: str = Field(..., description="Unique trace UUID.")
    root_run_id: str = Field(..., description="Root LangSmith / execution run UUID.")
    session_id: str = Field(..., description="Session identifier for multi-tenant scoping.")
    conversation_id: str = Field(..., description="Conversation thread identifier.")
    user_id: str = Field(..., description="User identifier.")
    agent_name: str = Field(default="ResearchAgent", description="Agent orchestrator name.")
    query: str = Field(..., description="User query text (sanitized).")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Trace start timestamp (UTC)."
    )
    completed_at: Optional[datetime] = Field(default=None, description="Trace completion timestamp (UTC).")
    total_duration_ms: float = Field(default=0.0, ge=0.0, description="Total end-to-end latency in ms.")
    status: str = Field(default=StageStatus.SUCCESS.value, description="Overall trace status.")
    query_classification: Optional[str] = Field(default=None, description="Classified intent.")
    stages: List[StageTiming] = Field(default_factory=list, description="Stage timing breakdown.")
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="Aggregated token usage.")
    retrieval_metrics: Optional[RetrievalMetrics] = Field(default=None, description="Retrieval telemetry.")
    grounding_metrics: Optional[GroundingMetrics] = Field(default=None, description="Grounding telemetry.")
    validation_metrics: Optional[ValidationMetrics] = Field(default=None, description="Validation telemetry.")
    fallback_metrics: Optional[FallbackMetrics] = Field(default=None, description="Fallback telemetry.")
    prompt_metadata: Optional[PromptExecutionMetadata] = Field(default=None, description="Prompt telemetry.")
    error_events: List[ErrorEvent] = Field(default_factory=list, description="Captured failure events.")
    runs: List[ResearchRun] = Field(default_factory=list, description="Nested run hierarchy.")
    langsmith_trace_url: Optional[str] = Field(default=None, description="LangSmith trace URL if enabled.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp (UTC)."
    )


class TraceSummaryResponse(BaseModel):
    """Concise trace summary for listing."""
    trace_id: str
    session_id: str
    conversation_id: str
    query: str
    started_at: datetime
    total_duration_ms: float
    status: str
    confidence_score: Optional[float] = None
    validation_status: Optional[str] = None
    fallback_occurred: bool = False
    final_provider: Optional[str] = None
    token_usage: TokenUsage


class TraceListResponse(BaseModel):
    """Response containing a list of trace summaries."""
    session_id: str
    traces: List[TraceSummaryResponse]
    total_count: int


class TraceDetailResponse(BaseModel):
    """Detailed response for an individual trace."""
    trace: ResearchTrace
