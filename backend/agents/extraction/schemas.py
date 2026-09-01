"""
Pydantic schemas and validation models for ExtractionAgent (Phase 2C / Master Plan).

Defines structured input/output contracts, LLM extraction schemas,
multi-year financial metric structures, and database persistence models.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from schemas.agent_results import ExtractionMetricItem, ExtractionResult


class RawLLMMetricItem(BaseModel):
    """Schema for individual metric extracted by the LLM."""

    metric_name: str = Field(..., description="Standard metric key, e.g. revenue, net_income, gross_margin, debt_to_equity, eps, operating_cash_flow, total_debt, total_equity")
    display_name: Optional[str] = Field(None, description="Human-readable title, e.g. Revenue / Total Net Sales")
    value: Optional[float] = Field(None, description="Current period numeric value, or null if not found")
    prior_value: Optional[float] = Field(None, description="Prior period numeric value, or null if not found")
    unit: Optional[str] = Field(None, description="Unit, e.g. Millions, Thousands, Crores, %, Ratio, USD, INR")
    currency: Optional[str] = Field(None, description="Currency symbol or ISO code, e.g. USD, $, INR, ₹")
    period: Optional[str] = Field(None, description="Current reporting period or fiscal year, e.g. FY2024, FY2022")
    prior_period: Optional[str] = Field(None, description="Prior reporting period or fiscal year, e.g. FY2023, FY2021")
    yoy_change_percent: Optional[float] = Field(None, description="Reported or derived YoY percentage change")
    source_chunk_ids: List[str] = Field(default_factory=list, description="Exact chunk IDs cited as source")
    page_numbers: List[int] = Field(default_factory=list, description="Page numbers where evidence appears")
    evidence_snippet: Optional[str] = Field(None, description="Exact text or table row quote from the source chunk")
    derivation_formula: Optional[str] = Field(None, description="Formula if mathematically derived, e.g. total_debt / total_equity")


class RawLLMExtractionResponse(BaseModel):
    """Schema for full structured JSON extraction returned by LLM."""

    filing_type: Optional[str] = Field("US 10-K", description="Detected filing type (US 10-K, Indian Annual Report / Ind AS, Standalone / Consolidated Financial Statements)")
    reporting_currency: Optional[str] = Field("USD", description="Dominant reporting currency (USD, INR, EUR, etc.)")
    reporting_scale: Optional[str] = Field("millions", description="Scale of financial figures (millions, thousands, crores, lakhs, units)")
    reporting_period: Optional[str] = Field(None, description="Latest fiscal period covered, e.g. FY2024 or FY2022")
    prior_period: Optional[str] = Field(None, description="Prior comparative period, e.g. FY2023 or FY2021")
    metrics: List[RawLLMMetricItem] = Field(default_factory=list, description="List of extracted quantitative metrics")
    multi_year_table: Dict[str, Dict[str, Optional[float]]] = Field(default_factory=dict, description="Fiscal year breakdown: {FY2022: {revenue: 5345.0, ...}}")


class ExtractionAgentPayload(BaseModel):
    """Input payload validation for ExtractionAgent."""

    session_id: str = Field(..., description="Target session ID")
    document_id: Optional[str] = Field(None, description="Target document ID")
    user_id: Optional[str] = Field(None, description="User ID for multi-tenant isolation")
    target_fields: List[str] = Field(
        default_factory=lambda: [
            "revenue",
            "net_income",
            "gross_margin",
            "debt_to_equity",
            "eps",
            "yoy_revenue_change",
            "prior_revenue",
            "prior_net_income",
            "prior_gross_margin",
            "operating_cash_flow",
            "total_debt",
            "prior_total_debt",
            "total_equity",
            "prior_total_equity",
            "operating_margin",
            "prior_operating_margin",
            "prior_eps",
        ],
        description="List of target metric names to extract",
    )


class ExtractedMetricsDocument(BaseModel):
    """Consolidated MongoDB document model stored in 'extracted_metrics' collection (one per document)."""

    document_id: str
    session_id: str
    user_id: Optional[str] = None
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
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    provenance_map: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    chunks_analyzed: int = 0
    financial_chunks_count: int = 0
    retry_attempted: bool = False
    retry_success: Optional[bool] = None
    confidence_average: float = 1.0
    low_confidence_count: int = 0
    failed_metrics_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
