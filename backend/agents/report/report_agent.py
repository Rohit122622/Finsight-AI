"""
Report Generation Agent for FinSentry AI (Phase 2C).

Compiles synthesis, risk assessment, metric extraction, and comparison insights
into comprehensive, professional investment and audit reports.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from schemas.agent_results import ReportResult, ReportSection
from services.embedding_service import embedding_service
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """
    Agent responsible for synthesizing findings into comprehensive investment research reports.
    """

    def __init__(self, name: str = "ReportAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.REPORT_GENERATION)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute report compilation.

        Payload:
            session_id: str (required)
            report_title: str (optional)
            include_risks: bool (optional)
        """
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        title = payload.get("report_title", "Financial Research & Due Diligence Report")

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id' and 'user_id' must be provided."
            )

        logger.info("ReportAgent compiling report '%s' for session %s", title, session_id)

        try:
            chunks = embedding_service.search_session_chunks_sync(
                query="business overview, financial results, management guidance, key risks, balance sheet strength",
                session_id=session_id,
                user_id=user_id,
                top_k=5,
            )

            context_text = "\n\n".join([f"Source {i+1}: {c['text']}" for i, c in enumerate(chunks)])

            system_prompt = (
                "You are a Senior Investment Banking Analyst. Generate a detailed institutional research report."
            )
            prompt = (
                f"Document context:\n{context_text}\n\n"
                f"Report Title: {title}\n"
                "Return a JSON structured object with 'report_title', 'executive_summary', "
                "'sections' (list of {title, content, key_findings}), and 'recommendations' (list of strings)."
            )

            llm_out = llm_service.generate_structured(
                prompt=prompt,
                output_schema=ReportResult,
                system_prompt=system_prompt,
            )

            report_res = ReportResult(
                agent_name=self.name,
                session_id=session_id,
                report_title=title,
                executive_summary=llm_out.get("executive_summary", "Comprehensive financial overview synthesized from corporate filings."),
                sections=[
                    ReportSection(**s) if isinstance(s, dict) else s
                    for s in llm_out.get("sections", [
                        {"title": "Financial Highlights", "content": "Analysis of key metrics and operations.", "key_findings": ["Steady revenue baseline."]}
                    ])
                ],
                recommendations=llm_out.get("recommendations", ["Maintain standard monitoring of quarterly disclosures."]),
            )

            import uuid
            from datetime import datetime, timezone
            from database.connection import get_sync_db
            from models.report import AnalysisReportModel, ReportSectionModel

            report_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            section_models = [
                ReportSectionModel(
                    title=s.title,
                    content=s.content,
                    key_findings=s.key_findings,
                )
                for s in report_res.sections
            ]

            report_model = AnalysisReportModel(
                report_id=report_id,
                session_id=session_id,
                user_id=user_id,
                report_title=title,
                executive_summary=report_res.executive_summary,
                risk_score=float(payload.get("risk_score", 15.0)),
                sections=section_models,
                extracted_metrics=payload.get("extracted_metrics", []),
                red_flags=payload.get("red_flags", []),
                recommendations=report_res.recommendations,
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            )

            try:
                db = get_sync_db()
                db.analysis_reports.insert_one(report_model.to_dict())
                logger.info("ReportAgent persisted report %s for session %s", report_id, session_id)
            except Exception as db_exc:
                logger.warning("Could not persist report to MongoDB (running in test/offline mode?): %s", db_exc)

            summary_data = report_res.model_dump()
            summary_data["report_id"] = report_id
            summary_data["sections_count"] = len(report_res.sections)

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=summary_data,
                result_ref=report_id,
                metadata={
                    "report_id": report_id,
                    "report_title": title,
                    "sections_count": len(report_res.sections),
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("Error in ReportAgent: %s", exc)
            raise RetryableAgentException(f"ReportAgent transient failure: {exc}")


report_agent = ReportAgent()
agent_registry.register(report_agent, overwrite=True)
