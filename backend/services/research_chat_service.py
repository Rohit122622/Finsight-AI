"""
FinSentry AI — Phase 3H/3J Research Chat & API Service.

Integrates the complete Phase 3A-3J pipeline:
  1. Conversation & History Loading (MongoDB)
  2. Session Memory Retrieval (MongoDB)
  3. Phase 3J Trace & LangSmith Lifecycle Initialization
  4. 3B Query Understanding & Intent Classification
  5. 3A Hybrid / Vector / Keyword Retrieval
  6. 3C Multi-Source Context Building (grounded evidence + history + memory)
  7. 3D Prompt Engineering & Prompt Package Generation
  8. 3F LLM Fallback & Provider Routing
  9. 3E Evidence-Based Reasoning & Claim Extraction
 10. 3G Output Validation & Strict Multi-Tenant Citation Verification
 11. 3J Comprehensive Telemetry, Token Tracking & Latency Observability
 12. Streaming (SSE) and Non-Streaming Responses
 13. Persistent State & Memory Management
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

from bson import ObjectId

from database.connection import mongodb
from schemas.context import (
    ContextCategory,
    ContextSourceType,
    ConversationMessage as ContextConversationMessage,
    ResearchContext,
    SessionMemoryItem,
)
from schemas.observability import FailureCategory, StageStatus
from schemas.output_validation import ValidationResult, ValidationStatus
from schemas.query_understanding import (
    QueryClassification,
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from schemas.reasoning import ConfidenceLevel, ResearchCitation, ResearchResponse
from schemas.research_api import (
    ResearchChatRequest,
    ResearchChatResponse,
    ResearchConversation,
    ResearchMessage,
    SessionMemoryResponse,
    StreamEvent,
    StreamEventType,
)
from schemas.retrieval import (
    MetadataFilter,
    RetrievalMetadata,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
)
from services.context_builder_service import context_builder_service
from services.evidence_reasoning_service import evidence_reasoning_service
from services.observability_service import observability_service
from services.output_validation_service import output_validation_service
from services.query_understanding_service import query_understanding_service
from services.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)


class ResearchChatService:
    """
    Production Research API Service orchestrating end-to-end research chat
    with integrated Phase 3J observability and LangSmith tracing.
    """

                                                                       

    async def get_or_create_conversation(
        self,
        session_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        initial_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve existing conversation or create a new one scoped to (session_id, user_id).
        """
        db = mongodb.get_db()
        now = datetime.now(timezone.utc)

        if conversation_id:
            conv = await db.research_conversations.find_one(
                {
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "user_id": user_id,
                }
            )
            if conv is not None:
                return conv

                                 
        new_conv_id = conversation_id or str(uuid.uuid4())
        conv_doc = {
            "conversation_id": new_conv_id,
            "session_id": session_id,
            "user_id": user_id,
            "title": initial_title[:80] if initial_title else "Financial Research Conversation",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.research_conversations.insert_one(conv_doc)
        return conv_doc

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get conversation details ensuring user ownership.
        """
        db = mongodb.get_db()
        return await db.research_conversations.find_one(
            {"conversation_id": conversation_id, "user_id": user_id}
        )

    async def list_conversations(
        self,
        session_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List all research conversations for a session sorted by updated_at descending.
        """
        db = mongodb.get_db()
        cursor = (
            db.research_conversations.find(
                {"session_id": session_id, "user_id": user_id}
            )
            .sort("updated_at", -1)
        )
        conversations: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc.pop("_id", None)
            conversations.append(doc)
        return conversations

                                                                       

    async def load_conversation_history(
        self,
        session_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        limit: int = 100,
    ) -> Tuple[List[ResearchMessage], List[ContextConversationMessage]]:
        """
        Load historical messages for conversation or entire session if conversation_id is omitted.
        Returns both ResearchMessage format (API) and ConversationMessage format (Context Builder).
        """
        db = mongodb.get_db()
        filter_dict: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
        }
        if conversation_id:
            filter_dict["conversation_id"] = conversation_id

        cursor = (
            db.research_messages.find(filter_dict)
            .sort("created_at", 1)
            .limit(limit)
        )

        messages: List[ResearchMessage] = []
        context_messages: List[ContextConversationMessage] = []

        async for doc in cursor:
            doc.pop("_id", None)
            msg = ResearchMessage(**doc)
            messages.append(msg)
            context_messages.append(
                ContextConversationMessage(
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at,
                    citations_count=len(msg.citations),
                )
            )

        return messages, context_messages

    async def load_session_memory(
        self,
        session_id: str,
        user_id: str,
    ) -> Optional[SessionMemoryItem]:
        """
        Load structured memory entity for the session.
        """
        db = mongodb.get_db()
        doc = await db.research_session_memory.find_one(
            {"session_id": session_id, "user_id": user_id}
        )
        if not doc:
            return None

        return SessionMemoryItem(
            topic=doc.get("topic"),
            entities=list(doc.get("entities", [])),
            metrics_discussed=list(doc.get("metrics_discussed", [])),
            periods_discussed=list(doc.get("periods_discussed", [])),
            prior_queries=list(doc.get("prior_queries", [])),
            document_ids=list(doc.get("document_ids", [])),
            category=ContextCategory.SESSION_MEMORY,
            source_type=ContextSourceType.SESSION_MEMORY,
        )

    async def update_session_memory(
        self,
        session_id: str,
        user_id: str,
        query: str,
        query_understanding: QueryUnderstandingResult,
        response: ResearchResponse,
    ) -> None:
        """
        Update session memory with newly discussed entities, metrics, and periods.
        """
        db = mongodb.get_db()
        now = datetime.now(timezone.utc)

        existing = await db.research_session_memory.find_one(
            {"session_id": session_id, "user_id": user_id}
        )

        entities: List[str] = list(existing.get("entities", [])) if existing else []
        metrics: List[str] = list(existing.get("metrics_discussed", [])) if existing else []
        periods: List[str] = list(existing.get("periods_discussed", [])) if existing else []
        prior_queries: List[str] = list(existing.get("prior_queries", [])) if existing else []
        doc_ids: List[str] = list(existing.get("document_ids", [])) if existing else []

                                      
        for metric in query_understanding.financial_signals.metrics:
            if metric not in metrics:
                metrics.append(metric)

        temporal_periods = (
            [str(y) for y in query_understanding.temporal_signals.years]
            + query_understanding.temporal_signals.fiscal_years
            + query_understanding.temporal_signals.quarters
            + query_understanding.temporal_signals.date_ranges
        )
        for period in temporal_periods:
            if period not in periods:
                periods.append(period)

        if query not in prior_queries:
            prior_queries.append(query)
            if len(prior_queries) > 20:
                prior_queries = prior_queries[-20:]

                                                    
        for cit in response.citations:
            if cit.document_id and cit.document_id not in doc_ids:
                doc_ids.append(cit.document_id)

        topic = existing.get("topic") if existing else None
        if not topic and query_understanding.financial_signals.metrics:
            topic = f"Financial analysis of {', '.join(query_understanding.financial_signals.metrics[:2])}"

        update_doc = {
            "session_id": session_id,
            "user_id": user_id,
            "topic": topic,
            "entities": entities[:20],
            "metrics_discussed": metrics[:30],
            "periods_discussed": periods[:20],
            "prior_queries": prior_queries,
            "document_ids": doc_ids[:50],
            "updated_at": now,
        }

        await db.research_session_memory.update_one(
            {"session_id": session_id, "user_id": user_id},
            {"$set": update_doc},
            upsert=True,
        )

    async def persist_message(
        self,
        conversation_id: str,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        response: Optional[ResearchResponse] = None,
        validation: Optional[ValidationResult] = None,
    ) -> ResearchMessage:
        """
        Persist message to MongoDB and update conversation message count.
        """
        db = mongodb.get_db()
        now = datetime.now(timezone.utc)
        message_id = str(uuid.uuid4())

        claims_data = []
        citations_data = []
        confidence_score = None
        confidence_tier = None
        validation_status = None

        if response is not None:
            claims_data = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in response.claims]
            citations_data = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in response.citations]
            confidence_score = getattr(response, "confidence", 0.0)
            confidence_tier = (
                response.confidence_level.value
                if hasattr(response.confidence_level, "value")
                else str(response.confidence_level)
            )

        if validation is not None:
            validation_status = (
                validation.status.value
                if hasattr(validation.status, "value")
                else str(validation.status)
            )
            if validation.final_confidence is not None:
                confidence_score = validation.final_confidence

        msg_doc = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "claims": claims_data,
            "citations": citations_data,
            "confidence_score": confidence_score,
            "confidence_tier": confidence_tier,
            "validation_status": validation_status,
            "created_at": now,
        }

        await db.research_messages.insert_one(msg_doc)

        await db.research_conversations.update_one(
            {"conversation_id": conversation_id, "user_id": user_id},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": now},
            },
        )

        return ResearchMessage(
            message_id=message_id,
            conversation_id=conversation_id,
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            claims=claims_data,
            citations=citations_data,
            confidence_score=confidence_score,
            confidence_tier=confidence_tier,
            validation_status=validation_status,
            created_at=now,
        )

                                                                       

    async def _execute_retrieval(
        self,
        session_id: str,
        user_id: str,
        request: ResearchChatRequest,
        qu: QueryUnderstandingResult,
    ) -> RetrievalResponse:
        """
        Entity-aware and comparison-aware retrieval orchestration.
        - Resolves target company entity to canonical document IDs BEFORE retrieval.
        - If multi-entity comparison: performs separate retrieval passes per entity and merges them.
        - If single-entity: strictly scopes retrieval to the resolved entity's document IDs.
        """
        from utils.company_resolution import is_company_match

        # 1. Multi-entity comparison query handling
        if qu.classification == QueryClassification.COMPARISON and len(qu.entities) >= 2:
            all_results: List[RetrievalResult] = []
            seen_chunks: Set[str] = set()
            per_entity_top_k = max(3, request.top_k // len(qu.entities) + 1)

            for entity in qu.entities:
                entity_query = f"{qu.normalized_query} {entity}"
                req_entity = RetrievalRequest(
                    query=entity_query,
                    top_k=per_entity_top_k,
                    mode=request.mode,
                    score_threshold=request.score_threshold,
                    document_ids=request.document_ids,
                )
                resp_entity = await retrieval_service.retrieve(
                    session_id=session_id,
                    user_id=user_id,
                    request=req_entity,
                )
                for r in resp_entity.results:
                    if r.chunk_id not in seen_chunks:
                        seen_chunks.add(r.chunk_id)
                        all_results.append(r)

            all_results.sort(key=lambda r: r.score, reverse=True)
            top_results = all_results[:request.top_k]
            return RetrievalResponse(
                query=qu.normalized_query or request.message,
                session_id=session_id,
                results=top_results,
                total=len(top_results),
                retrieval_metadata=RetrievalMetadata(
                    mode=request.mode,
                    vector_weight=0.7,
                    keyword_weight=0.3,
                    score_threshold=request.score_threshold,
                    total_candidates=len(all_results),
                    cache_hit=False,
                    query_understanding=qu,
                ),
            )

        # 2. Single-entity resolution BEFORE retrieval
        target_doc_ids: Optional[List[str]] = request.document_ids
        if len(qu.entities) == 1:
            target_entity = qu.entities[0]
            matching_doc_ids: Set[str] = set()
            try:
                db = mongodb.get_db()
                docs = await db.documents.find(
                    {"session_id": session_id, "user_id": user_id},
                    {"document_id": 1, "filename": 1, "company_name": 1, "ticker": 1},
                ).to_list(length=100)
                if not docs:
                    docs = await db.extracted_metrics.find(
                        {"session_id": session_id, "user_id": user_id},
                        {"document_id": 1, "company_name": 1, "document_filename": 1},
                    ).to_list(length=100)
                for doc in docs:
                    if is_company_match(target_entity, doc):
                        doc_id = doc.get("document_id")
                        if doc_id:
                            matching_doc_ids.add(doc_id)
            except Exception as db_exc:
                logger.warning("Error resolving target entity '%s' before retrieval: %s", target_entity, db_exc)

            if matching_doc_ids:
                target_doc_ids = list(matching_doc_ids)

        # 3. Standard scoped retrieval
        scoped_filters = MetadataFilter(document_ids=target_doc_ids) if target_doc_ids else None
        retrieval_resp = await retrieval_service.retrieve(
            session_id=session_id,
            user_id=user_id,
            request=RetrievalRequest(
                query=qu.normalized_query or request.message,
                top_k=request.top_k,
                mode=request.mode,
                score_threshold=request.score_threshold,
                document_ids=target_doc_ids,
                filters=scoped_filters,
            ),
        )

        # Multi-part / sub-query retrieval orchestration
        if qu.sub_queries and len(qu.sub_queries) >= 2:
            all_results: List[RetrievalResult] = list(retrieval_resp.results)
            seen_chunks: Set[str] = {r.chunk_id for r in all_results}
            per_sub_k = max(3, request.top_k // len(qu.sub_queries) + 1)

            for sub_q in qu.sub_queries:
                req_sub = RetrievalRequest(
                    query=sub_q,
                    top_k=per_sub_k,
                    mode=request.mode,
                    score_threshold=request.score_threshold,
                    document_ids=target_doc_ids,
                    filters=scoped_filters,
                )
                resp_sub = await retrieval_service.retrieve(
                    session_id=session_id,
                    user_id=user_id,
                    request=req_sub,
                )
                for r in resp_sub.results:
                    if r.chunk_id not in seen_chunks:
                        seen_chunks.add(r.chunk_id)
                        all_results.append(r)

            all_results.sort(key=lambda r: r.score, reverse=True)
            top_results = all_results[: max(request.top_k, 8)]
            retrieval_resp.results = top_results
            retrieval_resp.total = len(top_results)

        # Retrieval Query Expansion Merging
        elif qu.expanded_queries:
            all_results: List[RetrievalResult] = list(retrieval_resp.results)
            seen_chunks: Set[str] = {r.chunk_id for r in all_results}

            for exp_q in qu.expanded_queries[:3]:
                req_exp = RetrievalRequest(
                    query=exp_q,
                    top_k=request.top_k,
                    mode=request.mode,
                    score_threshold=request.score_threshold,
                    document_ids=target_doc_ids,
                    filters=scoped_filters,
                )
                resp_exp = await retrieval_service.retrieve(
                    session_id=session_id,
                    user_id=user_id,
                    request=req_exp,
                )
                for r in resp_exp.results:
                    if r.chunk_id not in seen_chunks:
                        seen_chunks.add(r.chunk_id)
                        all_results.append(r)

            all_results.sort(key=lambda r: r.score, reverse=True)
            top_results = all_results[: max(request.top_k, 8)]
            retrieval_resp.results = top_results
            retrieval_resp.total = len(top_results)

        return retrieval_resp

    async def _check_pre_retrieval_gates(
        self,
        session_id: str,
        user_id: str,
        query: str,
        qu: QueryUnderstandingResult,
        context_messages: List[ContextConversationMessage],
        session_memory: Optional[Any] = None,
    ) -> Optional[ResearchResponse]:
        """
        Pre-retrieval validation gates:
        1. Multi-Company Ambiguity Gate:
           If session has multiple distinct companies, and query does not specify a company,
           and is not a comparison query, and conversation history does not resolve it:
           STOP BEFORE RETRIEVAL / LLM -> Return clarification message with confidence=0.0.
        2. Future / Invalid Period Refusal Gate:
           If query asks for an unsupported future fiscal period (e.g. FY2029, FY2030) exceeding
           the canonical validated reporting period of the document:
           STOP BEFORE RETRIEVAL / LLM -> Return clean refusal with confidence=0.0, refused=True.
        """
        from utils.company_resolution import is_company_match, get_canonical_company_key
        db = mongodb.get_db()

        # Fetch session documents and extracted metrics
        session_docs = await db.documents.find(
            {"session_id": session_id, "user_id": user_id},
            {"document_id": 1, "filename": 1, "company_name": 1, "ticker": 1},
        ).to_list(length=100)

        metrics_records = await db.extracted_metrics.find(
            {"session_id": session_id, "user_id": user_id},
            {"document_id": 1, "company_name": 1, "reporting_period": 1, "multi_year_data": 1, "document_filename": 1},
        ).to_list(length=100)

        # Collect distinct companies in session
        distinct_companies: Set[str] = set()
        for d in session_docs:
            c = d.get("company_name")
            if c:
                distinct_companies.add(c.strip())
            elif d.get("filename"):
                can = get_canonical_company_key(d["filename"])
                if can:
                    distinct_companies.add(can.title())

        for m in metrics_records:
            c = m.get("company_name")
            if c:
                distinct_companies.add(c.strip())
            elif m.get("document_filename"):
                can = get_canonical_company_key(m["document_filename"])
                if can:
                    distinct_companies.add(can.title())

        # Gate 1: Multi-Company Ambiguity Gate
        if len(distinct_companies) >= 2:
            if not qu.entities and qu.classification != QueryClassification.COMPARISON:
                # Check recent history
                recent_entity = None
                for msg in reversed(context_messages[-4:]):
                    for comp in distinct_companies:
                        if is_company_match(comp, msg.content):
                            recent_entity = comp
                            break
                    if recent_entity:
                        break

                if not recent_entity:
                    sorted_comps = sorted(list(distinct_companies))
                    comp_display = " or ".join(sorted_comps) if len(sorted_comps) == 2 else ", ".join(sorted_comps)
                    clarification = f"Which company would you like me to analyze — {comp_display}?"
                    logger.info("PRE_RETRIEVAL_GATE: Multi-company ambiguity triggered for query '%s' -> %s", query, clarification)
                    return ResearchResponse(
                        session_id=session_id,
                        user_id=user_id,
                        query=query,
                        answer=clarification,
                        confidence=0.0,
                        confidence_level=ConfidenceLevel.LOW,
                        citations=[],
                        claims=[],
                        refused=False,
                        grounding_score=0.0,
                        hallucination_detected=False,
                        synthesis_notes="Multi-company ambiguity resolved before retrieval.",
                    )

        # Gate 2: Future / Invalid Fiscal Period Refusal Gate
        requested_years: List[int] = list(qu.temporal_signals.years)
        for fy in qu.temporal_signals.fiscal_years:
            m = re.search(r"20\d\d", fy)
            if m:
                requested_years.append(int(m.group(0)))

        for y_match in re.finditer(r"\b(20[2-9]\d)\b", query):
            yr = int(y_match.group(1))
            if yr not in requested_years:
                requested_years.append(yr)

        if requested_years:
            # Determine maximum validated reporting year across target document(s)
            max_validated_year = 2025  # Default upper bound
            doc_max_years: Dict[str, int] = {}
            for m in metrics_records:
                doc_id = m.get("document_id", "")
                rep_p = m.get("reporting_period", "")
                rep_match = re.search(r"20\d\d", str(rep_p))
                if rep_match:
                    doc_max_years[doc_id] = max(doc_max_years.get(doc_id, 0), int(rep_match.group(0)))
                doc_fn = m.get("document_filename") or m.get("filename", "")
                fn_match = re.search(r"(?<!\d)(20\d\d)(?!\d)", str(doc_fn))
                if fn_match:
                    doc_max_years[doc_id] = max(doc_max_years.get(doc_id, 0), int(fn_match.group(1)))

            if doc_max_years:
                max_validated_year = max(doc_max_years.values())

            for yr in requested_years:
                if yr > max_validated_year:
                    company_label = qu.entities[0] if qu.entities else ("the uploaded filing" if len(distinct_companies) <= 1 else "the target company")
                    refusal = f"Financial information for FY{yr} is not available in the uploaded {company_label} filing. The latest reporting period covered is FY{max_validated_year}."
                    logger.info("PRE_RETRIEVAL_GATE: Future-year refusal triggered for requested year %d (> max %d) -> %s", yr, max_validated_year, refusal)
                    return ResearchResponse(
                        session_id=session_id,
                        user_id=user_id,
                        query=query,
                        answer=refusal,
                        confidence=0.0,
                        confidence_level=ConfidenceLevel.LOW,
                        citations=[],
                        claims=[],
                        refused=True,
                        grounding_score=0.0,
                        hallucination_detected=False,
                        synthesis_notes="Future fiscal period refusal before retrieval.",
                    )

        return None

    async def execute_chat(
        self,
        session_id: str,
        user_id: str,
        request: ResearchChatRequest,
    ) -> ResearchChatResponse:
        """
        Execute end-to-end research chat (non-streaming) with full Phase 3J observability.
        """
        logger.info(
            "ResearchChatService.execute_chat starting: session=%s, user=%s, query='%s'",
            session_id,
            user_id,
            request.message[:60],
        )

                                       
        conv = await self.get_or_create_conversation(
            session_id=session_id,
            user_id=user_id,
            conversation_id=request.conversation_id,
            initial_title=request.message[:60],
        )
        conversation_id = conv["conversation_id"]

                                              
        trace_ctx = observability_service.create_trace(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            query=request.message,
        )

        try:
                                                             
            trace_ctx.start_stage("history_and_memory_loading")
            api_messages, context_messages = await self.load_conversation_history(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                limit=10,
            )
            session_memory = await self.load_session_memory(session_id=session_id, user_id=user_id)
            trace_ctx.end_stage("history_and_memory_loading")

                                     
            await self.persist_message(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=request.message,
            )

                                              
            trace_ctx.start_stage("query_understanding")
            qu = query_understanding_service.understand_query(
                QueryUnderstandingRequest(
                    query=request.message,
                    session_id=session_id,
                    conversation_history=[{"role": m.role, "content": m.content} for m in context_messages],
                )
            )
            trace_ctx.end_stage("query_understanding")
            trace_ctx.record_query_understanding(qu)

            # -------------------------------------------------------------
            # Pre-Retrieval Validation Gates (Ambiguity & Future Periods)
            # -------------------------------------------------------------
            gate_response = await self._check_pre_retrieval_gates(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                qu=qu,
                context_messages=context_messages,
                session_memory=session_memory,
            )
            if gate_response is not None:
                validation = ValidationResult(
                    valid=True,
                    status=ValidationStatus.VALID,
                    validation_errors=[],
                    validation_warnings=[],
                    final_confidence=gate_response.confidence,
                )
                if hasattr(gate_response, "metadata"):
                    gate_response.metadata.trace_id = trace_ctx.trace_id

                assistant_msg = await self.persist_message(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=gate_response.answer,
                    response=gate_response,
                    validation=validation,
                )
                trace = trace_ctx.finalize(
                    status=StageStatus.REFUSED.value if gate_response.refused else StageStatus.SUCCESS.value,
                    final_response=gate_response,
                )
                try:
                    await observability_service.save_trace(trace)
                except Exception as obs_exc:
                    logger.warning("Failed to save research trace (non-fatal): %s", obs_exc)

                return ResearchChatResponse(
                    conversation_id=conversation_id,
                    message_id=assistant_msg.message_id,
                    session_id=session_id,
                    user_id=user_id,
                    trace_id=trace_ctx.trace_id,
                    response=gate_response,
                    validation=validation,
                    created_at=assistant_msg.created_at,
                )

                                                                
            trace_ctx.start_stage("retrieval")
            retrieval_resp = await self._execute_retrieval(
                session_id=session_id,
                user_id=user_id,
                request=request,
                qu=qu,
            )
            ret_timing = trace_ctx.end_stage("retrieval")
            trace_ctx.record_retrieval(
                retrieval_resp,
                mode=request.mode.value if hasattr(request.mode, "value") else str(request.mode),
                top_k=request.top_k,
                duration_ms=ret_timing.duration_ms,
                score_threshold=request.score_threshold,
            )

                                           
            trace_ctx.start_stage("context_building")
            context = await context_builder_service.build_context(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                retrieved_results=retrieval_resp.results,
                chat_history=context_messages,
                session_memory=session_memory,
                query_understanding=qu,
                auto_retrieve=False,
            )
            trace_ctx.end_stage("context_building")

                                                                         
            trace_ctx.start_stage("evidence_reasoning")
            raw_response = await evidence_reasoning_service.reason(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                context=context,
                query_understanding=qu,
            )
            reason_timing = trace_ctx.end_stage("evidence_reasoning")

                                                                         
            if hasattr(raw_response, "metadata"):
                rmeta = raw_response.metadata
                if hasattr(rmeta, "is_fallback") and rmeta.is_fallback:
                    trace_ctx.fallback_metrics = getattr(trace_ctx, "fallback_metrics", None)
                if hasattr(rmeta, "total_tokens_estimate") and rmeta.total_tokens_estimate > 0:
                    trace_ctx.record_token_usage(
                        input_tokens=max(1, rmeta.total_tokens_estimate // 2),
                        output_tokens=max(1, rmeta.total_tokens_estimate // 2),
                        total_tokens=rmeta.total_tokens_estimate,
                        is_estimated=True,
                        provider=rmeta.llm_provider,
                        model=rmeta.llm_model,
                    )

                                            
            trace_ctx.start_stage("output_validation")
            validated_response, validation = output_validation_service.validate_response(
                response=raw_response,
                context=context,
                session_id=session_id,
                user_id=user_id,
            )
            response = validated_response
            val_timing = trace_ctx.end_stage("output_validation")
            trace_ctx.record_validation(validation, duration_ms=val_timing.duration_ms)
            trace_ctx.record_grounding(response, validation)

                                                  
            if hasattr(response, "metadata"):
                response.metadata.trace_id = trace_ctx.trace_id

                                           
            assistant_msg = await self.persist_message(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=response.answer,
                response=response,
                validation=validation,
            )

                                       
            await self.update_session_memory(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                query_understanding=qu,
                response=response,
            )

                                                            
            trace = trace_ctx.finalize(
                status=StageStatus.REFUSED.value if response.refused else StageStatus.SUCCESS.value,
                final_response=response,
            )
            try:
                await observability_service.save_trace(trace)
            except Exception as obs_exc:
                logger.warning("Failed to save research trace (non-fatal): %s", obs_exc)

            return ResearchChatResponse(
                conversation_id=conversation_id,
                message_id=assistant_msg.message_id,
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_ctx.trace_id,
                response=response,
                validation=validation,
                created_at=assistant_msg.created_at,
            )

        except Exception as exc:
            logger.exception("Error executing research chat: %s", exc)
            trace_ctx.record_error(
                category=FailureCategory.INTERNAL_ERROR,
                stage="execute_chat",
                error_message=str(exc),
            )
            trace = trace_ctx.finalize(status=StageStatus.FAILED.value)
            await observability_service.save_trace(trace)
            raise

                                                                       

    async def stream_chat(
        self,
        session_id: str,
        user_id: str,
        request: ResearchChatRequest,
    ) -> AsyncGenerator[str, None]:
        """
        Execute research chat pipeline and stream Server-Sent Events with Phase 3J Observability.
        Guarantees strict output validation before emitting the completed event.
        """
        logger.info(
            "ResearchChatService.stream_chat starting: session=%s, user=%s, query='%s'",
            session_id,
            user_id,
            request.message[:60],
        )

                                              
        def make_event(event_type: StreamEventType, data: Dict[str, Any]) -> str:
            evt = StreamEvent(event=event_type, data=data)
            return evt.to_sse()

                                       
        conv = await self.get_or_create_conversation(
            session_id=session_id,
            user_id=user_id,
            conversation_id=request.conversation_id,
            initial_title=request.message[:60],
        )
        conversation_id = conv["conversation_id"]

                                              
        trace_ctx = observability_service.create_trace(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            query=request.message,
        )

        try:
            yield make_event(
                StreamEventType.STARTED,
                {
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "query": request.message,
                    "trace_id": trace_ctx.trace_id,
                },
            )

                                                             
            trace_ctx.start_stage("history_and_memory_loading")
            api_messages, context_messages = await self.load_conversation_history(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
                limit=10,
            )
            session_memory = await self.load_session_memory(session_id=session_id, user_id=user_id)
            trace_ctx.end_stage("history_and_memory_loading")

                                     
            await self.persist_message(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=request.message,
            )

                                              
            trace_ctx.start_stage("query_understanding")
            qu = query_understanding_service.understand_query(
                QueryUnderstandingRequest(
                    query=request.message,
                    session_id=session_id,
                    recent_history=[{"role": m.role, "content": m.content} for m in context_messages[-4:]],
                )
            )
            trace_ctx.end_stage("query_understanding")
            trace_ctx.record_query_understanding(qu)

            yield make_event(
                StreamEventType.QUERY_UNDERSTANDING,
                {
                    "intent": qu.classification.value,
                    "financial_metrics": qu.financial_signals.metrics,
                    "temporal_periods": [str(y) for y in qu.temporal_signals.years] + qu.temporal_signals.fiscal_years,
                    "is_follow_up": qu.is_follow_up,
                },
            )

            # Pre-Retrieval Validation Gates for Streaming
            gate_response = await self._check_pre_retrieval_gates(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                qu=qu,
                context_messages=context_messages,
                session_memory=session_memory,
            )
            if gate_response is not None:
                validation = ValidationResult(
                    valid=True,
                    status=ValidationStatus.VALID,
                    validation_errors=[],
                    validation_warnings=[],
                    final_confidence=gate_response.confidence,
                )
                assistant_msg = await self.persist_message(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=gate_response.answer,
                    response=gate_response,
                    validation=validation,
                )
                trace = trace_ctx.finalize(
                    status=StageStatus.REFUSED.value if gate_response.refused else StageStatus.SUCCESS.value,
                    final_response=gate_response,
                )
                try:
                    await observability_service.save_trace(trace)
                except Exception as obs_exc:
                    logger.warning("Failed to save research trace (non-fatal): %s", obs_exc)

                yield make_event(
                    StreamEventType.CONTENT_DELTA,
                    {"content": gate_response.answer, "index": 0},
                )
                yield make_event(
                    StreamEventType.COMPLETED,
                    {
                        "conversation_id": conversation_id,
                        "message_id": assistant_msg.message_id,
                        "answer": gate_response.answer,
                        "citations": [],
                        "confidence": gate_response.confidence,
                        "validation_status": "VALID",
                        "trace_id": trace_ctx.trace_id,
                    },
                )
                return

                                                                
            trace_ctx.start_stage("retrieval")
            retrieval_resp = await self._execute_retrieval(
                session_id=session_id,
                user_id=user_id,
                request=request,
                qu=qu,
            )
            ret_timing = trace_ctx.end_stage("retrieval")
            trace_ctx.record_retrieval(
                retrieval_resp,
                mode=request.mode.value if hasattr(request.mode, "value") else str(request.mode),
                top_k=request.top_k,
                duration_ms=ret_timing.duration_ms,
                score_threshold=request.score_threshold,
            )

            yield make_event(
                StreamEventType.RETRIEVAL,
                {
                    "chunks_retrieved": len(retrieval_resp.results),
                    "retrieval_mode": retrieval_resp.retrieval_metadata.mode.value,
                    "cached": retrieval_resp.retrieval_metadata.cache_hit,
                },
            )

                                           
            trace_ctx.start_stage("context_building")
            context = await context_builder_service.build_context(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                retrieved_results=retrieval_resp.results,
                chat_history=context_messages,
                session_memory=session_memory,
                query_understanding=qu,
                auto_retrieve=False,
            )
            trace_ctx.end_stage("context_building")

            yield make_event(
                StreamEventType.CONTEXT,
                {
                    "total_characters": context.metadata.total_character_count,
                    "total_tokens": context.metadata.total_token_estimate,
                    "chunks_selected": context.metadata.chunks_selected,
                    "is_truncated": context.metadata.is_truncated,
                },
            )

                                                                         
            yield make_event(
                StreamEventType.GENERATION,
                {"status": "reasoning_on_evidence", "provider": "primary"},
            )

            trace_ctx.start_stage("evidence_reasoning")
            raw_response = await evidence_reasoning_service.reason(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                context=context,
                query_understanding=qu,
            )
            trace_ctx.end_stage("evidence_reasoning")

                                         
            yield make_event(
                StreamEventType.CITATION,
                {
                    "citation_count": len(raw_response.citations),
                    "citations": [
                        {
                            "document_id": c.document_id,
                            "chunk_id": c.chunk_id,
                            "page_number": c.page_number,
                            "section": c.section,
                        }
                        for c in raw_response.citations
                    ],
                },
            )

                                            
            trace_ctx.start_stage("output_validation")
            validated_response, validation = output_validation_service.validate_response(
                response=raw_response,
                context=context,
                session_id=session_id,
                user_id=user_id,
            )
            response = validated_response
            val_timing = trace_ctx.end_stage("output_validation")
            trace_ctx.record_validation(validation, duration_ms=val_timing.duration_ms)
            trace_ctx.record_grounding(response, validation)

                                                  
            if hasattr(response, "metadata"):
                response.metadata.trace_id = trace_ctx.trace_id

            yield make_event(
                StreamEventType.VALIDATION,
                {
                    "validation_status": validation.status.value,
                    "is_valid": validation.valid,
                    "confidence_score": response.confidence,
                    "confidence_tier": response.confidence_level.value,
                    "unsupported_claims_count": validation.unsupported_claim_count,
                    "invalid_citations_count": validation.invalid_citation_count,
                },
            )

                                             
            if response.refused or validation.status == ValidationStatus.REFUSED:
                yield make_event(
                    StreamEventType.REFUSED,
                    {
                        "reason": response.refusal_reason or "Insufficient evidence to answer question.",
                        "answer": response.answer,
                    },
                )

                                                                
            words = response.answer.split(" ")
            chunk_size = 4
            for i in range(0, len(words), chunk_size):
                delta = " ".join(words[i : i + chunk_size])
                if i + chunk_size < len(words):
                    delta += " "
                yield make_event(StreamEventType.CONTENT_DELTA, {"delta": delta})
                await asyncio.sleep(0.01)

                                           
            assistant_msg = await self.persist_message(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=response.answer,
                response=response,
                validation=validation,
            )

                                       
            await self.update_session_memory(
                session_id=session_id,
                user_id=user_id,
                query=request.message,
                query_understanding=qu,
                response=response,
            )

                                                            
            trace = trace_ctx.finalize(
                status=StageStatus.REFUSED.value if response.refused else StageStatus.SUCCESS.value,
                final_response=response,
            )
            try:
                await observability_service.save_trace(trace)
            except Exception as obs_exc:
                logger.warning("Failed to save research trace (non-fatal): %s", obs_exc)

                                                                                     
            yield make_event(
                StreamEventType.COMPLETED,
                {
                    "conversation_id": conversation_id,
                    "message_id": assistant_msg.message_id,
                    "trace_id": trace_ctx.trace_id,
                    "response": response.model_dump(),
                    "validation": validation.model_dump(),
                },
            )

        except Exception as exc:
            logger.exception("Error in stream_chat pipeline: %s", exc)
            trace_ctx.record_error(
                category=FailureCategory.INTERNAL_ERROR,
                stage="stream_chat",
                error_message=str(exc),
            )
            trace = trace_ctx.finalize(status=StageStatus.FAILED.value)
            await observability_service.save_trace(trace)

            yield make_event(
                StreamEventType.ERROR,
                {"error": "An error occurred during research reasoning. Please try again."},
            )


research_chat_service = ResearchChatService()
