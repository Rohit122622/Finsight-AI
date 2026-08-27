"""
Pydantic API schemas for Live Financial Analysis and Reporting (Phase 2G).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """Payload to trigger live multi-agent financial analysis."""

    query: Optional[str] = Field(
        None, description="Custom investigative query or focus area for research"
    )
    focus_areas: List[str] = Field(
        default_factory=list,
        description="Key analytical dimensions (e.g. ['accounting', 'solvency', 'governance', 'guidance'])",
    )
    report_title: Optional[str] = Field(
        "Comprehensive Financial Analysis Report",
        description="Custom title for the generated investment/audit report",
    )
    baseline_entity: Optional[str] = Field(
        "Current Reporting Period", description="Baseline period or entity for comparison"
    )
    comparison_entity: Optional[str] = Field(
        "Prior Reporting Period", description="Benchmark period or entity for comparison"
    )
    async_mode: bool = Field(
        default=True,
        description="Execute asynchronously via Celery job queue (True) or wait for synchronous completion (False)",
    )


class RedFlagItemResponse(BaseModel):
    """Schema for individual forensic red flag or risk anomaly."""

    severity: str = Field("MEDIUM", description="Severity level: LOW, MEDIUM, HIGH, CRITICAL")
    category: str = Field(..., description="Risk category: Accounting, Governance, Solvency, Disclosure, Legal")
    title: str
    description: str
    evidence_snippet: Optional[str] = None
    recommendation: Optional[str] = None


class ReportSectionResponse(BaseModel):
    """Schema for structured section within a financial report."""

    title: str
    content: str
    key_findings: List[str] = Field(default_factory=list)


class AnalysisReportResponse(BaseModel):
    """Schema for complete generated financial analysis report."""

    report_id: str
    session_id: str
    user_id: str
    report_title: str
    executive_summary: str
    risk_score: float = 0.0
    sections: List[ReportSectionResponse] = Field(default_factory=list)
    extracted_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    red_flags: List[RedFlagItemResponse] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    status: str = "COMPLETED"
    created_at: datetime
    updated_at: datetime


class AnalysisReportListResponse(BaseModel):
    """Paginated list of analysis reports for a research session."""

    reports: List[AnalysisReportResponse]
    total: int
    skip: int
    limit: int


class LiveProgressResponse(BaseModel):
    """Real-time progress representation of an active live analysis job."""

    job_id: str
    session_id: Optional[str] = None
    task_type: Optional[str] = None
    agent_name: Optional[str] = None
    status: str
    progress_percent: int = 0
    current_step: Optional[str] = None
    message: Optional[str] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
    result_ref: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
