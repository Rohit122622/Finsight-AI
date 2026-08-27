"""
FinSentry AI — Phase 3J Research Observability Service.

Orchestrates structured tracing, latency measurement, token usage tracking,
error categorization, fallback diagnostics, evidence grounding metrics,
and multi-tenant persistence for the Research Agent pipeline.
"""

import contextlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from core.config import get_settings
from database.connection import mongodb
from schemas.observability import (
    ErrorEvent,
    FailureCategory,
    FallbackMetrics,
    GroundingMetrics,
    PromptExecutionMetadata,
    ResearchRun,
    ResearchTrace,
    RetrievalMetrics,
    StageStatus,
    StageTiming,
    TokenUsage,
    TraceDetailResponse,
    TraceListResponse,
    TraceSummaryResponse,
    ValidationMetrics,
)
from services.langsmith_service import langsmith_service
from utils.sanitization import sanitize_data, sanitize_text

logger = logging.getLogger(__name__)


class ResearchTraceContext:
    """
    Active trace context manager tracking a single research request through
    all execution stages. Thread-safe and resilient.
    """

    def __init__(
        self,
        session_id: str,
        conversation_id: str,
        user_id: str,
        query: str,
        trace_id: Optional[str] = None,
    ) -> None:
        self.trace_id = trace_id or str(uuid.uuid4())
        self.root_run_id = str(uuid.uuid4())
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.query = sanitize_text(query)
        self.started_at = datetime.now(timezone.utc)
        self.start_perf = time.perf_counter()

        self.stages: List[StageTiming] = []
        self.runs: List[ResearchRun] = []
        self.error_events: List[ErrorEvent] = []

        self.token_usage = TokenUsage()
        self.retrieval_metrics: Optional[RetrievalMetrics] = None
        self.grounding_metrics: Optional[GroundingMetrics] = None
        self.validation_metrics: Optional[ValidationMetrics] = None
        self.fallback_metrics: Optional[FallbackMetrics] = None
        self.prompt_metadata: Optional[PromptExecutionMetadata] = None
        self.query_classification: Optional[str] = None
        self.status = StageStatus.SUCCESS.value
        self.langsmith_trace_url: Optional[str] = None

                                                                                                       
        self._active_stages: Dict[str, Tuple[float, datetime, Optional[str], Dict[str, Any]]] = {}

                                       
        settings = get_settings()
        if settings.OBSERVABILITY_ENABLED and langsmith_service.is_enabled:
            langsmith_run_id = langsmith_service.create_root_run(
                trace_id=self.trace_id,
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                query=self.query,
                metadata={"agent": "ResearchAgent", "environment": settings.APP_ENV},
            )
            if langsmith_run_id:
                self.root_run_id = langsmith_run_id
                self.langsmith_trace_url = langsmith_service.get_trace_url(langsmith_run_id)

                                                                       

    def start_stage(self, stage_name: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Start tracking an execution stage."""
        sanitized_details = sanitize_data(details or {})
        start_perf = time.perf_counter()
        started_at = datetime.now(timezone.utc)

        child_run_id = None
        if langsmith_service.is_enabled:
            child_run_id = langsmith_service.create_child_run(
                parent_run_id=self.root_run_id,
                name=f"Stage: {stage_name}",
                run_type="chain",
                inputs={"stage": stage_name, **sanitized_details},
                metadata={"trace_id": self.trace_id, "session_id": self.session_id},
            )

        self._active_stages[stage_name] = (start_perf, started_at, child_run_id, sanitized_details)

    def end_stage(
        self,
        stage_name: str,
        status: str = StageStatus.SUCCESS.value,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
    ) -> StageTiming:
        """Complete tracking for an execution stage."""
        completed_at = datetime.now(timezone.utc)
        end_perf = time.perf_counter()

        if stage_name in self._active_stages:
            start_perf, started_at, child_run_id, existing_details = self._active_stages.pop(stage_name)
            duration_ms = round((end_perf - start_perf) * 1000.0, 2)
        else:
            started_at = completed_at
            duration_ms = 0.0
            child_run_id = None
            existing_details = {}

        merged_details = {**existing_details, **(sanitize_data(details) if details else {})}
        sanitized_error = sanitize_text(error) if error else None
        sanitized_outputs = sanitize_data(outputs) if outputs else None

        stage_timing = StageTiming(
            stage_name=stage_name,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            status=status,
            error=sanitized_error,
            details=merged_details,
        )
        self.stages.append(stage_timing)

                           
        run_record = ResearchRun(
            run_id=child_run_id or str(uuid.uuid4()),
            parent_run_id=self.root_run_id,
            run_type="chain",
            name=f"Stage: {stage_name}",
            inputs={"stage": stage_name, **merged_details},
            outputs=sanitized_outputs,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            status=status,
            error=sanitized_error,
            metadata={"trace_id": self.trace_id},
        )
        self.runs.append(run_record)

        if langsmith_service.is_enabled and child_run_id:
            langsmith_service.end_run(
                run_id=child_run_id,
                outputs=sanitized_outputs or merged_details,
                error=sanitized_error,
                end_time=completed_at,
            )

        return stage_timing

    @contextlib.contextmanager
    def stage(
        self,
        stage_name: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Generator[None, None, None]:
        """Context manager for convenient stage timing."""
        self.start_stage(stage_name, details)
        try:
            yield
            self.end_stage(stage_name, status=StageStatus.SUCCESS.value)
        except Exception as exc:
            self.end_stage(
                stage_name,
                status=StageStatus.FAILED.value,
                error=str(exc),
            )
            raise

                                                                      

    def record_query_understanding(self, qu: Any) -> None:
        """Record classified intent and signal counts."""
        try:
            if hasattr(qu, "classification"):
                self.query_classification = (
                    qu.classification.value
                    if hasattr(qu.classification, "value")
                    else str(qu.classification)
                )
        except Exception as exc:
            logger.debug("Failed to record query understanding telemetry: %s", exc)

    def record_retrieval(
        self,
        retrieval_resp: Any,
        mode: str = "hybrid",
        top_k: int = 5,
        duration_ms: float = 0.0,
        score_threshold: float = 0.0,
    ) -> None:
        """Record Phase 3A retrieval metrics."""
        try:
            results = getattr(retrieval_resp, "results", [])
            meta = getattr(retrieval_resp, "retrieval_metadata", None)

            scores = [r.score for r in results if hasattr(r, "score") and r.score is not None]
            avg_score = round(sum(scores) / len(scores), 4) if scores else None
            max_score = round(max(scores), 4) if scores else None
            min_score = round(min(scores), 4) if scores else None

            self.retrieval_metrics = RetrievalMetrics(
                retrieval_mode=str(mode),
                query_classification=self.query_classification or "FACTUAL",
                top_k=top_k,
                candidates_examined=len(results),
                results_returned=len(results),
                cache_hit=getattr(meta, "cache_hit", False) if meta else False,
                duration_ms=duration_ms,
                score_threshold=score_threshold,
                avg_score=avg_score,
                max_score=max_score,
                min_score=min_score,
            )
        except Exception as exc:
            logger.debug("Failed to record retrieval telemetry: %s", exc)

    def record_prompt(
        self,
        prompt_pkg: Any,
        model: str = "",
        provider: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record Phase 3D prompt construction metadata."""
        settings = get_settings()
        if not settings.PROMPT_LOGGING_ENABLED:
            return

        try:
            sections = []
            char_count = 0
            est_tokens = 0
            if hasattr(prompt_pkg, "system_prompt"):
                sections.append("system_prompt")
                char_count += len(prompt_pkg.system_prompt or "")
            if hasattr(prompt_pkg, "user_prompt"):
                sections.append("user_prompt")
                char_count += len(prompt_pkg.user_prompt or "")
            if hasattr(prompt_pkg, "estimated_tokens"):
                est_tokens = prompt_pkg.estimated_tokens
            elif char_count:
                est_tokens = max(1, char_count // 4)

            self.prompt_metadata = PromptExecutionMetadata(
                prompt_version=getattr(prompt_pkg, "version", "1.0.0"),
                prompt_sections=sections,
                prompt_character_count=char_count,
                estimated_tokens=est_tokens,
                model=model,
                provider=provider,
                timestamp=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                success=True,
            )
        except Exception as exc:
            logger.debug("Failed to record prompt telemetry: %s", exc)

    def record_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        is_estimated: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Record token telemetry distinguishing actual usage from estimates."""
        settings = get_settings()
        if not settings.TOKEN_TRACKING_ENABLED:
            return

        calc_total = total_tokens if total_tokens > 0 else (input_tokens + output_tokens)
        self.token_usage = TokenUsage(
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            total_tokens=max(0, calc_total),
            is_estimated=is_estimated,
            provider=provider,
            model=model,
        )

    def record_fallback(self, fallback_result: Any) -> None:
        """Record Phase 3F fallback telemetry."""
        try:
            if fallback_result is None:
                return

            fallback_occurred = bool(getattr(fallback_result, "fallback_occurred", False))
            primary_provider = str(getattr(fallback_result, "primary_provider", "") or "")
            primary_model = str(getattr(fallback_result, "primary_model", "") or "")
            final_provider = str(getattr(fallback_result, "provider", "") or "")
            final_model = str(getattr(fallback_result, "model_name", "") or "")
            attempts = getattr(fallback_result, "attempts", []) or []
            total_latency = float(getattr(fallback_result, "total_fallback_latency_ms", 0.0) or 0.0)

            error_cats: List[str] = []
            for att in attempts:
                if hasattr(att, "error_category") and att.error_category:
                    cat_val = (
                        att.error_category.value
                        if hasattr(att.error_category, "value")
                        else str(att.error_category)
                    )
                    if isinstance(cat_val, str) and cat_val not in error_cats:
                        error_cats.append(cat_val)

                             
            if not fallback_occurred and len(attempts) <= 1:
                chain_summary = "PRIMARY_SUCCESS"
            elif "claude" in str(final_provider).lower():
                chain_summary = "PRIMARY_FAILED_CLAUDE_SUCCESS"
            elif "groq" in str(final_provider).lower():
                chain_summary = "PRIMARY_FAILED_CLAUDE_FAILED_GROQ_SUCCESS"
            else:
                chain_summary = f"FALLBACK_SUCCESS_{final_provider.upper()}"

            self.fallback_metrics = FallbackMetrics(
                fallback_occurred=fallback_occurred,
                primary_provider=primary_provider,
                primary_model=primary_model,
                failed_attempts=max(0, len(attempts) - 1),
                error_categories=error_cats,
                fallback_provider=final_provider if fallback_occurred else None,
                fallback_model=final_model if fallback_occurred else None,
                final_provider=final_provider,
                final_model=final_model,
                fallback_attempt_count=len(attempts),
                total_fallback_latency_ms=total_latency,
                chain_summary=chain_summary,
            )

                                                                     
            in_tokens = int(getattr(fallback_result, "prompt_tokens", 0) or 0)
            out_tokens = int(getattr(fallback_result, "completion_tokens", 0) or 0)
            tot_tokens = int(getattr(fallback_result, "total_tokens", 0) or 0)
            if in_tokens or out_tokens or tot_tokens:
                self.record_token_usage(
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=tot_tokens,
                    is_estimated=False,
                    provider=final_provider,
                    model=final_model,
                )
        except Exception as exc:
            logger.debug("Failed to record fallback telemetry: %s", exc)

    def record_grounding(self, response: Any, validation: Optional[Any] = None) -> None:
        """Record Phase 3E/3G citation and evidence grounding metrics."""
        try:
            if response is None:
                return

            citations = getattr(response, "citations", []) or []
            claims = getattr(response, "claims", []) or []
            confidence = float(getattr(response, "confidence", 0.0) or 0.0)
            conf_tier = getattr(response, "confidence_level", "HIGH")
            tier_str = conf_tier.value if hasattr(conf_tier, "value") else str(conf_tier)
            refused = bool(getattr(response, "refused", False))
            refusal_reason = getattr(response, "refusal_reason", None)
            if refusal_reason is not None:
                refusal_reason = str(refusal_reason)

            supported = 0
            unsupported = 0
            partially_supported = 0
            for c in claims:
                status = getattr(c, "support_status", None)
                status_str = status.value if hasattr(status, "value") else str(status)
                if str(status_str).upper() == "SUPPORTED":
                    supported += 1
                elif str(status_str).upper() == "UNSUPPORTED":
                    unsupported += 1
                elif str(status_str).upper() == "PARTIALLY_SUPPORTED":
                    partially_supported += 1

            total_claims = len(claims)
            ratio = (supported / total_claims) if total_claims > 0 else 1.0

            valid_citations = len(citations)
            invalid_citations = 0
            if validation is not None:
                invalid_citations = int(getattr(validation, "invalid_citation_count", 0) or 0)
                valid_citations = max(0, len(citations) - invalid_citations)

            self.grounding_metrics = GroundingMetrics(
                citations_generated=len(citations),
                citations_validated=valid_citations,
                invalid_citations=invalid_citations,
                supported_claims=supported,
                unsupported_claims=unsupported,
                partially_supported_claims=partially_supported,
                grounding_ratio=round(ratio, 4),
                confidence_score=round(confidence, 4),
                confidence_level=str(tier_str),
                refusal_status=refused,
                refusal_reason=refusal_reason,
            )
        except Exception as exc:
            logger.debug("Failed to record grounding telemetry: %s", exc)

    def record_validation(self, validation: Any, duration_ms: float = 0.0) -> None:
        """Record Phase 3G output validation metrics."""
        try:
            if validation is None:
                return

            status = getattr(validation, "status", "VALID")
            status_str = status.value if hasattr(status, "value") else str(status)
            is_valid = getattr(validation, "valid", True)
            inv_cits = getattr(validation, "invalid_citation_count", 0)
            unsup_claims = getattr(validation, "unsupported_claim_count", 0)
            conflicts = getattr(validation, "duplicate_count", 0)
            final_conf = getattr(validation, "final_confidence", 0.0)
            refusal_req = getattr(validation, "refusal_required", False)
            errors = [sanitize_text(e) for e in getattr(validation, "validation_errors", [])]
            warnings = [sanitize_text(w) for w in getattr(validation, "validation_warnings", [])]

            self.validation_metrics = ValidationMetrics(
                validation_status=status_str,
                is_valid=is_valid,
                duration_ms=duration_ms,
                invalid_citation_count=inv_cits,
                unsupported_claim_count=unsup_claims,
                conflict_count=conflicts,
                confidence_before=0.0,
                confidence_after=final_conf,
                refusal_decision=refusal_req,
                validation_errors=errors,
                validation_warnings=warnings,
            )
        except Exception as exc:
            logger.debug("Failed to record validation telemetry: %s", exc)

    def record_error(
        self,
        category: FailureCategory,
        stage: str,
        error_message: str,
        retry_count: int = 0,
        provider: Optional[str] = None,
    ) -> None:
        """Record structured error event."""
        cat_val = category.value if hasattr(category, "value") else str(category)
        sanitized_msg = sanitize_text(error_message)

        event = ErrorEvent(
            category=cat_val,
            stage=stage,
            error_message=sanitized_msg,
            timestamp=datetime.now(timezone.utc),
            retry_count=retry_count,
            provider=provider,
        )
        self.error_events.append(event)
        self.status = StageStatus.FAILED.value

                                                                      

    def finalize(
        self,
        status: str = StageStatus.SUCCESS.value,
        final_response: Optional[Any] = None,
    ) -> ResearchTrace:
        """
        Finalize the active trace, calculate overall latency, end LangSmith root run,
        and construct the finalized ResearchTrace contract.
        """
        completed_at = datetime.now(timezone.utc)
        total_duration_ms = round((time.perf_counter() - self.start_perf) * 1000.0, 2)

                                           
        for stage_name in list(self._active_stages.keys()):
            self.end_stage(stage_name, status=status)

                                        
        if self.error_events:
            self.status = StageStatus.FAILED.value
        elif final_response and getattr(final_response, "refused", False):
            self.status = StageStatus.REFUSED.value
        else:
            self.status = status

                                                                       
        if self.token_usage.total_tokens == 0:
            query_len = len(self.query)
            ans_len = len(getattr(final_response, "answer", "") or "")
            est_in = max(1, query_len // 4)
            est_out = max(1, ans_len // 4)
            self.record_token_usage(
                input_tokens=est_in,
                output_tokens=est_out,
                total_tokens=est_in + est_out,
                is_estimated=True,
            )

        trace = ResearchTrace(
            trace_id=self.trace_id,
            root_run_id=self.root_run_id,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            agent_name="ResearchAgent",
            query=self.query,
            started_at=self.started_at,
            completed_at=completed_at,
            total_duration_ms=total_duration_ms,
            status=self.status,
            query_classification=self.query_classification,
            stages=self.stages,
            token_usage=self.token_usage,
            retrieval_metrics=self.retrieval_metrics,
            grounding_metrics=self.grounding_metrics,
            validation_metrics=self.validation_metrics,
            fallback_metrics=self.fallback_metrics,
            prompt_metadata=self.prompt_metadata,
            error_events=self.error_events,
            runs=self.runs,
            langsmith_trace_url=self.langsmith_trace_url,
            created_at=completed_at,
        )

                                
        if langsmith_service.is_enabled:
            output_dict = None
            if final_response:
                output_dict = {
                    "answer": sanitize_text(getattr(final_response, "answer", "")[:300]),
                    "confidence": getattr(final_response, "confidence", 0.0),
                    "refused": getattr(final_response, "refused", False),
                }
            langsmith_service.end_run(
                run_id=self.root_run_id,
                outputs=output_dict,
                error=self.error_events[-1].error_message if self.error_events else None,
                end_time=completed_at,
            )

        return trace


class ObservabilityService:
    """
    Central service managing Research Agent telemetry collection,
    multi-tenant MongoDB storage, and LangSmith coordination.
    """

    def __init__(self) -> None:
        self._indexes_created = False

    def create_trace(
        self,
        session_id: str,
        conversation_id: str,
        user_id: str,
        query: str,
        trace_id: Optional[str] = None,
    ) -> ResearchTraceContext:
        """Create a new trace context for a research request."""
        return ResearchTraceContext(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            query=query,
            trace_id=trace_id,
        )

    async def ensure_indexes(self) -> None:
        """Ensure MongoDB indexes exist on the research_traces collection."""
        if self._indexes_created:
            return
        try:
            db = mongodb.get_db()
            await db.research_traces.create_index([("session_id", 1), ("created_at", -1)])
            await db.research_traces.create_index([("conversation_id", 1)])
            await db.research_traces.create_index([("trace_id", 1)], unique=True)
            await db.research_traces.create_index([("user_id", 1)])
            self._indexes_created = True
            logger.info("Observability indexes verified on 'research_traces' collection.")
        except Exception as exc:
            logger.debug("Non-fatal index creation note: %s", exc)

    async def save_trace(self, trace: ResearchTrace) -> None:
        """
        Persist a finalized trace to MongoDB.
        Guarantees that database write failures never raise exceptions to the caller.
        """
        settings = get_settings()
        if not settings.OBSERVABILITY_ENABLED:
            return

        try:
            await self.ensure_indexes()
            db = mongodb.get_db()
            trace_obj = trace.to_trace() if hasattr(trace, "to_trace") else trace
            doc = trace_obj.model_dump()
            await db.research_traces.insert_one(doc)
            logger.debug("Successfully saved research trace %s", trace_obj.trace_id)
        except Exception as exc:
            logger.warning("Failed to persist research trace %s (non-fatal): %s", trace.trace_id, exc)

    async def get_session_traces(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> TraceListResponse:
        """
        Retrieve paginated trace summaries scoped strictly to session_id and user_id.
        """
        try:
            db = mongodb.get_db()
            cursor = (
                db.research_traces.find(
                    {"session_id": session_id, "user_id": user_id},
                    {
                        "trace_id": 1,
                        "session_id": 1,
                        "conversation_id": 1,
                        "query": 1,
                        "started_at": 1,
                        "total_duration_ms": 1,
                        "status": 1,
                        "grounding_metrics.confidence_score": 1,
                        "validation_metrics.validation_status": 1,
                        "fallback_metrics.fallback_occurred": 1,
                        "fallback_metrics.final_provider": 1,
                        "token_usage": 1,
                    },
                )
                .sort("created_at", -1)
                .skip(skip)
                .limit(limit)
            )

            docs = await cursor.to_list(length=limit)
            total_count = await db.research_traces.count_documents(
                {"session_id": session_id, "user_id": user_id}
            )

            summaries = []
            for d in docs:
                gm = d.get("grounding_metrics") or {}
                vm = d.get("validation_metrics") or {}
                fm = d.get("fallback_metrics") or {}
                tu = d.get("token_usage") or {}

                summaries.append(
                    TraceSummaryResponse(
                        trace_id=d["trace_id"],
                        session_id=d["session_id"],
                        conversation_id=d["conversation_id"],
                        query=d.get("query", ""),
                        started_at=d["started_at"],
                        total_duration_ms=d.get("total_duration_ms", 0.0),
                        status=d.get("status", "SUCCESS"),
                        confidence_score=gm.get("confidence_score"),
                        validation_status=vm.get("validation_status"),
                        fallback_occurred=fm.get("fallback_occurred", False),
                        final_provider=fm.get("final_provider"),
                        token_usage=TokenUsage(**tu) if tu else TokenUsage(),
                    )
                )

            return TraceListResponse(
                session_id=session_id,
                traces=summaries,
                total_count=total_count,
            )
        except Exception as exc:
            logger.error("Error retrieving session traces: %s", exc)
            return TraceListResponse(session_id=session_id, traces=[], total_count=0)

    async def get_trace_detail(
        self,
        trace_id: str,
        user_id: str,
    ) -> Optional[ResearchTrace]:
        """
        Retrieve complete trace detail verifying user ownership.
        """
        try:
            db = mongodb.get_db()
            doc = await db.research_traces.find_one({"trace_id": trace_id, "user_id": user_id})
            if not doc:
                return None
            doc.pop("_id", None)
            return ResearchTrace(**doc)
        except Exception as exc:
            logger.error("Error retrieving trace %s: %s", trace_id, exc)
            return None


observability_service = ObservabilityService()
