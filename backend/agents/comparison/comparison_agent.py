"""
Comparison Agent for FinSentry AI (Phase 2C).

Compares financial metrics, disclosures, and performance trends
across reporting periods or benchmark entities.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from schemas.agent_results import ComparisonItem, ComparisonResult
from services.embedding_service import embedding_service
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ComparisonAgent(BaseAgent):
    """
    Agent responsible for comparative financial performance and ratio analysis.
    """

    def __init__(self, name: str = "ComparisonAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.COMPARISON)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute financial comparison.

        Payload:
            session_id: str (required)
            baseline_entity: str (optional)
            comparison_entity: str (optional)
        """
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        baseline = payload.get("baseline_entity", "Current Period")
        comparison = payload.get("comparison_entity", "Prior Period")

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id' and 'user_id' must be provided."
            )

        logger.info("ComparisonAgent comparing %s vs %s in session %s", baseline, comparison, session_id)

        try:
            chunks = embedding_service.search_session_chunks_sync(
                query=f"financial comparison, revenue growth, operating margin, earnings per share, {baseline} vs {comparison}",
                session_id=session_id,
                user_id=user_id,
                top_k=5,
            )

            context_text = "\n\n".join([f"Snippet {i+1}: {c['text']}" for i, c in enumerate(chunks)])

            system_prompt = (
                "You are an expert equity research analyst. "
                "Compare financial performance between entities/periods."
            )
            prompt = (
                f"Context snippets:\n{context_text}\n\n"
                f"Baseline: {baseline}, Comparison Target: {comparison}\n"
                "Return a JSON structured object with 'metrics_compared' (list of {metric_name, baseline_value, comparison_value, variance_percentage, trend}), "
                "'key_takeaways' (list of strings), and 'executive_summary'."
            )

            llm_out = llm_service.generate_structured(
                prompt=prompt,
                output_schema=ComparisonResult,
                system_prompt=system_prompt,
            )

            comp_res = ComparisonResult(
                agent_name=self.name,
                session_id=session_id,
                baseline_entity=baseline,
                comparison_entity=comparison,
                metrics_compared=[
                    ComparisonItem(**m) if isinstance(m, dict) else m
                    for m in llm_out.get("metrics_compared", [])
                ],
                key_takeaways=llm_out.get("key_takeaways", ["Stable year-over-year operational trends."]),
                executive_summary=llm_out.get("executive_summary", f"Comparison between {baseline} and {comparison} complete."),
            )

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=comp_res.model_dump(),
                result_ref=session_id,
                metadata={"baseline": baseline, "comparison": comparison},
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("Error in ComparisonAgent: %s", exc)
            raise RetryableAgentException(f"ComparisonAgent transient failure: {exc}")


comparison_agent = ComparisonAgent()
agent_registry.register(comparison_agent, overwrite=True)
