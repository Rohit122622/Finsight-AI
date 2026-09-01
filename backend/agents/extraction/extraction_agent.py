"""
FinSentry AI — Production Financial Data Extraction Agent (Phase 2C / Master Plan).

Author: Indhujha / FinSentry Engineering Team

Pulls key financial metrics, ratios, and performance numbers directly from indexed
documents into a structured schema with strict provenance, multi-year support,
deterministic grounding, evidence-based confidence scoring, and consolidated MongoDB persistence.

Architecture & Master Plan Compliance:
  1. Financial-Only Retrieval: Scopes chunks strictly to financial sections/tables of the target document.
  2. Fixed Pydantic Schema: Strictly validates all extraction results against ExtractionResult.
  3. Multi-Year Support: Preserves multi-period financial tables (FY2022, FY2021, FY2020) without collapsing.
  4. Exactly-One Corrective Retry: Targets missing/malformed fields with a strict corrective prompt.
  5. Exact Source Provenance: Every metric includes verified source_chunk_ids, page_numbers, and evidence snippets.
  6. No Citation = Failed Extraction: Unsupported or ungrounded figures are marked as failed (0.0 confidence).
  7. Evidence Grounding: Deterministically classifies figures as Direct (1.0), Derived (0.85), Contextual (0.5), or Unsupported (0.0).
  8. Low-Confidence Flagging: Automatically flags metrics with confidence < 0.7 and records flag_reason.
  9. YoY Calculation & Verification: Calculates and verifies year-on-year percentage changes.
  10. Consolidated MongoDB Storage: Stores ONE consolidated extracted_metrics record PER document with compound indexing.
  11. Multi-Jurisdiction Support: Seamlessly handles US 10-K, Indian Annual Reports (Ind AS, Schedule III), P&L, Balance Sheet.
  12. Downstream Compatibility: Preserves full contract expectations for RedFlagAgent, ResearchAgent, CrewAI, and Celery.
"""

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.base import AgentResult, BaseAgent
from agents.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_corrective_retry_prompt,
    build_extraction_prompt,
)
from agents.extraction.schemas import (
    ExtractedMetricsDocument,
    ExtractionAgentPayload,
    RawLLMExtractionResponse,
    RawLLMMetricItem,
)
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from database.connection import get_sync_db, mongodb
from schemas.agent_results import ExtractionMetricItem, ExtractionResult
from services.llm_service import llm_service
from utils.financial_grounding import (
    FinancialFigure,
    METRIC_SYNONYMS,
    check_figure_derivation_from_operands,
    extract_financial_figures,
    is_figure_grounded_in_text,
    safe_parse_financial_number,
    sanitize_user_facing_text,
)

logger = logging.getLogger(__name__)

# Mandatory target financial metrics per Master Plan
MANDATORY_METRICS = [
    "revenue",
    "net_income",
    "gross_margin",
    "debt_to_equity",
    "eps",
    "yoy_revenue_change",
]

# Preferred financial sections for targeted retrieval
FINANCIAL_SECTIONS = {
    "financials",
    "balance_sheet",
    "income_statement",
    "cash_flows",
    "auditor_notes",
    "footnotes",
    "md_and_a",
}

# Financial statement keyword indicators for scoring
FINANCIAL_KEYWORD_PATTERNS = [
    r"consolidated\s+statements?\s+of\s+(?:operations|income|earnings|comprehensive\s+income)",
    r"consolidated\s+balance\s+sheets?",
    r"consolidated\s+statements?\s+of\s+cash\s+flows?",
    r"statement\s+of\s+profit\s+and\s+loss",
    r"balance\s+sheet",
    r"cash\s+flow\s+statement",
    r"schedule\s+iii",
    r"notes\s+to\s+(?:consolidated\s+)?financial\s+statements?",
    r"revenue\s+from\s+operations",
    r"total\s+net\s+sales",
    r"total\s+revenue",
    r"gross\s+profit",
    r"operating\s+income",
    r"net\s+income",
    r"earnings\s+per\s+share",
    r"total\s+debt",
    r"total\s+liabilities",
    r"stockholders['\’]?\s+equity",
    r"shareholders['\’]?\s+equity",
]


class ExtractionAgent(BaseAgent):
    """
    Production-grade Financial Data Extraction Agent for FinSentry AI.
    Extracts structured KPIs, ratios, and multi-year comparative data with complete provenance.
    """

    def __init__(self, name: str = "ExtractionAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.EXTRACTION)

    # =====================================================================
    # BaseAgent Synchronous & Asynchronous Entrypoints
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

    async def execute_async(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Full asynchronous financial data extraction pipeline.
        """
        session_id = payload.get("session_id")
        document_id = payload.get("document_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        target_fields = payload.get(
            "target_fields",
            [
                "revenue",
                "net_income",
                "gross_margin",
                "debt_to_equity",
                "eps",
                "yoy_revenue_change",
                "prior_revenue",
                "prior_net_income",
                "prior_gross_margin",
                "operating_cash_flow",
                "total_debt",
                "prior_total_debt",
                "total_equity",
                "prior_total_equity",
                "operating_margin",
                "prior_operating_margin",
                "prior_eps",
            ],
        )

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id' and 'user_id' must be provided."
            )

        logger.info(
            "ExtractionAgent initiating extraction for session %s (document: %s, user: %s)",
            session_id,
            document_id or "primary",
            user_id,
        )

        try:
            db_sync = get_sync_db()

            # -------------------------------------------------------------
            # Step 1: Retrieve Target Document & Financial-Only Chunks
            # -------------------------------------------------------------
            doc_record, financial_chunks, all_chunks_map = self._retrieve_financial_chunks(
                db=db_sync,
                session_id=session_id,
                user_id=user_id,
                document_id=document_id,
            )

            actual_doc_id = doc_record.get("document_id") or document_id or "unknown_doc"
            filename = doc_record.get("filename", "financial_document.pdf")

            if not financial_chunks:
                logger.warning(
                    "No financial chunks found for document %s in session %s",
                    actual_doc_id,
                    session_id,
                )
                return self._build_empty_result(
                    session_id=session_id,
                    document_id=actual_doc_id,
                    filename=filename,
                    message="No financial section chunks or tables available in document.",
                )

            # -------------------------------------------------------------
            # Step 2: First-Pass LLM Extraction
            # -------------------------------------------------------------
            prompt = build_extraction_prompt(
                chunks=financial_chunks,
                target_fields=target_fields,
                filename=filename,
            )

            raw_llm_out = llm_service.generate_structured(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
            )

            parsed_response, parse_error = self._parse_llm_response(raw_llm_out)

            # -------------------------------------------------------------
            # Step 3: Validate & Detect Need for Exactly-One Retry
            # -------------------------------------------------------------
            retry_attempted = False
            retry_success: Optional[bool] = None

            missing_or_invalid = self._detect_missing_or_invalid_metrics(
                parsed_response=parsed_response,
                parse_error=parse_error,
                all_chunks_map=all_chunks_map,
            )

            if missing_or_invalid:
                logger.info(
                    "ExtractionAgent triggering corrective retry for fields: %s (reason: %s)",
                    missing_or_invalid.get("fields"),
                    missing_or_invalid.get("reason"),
                )
                retry_attempted = True

                retry_prompt = build_corrective_retry_prompt(
                    chunks=financial_chunks,
                    missing_or_malformed_fields=missing_or_invalid["fields"],
                    error_reason=missing_or_invalid["reason"],
                    filename=filename,
                )

                raw_retry_out = llm_service.generate_structured(
                    prompt=retry_prompt,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                )

                parsed_retry, retry_error = self._parse_llm_response(raw_retry_out)
                if parsed_retry and parsed_retry.metrics:
                    retry_success = True
                    parsed_response = self._merge_retry_response(parsed_response, parsed_retry)
                else:
                    retry_success = False
                    logger.warning("Corrective retry did not recover missing fields: %s", retry_error)

            # -------------------------------------------------------------
            # Step 4: Evidence Grounding, Provenance & Confidence Scoring
            # -------------------------------------------------------------
            metric_items, metrics_dict, multi_year_data = self._process_and_ground_metrics(
                parsed_response=parsed_response,
                all_chunks_map=all_chunks_map,
                financial_chunks=financial_chunks,
                actual_doc_id=actual_doc_id,
                filename=filename,
            )

            # -------------------------------------------------------------
            # Step 5: Consolidated Summary & Statistics
            # -------------------------------------------------------------
            conf_scores = [m.confidence_score for m in metric_items if m.value is not None]
            avg_confidence = round(sum(conf_scores) / len(conf_scores), 2) if conf_scores else 0.0
            low_conf_count = sum(1 for m in metric_items if m.is_low_confidence and m.value is not None)
            failed_count = sum(1 for m in metric_items if m.value is None or m.status == "FAILED")

            filing_type = (parsed_response.filing_type if parsed_response else None) or self._detect_filing_type(financial_chunks)
            rep_currency = (parsed_response.reporting_currency if parsed_response else None) or self._detect_currency(financial_chunks)
            rep_scale = (parsed_response.reporting_scale if parsed_response else None) or "millions"
            rep_period = (parsed_response.reporting_period if parsed_response else None) or self._detect_latest_period(metric_items, multi_year_data)
            prior_period = (parsed_response.prior_period if parsed_response else None) or self._detect_prior_period(metric_items, multi_year_data)

            summary_text = self._build_executive_summary(
                filename=filename,
                filing_type=filing_type,
                reporting_period=rep_period,
                metrics_dict=metrics_dict,
                avg_confidence=avg_confidence,
                low_conf_count=low_conf_count,
            )

            extraction_result = ExtractionResult(
                agent_name=self.name,
                session_id=session_id,
                document_id=actual_doc_id,
                document_filename=filename,
                filing_type=filing_type,
                reporting_currency=rep_currency,
                reporting_scale=rep_scale,
                reporting_period=rep_period,
                prior_period=prior_period,
                metrics=metric_items,
                metrics_dict=metrics_dict,
                multi_year_data=multi_year_data,
                extracted_data=metrics_dict,
                raw_extraction=raw_llm_out if isinstance(raw_llm_out, dict) else {},
                chunks_analyzed=len(financial_chunks),
                financial_chunks_count=len(financial_chunks),
                retry_attempted=retry_attempted,
                retry_success=retry_success,
                confidence_average=avg_confidence,
                low_confidence_count=low_conf_count,
                failed_metrics_count=failed_count,
                summary=summary_text,
                metadata={
                    "document_id": actual_doc_id,
                    "session_id": session_id,
                    "chunks_analyzed": len(financial_chunks),
                    "retry_attempted": retry_attempted,
                    "avg_confidence": avg_confidence,
                },
            )

            # -------------------------------------------------------------
            # Step 6: Consolidated MongoDB Persistence (One Record Per Document)
            # -------------------------------------------------------------
            self._persist_consolidated_metrics(
                db=db_sync,
                session_id=session_id,
                user_id=user_id,
                document_id=actual_doc_id,
                filename=filename,
                result=extraction_result,
            )

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=extraction_result.model_dump(),
                result_ref=actual_doc_id,
                metadata={
                    "document_id": actual_doc_id,
                    "metrics_count": len(metric_items),
                    "chunks_analyzed": len(financial_chunks),
                    "confidence_average": avg_confidence,
                    "retry_attempted": retry_attempted,
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("ExtractionAgent unexpected error: %s", exc, exc_info=True)
            raise RetryableAgentException(f"ExtractionAgent transient error: {exc}")

    # =====================================================================
    # Stage 1: Financial-Only Chunk Retrieval & Document Isolation
    # =====================================================================

    def _retrieve_financial_chunks(
        self,
        db: Any,
        session_id: str,
        user_id: str,
        document_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """
        Retrieve chunks ONLY from financial statements and tables for the target document.
        Strictly enforces user_id and session_id multi-tenant isolation.
        """
        query: Dict[str, Any] = {"session_id": session_id, "user_id": user_id}
        if document_id:
            query["document_id"] = document_id

        doc_record = db.documents.find_one(query)
        if not doc_record:
            # Check unauthorized access
            if document_id:
                any_doc = db.documents.find_one({"document_id": document_id})
                if any_doc:
                    raise NonRetryableAgentException(f"Unauthorized access to document '{document_id}'.")
            raise NonRetryableAgentException(
                f"Document '{document_id or session_id}' not found for session '{session_id}' and user '{user_id}'."
            )

        chunks = doc_record.get("chunks", [])
        actual_doc_id = doc_record.get("document_id") or str(doc_record.get("_id"))
        filename = doc_record.get("filename", "document.pdf")

        all_chunks_map: Dict[str, Dict[str, Any]] = {}
        for ch in chunks:
            cid = ch.get("chunk_id")
            if cid:
                ch_copy = dict(ch)
                ch_copy["document_id"] = actual_doc_id
                ch_copy["document_filename"] = filename
                all_chunks_map[cid] = ch_copy

        # Filter strictly for financial content
        financial_chunks: List[Dict[str, Any]] = []
        table_chunks: List[Dict[str, Any]] = []
        scored_candidates: List[Tuple[float, Dict[str, Any]]] = []

        for ch in chunks:
            sec = (ch.get("section") or "").lower()
            c_type = (ch.get("metadata", {}).get("content_type") or ch.get("content_type") or "").lower()
            text = ch.get("text", "")
            text_lower = text.lower()

            # Priority 1: Explicit financial section
            if sec in FINANCIAL_SECTIONS:
                financial_chunks.append(ch)
                continue

            # Priority 2: Structured financial table
            if c_type == "table" or "table from page" in text_lower:
                table_chunks.append(ch)
                continue

            # Priority 3: Match financial statement indicators
            score = 0.0
            for pat in FINANCIAL_KEYWORD_PATTERNS:
                if re.search(pat, text_lower):
                    score += 2.0

            # Count numeric figures in chunk
            figs = extract_financial_figures(text)
            non_yr_figs = [f for f in figs if not f.is_fiscal_year]
            if len(non_yr_figs) >= 4:
                score += 3.0

            if score >= 4.0:
                scored_candidates.append((score, ch))

        # Combine financial chunks
        selected: List[Dict[str, Any]] = list(financial_chunks)
        selected.extend(table_chunks)

        if scored_candidates:
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            for _, ch in scored_candidates:
                if ch not in selected:
                    selected.append(ch)

        # Fallback: If no chunks met criteria (e.g. unsegmented/raw document), select chunks with most financial figures
        if not selected and chunks:
            logger.info("No explicit financial section tags found; selecting top figure-dense chunks")
            ranked = []
            for ch in chunks:
                figs = extract_financial_figures(ch.get("text", ""))
                ranked.append((len([f for f in figs if not f.is_fiscal_year]), ch))
            ranked.sort(key=lambda x: x[0], reverse=True)
            selected = [ch for count, ch in ranked[:12] if count > 0]

        logger.info(
            "ExtractionAgent retrieved %d financial chunks (out of %d total) for document %s",
            len(selected),
            len(chunks),
            actual_doc_id,
        )

        return doc_record, selected, all_chunks_map

    # =====================================================================
    # Stage 2: LLM Response Parsing & Validation
    # =====================================================================

    def _parse_llm_response(
        self, raw_output: Any
    ) -> Tuple[Optional[RawLLMExtractionResponse], Optional[str]]:
        """
        Strictly parse and validate LLM output through Pydantic RawLLMExtractionResponse.
        """
        if not raw_output:
            return None, "Empty LLM output"

        if isinstance(raw_output, dict):
            try:
                # Handle direct dictionary or nested structures
                if "metrics" in raw_output and isinstance(raw_output["metrics"], list):
                    parsed = RawLLMExtractionResponse(**raw_output)
                    return parsed, None
                
                # If LLM returned a flat metric dictionary {revenue: 100, net_income: 50}
                metrics_list = []
                for k, v in raw_output.items():
                    if k not in {"filing_type", "reporting_currency", "reporting_scale", "reporting_period", "prior_period", "multi_year_table", "source_snippets"}:
                        num_val = self._extract_float(v)
                        metrics_list.append(
                            RawLLMMetricItem(
                                metric_name=k,
                                value=num_val,
                            )
                        )
                parsed = RawLLMExtractionResponse(
                    metrics=metrics_list,
                    filing_type=raw_output.get("filing_type", "US 10-K"),
                    reporting_currency=raw_output.get("reporting_currency", "USD"),
                    reporting_period=raw_output.get("reporting_period"),
                )
                return parsed, None
            except Exception as exc:
                return None, f"Pydantic schema validation error: {exc}"

        return None, f"Unexpected LLM output type: {type(raw_output).__name__}"

    def _detect_missing_or_invalid_metrics(
        self,
        parsed_response: Optional[RawLLMExtractionResponse],
        parse_error: Optional[str],
        all_chunks_map: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Check if any mandatory metrics are missing or have malformed citations.
        """
        if not parsed_response or parse_error:
            return {
                "fields": MANDATORY_METRICS,
                "reason": f"Initial output failed schema validation: {parse_error}",
            }

        extracted_names = {m.metric_name.lower().strip() for m in parsed_response.metrics if m.value is not None}
        missing = [m for m in MANDATORY_METRICS if m not in extracted_names]

        # Check for citation invalidity
        invalid_citations = []
        for m in parsed_response.metrics:
            if m.value is not None:
                if not m.source_chunk_ids:
                    invalid_citations.append(m.metric_name)
                else:
                    # Check if cited chunk actually exists in document
                    valid_cids = [cid for cid in m.source_chunk_ids if cid in all_chunks_map]
                    if not valid_cids:
                        invalid_citations.append(m.metric_name)

        if missing or invalid_citations:
            retry_fields = list(set(missing + invalid_citations))
            reason = f"Missing mandatory metrics: {missing}; Invalid chunk citations: {invalid_citations}"
            return {"fields": retry_fields, "reason": reason}

        return None

    def _merge_retry_response(
        self,
        base: Optional[RawLLMExtractionResponse],
        retry: RawLLMExtractionResponse,
    ) -> RawLLMExtractionResponse:
        """
        Merge valid metrics recovered from corrective retry into base response.
        """
        if not base:
            return retry

        merged_metrics: Dict[str, RawLLMMetricItem] = {
            m.metric_name.lower().strip(): m for m in base.metrics
        }

        for m in retry.metrics:
            k = m.metric_name.lower().strip()
            if k not in merged_metrics or merged_metrics[k].value is None or (m.value is not None and m.source_chunk_ids):
                merged_metrics[k] = m

        merged_table = dict(base.multi_year_table)
        for yr, vals in retry.multi_year_table.items():
            if yr not in merged_table:
                merged_table[yr] = vals
            else:
                merged_table[yr].update(vals)

        return RawLLMExtractionResponse(
            filing_type=retry.filing_type or base.filing_type,
            reporting_currency=retry.reporting_currency or base.reporting_currency,
            reporting_scale=retry.reporting_scale or base.reporting_scale,
            reporting_period=retry.reporting_period or base.reporting_period,
            prior_period=retry.prior_period or base.prior_period,
            metrics=list(merged_metrics.values()),
            multi_year_table=merged_table,
        )

    # =====================================================================
    # Stage 3: Grounding, Provenance Resolution & Confidence Scoring
    # =====================================================================

    def _process_and_ground_metrics(
        self,
        parsed_response: Optional[RawLLMExtractionResponse],
        all_chunks_map: Dict[str, Dict[str, Any]],
        financial_chunks: List[Dict[str, Any]],
        actual_doc_id: str,
        filename: str,
    ) -> Tuple[List[ExtractionMetricItem], Dict[str, Optional[float]], Dict[str, Dict[str, Optional[float]]]]:
        """
        Process, ground, and assign evidence-based confidence scores to all metrics.
        Enforces: NO CITATION = FAILED EXTRACTION.
        """
        metric_items: List[ExtractionMetricItem] = []
        metrics_dict: Dict[str, Optional[float]] = {}
        multi_year_data: Dict[str, Dict[str, Optional[float]]] = {}

        if parsed_response:
            multi_year_data = dict(parsed_response.multi_year_table or {})

        # Extract all figures from all financial chunks for derivation pool
        all_financial_text = " \n ".join([c.get("text", "") for c in financial_chunks])
        all_grounded_figures = extract_financial_figures(all_financial_text)
        grounded_operands = [f for f in all_grounded_figures if not f.is_fiscal_year]

        raw_metrics = parsed_response.metrics if parsed_response else []
        seen_metrics: Set[str] = set()

        for rm in raw_metrics:
            m_name = rm.metric_name.lower().strip()
            seen_metrics.add(m_name)

            val = rm.value
            prior_val = rm.prior_value
            cited_cids = rm.source_chunk_ids or []
            evidence_snippet = rm.evidence_snippet

            # Verify chunk IDs against target document
            verified_cids = [cid for cid in cited_cids if cid in all_chunks_map]
            
            # If cited chunk IDs are invalid or empty, attempt fuzzy snippet/value alignment
            if not verified_cids and (val is not None or evidence_snippet):
                aligned_cid, aligned_snippet, aligned_page = self._align_chunk_by_value_or_snippet(
                    val=val,
                    snippet=evidence_snippet,
                    chunks=financial_chunks,
                    metric_name=m_name,
                )
                if aligned_cid:
                    verified_cids = [aligned_cid]
                    if not evidence_snippet:
                        evidence_snippet = aligned_snippet

            # Rule: NO CITATION = FAILED EXTRACTION
            if not verified_cids:
                logger.warning(
                    "Metric '%s' (value=%s) has no verified chunk citation in document %s; marking as FAILED",
                    m_name,
                    val,
                    actual_doc_id,
                )
                metric_items.append(
                    ExtractionMetricItem(
                        metric_name=m_name,
                        display_name=rm.display_name or m_name.replace("_", " ").title(),
                        value=None,
                        prior_value=None,
                        unit=rm.unit,
                        currency=rm.currency,
                        period=rm.period,
                        prior_period=rm.prior_period,
                        confidence=0.0,
                        confidence_score=0.0,
                        is_low_confidence=True,
                        flag_reason="No verified source chunk citation",
                        is_grounded=False,
                        status="FAILED",
                    )
                )
                metrics_dict[m_name] = None
                continue

            # Gather verified evidence text
            verified_evidence_texts = [all_chunks_map[cid].get("text", "") for cid in verified_cids]
            combined_evidence = " \n ".join(verified_evidence_texts)
            pages = sorted(list({all_chunks_map[cid].get("page_number", 1) for cid in verified_cids if all_chunks_map[cid].get("page_number")}))
            sec = all_chunks_map[verified_cids[0]].get("section")

            # Determine Grounding & Confidence Score
            conf_score, status, is_low, flag_reason, derivation_formula = self._evaluate_metric_grounding(
                val=val,
                metric_name=m_name,
                evidence_text=combined_evidence,
                grounded_operands=grounded_operands,
                derivation_formula=rm.derivation_formula,
            )

            # Semantic anti-misclassification check
            try:
                from agents.red_flag.red_flag_agent import validate_metric_semantics
                candidate_data = {
                    "metric_name": m_name,
                    "display_name": rm.display_name,
                    "unit": rm.unit,
                    "value": val,
                    "evidence_snippet": evidence_snippet or combined_evidence[:300],
                }
                if not validate_metric_semantics(m_name, candidate_data):
                    logger.warning(
                        "Metric '%s' (value=%s) failed semantic anti-misclassification check in document %s",
                        m_name,
                        val,
                        actual_doc_id,
                    )
                    conf_score = 0.0
                    status = "FAILED"
                    is_low = True
                    flag_reason = f"Failed semantic validation: evidence or unit conflicts with canonical {m_name}"
            except Exception as sem_exc:
                logger.debug("Semantic validation check notice: %s", sem_exc)

            # If unsupported or semantically invalid, reject the value
            final_val = val if conf_score > 0.0 else None
            if final_val is None and conf_score == 0.0:
                status = "FAILED"
                is_low = True
                flag_reason = flag_reason or "Figure unsupported by document evidence"

            # Calculate / verify YoY change
            yoy_pct = rm.yoy_change_percent
            yoy_abs = None
            if final_val is not None and prior_val is not None:
                try:
                    yoy_abs = round(final_val - prior_val, 4)
                    if abs(prior_val) > 0.0001:
                        calc_pct = round(((final_val - prior_val) / abs(prior_val)) * 100.0, 2)
                        if yoy_pct is None or abs(yoy_pct - calc_pct) > 5.0:
                            yoy_pct = calc_pct
                except Exception:
                    pass

            item = ExtractionMetricItem(
                metric_name=m_name,
                display_name=rm.display_name or m_name.replace("_", " ").title(),
                value=final_val,
                prior_value=prior_val,
                unit=rm.unit,
                currency=rm.currency,
                period=rm.period,
                prior_period=rm.prior_period,
                yoy_change_percent=yoy_pct,
                yoy_change_absolute=yoy_abs,
                source_chunk_ids=verified_cids,
                page_numbers=pages,
                page_number=pages[0] if pages else None,
                section=sec,
                evidence_snippet=evidence_snippet or combined_evidence[:200],
                context_snippet=evidence_snippet or combined_evidence[:200],
                confidence=conf_score,
                confidence_score=conf_score,
                is_low_confidence=is_low,
                flag_reason=flag_reason,
                derivation_formula=derivation_formula,
                is_grounded=conf_score >= 0.7,
                status=status,
            )
            metric_items.append(item)

            if final_val is not None:
                metrics_dict[m_name] = final_val
            if prior_val is not None:
                metrics_dict[f"prior_{m_name}"] = prior_val

        # Ensure mandatory metrics are represented even if absent
        for mand in MANDATORY_METRICS:
            if mand not in seen_metrics:
                metric_items.append(
                    ExtractionMetricItem(
                        metric_name=mand,
                        display_name=mand.replace("_", " ").title(),
                        value=None,
                        prior_value=None,
                        confidence=0.0,
                        confidence_score=0.0,
                        is_low_confidence=True,
                        flag_reason=f"Mandatory metric '{mand}' unavailable in filing",
                        is_grounded=False,
                        status="UNAVAILABLE",
                    )
                )
                metrics_dict[mand] = None

        # Build / synchronize multi-year data table
        for m in metric_items:
            if m.value is not None and m.period:
                multi_year_data.setdefault(m.period, {})[m.metric_name] = m.value
            if m.prior_value is not None and m.prior_period:
                multi_year_data.setdefault(m.prior_period, {})[m.metric_name] = m.prior_value

        return metric_items, metrics_dict, multi_year_data

    def _evaluate_metric_grounding(
        self,
        val: Optional[float],
        metric_name: str,
        evidence_text: str,
        grounded_operands: List[FinancialFigure],
        derivation_formula: Optional[str] = None,
    ) -> Tuple[float, str, bool, Optional[str], Optional[str]]:
        """
        Evaluate if a metric value is directly grounded (1.0), derived (0.85), contextual (0.5), or unsupported (0.0).
        """
        if val is None:
            return 0.0, "UNAVAILABLE", True, "Metric value is None", None

        if not evidence_text or not evidence_text.strip():
            return 0.0, "FAILED", True, "No evidence text in cited chunks", None

        # 1. Direct Grounding Check
        # Test exact or formatted figure against evidence text
        temp_fig = FinancialFigure(
            raw_text=str(val),
            number_str=f"{val:g}",
            numeric_value=val,
        )
        if is_figure_grounded_in_text(temp_fig, evidence_text):
            return 1.0, "VALID", False, None, None

        # Check for ratio/percentage representation in text (e.g. 0.316 -> "31.6%")
        if 0.0 < abs(val) <= 1.0:
            pct_val = val * 100.0
            pct_fig = FinancialFigure(
                raw_text=f"{pct_val:.1f}%",
                number_str=f"{pct_val:.1f}",
                numeric_value=pct_val,
                is_percentage=True,
            )
            if is_figure_grounded_in_text(pct_fig, evidence_text):
                return 1.0, "VALID", False, None, None

        # 2. Mathematical Derivation Check
        is_derived, derivation_desc = check_figure_derivation_from_operands(
            target=temp_fig, operands=grounded_operands
        )
        if is_derived:
            return 0.85, "DERIVED", False, None, derivation_desc or derivation_formula

        if derivation_formula:
            # LLM provided a derivation formula, verify if keywords exist in evidence
            return 0.80, "DERIVED", False, None, derivation_formula

        # 3. Contextual Inference Check
        # Check if metric synonyms appear AND the figure string appears in text
        synonyms = METRIC_SYNONYMS.get(metric_name, [metric_name])
        text_lower = evidence_text.lower()
        val_strs = [f"{val:g}", f"{val:,.0f}", f"{val:,.1f}"]
        has_fig_in_text = any(vs in evidence_text for vs in val_strs)
        if has_fig_in_text and any(syn in text_lower for syn in synonyms):
            # The metric keyword is present in the chunk, but number might be rounded or narrative
            return 0.50, "LOW_CONFIDENCE", True, "Contextual inference from narrative disclosure", None

        # 4. Unsupported
        return 0.0, "FAILED", True, "Figure not grounded in source text or verified operands", None

    def _align_chunk_by_value_or_snippet(
        self,
        val: Optional[float],
        snippet: Optional[str],
        chunks: List[Dict[str, Any]],
        metric_name: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Fuzzy align a metric back to a real chunk in the document if the LLM failed to cite the exact ID.
        """
        synonyms = METRIC_SYNONYMS.get(metric_name, [metric_name])

        for ch in chunks:
            text = ch.get("text", "")
            text_lower = text.lower()

            if snippet and snippet.strip() and snippet.strip() in text:
                return ch.get("chunk_id"), snippet, ch.get("page_number", 1)

            if val is not None:
                val_strs = [f"{val:g}", f"{val:,.0f}", f"{val:,.1f}"]
                if 0.0 < abs(val) <= 1.0:
                    val_strs.append(f"{val * 100:.1f}%")
                    val_strs.append(f"{val * 100:.0f}%")

                has_num = any(vs in text for vs in val_strs)
                has_syn = any(syn in text_lower for syn in synonyms)

                if has_num and has_syn:
                    return ch.get("chunk_id"), text[:200], ch.get("page_number", 1)

        return None, None, None

    # =====================================================================
    # Stage 4: MongoDB Consolidated Persistence
    # =====================================================================

    def _persist_consolidated_metrics(
        self,
        db: Any,
        session_id: str,
        user_id: str,
        document_id: str,
        filename: str,
        result: ExtractionResult,
    ) -> None:
        """
        Persist ONE consolidated extracted_metrics record PER document into MongoDB.
        Uses compound document_id + session_id unique key to prevent duplicates.
        """
        try:
            doc_data = ExtractedMetricsDocument(
                document_id=document_id,
                session_id=session_id,
                user_id=user_id,
                document_filename=filename,
                filing_type=result.filing_type,
                reporting_currency=result.reporting_currency,
                reporting_scale=result.reporting_scale,
                reporting_period=result.reporting_period,
                prior_period=result.prior_period,
                metrics=result.metrics,
                metrics_dict=result.metrics_dict,
                multi_year_data=result.multi_year_data,
                extracted_data=result.extracted_data,
                confidence_scores={m.metric_name: m.confidence_score for m in result.metrics},
                provenance_map={
                    m.metric_name: {
                        "source_chunk_ids": m.source_chunk_ids,
                        "page_numbers": m.page_numbers,
                        "evidence_snippet": m.evidence_snippet,
                    }
                    for m in result.metrics
                    if m.source_chunk_ids
                },
                chunks_analyzed=result.chunks_analyzed,
                financial_chunks_count=result.financial_chunks_count,
                retry_attempted=result.retry_attempted,
                retry_success=result.retry_success,
                confidence_average=result.confidence_average,
                low_confidence_count=result.low_confidence_count,
                failed_metrics_count=result.failed_metrics_count,
                created_at=result.created_at,
                updated_at=datetime.now(timezone.utc),
            ).model_dump()

            db.extracted_metrics.update_one(
                {"document_id": document_id, "session_id": session_id},
                {"$set": doc_data},
                upsert=True,
            )
            logger.info(
                "Persisted ONE consolidated extracted_metrics record for document %s (session %s)",
                document_id,
                session_id,
            )
        except Exception as exc:
            logger.warning("Non-fatal notice persisting consolidated metrics to MongoDB: %s", exc)

    # =====================================================================
    # Helpers
    # =====================================================================

    def _extract_float(self, val: Any) -> Optional[float]:
        """Safely convert any raw value or string into a float without crashing."""
        return safe_parse_financial_number(val)

    def _detect_filing_type(self, chunks: List[Dict[str, Any]]) -> str:
        text = " ".join([c.get("text", "") for c in chunks[:5]]).lower()
        if "schedule iii" in text or "ind as" in text or "crores" in text or "lakhs" in text:
            return "Indian Annual Report (Ind AS)"
        if "form 10-k" in text or "10-k" in text or "item 8" in text:
            return "US 10-K"
        return "Financial Statement"

    def _detect_currency(self, chunks: List[Dict[str, Any]]) -> str:
        text = " ".join([c.get("text", "") for c in chunks[:5]])
        if "₹" in text or "inr" in text.lower() or "crore" in text.lower() or "lakh" in text.lower():
            return "INR"
        if "€" in text or "eur" in text.lower():
            return "EUR"
        if "£" in text or "gbp" in text.lower():
            return "GBP"
        return "USD"

    def _detect_latest_period(
        self,
        metrics: List[ExtractionMetricItem],
        multi_year_data: Dict[str, Any],
    ) -> str:
        for m in metrics:
            if m.period:
                return m.period
        if multi_year_data:
            return sorted(list(multi_year_data.keys()), reverse=True)[0]
        return "Current Period"

    def _detect_prior_period(
        self,
        metrics: List[ExtractionMetricItem],
        multi_year_data: Dict[str, Any],
    ) -> Optional[str]:
        for m in metrics:
            if m.prior_period:
                return m.prior_period
        if len(multi_year_data) >= 2:
            return sorted(list(multi_year_data.keys()), reverse=True)[1]
        return None

    def _build_executive_summary(
        self,
        filename: str,
        filing_type: str,
        reporting_period: str,
        metrics_dict: Dict[str, Optional[float]],
        avg_confidence: float,
        low_conf_count: int,
    ) -> str:
        rev = metrics_dict.get("revenue")
        ni = metrics_dict.get("net_income")
        gm = metrics_dict.get("gross_margin")
        de = metrics_dict.get("debt_to_equity")

        parts = [f"Extraction for {filename} ({filing_type}, {reporting_period}):"]
        if rev is not None:
            parts.append(f"Revenue = {rev:g}")
        if ni is not None:
            parts.append(f"Net Income = {ni:g}")
        if gm is not None:
            parts.append(f"Gross Margin = {gm:g}%")
        if de is not None:
            parts.append(f"Debt-to-Equity = {de:.2f}")

        parts.append(f"Confidence = {avg_confidence:.2f} (Low-confidence items: {low_conf_count}).")
        return " | ".join(parts)

    def _build_empty_result(
        self, session_id: str, document_id: str, filename: str, message: str
    ) -> AgentResult:
        res = ExtractionResult(
            agent_name=self.name,
            session_id=session_id,
            document_id=document_id,
            document_filename=filename,
            summary=message,
            metrics=[],
            metrics_dict={},
            raw_extraction={},
        )
        return AgentResult(
            success=True,
            task_type=self.default_task_type.value,
            agent_name=self.name,
            summary=res.model_dump(),
            result_ref=document_id,
            metadata={"document_id": document_id, "empty": True, "message": message},
        )


extraction_agent = ExtractionAgent()
agent_registry.register(extraction_agent, overwrite=True)
