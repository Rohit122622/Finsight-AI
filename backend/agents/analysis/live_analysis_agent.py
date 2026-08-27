"""
Live Analysis Agent for FinSentry AI (Phase 2G - Live Processing).

Coordinates the multi-agent analysis pipeline during background Celery execution,
updating progress milestones in real-time and generating persistent institutional reports.
"""

import logging
from typing import Any, Dict, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from services.live_analysis_service import live_analysis_service

logger = logging.getLogger(__name__)


class LiveAnalysisAgent(BaseAgent):
    """
    Agent responsible for executing live multi-agent analysis workflows in worker tasks.
    """

    def __init__(self, name: str = "LiveAnalysisAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.DOCUMENT_ANALYSIS)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute live analysis pipeline.

        Payload:
            session_id: str (required)
            query: str (optional)
            focus_areas: List[str] (optional)
            report_title: str (optional)
            baseline_entity: str (optional)
            comparison_entity: str (optional)

        Context:
            user_id: str (required)
            job_id: str (optional)
        """
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        job_id = (context or {}).get("job_id") or payload.get("job_id")

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id' and 'user_id' must be provided."
            )

        logger.info(
            "LiveAnalysisAgent executing for session %s (job: %s)",
            session_id,
            job_id or "sync",
        )

        try:
            report = live_analysis_service.run_live_analysis_sync(
                session_id=session_id,
                user_id=user_id,
                query=payload.get("query"),
                focus_areas=payload.get("focus_areas"),
                report_title=payload.get("report_title"),
                baseline_entity=payload.get("baseline_entity"),
                comparison_entity=payload.get("comparison_entity"),
                job_id=job_id,
            )

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary={
                    "report_id": report.report_id,
                    "session_id": session_id,
                    "report_title": report.report_title,
                    "risk_score": report.risk_score,
                    "sections_count": len(report.sections),
                    "red_flags_count": len(report.red_flags),
                    "executive_summary": report.executive_summary,
                },
                result_ref=report.report_id,
                metadata={
                    "report_id": report.report_id,
                    "risk_score": report.risk_score,
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("Error in LiveAnalysisAgent: %s", exc)
            raise RetryableAgentException(f"Live analysis pipeline transient error: {exc}")



live_analysis_agent = LiveAnalysisAgent("LiveAnalysisAgent")
agent_registry.register(live_analysis_agent, overwrite=True)

analysis_agent = LiveAnalysisAgent("AnalysisAgent")
agent_registry.register(analysis_agent, overwrite=True)
