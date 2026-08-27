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
    """Individual financial metric extracted from a document."""

    metric_name: str
    value: Any
    unit: Optional[str] = None
    period: Optional[str] = None
    confidence: float = 1.0
    context_snippet: Optional[str] = None


class ExtractionResult(BaseAgentOutput):
    """Output contract for ExtractionAgent."""

    session_id: str
    document_id: Optional[str] = None
    metrics: List[ExtractionMetricItem] = Field(default_factory=list)
    raw_extraction: Dict[str, Any] = Field(default_factory=dict)
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
    company_name: Optional[str] = None
    total_flags: int = 0
    high_severity_count: int = 0
    flags: List[RedFlagItem] = Field(default_factory=list)
    risk_score: float = 0.0                                   
    overall_assessment: str = ""
    quantitative_flags_count: int = 0
    qualitative_flags_count: int = 0


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
