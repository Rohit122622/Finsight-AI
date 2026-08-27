"""
FinSentry AI — Production Research Agent (Phase 2C/3H / Master Architecture).

Author: Rohit / FinSentry Engineering Team

Agentic RAG specialist for financial document research, multi-turn conversational reasoning,
and strictly grounded Q&A with exact document/page/chunk citations.

Architecture:
  1. Natural-language query understanding & multi-part decomposition
  2. Hybrid vector + BM25 keyword retrieval scoped by session and user
  3. Multi-source evidence aggregation (documents, extracted metrics, red flags, memory)
  4. Evidence-first reasoning with hard refusal on missing/unsupported queries
  5. Exact citation integrity (document_id, filename, page_number, chunk_id)
  6. Numerical grounding verification (percentages, YoY changes, arithmetic operands)
  7. Automated provider fallback (GPT-4o -> Claude -> Groq)
  8. Conversation history & session memory management
  9. Full persistence to MongoDB (research_conversations, research_messages, research_session_memory)
  10. Streaming (SSE) and Celery asynchronous task execution contracts
"""

import asyncio
import concurrent.futures
import logging
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Set

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from database.connection import mongodb
from schemas.agent_results import ResearchResult
from schemas.reasoning import ResearchCitation, ResearchResponse
from schemas.research_api import ResearchChatRequest, ResearchChatResponse
from schemas.retrieval import RetrievalMode
from services.research_chat_service import research_chat_service

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Production-grade Agentic RAG specialist for institutional financial research and grounded Q&A.
    """

    def __init__(self, name: str = "ResearchAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.RESEARCH)

    # =====================================================================
    # BaseAgent Synchronous Execution Entrypoint (Celery & CLI Contract)
    # =====================================================================

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Synchronous execution entrypoint conforming to FinSentry BaseAgent and Celery worker contracts.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.execute_async(payload, context)).result()
        else:
            return asyncio.run(self.execute_async(payload, context))

    # =====================================================================
    # Asynchronous Research Pipeline
    # =====================================================================

    async def execute_async(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Full asynchronous research chat pipeline with query decomposition, multi-source retrieval,
        evidence-based reasoning, provider fallback, citation grounding, and MongoDB persistence.

        Payload:
            query (str): User research question (required).
            session_id (str): Research session ID (required).
            conversation_id (str, optional): Conversation ID for multi-turn history.
            document_ids (List[str], optional): Document filter scope.
            top_k (int, optional): Number of chunks to retrieve (default: 5).
            score_threshold (float, optional): Minimum similarity threshold (default: 0.0).
            mode (str, optional): Retrieval mode ('hybrid', 'vector', 'keyword').

        Context:
            user_id (str): Authenticated user ID (required).
            job_id (str, optional): Celery job ID if running asynchronously.
        """
        query = payload.get("query") or payload.get("message")
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        conversation_id = payload.get("conversation_id")
        document_ids = payload.get("document_ids")
        top_k = payload.get("top_k", 5)
        score_threshold = payload.get("score_threshold", 0.0)
        mode_str = str(payload.get("mode", "hybrid")).lower()

        if not query or not query.strip():
            raise NonRetryableAgentException("Parameter 'query' cannot be empty.")
        if not session_id or not user_id:
            raise NonRetryableAgentException("Missing required parameters: 'session_id' and 'user_id'.")

        try:
            retrieval_mode = RetrievalMode(mode_str)
        except ValueError:
            retrieval_mode = RetrievalMode.HYBRID

        logger.info(
            "ResearchAgent executing grounded research query '%s' for session %s (user %s)",
            query,
            session_id,
            user_id,
        )

        try:
            if mongodb._database is None:
                try:
                    await mongodb.connect()
                except Exception as db_exc:
                    logger.debug("MongoDB auto-connect notice in ResearchAgent: %s", db_exc)

            chat_req = ResearchChatRequest(
                session_id=session_id,
                conversation_id=conversation_id,
                message=query.strip(),
                mode=retrieval_mode,
                top_k=top_k,
                score_threshold=score_threshold,
                document_ids=document_ids,
                stream=False,
            )

            chat_res: ResearchChatResponse = await research_chat_service.execute_chat(
                session_id=session_id,
                user_id=user_id,
                request=chat_req,
            )

            resp: ResearchResponse = chat_res.response

            # Collect legacy-compatible and detailed citations
            legacy_citations: List[Dict[str, Any]] = []
            cited_chunk_ids: List[str] = []
            seen_cids: Set[str] = set()

            for idx, cit in enumerate(resp.citations, start=1):
                cid = cit.chunk_id
                if cid and cid not in seen_cids:
                    seen_cids.add(cid)
                    cited_chunk_ids.append(cid)

                legacy_citations.append({
                    "citation_id": idx,
                    "document_id": cit.document_id,
                    "document_filename": cit.document_filename or "document",
                    "chunk_id": cit.chunk_id,
                    "chunk_index": 0,
                    "page_number": cit.page_number,
                    "relevance_score": 1.0 if cit.is_valid else 0.5,
                    "snippet": cit.quoted_snippet or "",
                    "is_valid": cit.is_valid,
                })

            # Also check claims for any cited chunks
            for claim in resp.claims:
                for ev in getattr(claim, "supporting_evidence", []):
                    cid = getattr(ev, "chunk_id", None) if hasattr(ev, "chunk_id") else (ev.get("chunk_id") if isinstance(ev, dict) else None)
                    if cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        cited_chunk_ids.append(cid)

            summary = {
                "query": query,
                "session_id": session_id,
                "conversation_id": chat_res.conversation_id,
                "message_id": chat_res.message_id,
                "answer": resp.answer,
                "citations": legacy_citations,
                "cited_chunk_ids": cited_chunk_ids,
                "chunks_retrieved": resp.metadata.chunks_analyzed if resp.metadata else 0,
                "confidence": resp.confidence,
                "confidence_level": resp.confidence_level.value if hasattr(resp.confidence_level, "value") else str(resp.confidence_level),
                "refused": resp.refused,
                "refusal_reason": resp.refusal_reason,
                "claims_count": len(resp.claims),
                "supported_claims_count": resp.metadata.supported_claims if resp.metadata else 0,
                "key_points": resp.key_points,
                "limitations": resp.limitations,
                "trace_id": chat_res.trace_id,
                "llm_provider": resp.metadata.llm_provider if resp.metadata else None,
                "llm_model": resp.metadata.llm_model if resp.metadata else None,
                "is_fallback": resp.metadata.is_fallback if resp.metadata else False,
                "validation_status": chat_res.validation.status.value if chat_res.validation and hasattr(chat_res.validation.status, "value") else None,
            }

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=summary,
                result_ref=session_id,
                metadata={
                    "top_k": top_k,
                    "score_threshold": score_threshold,
                    "conversation_id": chat_res.conversation_id,
                    "message_id": chat_res.message_id,
                    "trace_id": chat_res.trace_id,
                    "reasoning_response": resp.model_dump(),
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("ResearchAgent encountered error: %s", exc, exc_info=True)
            raise RetryableAgentException(f"Transient error during research execution: {exc}")

    # =====================================================================
    # Streaming Support (SSE)
    # =====================================================================

    async def stream_async(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous streaming generator yielding Server-Sent Events (SSE).
        """
        query = payload.get("query") or payload.get("message")
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        conversation_id = payload.get("conversation_id")
        document_ids = payload.get("document_ids")
        top_k = payload.get("top_k", 5)
        score_threshold = payload.get("score_threshold", 0.0)
        mode_str = str(payload.get("mode", "hybrid")).lower()

        if not query or not query.strip():
            raise NonRetryableAgentException("Parameter 'query' cannot be empty.")
        if not session_id or not user_id:
            raise NonRetryableAgentException("Missing required parameters: 'session_id' and 'user_id'.")

        try:
            retrieval_mode = RetrievalMode(mode_str)
        except ValueError:
            retrieval_mode = RetrievalMode.HYBRID

        chat_req = ResearchChatRequest(
            session_id=session_id,
            conversation_id=conversation_id,
            message=query.strip(),
            mode=retrieval_mode,
            top_k=top_k,
            score_threshold=score_threshold,
            document_ids=document_ids,
            stream=True,
        )

        async for sse_event in research_chat_service.stream_chat(
            session_id=session_id,
            user_id=user_id,
            request=chat_req,
        ):
            yield sse_event


research_agent = ResearchAgent()
agent_registry.register(research_agent, overwrite=True)
