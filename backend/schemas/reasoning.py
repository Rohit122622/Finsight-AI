"""
FinSentry AI — Phase 3E Evidence-Based Reasoning Schemas.

Strongly typed Pydantic contracts for:
  - Claim types and support status
  - Evidence references and citations
  - Evidence conflicts and sufficiency assessments
  - Confidence scoring and levels
  - Structured ResearchResponse envelope
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.context import ContextLimitsConfig, ResearchContext
from schemas.prompt import PromptConfiguration
from schemas.query_understanding import QueryUnderstandingResult


class ClaimType(str, Enum):
    """Classification of an extracted analytical claim."""

    FACT = "FACT"
    METRIC = "METRIC"
    TREND = "TREND"
    COMPARISON = "COMPARISON"
    CAUSAL = "CAUSAL"
    RISK = "RISK"
    INTERPRETATION = "INTERPRETATION"


class ClaimSupportStatus(str, Enum):
    """Grounding determination for a claim against SOURCE_EVIDENCE."""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class ConfidenceLevel(str, Enum):
    """Confidence level tier based on evidence strength."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceRef(BaseModel):
    """Precise pointer to a verified source evidence item."""

    document_id: str = Field(..., description="Parent document identifier")
    chunk_id: str = Field(..., description="Chunk identifier")
    document_filename: Optional[str] = Field(None, description="Document filename if available")
    page_number: Optional[int] = Field(None, description="Page number if available")
    section: Optional[str] = Field(None, description="Disclosed financial section")
    source_reference: Optional[str] = Field(None, description="Formatted reference string")


class ResearchClaim(BaseModel):
    """An individual assertion extracted from the research answer."""

    claim_id: str = Field(..., description="Unique claim identifier (e.g. claim_001)")
    claim_text: str = Field(..., description="Verbatim assertion sentence/clause")
    claim_type: ClaimType = Field(default=ClaimType.FACT, description="Analytical claim category")
    support_status: ClaimSupportStatus = Field(
        default=ClaimSupportStatus.UNSUPPORTED,
        description="Verification status against SOURCE_EVIDENCE",
    )
    evidence_refs: List[EvidenceRef] = Field(
        default_factory=list, description="Verified evidence references supporting this claim"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Claim-level confidence score"
    )
    is_causal: bool = Field(
        default=False, description="Whether the claim asserts a causal explanation (e.g. 'because')"
    )
    unsupported_reasons: List[str] = Field(
        default_factory=list, description="Reasons if claim is unsupported or partially supported"
    )


class ResearchCitation(BaseModel):
    """Citation mapping claims to source chunks with validation metadata."""

    citation_id: str = Field(..., description="Unique citation identifier (e.g. cit_001)")
    chunk_id: str = Field(..., description="Referenced chunk ID")
    document_id: str = Field(..., description="Referenced document ID")
    document_filename: Optional[str] = Field(None, description="Filename")
    page_number: Optional[int] = Field(None, description="Page number")
    section: Optional[str] = Field(None, description="Section")
    quoted_snippet: str = Field(default="", description="Snippet supporting the claim")
    claim_ids: List[str] = Field(
        default_factory=list, description="Claim IDs supported by this citation"
    )
    is_valid: bool = Field(default=True, description="Whether citation resolves to actual evidence")
    validation_error: Optional[str] = Field(
        None, description="Explanation if citation is invalid or fabricated"
    )


class EvidenceConflict(BaseModel):
    """Contradiction or variance detected across multiple evidence sources."""

    metric_or_topic: str = Field(..., description="Subject of the discrepancy")
    competing_values: List[str] = Field(..., description="Conflicting values found in evidence")
    evidence_refs: List[EvidenceRef] = Field(
        default_factory=list, description="References to the conflicting sources"
    )
    description: str = Field(..., description="Detailed description of the conflict")


class EvidenceSufficiencyAssessment(BaseModel):
    """Deterministic evaluation of whether evidence is adequate to answer the query."""

    is_sufficient: bool = Field(..., description="True if evidence adequately covers question")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Sufficiency score")
    reasons: List[str] = Field(default_factory=list, description="Assessment rationale")
    has_target_metric_match: bool = Field(default=False)
    has_temporal_match: bool = Field(default=False)
    has_section_match: bool = Field(default=False)
    missing_evidence_items: List[str] = Field(
        default_factory=list, description="Key data points missing from evidence"
    )


class ConfidenceAssessment(BaseModel):
    """Overall confidence score breakdown for the research response."""

    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence (0.0 - 1.0)")
    level: ConfidenceLevel = Field(default=ConfidenceLevel.LOW, description="Tier: LOW, MEDIUM, HIGH")
    retrieval_relevance: float = Field(default=0.0, description="Relevance score contribution")
    evidence_coverage: float = Field(default=0.0, description="Evidence coverage contribution")
    citation_validity_rate: float = Field(default=0.0, description="Ratio of valid citations")
    supported_claim_ratio: float = Field(default=0.0, description="Ratio of supported claims")
    conflict_penalty: float = Field(default=0.0, description="Deduction for unresolved conflicts")


class ReasoningMetadata(BaseModel):
    """Execution and validation metrics."""

    total_claims: int = Field(default=0)
    supported_claims: int = Field(default=0)
    unsupported_claims: int = Field(default=0)
    partially_supported_claims: int = Field(default=0)
    causal_claims_count: int = Field(default=0)
    unsupported_causal_claims_count: int = Field(default=0)
    citation_validation_rate: float = Field(default=0.0)
    total_tokens_estimate: int = Field(default=0)
    chunks_analyzed: int = Field(default=0)
    execution_time_ms: float = Field(default=0.0)
    llm_provider: Optional[str] = Field(default=None, description="LLM provider that generated the response")
    llm_model: Optional[str] = Field(default=None, description="LLM model name")
    is_fallback: bool = Field(default=False, description="True if response was generated via fallback provider")
    fallback_attempts: int = Field(default=1, description="Number of fallback attempts executed")
    trace_id: Optional[str] = Field(default=None, description="Observability trace ID")


class ResearchResponse(BaseModel):
    """
    Complete structured, evidence-grounded research response contract.
    """

    session_id: str = Field(..., description="Owning research session ID")
    user_id: str = Field(..., description="Owning user ID")
    query: str = Field(..., description="User question")
    answer: str = Field(..., description="Grounded analytical answer")
    refused: bool = Field(
        default=False, description="True if agent refused due to insufficient evidence"
    )
    refusal_reason: Optional[str] = Field(
        None, description="Explanation if answer was refused"
    )
    claims: List[ResearchClaim] = Field(default_factory=list, description="Extracted & verified claims")
    citations: List[ResearchCitation] = Field(
        default_factory=list, description="Verified source citations"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    confidence_level: ConfidenceLevel = Field(
        default=ConfidenceLevel.LOW, description="Confidence tier"
    )
    key_points: List[str] = Field(default_factory=list, description="Key analytical findings")
    limitations: List[str] = Field(
        default_factory=list, description="Disclosed constraints or missing information"
    )
    evidence_conflicts: List[EvidenceConflict] = Field(
        default_factory=list, description="Detected source discrepancies"
    )
    sufficiency: EvidenceSufficiencyAssessment = Field(
        default_factory=lambda: EvidenceSufficiencyAssessment(is_sufficient=False),
        description="Evidence sufficiency assessment",
    )
    confidence_assessment: ConfidenceAssessment = Field(
        default_factory=ConfidenceAssessment,
        description="Confidence calculation breakdown",
    )
    metadata: ReasoningMetadata = Field(
        default_factory=ReasoningMetadata,
        description="Operational and validation metadata",
    )


class ReasonQueryRequest(BaseModel):
    """Request payload for executing Phase 3E Evidence-Based Reasoning."""

    query: str = Field(..., min_length=1, description="Financial research query")
    query_understanding: Optional[QueryUnderstandingResult] = Field(
        default=None, description="Pre-computed Phase 3B understanding"
    )
    context: Optional[ResearchContext] = Field(
        default=None, description="Pre-built Phase 3C context"
    )
    prompt_config: Optional[PromptConfiguration] = Field(
        default=None, description="Prompt configuration"
    )
    limits: Optional[ContextLimitsConfig] = Field(
        default=None, description="Context window limits"
    )
