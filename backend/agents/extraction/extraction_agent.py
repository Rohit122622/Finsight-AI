"""
Financial Data Extraction Agent for FinSentry AI (Phase 2C).

Extracts structured financial KPIs, metrics, revenues, and risk factors
from session documents into validated JSON format.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from services.embedding_service import embedding_service
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ExtractionAgent(BaseAgent):
    """
    Agent specializing in structured tabular and financial metric extraction.
    """

    def __init__(self, name: str = "ExtractionAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.EXTRACTION)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Extract structured financial metrics from session documents.

        Payload:
            session_id: str (required)
            document_id: str (optional)
            target_fields: List[str] (optional target attributes)

        Context:
            user_id: str (required)
            job_id: str (optional)
        """
        session_id = payload.get("session_id")
        document_id = payload.get("document_id")
        target_fields = payload.get(
            "target_fields",
            [
                "revenue", "prior_revenue", "total_debt", "prior_total_debt",
                "gross_margin", "prior_gross_margin", "operating_margin",
                "operating_cash_flow", "net_income", "total_equity", "risks"
            ],
        )
        user_id = (context or {}).get("user_id") or payload.get("user_id")

        if not session_id or not user_id:
            raise NonRetryableAgentException("Missing required parameters: 'session_id' and 'user_id'.")

        logger.info(
            "ExtractionAgent running for session %s (document: %s)",
            session_id,
            document_id or "all",
        )

        try:

            doc_filter = [document_id] if document_id else None
            chunks = embedding_service.search_session_chunks_sync(
                user_id=user_id,
                session_id=session_id,
                query="revenue net sales gross profit margin total debt borrowings operating cash flow net income balance sheet",
                top_k=8,
                document_ids=doc_filter,
            )

            context_text = "\n\n".join([f"Source [{c['document_filename']}]:\n{c['text']}" for c in chunks])
            if not context_text:
                context_text = "No processed document text available."

            prompt = (
                f"Extract structured quantitative financial figures and qualitative disclosures for: {target_fields}\n\n"
                f"Document Context:\n{context_text}\n\n"
                "Return a JSON dictionary mapping standard metric names (e.g. 'total_debt', 'prior_total_debt', "
                "'gross_margin', 'prior_gross_margin', 'operating_cash_flow', 'net_income', 'revenue', 'prior_revenue') "
                "to their verified values (as numbers or percentages), and include a 'source_snippets' mapping. "
                "If a metric is not mentioned in the context, do NOT invent it or set it to 0; simply omit it or set it to null."
            )

            structured_result = llm_service.generate_structured(
                prompt=prompt,
                system_prompt="You are an expert financial data extraction system. Output strictly valid JSON without markdown wrapping.",
            )


            try:
                from database.connection import get_sync_db
                from datetime import datetime, timezone
                if isinstance(structured_result, dict):
                    db_sync = get_sync_db()
                    for k, v in structured_result.items():
                        if k != "source_snippets" and v is not None:
                            db_sync.extracted_metrics.update_one(
                                {"session_id": session_id, "metric_name": k},
                                {
                                    "$set": {
                                        "document_id": document_id,
                                        "session_id": session_id,
                                        "user_id": user_id,
                                        "metric_name": k,
                                        "value": v,
                                        "updated_at": datetime.now(timezone.utc),
                                    }
                                },
                                upsert=True,
                            )
            except Exception as db_err:
                logger.debug("ExtractionAgent metric persistence notice: %s", db_err)

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary={
                    "session_id": session_id,
                    "document_id": document_id,
                    "target_fields": target_fields,
                    "extracted_data": structured_result,
                    "extracted_metrics": structured_result if isinstance(structured_result, dict) else {},
                    "chunks_analyzed": len(chunks),
                },
                result_ref=session_id,
                metadata={"document_id": document_id},
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("ExtractionAgent error: %s", exc)
            raise RetryableAgentException(f"Transient error during metric extraction: {exc}")



extraction_agent = ExtractionAgent()
agent_registry.register(extraction_agent, overwrite=True)
