"""
FinSentry AI — Phase 3C Context Building Service.

Assembles, deduplicates, prioritizes, ranks, compresses, and limits multi-source
financial research context ready for downstream Research Agent reasoning (Phase 3D/3E):
  1. Multi-source evidence aggregation (documents, metrics, red flags, comparisons, history, memory)
  2. Evidence categorization (SOURCE_EVIDENCE, CONVERSATION_CONTEXT, SESSION_MEMORY)
  3. Strict citation metadata preservation
  4. Deterministic deduplication and ranking (boost by metric, period, section relevance)
  5. Deterministic, fact-preserving context compression
  6. Context window limit enforcement and truncation tracking
  7. Multi-tenant session and user isolation
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from schemas.context import (
    ComparisonEvidence,
    ContextCategory,
    ContextLimitsConfig,
    ContextMetadata,
    ContextSourceType,
    ConversationMessage,
    DocumentEvidence,
    MetricEvidence,
    RedFlagEvidence,
    ResearchContext,
    SessionMemoryItem,
)
from schemas.query_understanding import (
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from schemas.retrieval import (
    MetadataFilter,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResult,
)
from services.query_understanding_service import query_understanding_service
from services.retrieval_service import retrieval_service
from database.connection import mongodb
from utils.company_resolution import is_company_match

logger = logging.getLogger(__name__)

                       
DEFAULT_LIMITS = ContextLimitsConfig(
    max_chunks=10,
    max_characters=8000,
    max_tokens=2000,
    max_history_messages=5,
    max_metrics=10,
    max_red_flags=5,
    max_comparisons=5,
)


class ContextBuilderService:
    """
    Assembles structured research context for the Research Agent.
    Does NOT generate the final financial answer.
    """

    def __init__(self, default_limits: Optional[ContextLimitsConfig] = None) -> None:
        self.default_limits = default_limits or DEFAULT_LIMITS

                                                                       

    async def build_context(
        self,
        session_id: str,
        user_id: str,
        query: str,
        retrieved_results: Optional[List[RetrievalResult]] = None,
        financial_metrics: Optional[List[MetricEvidence]] = None,
        red_flags: Optional[List[RedFlagEvidence]] = None,
        comparisons: Optional[List[ComparisonEvidence]] = None,
        chat_history: Optional[List[ConversationMessage]] = None,
        session_memory: Optional[SessionMemoryItem] = None,
        query_understanding: Optional[QueryUnderstandingResult] = None,
        limits: Optional[ContextLimitsConfig] = None,
        auto_retrieve: bool = True,
    ) -> ResearchContext:
        """
        Assemble and compress multi-source evidence into a structured ResearchContext.

        Args:
            session_id: Owning research session ID.
            user_id: Owning user ID.
            query: User research question.
            retrieved_results: Pre-retrieved document chunks (optional).
            financial_metrics: Pre-extracted financial metrics (optional).
            red_flags: Identified red flag risks (optional).
            comparisons: Structured period/metric comparisons (optional).
            chat_history: Recent conversation messages (optional).
            session_memory: Session research memory (optional).
            query_understanding: Phase 3B understanding result (optional).
            limits: Custom context window limits (optional).
            auto_retrieve: If True and chunks not provided, executes Phase 3A retrieval.

        Returns:
            Structured ResearchContext envelope.
        """
        cfg = limits or self.default_limits
        truncated_sources: List[str] = []
        is_truncated = False

                                                        
        qu_result = query_understanding
        if qu_result is None:
            try:
                hist_dicts = None
                if chat_history:
                    hist_dicts = [{"role": m.role, "content": m.content} for m in chat_history]
                qu_result = query_understanding_service.understand_query(
                    QueryUnderstandingRequest(
                        query=query,
                        conversation_history=hist_dicts,
                        session_id=session_id,
                    )
                )
            except Exception as exc:
                logger.warning("Query understanding error in context builder: %s", exc)

                                                                                 
        raw_chunks = retrieved_results
        total_chunks_retrieved = len(raw_chunks) if raw_chunks else 0
        if raw_chunks is None and auto_retrieve:
            try:
                ret_req = RetrievalRequest(
                    query=query,
                    top_k=cfg.max_chunks * 2,                                       
                    mode=RetrievalMode.HYBRID,
                    enable_query_understanding=False,
                )
                ret_res = await retrieval_service.retrieve(
                    session_id=session_id,
                    user_id=user_id,
                    request=ret_req,
                )
                raw_chunks = ret_res.results
                total_chunks_retrieved = len(raw_chunks)
            except Exception as exc:
                logger.warning("Auto-retrieval error in context builder: %s", exc)
                raw_chunks = []

                                                            
        # Auto-load session structured artifacts if not explicitly provided
        if not financial_metrics and not red_flags and not comparisons:
            auto_metrics, auto_flags, auto_comps = await self._load_session_artifacts(
                session_id=session_id, user_id=user_id, qu_result=qu_result
            )
            financial_metrics = financial_metrics or auto_metrics
            red_flags = red_flags or auto_flags
            comparisons = comparisons or auto_comps

        doc_evidence = self._process_document_chunks(raw_chunks or [], session_id, user_id)
        doc_evidence = self._rank_documents(doc_evidence, qu_result)

        # Strict Research Isolation: Resolve canonical document IDs for target company
        target_doc_ids: Optional[Set[str]] = None
        target_company_name: Optional[str] = None
        if qu_result and qu_result.entities and len(qu_result.entities) == 1:
            target_company_name = qu_result.entities[0]
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
                matched_ids = {
                    d["document_id"] for d in docs
                    if is_company_match(target_company_name, d) and d.get("document_id")
                }
                if matched_ids:
                    target_doc_ids = matched_ids
            except Exception as e_res:
                logger.debug("Entity isolation lookup notice: %s", e_res)

        if target_doc_ids:
            doc_evidence = [d for d in doc_evidence if not getattr(d, "document_id", None) or d.document_id in target_doc_ids]
            if financial_metrics:
                financial_metrics = [
                    m for m in financial_metrics
                    if not (getattr(m, "document_reference", None) or getattr(m, "document_id", None))
                    or (getattr(m, "document_reference", None) or getattr(m, "document_id", None)) in target_doc_ids
                ]
            if red_flags:
                red_flags = [
                    rf for rf in red_flags
                    if not (getattr(rf, "source_reference", None) or getattr(rf, "document_id", None))
                    or (getattr(rf, "source_reference", None) or getattr(rf, "document_id", None)) in target_doc_ids
                ]

        metrics_evidence = self._process_metrics(financial_metrics or [], qu_result)
        red_flag_evidence = self._process_red_flags(red_flags or [])
        comparison_evidence = self._process_comparisons(comparisons or [])

        context_doc_set = set()
        for d in (doc_evidence or []):
            if getattr(d, "document_id", None):
                context_doc_set.add(d.document_id)
        for m in (metrics_evidence or []):
            doc_ref = getattr(m, "document_reference", None) or getattr(m, "document_id", None)
            if doc_ref:
                context_doc_set.add(doc_ref)
        for rf in (red_flag_evidence or []):
            src_ref = getattr(rf, "source_reference", None) or getattr(rf, "document_id", None)
            if src_ref:
                context_doc_set.add(src_ref)

        context_document_ids = sorted(list(context_doc_set))

        logger.info(
            "RESEARCH_ISOLATION: target_company=%s, target_document_ids=%s, context_document_ids=%s",
            target_company_name or "ALL",
            sorted(list(target_doc_ids)) if target_doc_ids else "ALL",
            context_document_ids,
        )

                                                          
        history_evidence = self._process_chat_history(chat_history or [], cfg.max_history_messages)
        memory_evidence = self._process_session_memory(session_memory, session_id, qu_result)

                                       
        if len(doc_evidence) > cfg.max_chunks:
            doc_evidence = doc_evidence[:cfg.max_chunks]
            truncated_sources.append(ContextSourceType.DOCUMENT_CHUNK.value)
            is_truncated = True

        if len(metrics_evidence) > cfg.max_metrics:
            metrics_evidence = metrics_evidence[:cfg.max_metrics]
            truncated_sources.append(ContextSourceType.FINANCIAL_METRIC.value)
            is_truncated = True

        if len(red_flag_evidence) > cfg.max_red_flags:
            red_flag_evidence = red_flag_evidence[:cfg.max_red_flags]
            truncated_sources.append(ContextSourceType.RED_FLAG.value)
            is_truncated = True

        if len(comparison_evidence) > cfg.max_comparisons:
            comparison_evidence = comparison_evidence[:cfg.max_comparisons]
            truncated_sources.append(ContextSourceType.COMPARISON.value)
            is_truncated = True

        if len(history_evidence) > cfg.max_history_messages:
            history_evidence = history_evidence[-cfg.max_history_messages:]
            truncated_sources.append(ContextSourceType.CHAT_HISTORY.value)
            is_truncated = True

                                                                                                   
        doc_evidence = self._compress_documents(doc_evidence)

                                                                                      
        (
            doc_evidence,
            metrics_evidence,
            red_flag_evidence,
            comparison_evidence,
            history_evidence,
            memory_evidence,
            budget_truncated,
            budget_trunc_sources,
        ) = self._enforce_window_budget(
            doc_evidence,
            metrics_evidence,
            red_flag_evidence,
            comparison_evidence,
            history_evidence,
            memory_evidence,
            max_chars=cfg.max_characters,
            max_tokens=cfg.max_tokens,
        )

        if budget_truncated:
            is_truncated = True
            for s in budget_trunc_sources:
                if s not in truncated_sources:
                    truncated_sources.append(s)

                                                      
        available_sources: List[ContextSourceType] = []
        missing_sources: List[ContextSourceType] = []

        if doc_evidence:
            available_sources.append(ContextSourceType.DOCUMENT_CHUNK)
        else:
            missing_sources.append(ContextSourceType.DOCUMENT_CHUNK)

        if metrics_evidence:
            available_sources.append(ContextSourceType.FINANCIAL_METRIC)
        else:
            missing_sources.append(ContextSourceType.FINANCIAL_METRIC)

        if red_flag_evidence:
            available_sources.append(ContextSourceType.RED_FLAG)
        else:
            missing_sources.append(ContextSourceType.RED_FLAG)

        if comparison_evidence:
            available_sources.append(ContextSourceType.COMPARISON)
        else:
            missing_sources.append(ContextSourceType.COMPARISON)

        if history_evidence:
            available_sources.append(ContextSourceType.CHAT_HISTORY)
        else:
            missing_sources.append(ContextSourceType.CHAT_HISTORY)

        if memory_evidence:
            available_sources.append(ContextSourceType.SESSION_MEMORY)
        else:
            missing_sources.append(ContextSourceType.SESSION_MEMORY)

        tot_chars = self._calculate_total_characters(
            doc_evidence, metrics_evidence, red_flag_evidence,
            comparison_evidence, history_evidence, memory_evidence
        )
        tot_tokens = self._calculate_total_tokens(
            doc_evidence, metrics_evidence, red_flag_evidence,
            comparison_evidence, history_evidence, memory_evidence
        )

        metadata = ContextMetadata(
            total_chunks_retrieved=total_chunks_retrieved,
            chunks_selected=len(doc_evidence),
            metrics_selected=len(metrics_evidence),
            red_flags_selected=len(red_flag_evidence),
            comparisons_selected=len(comparison_evidence),
            history_messages_selected=len(history_evidence),
            has_session_memory=memory_evidence is not None,
            total_character_count=tot_chars,
            total_token_estimate=tot_tokens,
            is_truncated=is_truncated,
            truncated_sources=truncated_sources,
            available_sources=available_sources,
            missing_sources=missing_sources,
        )

        context = ResearchContext(
            session_id=session_id,
            user_id=user_id,
            query=query,
            query_understanding=qu_result,
            documents=doc_evidence,
            metrics=metrics_evidence,
            red_flags=red_flag_evidence,
            comparisons=comparison_evidence,
            chat_history=history_evidence,
            session_memory=memory_evidence,
            metadata=metadata,
        )

        logger.info(
            "Research context built (session=%s, docs=%d, metrics=%d, flags=%d, hist=%d, chars=%d, truncated=%s)",
            session_id,
            len(doc_evidence),
            len(metrics_evidence),
            len(red_flag_evidence),
            len(history_evidence),
            tot_chars,
            is_truncated,
        )

        return context

                                                                       

    def _process_document_chunks(
        self,
        chunks: List[RetrievalResult],
        session_id: str,
        user_id: str,
    ) -> List[DocumentEvidence]:
        """
        Convert RetrievalResults to DocumentEvidence, preserving all citation fields,
        and deduplicate by chunk_id and text hash (retaining highest score).
        """
        seen_ids: Set[str] = set()
        seen_hashes: Dict[str, DocumentEvidence] = {}
        processed: List[DocumentEvidence] = []

        for ch in chunks:
                                         
            if ch.session_id != session_id or ch.user_id != user_id:
                logger.warning("Filtered cross-tenant/cross-session chunk %s", ch.chunk_id)
                continue

            doc_ev = DocumentEvidence(
                document_id=ch.document_id,
                chunk_id=ch.chunk_id,
                session_id=ch.session_id,
                user_id=ch.user_id,
                source_text=ch.source_text,
                page_number=ch.page_number,
                section=ch.section,
                chunk_index=ch.chunk_index,
                score=ch.score,
                retrieval_method=ch.retrieval_method,
                document_filename=ch.document_filename,
                token_estimate=ch.token_estimate or len(ch.source_text.split()),
                metadata=ch.metadata or {},
                category=ContextCategory.SOURCE_EVIDENCE,
                source_type=ContextSourceType.DOCUMENT_CHUNK,
            )

                                       
            if doc_ev.chunk_id in seen_ids:
                continue

                                                
            text_hash = hashlib.sha256(doc_ev.source_text.strip().encode("utf-8")).hexdigest()
            if text_hash in seen_hashes:
                existing = seen_hashes[text_hash]
                if doc_ev.score > existing.score:
                                                       
                    idx = processed.index(existing)
                    processed[idx] = doc_ev
                    seen_hashes[text_hash] = doc_ev
                continue

            seen_ids.add(doc_ev.chunk_id)
            seen_hashes[text_hash] = doc_ev
            processed.append(doc_ev)

        return processed

                                                                       
    def _rank_documents(
        self,
        docs: List[DocumentEvidence],
        qu_result: Optional[QueryUnderstandingResult],
    ) -> List[DocumentEvidence]:
        """
        Rank candidate documents using retrieval score and query understanding signals:
        - Target entity match bonus (+0.5 for filename, +0.3 for text)
        - Metric presence bonus (+0.1)
        - Temporal presence bonus (+0.05)
        - Suggested section match bonus (+0.1)
        """
        if not docs:
            return []

        if qu_result is None:
            return sorted(docs, key=lambda d: d.score, reverse=True)

        target_metrics = [m.lower() for m in qu_result.financial_signals.metrics]
        target_years = [str(y) for y in qu_result.temporal_signals.years]
        suggested_section = qu_result.retrieval_hints.get("suggested_section", "").lower().replace("_", " ")
        target_entities = [e.lower() for e in qu_result.entities] if qu_result.entities else []

        def compute_ranking_score(doc: DocumentEvidence) -> float:
            base_score = doc.score
            text_lower = doc.source_text.lower()
            filename_lower = (doc.document_filename or "").lower()

            if target_entities:
                for ent in target_entities:
                    ent_clean = ent.strip()
                    if not ent_clean:
                        continue
                    words = [
                        w for w in re.split(r"[\s\-]+", ent_clean)
                        if w and w not in {"&", "and", "the", "inc", "corp", "co", "ltd", "llc", "plc", "group"}
                    ]
                    if ent_clean in filename_lower or (words and all(w in filename_lower for w in words)):
                        base_score += 0.5
                        break
                    if ent_clean in text_lower or (len(words) >= 2 and all(w in text_lower for w in words)):
                        base_score += 0.3
                        break

            for m in target_metrics:
                if m in text_lower:
                    base_score += 0.1
                    break

            for y in target_years:
                if y in text_lower:
                    base_score += 0.05
                    break

            if suggested_section and doc.section:
                sec_lower = doc.section.lower().replace("_", " ")
                if suggested_section in sec_lower or sec_lower in suggested_section:
                    base_score += 0.1

            return base_score

        return sorted(docs, key=compute_ranking_score, reverse=True)

    async def _load_session_artifacts(
        self,
        session_id: str,
        user_id: str,
        qu_result: Optional[QueryUnderstandingResult] = None,
    ) -> Tuple[List[MetricEvidence], List[RedFlagEvidence], List[ComparisonEvidence]]:
        """
        Query MongoDB for extracted metrics, red flags, and comparison results for this session.
        Respects entity filtering when entities are present in query understanding.
        """
        import uuid
        metrics: List[MetricEvidence] = []
        red_flags: List[RedFlagEvidence] = []
        comparisons: List[ComparisonEvidence] = []

        try:
            from database.connection import mongodb
            db = mongodb.get_db()

            from utils.company_resolution import is_company_match

            # Pre-fetch session documents map for fallback company matching
            session_docs_list = await db.documents.find(
                {"session_id": session_id, "user_id": user_id},
                {"document_id": 1, "filename": 1, "company_name": 1, "ticker": 1},
            ).to_list(length=100)
            doc_meta_map = {d.get("document_id"): d for d in session_docs_list if d.get("document_id")}

            # 1. Extracted Metrics (scoped strictly by session_id and user_id)
            cursor_m = db.extracted_metrics.find({"session_id": session_id, "user_id": user_id})
            docs_m = await cursor_m.to_list(length=200)
            for doc in docs_m:
                doc_id = doc.get("document_id", "")
                company = doc.get("company_name", "")
                doc_metrics = doc.get("metrics", [])

                # Merge document metadata if present
                doc_lookup = dict(doc)
                if doc_id in doc_meta_map:
                    for k, v in doc_meta_map[doc_id].items():
                        if k not in doc_lookup or not doc_lookup[k]:
                            doc_lookup[k] = v

                if qu_result and qu_result.entities:
                    is_match = any(is_company_match(ent, doc_lookup) for ent in qu_result.entities)
                    if not is_match:
                        continue

                # multi_year_data is the canonical extraction representation:
                # it contains the normalized number keyed by the validated
                # fiscal period. Keep source metric metadata for citations.
                metadata_by_metric = {
                    m.get("metric_name"): m for m in doc_metrics if m.get("metric_name")
                }
                canonical_years = doc.get("multi_year_data") or {}
                if isinstance(canonical_years, dict) and canonical_years:
                    for period, year_metrics in canonical_years.items():
                        if not isinstance(year_metrics, dict):
                            continue
                        for metric_name, val in year_metrics.items():
                            if val is None or str(val).strip() == "" or str(val).lower() in {"null", "not available", "none"}:
                                continue
                            source = metadata_by_metric.get(metric_name, {})
                            metrics.append(
                                MetricEvidence(
                                    document_reference=doc_id,
                                    metric_name=metric_name,
                                    value=val,
                                    period=period,
                                    unit_or_currency=source.get("unit") or source.get("currency"),
                                    confidence=source.get("confidence", 0.95),
                                    source_chunk_id=source.get("source_chunk_id") or (source.get("source_chunk_ids") or [None])[0],
                                    page_number=source.get("page_number"),
                                    category=ContextCategory.SOURCE_EVIDENCE,
                                    source_type=ContextSourceType.FINANCIAL_METRIC,
                                )
                            )
                else:
                    for m in doc_metrics:
                        val = m.get("value")
                        if val is None or str(val).strip() == "" or str(val).lower() in {"null", "not available", "none"}:
                            continue
                        metrics.append(
                            MetricEvidence(
                                document_reference=doc_id,
                                metric_name=m.get("metric_name", ""),
                                value=val,
                                period=m.get("period"),
                                unit_or_currency=m.get("unit") or m.get("currency"),
                                confidence=m.get("confidence", 0.95),
                                source_chunk_id=m.get("source_chunk_id"),
                                page_number=m.get("page_number"),
                                category=ContextCategory.SOURCE_EVIDENCE,
                                source_type=ContextSourceType.FINANCIAL_METRIC,
                            )
                        )

            # 2. Red Flags (scoped strictly by session_id and user_id)
            cursor_rf = db.red_flags.find({"session_id": session_id, "user_id": user_id})
            docs_rf = await cursor_rf.to_list(length=200)
            for doc in docs_rf:
                doc_id = doc.get("document_id", "")
                company = doc.get("company_name", "")
                flags = doc.get("flags", [])

                if qu_result and qu_result.entities:
                    is_match = any(is_company_match(ent, doc) for ent in qu_result.entities)
                    if not is_match:
                        continue

                for rf in flags:
                    red_flags.append(
                        RedFlagEvidence(
                            flag_id=rf.get("flag_id", str(uuid.uuid4())),
                            title=rf.get("title", ""),
                            description=rf.get("description", ""),
                            severity=rf.get("severity", "MEDIUM"),
                            category=ContextCategory.SOURCE_EVIDENCE,
                            source_type=ContextSourceType.RED_FLAG,
                            document_id=doc_id,
                            company_name=company,
                        )
                    )

            # 3. Comparison Results (scoped strictly by session_id and user_id)
            cursor_cr = db.comparison_results.find({"session_id": session_id, "user_id": user_id})
            docs_cr = await cursor_cr.to_list(length=50)
            for doc in docs_cr:
                comp_data = doc.get("comparison", {})
                side_by_side = comp_data.get("side_by_side", [])
                for item in side_by_side:
                    comparisons.append(
                        ComparisonEvidence(
                            metric_name=item.get("metric_name", ""),
                            base_period=str(item.get("period", "")),
                            target_period=str(item.get("period", "")),
                            base_value=str(item.get("values", {}).get(item.get("base_company", ""), "")),
                            target_value=str(item.get("values", {}).get(item.get("target_company", ""), "")),
                            difference=str(item.get("variance", "")),
                            percentage_change=str(item.get("variance_pct", "")),
                            category=ContextCategory.SOURCE_EVIDENCE,
                            source_type=ContextSourceType.COMPARISON,
                        )
                    )
        except Exception as exc:
            logger.warning("Error auto-loading session artifacts in context builder: %s", exc)

        return metrics, red_flags, comparisons

                                                                       

    def _process_metrics(
        self,
        metrics: List[MetricEvidence],
        qu_result: Optional[QueryUnderstandingResult],
    ) -> List[MetricEvidence]:
        """
        Deduplicate and rank financial metric evidence.
        """
        seen_keys: Set[Tuple[str, Optional[str], Optional[str]]] = set()
        deduped: List[MetricEvidence] = []

        for m in metrics:
            key = (m.metric_name.lower(), str(m.period).lower() if m.period else None, str(m.unit_or_currency).lower() if m.unit_or_currency else None)
            if key not in seen_keys:
                seen_keys.add(key)
                m.category = ContextCategory.SOURCE_EVIDENCE
                m.source_type = ContextSourceType.FINANCIAL_METRIC
                deduped.append(m)

        if qu_result and qu_result.financial_signals.metrics:
            target_metrics = [tm.lower() for tm in qu_result.financial_signals.metrics]
            deduped.sort(
                key=lambda item: (
                    1 if item.metric_name.lower() in target_metrics else 0,
                    item.confidence or 0.5,
                ),
                reverse=True,
            )

        return deduped

                                                                       

    def _process_red_flags(self, red_flags: List[RedFlagEvidence]) -> List[RedFlagEvidence]:
        seen: Set[str] = set()
        deduped: List[RedFlagEvidence] = []
        for rf in red_flags:
            if rf.flag_id not in seen:
                seen.add(rf.flag_id)
                rf.category = ContextCategory.SOURCE_EVIDENCE
                rf.source_type = ContextSourceType.RED_FLAG
                deduped.append(rf)
        return deduped

    def _process_comparisons(self, comparisons: List[ComparisonEvidence]) -> List[ComparisonEvidence]:
        seen: Set[Tuple[str, str, str]] = set()
        deduped: List[ComparisonEvidence] = []
        for comp in comparisons:
            key = (comp.metric_name.lower(), comp.base_period.lower(), comp.target_period.lower())
            if key not in seen:
                seen.add(key)
                comp.category = ContextCategory.SOURCE_EVIDENCE
                comp.source_type = ContextSourceType.COMPARISON
                deduped.append(comp)
        return deduped

                                                                       

    def _process_chat_history(
        self,
        messages: List[ConversationMessage],
        max_messages: int,
    ) -> List[ConversationMessage]:
        """
        Deduplicate and retain the most recent conversation messages up to limit.
        Guarantees messages are strictly labeled CONVERSATION_CONTEXT (not source evidence).
        """
        seen: Set[Tuple[str, str]] = set()
        deduped: List[ConversationMessage] = []

        for msg in messages:
            key = (msg.role.lower(), msg.content.strip())
            if key not in seen:
                seen.add(key)
                msg.category = ContextCategory.CONVERSATION_CONTEXT
                msg.source_type = ContextSourceType.CHAT_HISTORY
                deduped.append(msg)

                            
        return deduped[-max_messages:] if max_messages > 0 else []

    def _process_session_memory(
        self,
        memory: Optional[SessionMemoryItem],
        session_id: str,
        qu_result: Optional[QueryUnderstandingResult],
    ) -> Optional[SessionMemoryItem]:
        """
        Format session research memory, ensuring SESSION_MEMORY classification.
        """
        if memory is None:
                                                                                       
            if qu_result and (qu_result.financial_signals.metrics or qu_result.temporal_signals.years):
                return SessionMemoryItem(
                    metrics_discussed=qu_result.financial_signals.metrics,
                    periods_discussed=[str(y) for y in qu_result.temporal_signals.years],
                    prior_queries=[qu_result.original_query],
                    category=ContextCategory.SESSION_MEMORY,
                    source_type=ContextSourceType.SESSION_MEMORY,
                )
            return None

        memory.category = ContextCategory.SESSION_MEMORY
        memory.source_type = ContextSourceType.SESSION_MEMORY
        return memory

                                                                       

    def _compress_documents(self, docs: List[DocumentEvidence]) -> List[DocumentEvidence]:
        """
        Perform deterministic, fact-preserving whitespace and structure compression
        without altering numbers, years, percentages, currencies, or citation IDs.
        """
        compressed: List[DocumentEvidence] = []
        for doc in docs:
            text = doc.source_text
                                                                    
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.strip()

            comp_doc = doc.model_copy(update={
                "source_text": text,
                "token_estimate": len(text.split()),
            })
            compressed.append(comp_doc)
        return compressed

                                                                       

    def _enforce_window_budget(
        self,
        docs: List[DocumentEvidence],
        metrics: List[MetricEvidence],
        red_flags: List[RedFlagEvidence],
        comparisons: List[ComparisonEvidence],
        history: List[ConversationMessage],
        memory: Optional[SessionMemoryItem],
        max_chars: int,
        max_tokens: int,
    ) -> Tuple[
        List[DocumentEvidence],
        List[MetricEvidence],
        List[RedFlagEvidence],
        List[ComparisonEvidence],
        List[ConversationMessage],
        Optional[SessionMemoryItem],
        bool,
        List[str],
    ]:
        """
        Enforce character and token budgets according to the priority hierarchy:
          Priority 1: Document chunks & Primary Metrics
          Priority 2: Comparison evidence
          Priority 3: Red flags
          Priority 4: Chat history
          Priority 5: Session memory
        Lower priority items are dropped first if limits are breached.
        """
        is_truncated = False
        truncated_sources: List[str] = []

        cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
        cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

                                                        
        if (cur_chars > max_chars or cur_tokens > max_tokens) and memory is not None:
            memory = None
            is_truncated = True
            truncated_sources.append(ContextSourceType.SESSION_MEMORY.value)
            cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
            cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

                                                          
        while (cur_chars > max_chars or cur_tokens > max_tokens) and history:
            history.pop(0)
            is_truncated = True
            if ContextSourceType.CHAT_HISTORY.value not in truncated_sources:
                truncated_sources.append(ContextSourceType.CHAT_HISTORY.value)
            cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
            cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

                                                    
        while (cur_chars > max_chars or cur_tokens > max_tokens) and red_flags:
            red_flags.pop(-1)
            is_truncated = True
            if ContextSourceType.RED_FLAG.value not in truncated_sources:
                truncated_sources.append(ContextSourceType.RED_FLAG.value)
            cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
            cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

                                                          
        while (cur_chars > max_chars or cur_tokens > max_tokens) and comparisons:
            comparisons.pop(-1)
            is_truncated = True
            if ContextSourceType.COMPARISON.value not in truncated_sources:
                truncated_sources.append(ContextSourceType.COMPARISON.value)
            cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
            cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

                                                  
        while (cur_chars > max_chars or cur_tokens > max_tokens) and docs:
            if len(docs) == 1 and len(docs[0].source_text) > max_chars:
                allowed_len = max(50, max_chars - 20)
                docs[0] = docs[0].model_copy(update={
                    "source_text": docs[0].source_text[:allowed_len] + "...",
                    "token_estimate": len(docs[0].source_text[:allowed_len].split()),
                })
                is_truncated = True
                if ContextSourceType.DOCUMENT_CHUNK.value not in truncated_sources:
                    truncated_sources.append(ContextSourceType.DOCUMENT_CHUNK.value)
                break
            else:
                docs.pop(-1)
                is_truncated = True
                if ContextSourceType.DOCUMENT_CHUNK.value not in truncated_sources:
                    truncated_sources.append(ContextSourceType.DOCUMENT_CHUNK.value)
            cur_chars = self._calculate_total_characters(docs, metrics, red_flags, comparisons, history, memory)
            cur_tokens = self._calculate_total_tokens(docs, metrics, red_flags, comparisons, history, memory)

        return (
            docs,
            metrics,
            red_flags,
            comparisons,
            history,
            memory,
            is_truncated,
            truncated_sources,
        )

                                                                       

    def _calculate_total_characters(
        self,
        docs: List[DocumentEvidence],
        metrics: List[MetricEvidence],
        red_flags: List[RedFlagEvidence],
        comparisons: List[ComparisonEvidence],
        history: List[ConversationMessage],
        memory: Optional[SessionMemoryItem],
    ) -> int:
        total = sum(len(d.source_text) for d in docs)
        total += sum(len(f"{m.metric_name}: {m.value} {m.period or ''}") for m in metrics)
        total += sum(len(f"{rf.title}: {rf.description}") for rf in red_flags)
        total += sum(len(f"{c.metric_name}: {c.base_period} vs {c.target_period} ({c.percentage_change or ''})") for c in comparisons)
        total += sum(len(h.content) for h in history)
        if memory:
            total += len(str(memory.model_dump()))
        return total

    def _calculate_total_tokens(
        self,
        docs: List[DocumentEvidence],
        metrics: List[MetricEvidence],
        red_flags: List[RedFlagEvidence],
        comparisons: List[ComparisonEvidence],
        history: List[ConversationMessage],
        memory: Optional[SessionMemoryItem],
    ) -> int:
        total = sum(d.token_estimate for d in docs)
        total += sum(len(f"{m.metric_name} {m.value}".split()) for m in metrics)
        total += sum(len(f"{rf.title} {rf.description}".split()) for rf in red_flags)
        total += sum(len(f"{c.metric_name} {c.base_period} {c.target_period}".split()) for c in comparisons)
        total += sum(len(h.content.split()) for h in history)
        if memory:
            total += len(str(memory.model_dump()).split())
        return int(total * 1.3)


                                                                       

context_builder_service = ContextBuilderService()
