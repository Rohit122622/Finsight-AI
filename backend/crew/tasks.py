"""
CrewAI and FinSentry Task Definitions (Phase 2C).

Encapsulates discrete units of analytical work assigned to specialized agents.
"""

from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from schemas.agent_results import (
    ComparisonResult,
    DocumentResult,
    ExtractionResult,
    RedFlagResult,
    ReportResult,
    ResearchResult,
)


class FinSentryTask(BaseModel):
    """
    Standard task representation for FinSentry agent workflows.
    """

    description: str = Field(..., description="Clear instructions of what needs to be accomplished")
    expected_output: str = Field(..., description="Clear description of the expected output format")
    agent_name: str = Field(..., description="Name of the agent responsible for executing this task")
    output_schema: Optional[Type[BaseModel]] = Field(
        default=None, description="Pydantic schema used to validate task output"
    )
    tools: List[str] = Field(default_factory=list, description="Tool names available to this task")
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters and context")


def create_document_task(session_id: str, document_id: str) -> FinSentryTask:
    return FinSentryTask(
        description=f"Parse, extract, clean, and chunk document '{document_id}' in session '{session_id}'.",
        expected_output="DocumentResult with word count, chunk count, and metadata.",
        agent_name="DocumentAgent",
        output_schema=DocumentResult,
        tools=["document_search_tool"],
        context={"session_id": session_id, "document_id": document_id},
    )


def create_extraction_task(session_id: str, document_id: Optional[str] = None) -> FinSentryTask:
    return FinSentryTask(
        description=f"Extract key quantitative financial metrics and accounting figures from session '{session_id}'.",
        expected_output="ExtractionResult containing list of extracted financial metrics and confidence scores.",
        agent_name="ExtractionAgent",
        output_schema=ExtractionResult,
        tools=["metric_extraction_tool", "document_search_tool"],
        context={"session_id": session_id, "document_id": document_id},
    )


def create_red_flag_task(session_id: str, risk_focus: Optional[str] = None) -> FinSentryTask:
    return FinSentryTask(
        description=f"Perform forensic risk and anomaly analysis on session '{session_id}' focusing on '{risk_focus or 'all anomalies'}'.",
        expected_output="RedFlagResult containing identified risks, severity scores, and recommendations.",
        agent_name="RedFlagAgent",
        output_schema=RedFlagResult,
        tools=["document_search_tool", "financial_lookup_tool"],
        context={"session_id": session_id, "risk_focus": risk_focus},
    )


def create_comparison_task(session_id: str, baseline: str, comparison: str) -> FinSentryTask:
    return FinSentryTask(
        description=f"Compare financial performance and operational metrics of '{baseline}' vs '{comparison}' in session '{session_id}'.",
        expected_output="ComparisonResult containing metric variances, trends, and executive summary.",
        agent_name="ComparisonAgent",
        output_schema=ComparisonResult,
        tools=["document_search_tool", "metric_extraction_tool"],
        context={"session_id": session_id, "baseline_entity": baseline, "comparison_entity": comparison},
    )


def create_research_task(session_id: str, query: str) -> FinSentryTask:
    return FinSentryTask(
        description=f"Synthesize comprehensive research answering query '{query}' in session '{session_id}'.",
        expected_output="ResearchResult containing answer, sources, and confidence score.",
        agent_name="ResearchAgent",
        output_schema=ResearchResult,
        tools=["document_search_tool"],
        context={"session_id": session_id, "query": query},
    )


def create_report_task(session_id: str, report_title: str) -> FinSentryTask:
    return FinSentryTask(
        description=f"Generate professional analytical research report '{report_title}' for session '{session_id}'.",
        expected_output="ReportResult containing structured report sections and recommendations.",
        agent_name="ReportAgent",
        output_schema=ReportResult,
        tools=["document_search_tool", "financial_lookup_tool"],
        context={"session_id": session_id, "report_title": report_title},
    )
