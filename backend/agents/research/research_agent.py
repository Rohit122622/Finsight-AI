"""
Financial Research RAG Agent for FinSentry AI (Phase 2C).

Performs semantic retrieval across session document chunks and synthesizes
grounded financial analysis with source citations.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from services.embedding_service import embedding_service
from services.llm_service import llm_service

from services.evidence_reasoning_service import evidence_reasoning_service

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Agentic RAG specialist for financial document research and grounded Q&A.
    """

    def __init__(self, name: str = "ResearchAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.RESEARCH)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute financial research over session documents using Phase 3E Evidence-Based Reasoning.

        Payload:
            query: str (required)
            session_id: str (required)
            document_ids: List[str] (optional filter)
            top_k: int (optional, default 5)
            score_threshold: float (optional, default 0.0)

        Context:
            user_id: str (required)
            job_id: str (optional)
        """
        query = payload.get("query")
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        document_ids = payload.get("document_ids")
        top_k = payload.get("top_k", 5)
        score_threshold = payload.get("score_threshold", 0.0)

        if not query or not query.strip():
            raise NonRetryableAgentException("Parameter 'query' cannot be empty.")
        if not session_id or not user_id:
            raise NonRetryableAgentException("Missing required parameters: 'session_id' and 'user_id'.")

        logger.info(
            "ResearchAgent executing grounded reasoning query '%s' for session %s (user %s)",
            query,
            session_id,
            user_id,
        )

        try:

            reasoning_resp = evidence_reasoning_service.reason_sync(
                session_id=session_id,
                user_id=user_id,
                query=query,
            )


            legacy_citations = []
            for idx, cit in enumerate(reasoning_resp.citations, start=1):
                legacy_citations.append({
                    "citation_id": idx,
                    "document_id": cit.document_id,
                    "document_filename": cit.document_filename or "document",
                    "chunk_id": cit.chunk_id,
                    "chunk_index": 0,
                    "page_number": cit.page_number,
                    "relevance_score": 1.0,
                    "snippet": cit.quoted_snippet or "",
                })

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary={
                    "query": query,
                    "session_id": session_id,
                    "answer": reasoning_resp.answer,
                    "citations": legacy_citations,
                    "chunks_retrieved": reasoning_resp.metadata.chunks_analyzed,
                    "confidence": reasoning_resp.confidence,
                    "confidence_level": reasoning_resp.confidence_level.value,
                    "refused": reasoning_resp.refused,
                    "claims_count": len(reasoning_resp.claims),
                    "supported_claims_count": reasoning_resp.metadata.supported_claims,
                },
                result_ref=session_id,
                metadata={
                    "top_k": top_k,
                    "score_threshold": score_threshold,
                    "reasoning_response": reasoning_resp.model_dump(),
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("ResearchAgent encountered error: %s", exc)
            raise RetryableAgentException(f"Transient error during research execution: {exc}")



research_agent = ResearchAgent()
agent_registry.register(research_agent, overwrite=True)
