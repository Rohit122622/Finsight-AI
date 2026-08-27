"""
CrewAI and FinSentry Agent Tools Foundation (Phase 2C).

Provides modular, reusable tools for agent orchestration and autonomous workflows.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.embedding_service import embedding_service
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


class FinSentryTool(BaseModel):
    """Base class for FinSentry agent tools."""

    name: str
    description: str

    def run(self, **kwargs: Any) -> Any:
        """Execute the tool."""
        raise NotImplementedError("Tool must implement run()")


class DocumentSearchTool(FinSentryTool):
    """Tool to perform semantic search across session document chunks."""

    name: str = "document_search_tool"
    description: str = "Semantically search parsed corporate filings and financial document chunks for a session."

    def run(self, query: str, session_id: str, user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        logger.info("Executing DocumentSearchTool: query='%s', session_id='%s'", query, session_id)
        return embedding_service.search_session_chunks_sync(
            query=query,
            session_id=session_id,
            user_id=user_id,
            top_k=top_k,
        )


class MetricExtractionTool(FinSentryTool):
    """Tool to extract financial KPIs and balance sheet figures from context."""

    name: str = "metric_extraction_tool"
    description: str = "Extract key financial metrics, ratios, and values from textual contexts."

    def run(self, text_context: str, target_metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        logger.info("Executing MetricExtractionTool on %d chars of context", len(text_context))
        prompt = (
            f"Context:\n{text_context}\n\n"
            f"Extract target metrics: {target_metrics or 'all major financial metrics'}.\n"
            "Return JSON mapping metric name to value, unit, and period."
        )
        return llm_service.generate_structured(
            prompt=prompt,
            output_schema=dict,
            system_prompt="You are a financial data extraction engine.",
        )


class FinancialLookupTool(FinSentryTool):
    """Tool for looking up standardized financial term definitions and accounting criteria."""

    name: str = "financial_lookup_tool"
    description: str = "Lookup accounting standards, US GAAP, and IFRS reporting guidelines."

    def run(self, term: str) -> Dict[str, Any]:
        return {
            "term": term,
            "standard": "US GAAP / IFRS",
            "summary": f"Standardized financial metrics and compliance rules for '{term}'.",
        }


                     
document_search_tool = DocumentSearchTool()
metric_extraction_tool = MetricExtractionTool()
financial_lookup_tool = FinancialLookupTool()
