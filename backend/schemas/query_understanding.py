"""
FinSentry AI — Phase 3B Query Understanding Result Contract.

Strongly typed Pydantic schemas for the Query Understanding layer:
- Deterministic query classification (FACTUAL, FINANCIAL_METRIC, COMPARISON, etc.)
- Multi-step question detection
- Query expansion / reformulation without fact invention
- Follow-up question detection
- Conversational context detection
- Financial and temporal signal extraction
- Structured output representation consumed by Phase 3A Retrieval and Research Agent
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


                                                                       

class QueryClassification(str, Enum):
    """Primary intent categories for financial research queries."""

    FACTUAL = "FACTUAL"
    COMPARISON = "COMPARISON"
    TREND = "TREND"
    CAUSAL = "CAUSAL"
    RISK = "RISK"
    FINANCIAL_METRIC = "FINANCIAL_METRIC"
    DOCUMENT_LOOKUP = "DOCUMENT_LOOKUP"
    DEFINITION = "DEFINITION"
    SUMMARY = "SUMMARY"
    MULTI_STEP = "MULTI_STEP"
    FOLLOW_UP = "FOLLOW_UP"
    UNKNOWN = "UNKNOWN"


                                                                       

class QueryContextType(str, Enum):
    """Type of conversational context required to interpret the query."""

    NONE = "NONE"
    PREVIOUS_QUERY = "PREVIOUS_QUERY"
    PREVIOUS_ANSWER = "PREVIOUS_ANSWER"
    SESSION_CONTEXT = "SESSION_CONTEXT"
    MULTI_TURN = "MULTI_TURN"


                                                                       

class FinancialSignal(BaseModel):
    """Extracted financial entities, KPIs, currencies, and metric signals."""

    metrics: List[str] = Field(
        default_factory=list,
        description="Identified financial metrics/KPIs (e.g., revenue, EBITDA, net_income)",
    )
    currencies: List[str] = Field(
        default_factory=list,
        description="Extracted currency values and symbols (e.g., $12.4 billion, €50M)",
    )
    percentages: List[str] = Field(
        default_factory=list,
        description="Extracted percentage and basis point expressions (e.g., 15%, 450 bps)",
    )
    comparison_indicators: List[str] = Field(
        default_factory=list,
        description="Words or phrases indicating comparative analysis (e.g., compare, versus, higher than)",
    )
    raw_values: List[str] = Field(
        default_factory=list,
        description="Raw financial and numeric tokens extracted from query",
    )


                                                                       

class TemporalSignal(BaseModel):
    """Extracted temporal parameters, periods, and time-series indicators."""

    years: List[int] = Field(
        default_factory=list,
        description="Identified calendar/fiscal year numbers (e.g., 2023, 2024)",
    )
    fiscal_years: List[str] = Field(
        default_factory=list,
        description="Identified fiscal year expressions (e.g., FY2024, FY24)",
    )
    quarters: List[str] = Field(
        default_factory=list,
        description="Identified fiscal/calendar quarters (e.g., Q1 2024, Q4)",
    )
    date_ranges: List[str] = Field(
        default_factory=list,
        description="Identified multi-period ranges (e.g., from 2023 to 2024, last 3 years)",
    )
    raw_temporal_terms: List[str] = Field(
        default_factory=list,
        description="Raw temporal tokens and keywords",
    )


                                                                       

class QueryUnderstandingResult(BaseModel):
    """
    Complete structured representation of query intent and retrieval parameters.

    Produced by the Query Understanding service and consumed by Phase 3A Retrieval.
    Does NOT answer the financial question.
    """

    original_query: str = Field(..., min_length=1, description="Raw input query as submitted by user")
    normalized_query: str = Field(..., min_length=1, description="Cleaned and normalized query string")
    classification: QueryClassification = Field(..., description="Primary detected query intent")
    secondary_classifications: List[QueryClassification] = Field(
        default_factory=list,
        description="Additional secondary classifications if applicable",
    )
    is_multi_step: bool = Field(
        default=False,
        description="Whether query requires multi-phase retrieval or multiple distinct reasoning steps",
    )
    is_follow_up: bool = Field(
        default=False,
        description="Whether query refers to or depends on previous conversational context",
    )
    requires_context: bool = Field(
        default=False,
        description="Whether full conversation history is required to resolve ambiguity",
    )
    context_type: QueryContextType = Field(
        default=QueryContextType.NONE,
        description="Type of conversational dependency detected",
    )
    expanded_queries: List[str] = Field(
        default_factory=list,
        description="Deterministic query reformulations with domain synonyms (no facts invented)",
    )
    sub_queries: List[str] = Field(
        default_factory=list,
        description="Decomposed sub-questions for multi-part queries",
    )
    financial_signals: FinancialSignal = Field(
        default_factory=FinancialSignal,
        description="Extracted financial metrics, currencies, and figures",
    )
    temporal_signals: TemporalSignal = Field(
        default_factory=TemporalSignal,
        description="Extracted temporal periods, years, and quarters",
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Extracted company or entity names referenced in the query (e.g., Apple, Microsoft)",
    )
    retrieval_hints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operational hints for retrieval service (e.g., suggested section, target filters)",
    )

    @field_validator("original_query", "normalized_query")
    @classmethod
    def validate_non_empty_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query string cannot be empty")
        return v.strip()


                                                                       

class QueryUnderstandingRequest(BaseModel):
    """Request payload for standalone query analysis."""

    query: str = Field(..., min_length=1, description="User's natural language question")
    conversation_history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional recent conversation turns for context resolution",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional research session ID for session-scoped context",
    )
