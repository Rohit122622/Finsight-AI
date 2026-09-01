"""
Standard Pydantic result schemas for FinSentry AI Agents (Phase 2C).

Enforces the Common Agent Contract: Input -> Agent -> Pydantic Output -> Validation -> Log.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BaseAgentOutput(BaseModel):
    """Base schema for all typed agent outputs."""

    agent_name: str
    success: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_time_ms: float = 0.0
    model_used: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentResult(BaseAgentOutput):
    """Output contract for DocumentAgent / DocumentProcessingAgent."""

    document_id: str
    session_id: str
    filename: str = ""
    chunk_count: int = 0
    word_count: int = 0
    character_count: int = 0
    page_count: Optional[int] = None
    sha256: str = ""
    summary: Optional[str] = None


class ExtractionMetricItem(BaseModel):
    """Individual financial metric extracted from a document with exact provenance and grounding."""

    metric_name: str
    value: Optional[float] = None
    prior_value: Optional[float] = None
    display_name: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    period: Optional[str] = None
    prior_period: Optional[str] = None
    yoy_change_percent: Optional[float] = None
    yoy_change_absolute: Optional[float] = None
    source_chunk_ids: List[str] = Field(default_factory=list)
    page_numbers: List[int] = Field(default_factory=list)
    page_number: Optional[int] = None
    section: Optional[str] = None
    evidence_snippet: Optional[str] = None
    context_snippet: Optional[str] = None
    confidence: float = 1.0
    confidence_score: float = 1.0
    is_low_confidence: bool = False
    flag_reason: Optional[str] = None
    derivation_formula: Optional[str] = None
    is_grounded: bool = True
    status: str = "VALID"


class ExtractionResult(BaseAgentOutput):
    """Output contract for ExtractionAgent (Phase 2C Master Plan compliant)."""

    session_id: str
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    filing_type: Optional[str] = None
    reporting_currency: Optional[str] = None
    reporting_scale: Optional[str] = None
    reporting_period: Optional[str] = None
    prior_period: Optional[str] = None
    metrics: List[ExtractionMetricItem] = Field(default_factory=list)
    metrics_dict: Dict[str, Optional[float]] = Field(default_factory=dict)
    multi_year_data: Dict[str, Dict[str, Optional[float]]] = Field(default_factory=dict)
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    raw_extraction: Dict[str, Any] = Field(default_factory=dict)
    chunks_analyzed: int = 0
    financial_chunks_count: int = 0
    retry_attempted: bool = False
    retry_success: Optional[bool] = None
    confidence_average: float = 1.0
    low_confidence_count: int = 0
    failed_metrics_count: int = 0
    summary: str = ""


class RedFlagItem(BaseModel):
    """Individual risk or compliance anomaly flag."""

    severity: str = Field("MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")
    category: str = Field(..., description="E.g. Accounting, Governance, Solvency, Disclosure, Legal, Profitability, Operational")
    title: str
    description: str
    source: str = Field("QUALITATIVE", description="QUANTITATIVE or QUALITATIVE")
    type: Optional[str] = None
    metric_name: Optional[str] = None
    evidence_snippet: Optional[str] = None
    recommendation: Optional[str] = None
    page_number: Optional[int] = None
    section: Optional[str] = None
    document_filename: Optional[str] = None
    document_id: Optional[str] = None
    source_chunk_ids: List[str] = Field(
        default_factory=list,
        description="Internal chunk IDs for auditability - must not leak to user-facing text",
    )


class RedFlagResult(BaseAgentOutput):
    """Output contract for RedFlagAgent."""

    session_id: str
    user_id: Optional[str] = None
    document_id: Optional[str] = None
    company_name: Optional[str] = None
    total_flags: int = 0
    high_severity_count: int = 0
    flags: List[RedFlagItem] = Field(default_factory=list)
    risk_score: float = 0.0
    overall_assessment: str = ""
    quantitative_flags_count: int = 0
    qualitative_flags_count: int = 0
    updated_at: Optional[datetime] = None


class ComparisonItem(BaseModel):
    """Comparison metric across periods or companies."""

    metric_name: str
    baseline_value: Any
    comparison_value: Any
    variance_percentage: Optional[float] = None
    trend: str = "NEUTRAL"                               


class ComparisonResult(BaseAgentOutput):
    """Output contract for ComparisonAgent."""

    session_id: str
    baseline_entity: str
    comparison_entity: str
    metrics_compared: List[ComparisonItem] = Field(default_factory=list)
    key_takeaways: List[str] = Field(default_factory=list)
    executive_summary: str = ""


class ResearchResult(BaseAgentOutput):
    """Output contract for ResearchAgent."""

    session_id: str
    query: str
    answer: str
    sources_used: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = 1.0


class ReportSection(BaseModel):
    """Individual section within an analytical report."""

    title: str
    content: str
    key_findings: List[str] = Field(default_factory=list)


class ReportResult(BaseAgentOutput):
    """Output contract for ReportAgent."""

    session_id: str
    report_title: str
    executive_summary: str
    sections: List[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recommendations: List[str] = Field(default_factory=list)
