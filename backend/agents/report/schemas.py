"""
FinSentry AI — Report Agent Pydantic Schemas and Contracts.

Owner: Vanshika / FinSentry Engineering Team

Defines typed, validated data structures for the deterministic Report Agent pipeline:
  1. ReportMetadata
  2. ExecutiveSummarySection
  3. KeyFinancialsSection (MetricValueItem, CompanyMetricRow)
  4. RedFlagsSection (RedFlagFinding)
  5. CompanyComparisonSection (ComparisonMetricItem)
  6. OutlookSection (OutlookFinding)
  7. ReportDocument (Authoritative internal validated report model)
  8. ReportGenerateRequest / Response
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReportMetadata(BaseModel):
    """Metadata describing the generated report and provenance boundary."""

    report_id: str = Field(..., description="Deterministic unique report identifier")
    session_id: str = Field(..., description="Research session ID boundary")
    user_id: str = Field(..., description="Authenticated user ID boundary")
    document_ids: List[str] = Field(default_factory=list, description="IDs of documents included")
    companies: List[str] = Field(default_factory=list, description="Canonical company names analyzed")
    report_title: str = Field(default="Financial Research & Institutional Audit Report")
    report_version: str = Field(default="v1.0", description="Report version string")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Explicit generation timestamp",
    )
    generator: str = Field(default="FinSentry AI Report Agent (Deterministic Engine)")


class ExecutiveSummarySection(BaseModel):
    """Section 1: Executive Summary compiled strictly from persisted agent outputs."""

    companies_analyzed: List[str] = Field(default_factory=list)
    reporting_periods: List[str] = Field(default_factory=list)
    overall_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    overall_risk_assessment: str = Field(default="Normal Financial Risk Profile")
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    major_red_flags_summary: List[str] = Field(default_factory=list)
    comparison_highlights: List[str] = Field(default_factory=list)
    key_research_takeaways: List[str] = Field(default_factory=list)
    narrative: str = Field(default="")


class MetricValueItem(BaseModel):
    """Single metric value for a specific company and period with strict missing distinction."""

    company_name: str
    fiscal_period: str
    raw_value: Optional[float] = None
    formatted_value: str = "N/A"
    available: bool = False
    unit: str = "USD"
    scale: str = "millions"
    document_id: Optional[str] = None
    source_page: Optional[int] = None
    chunk_id: Optional[str] = None


class CompanyMetricRow(BaseModel):
    """Row in Key Financials table representing a canonical metric across companies/periods."""

    metric_key: str
    display_name: str
    category: str
    order_index: int
    values: List[MetricValueItem] = Field(default_factory=list)


class KeyFinancialsSection(BaseModel):
    """Section 2: Key Financials table populated strictly from extracted_metrics."""

    companies: List[str] = Field(default_factory=list)
    reporting_periods: List[str] = Field(default_factory=list)
    metrics: List[CompanyMetricRow] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)


class RedFlagFinding(BaseModel):
    """Forensic red flag item populated strictly from persisted Red Flag Agent output."""

    finding_id: str
    company_name: str
    title: str
    severity: str  # HIGH, MEDIUM, LOW, CRITICAL
    category: str
    metric_name: Optional[str] = None
    current_value: Optional[str] = None
    prior_value: Optional[str] = None
    change_description: Optional[str] = None
    description: str
    evidence: str
    recommendation: Optional[str] = None
    source_page: Optional[int] = None
    section: Optional[str] = None
    document_id: Optional[str] = None


class RedFlagsSection(BaseModel):
    """Section 3: Red Flags section with exact persisted risk score."""

    total_flags: int = 0
    high_severity_count: int = 0
    composite_risk_score: float = 0.0
    overall_assessment: str = ""
    findings: List[RedFlagFinding] = Field(default_factory=list)
    is_empty_state: bool = False
    empty_state_message: str = "No material red flags were identified in the available analysis."


class ComparisonMetricItem(BaseModel):
    """A metric compared across peer companies populated from comparison_results."""

    metric_name: str
    display_name: str
    fiscal_period: str
    unit: str = "USD"
    peer_average: Optional[float] = None
    highest_company: Optional[str] = None
    highest_value: Optional[float] = None
    lowest_company: Optional[str] = None
    lowest_value: Optional[float] = None
    company_values: Dict[str, Optional[float]] = Field(default_factory=dict)
    percentile_ranks: Dict[str, Optional[float]] = Field(default_factory=dict)


class CompanyComparisonSection(BaseModel):
    """Section 4: Company Comparison populated strictly from comparison_results."""

    is_available: bool = True
    unavailable_reason: Optional[str] = None
    compared_companies: List[str] = Field(default_factory=list)
    fiscal_periods: List[str] = Field(default_factory=list)
    metrics: List[ComparisonMetricItem] = Field(default_factory=list)
    chart_image_bytes: Optional[bytes] = None
    chart_description: Optional[str] = None


class OutlookFinding(BaseModel):
    """Grounded observation or finding relevant to corporate outlook from research messages."""

    topic: str
    observation: str
    source_query: Optional[str] = None
    confidence_score: Optional[float] = None
    company_name: Optional[str] = None


class OutlookSection(BaseModel):
    """Section 5: Outlook populated strictly from persisted research findings (zero predictions)."""

    findings: List[OutlookFinding] = Field(default_factory=list)
    is_empty_state: bool = False
    empty_state_message: str = "No outlook information was available in the analyzed session."


class ReportDocument(BaseModel):
    """
    Authoritative, typed internal representation of the completed report.
    This model decouples data compilation from PDF rendering.
    """

    metadata: ReportMetadata
    executive_summary: ExecutiveSummarySection
    key_financials: KeyFinancialsSection
    red_flags: RedFlagsSection
    comparison: CompanyComparisonSection
    outlook: OutlookSection
    object_key: str = Field(default="")
    download_url: Optional[str] = None
    status: str = Field(default="COMPLETED")
    pdf_size_bytes: int = Field(default=0)
    pdf_sha256: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        """Convert to MongoDB document for the authoritative 'reports' collection."""
        doc = self.model_dump(exclude={"comparison": {"chart_image_bytes"}})
        # Ensure root-level fields for indexing, querying, and user/session isolation
        doc["report_id"] = self.metadata.report_id
        doc["session_id"] = self.metadata.session_id
        doc["user_id"] = self.metadata.user_id
        doc["report_version"] = self.metadata.report_version
        doc["document_ids"] = self.metadata.document_ids
        doc["companies"] = self.metadata.companies
        doc["sections"] = [
            "executive_summary",
            "key_financials",
            "red_flags",
            "comparison",
            "outlook",
        ]
        return doc


class ReportGenerateRequest(BaseModel):
    """API request payload for generating a report."""

    report_title: Optional[str] = "Financial Research & Institutional Audit Report"
    report_version: Optional[str] = "v1.0"
    async_mode: bool = False


class ReportGenerateResponse(BaseModel):
    """API response payload for report generation."""

    report_id: str
    session_id: str
    status: str
    report_title: str
    download_url: Optional[str] = None
    object_key: Optional[str] = None
    pdf_size_bytes: int = 0
    pdf_sha256: Optional[str] = None
    sections_included: List[str] = Field(default_factory=list)
    generated_at: str
