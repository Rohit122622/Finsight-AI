"""
FinSentry AI — Phase 3G Output Validation Schemas.

Strongly typed Pydantic contracts for:
  - Research Agent response structure validation
  - Claim, citation, and evidence support validation
  - Duplicate answer & claim detection
  - Multi-tenant citation verification
  - Structured ValidationResult envelope
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from schemas.reasoning import ConfidenceLevel, ResearchClaim, ResearchCitation, ResearchResponse
from schemas.context import ResearchContext


class ValidationStatus(str, Enum):
    """Validation lifecycle status for the Research Agent response."""

    VALID = "VALID"
    INVALID = "INVALID"
    MODIFIED = "MODIFIED"
    REFUSED = "REFUSED"


class OutputValidationConfig(BaseModel):
    """Configuration governing Phase 3G validation thresholds and strictness."""

    strict_mode: bool = Field(default=True, description="Enforce strict rejection on severe anomalies")
    refuse_on_unsupported_metrics: bool = Field(
        default=True, description="Refuse response if key financial metrics are fabricated/unsupported"
    )
    refuse_on_unsupported_causal: bool = Field(
        default=True, description="Refuse response if causal explanations are fabricated"
    )
    unsupported_claims_tolerance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Max allowed ratio of unsupported claims before refusal"
    )
    deduplicate_claims: bool = Field(default=True, description="Remove or merge redundant identical claims")
    deduplicate_citations: bool = Field(default=True, description="Deduplicate repetitive citations")
    deduplicate_answer_text: bool = Field(default=True, description="Detect repetitive sentence loops in answer")
    enforce_multi_tenant_citations: bool = Field(
        default=True, description="Enforce user_id & session_id isolation on all citations"
    )
    max_confidence_with_unsupported: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence ceiling when unsupported claims are present"
    )
    max_confidence_with_invalid_citations: float = Field(
        default=0.4, ge=0.0, le=1.0, description="Confidence ceiling when invalid/fabricated citations are found"
    )
    high_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    medium_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class ValidationResult(BaseModel):
    """
    Structured outcome of Phase 3G Output Validation pipeline.
    """

    valid: bool = Field(..., description="True if response meets all safety and accuracy criteria")
    status: ValidationStatus = Field(default=ValidationStatus.VALID, description="Validation status")
    validation_errors: List[str] = Field(default_factory=list, description="Fatal validation errors detected")
    validation_warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings detected")
    validated_claim_count: int = Field(default=0, description="Total claims verified")
    supported_claim_count: int = Field(default=0, description="Count of authoritative supported claims")
    unsupported_claim_count: int = Field(default=0, description="Count of unsupported or fabricated claims")
    partially_supported_claim_count: int = Field(default=0, description="Count of partially supported claims")
    validated_citation_count: int = Field(default=0, description="Valid citation count")
    invalid_citation_count: int = Field(default=0, description="Fabricated/invalid citation count")
    duplicate_count: int = Field(default=0, description="Count of redundant claims/sentences/citations removed")
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Validated confidence score")
    confidence_level: ConfidenceLevel = Field(default=ConfidenceLevel.LOW, description="Validated confidence level")
    refusal_required: bool = Field(default=False, description="True if answer must be converted to safe refusal")
    refusal_reason: Optional[str] = Field(None, description="Reason for refusal if refusal_required is True")
    duplicate_claims: List[str] = Field(default_factory=list, description="Identified duplicate claim texts")
    duplicate_citations: List[str] = Field(default_factory=list, description="Identified duplicate citation IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic telemetry")


class ValidateOutputRequest(BaseModel):
    """Request payload for validating a research response against session context."""

    response: ResearchResponse = Field(..., description="Research response to validate")
    context: Optional[ResearchContext] = Field(None, description="Session evidence context for citation validation")
    config: Optional[OutputValidationConfig] = Field(None, description="Validation policy configuration")


class ValidateOutputResponse(BaseModel):
    """Validated response payload containing safe sanitized response and validation report."""

    validated_response: ResearchResponse = Field(..., description="Sanitized and validated response envelope")
    validation_result: ValidationResult = Field(..., description="Validation report")
