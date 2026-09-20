"""
Pydantic schemas for the Comparison Agent (Phase 2C — Multi-Company Peer Comparison).

Defines structured input/output contracts, chart-ready output models,
peer statistics structures, and MongoDB persistence models for the
comparison_results collection.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =====================================================================
# Metric directionality for best/worst determination
# =====================================================================

# True  = higher value is conventionally "better" (revenue, margin)
# False = lower value is conventionally "better" (debt, expense ratios)
# None  = no directional assumption — report both highest and lowest
METRIC_DIRECTIONALITY: Dict[str, Optional[bool]] = {
    "revenue": True,
    "net_income": True,
    "gross_margin": True,
    "operating_margin": True,
    "operating_income": True,
    "operating_cash_flow": True,
    "eps": True,
    "yoy_revenue_change": True,
    "total_debt": False,
    "debt_to_equity": False,
    "total_equity": True,
}


# =====================================================================
# Input validation
# =====================================================================

class ComparisonRequest(BaseModel):
    """Input payload for the Comparison Agent."""

    session_id: str = Field(..., description="Research session ID")
    document_ids: List[str] = Field(
        ...,
        min_length=2,
        description="List of document IDs to compare (minimum 2)",
    )
    async_mode: bool = Field(
        default=True,
        description="Execute asynchronously via Celery job queue",
    )


# =====================================================================
# Company identity
# =====================================================================

class CompanyInfo(BaseModel):
    """Identity of a company within the comparison."""

    document_id: str = Field(..., description="Source document ID from extracted_metrics")
    company_name: str = Field(..., description="Company or document name")
    filing_type: Optional[str] = Field(None, description="Filing type (e.g. US 10-K)")
    reporting_currency: Optional[str] = Field(None, description="Reporting currency")
    reporting_scale: Optional[str] = Field(None, description="Reporting scale (millions, crores)")


# =====================================================================
# Individual metric value
# =====================================================================

class MetricValue(BaseModel):
    """A single metric value for one company in one fiscal period."""

    document_id: str
    company_name: str
    fiscal_period: str
    value: Optional[float] = Field(None, description="Numeric value, or None if unavailable")
    available: bool = Field(True, description="Whether valid data exists for this metric")
    unit: Optional[str] = Field(None, description="Metric unit (e.g. Millions, %, Ratio)")
    currency: Optional[str] = Field(None, description="Currency code (e.g. USD, INR)")
    provenance: Optional[Dict[str, Any]] = Field(
        None,
        description="Source evidence when available from extracted_metrics",
    )
    raw_value: Optional[float] = Field(None, description="Raw unnormalized value from source filing")
    source_unit: Optional[str] = Field(None, description="Source unit before normalization")
    source_scale: Optional[str] = Field(None, description="Source scale before normalization (thousands, millions)")
    normalized_value: Optional[float] = Field(None, description="Normalized value in canonical USD Millions / INR Crores")
    normalized_unit: Optional[str] = Field(None, description="Canonical normalized unit")


# =====================================================================
# Peer statistics for a single metric in a single period
# =====================================================================

class PercentileEntry(BaseModel):
    """Percentile rank for a single company on a single metric."""

    document_id: str
    company_name: str
    percentile: Optional[float] = Field(
        None,
        description="Percentile rank [0.0–1.0] or None if insufficient data",
    )


class PeerStatistics(BaseModel):
    """Peer-relative statistics for a metric in a given fiscal period. Only populated when valid_count >= 2."""

    valid_count: int = Field(0, description="Number of companies with valid values")
    peer_average: Optional[float] = Field(None, description="Mean of valid values (strictly None if valid_count < 2)")
    highest: Optional[Dict[str, Any]] = Field(
        None,
        description="{'document_id': str, 'company_name': str, 'value': float} (strictly None if valid_count < 2)",
    )
    lowest: Optional[Dict[str, Any]] = Field(
        None,
        description="{'document_id': str, 'company_name': str, 'value': float} (strictly None if valid_count < 2)",
    )
    percentile_ranks: List[PercentileEntry] = Field(
        default_factory=list,
        description="Percentile rank per company (only populated when valid_count >= 2; None when valid_count < 2)",
    )


# =====================================================================
# Comparison metric (one metric across all companies and periods)
# =====================================================================

class ComparisonMetricPeriod(BaseModel):
    """One metric for one fiscal period across all compared companies."""

    fiscal_period: str
    values: List[MetricValue] = Field(default_factory=list)
    peer_statistics: PeerStatistics = Field(default_factory=PeerStatistics)
    unit_compatible: bool = Field(
        True,
        description="Whether all companies share compatible units for this period",
    )
    unit_mismatch_detail: Optional[str] = Field(
        None,
        description="Explanation when units are incompatible",
    )


class ComparisonMetric(BaseModel):
    """A single metric compared across all companies and fiscal periods."""

    metric_name: str
    display_name: Optional[str] = None
    periods: List[ComparisonMetricPeriod] = Field(default_factory=list)


# =====================================================================
# Chart-ready comparison output
# =====================================================================

class ComparisonOutput(BaseModel):
    """Chart-ready multi-company comparison output."""

    session_id: str
    companies: List[CompanyInfo] = Field(default_factory=list)
    fiscal_periods: List[str] = Field(
        default_factory=list,
        description="All aligned fiscal periods across companies (sorted chronologically)",
    )
    common_periods: List[str] = Field(
        default_factory=list,
        description="Periods represented by >= 2 participating companies",
    )
    company_only_periods: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Periods represented only by 1 company: {company_name: [periods]}",
    )
    has_common_periods: bool = Field(
        True,
        description="Whether any common fiscal reporting period exists across participating companies",
    )
    comparison_note: Optional[str] = Field(
        None,
        description="Contextual note (e.g. when no common periods exist)",
    )
    summary_insights: List[str] = Field(
        default_factory=list,
        description="Deterministic summary takeaways from the comparison",
    )
    metrics: List[ComparisonMetric] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =====================================================================
# MongoDB persistence model for comparison_results collection
# =====================================================================

class ComparisonResultDocument(BaseModel):
    """
    MongoDB document model stored in the 'comparison_results' collection.

    Cache identity is determined by (session_id, document_ids_hash).
    Stale-data detection uses data_version (max updated_at from extracted_metrics).
    """

    session_id: str
    user_id: str
    document_ids: List[str] = Field(
        ..., description="Sorted list of document IDs in this comparison"
    )
    document_ids_hash: str = Field(
        ..., description="Deterministic SHA-256 hash of sorted document_ids"
    )
    data_version: str = Field(
        ...,
        description="ISO timestamp of the latest extracted_metrics.updated_at used",
    )
    comparison: ComparisonOutput = Field(
        ..., description="Chart-ready comparison result"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def compute_document_ids_hash(document_ids: List[str]) -> str:
        """Compute a deterministic hash from sorted document IDs."""
        canonical = "|".join(sorted(document_ids))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
