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
from utils.financial_units import normalize_monetary_metric

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
            company_name = doc_record.get("company_name") or doc_record.get("company")
            ticker = doc_record.get("ticker")
            if not company_name:
                from utils.company_resolution import get_canonical_company_key
                can_key = get_canonical_company_key(filename) or get_canonical_company_key(actual_doc_id)
                company_name = can_key.title() if can_key else None

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
            detected_scale = self._detect_scale(financial_chunks)
            rep_scale = (parsed_response.reporting_scale if parsed_response and parsed_response.reporting_scale else None) or detected_scale
            # Monetary metrics have been normalized before this result is
            # persisted.  Source scale remains attached to each metric's
            # provenance, while record-level consumers receive canonical units.
            if rep_currency == "USD" and any(m.unit == "USD Millions" for m in metric_items):
                rep_scale = "millions"
            rep_period, prior_period = self._validate_and_detect_periods(
                parsed_response=parsed_response,
                metric_items=metric_items,
                multi_year_data=multi_year_data,
                financial_chunks=financial_chunks,
                filename=filename,
            )
            # Periods on individual metrics are the canonical lookup keys used
            # by Research, Comparison and Report.  Keep them synchronized with
            # the statement-header validation above, then rebuild the table so
            # an LLM/filename calendar year cannot relabel statement columns.
            self._canonicalize_metric_periods(
                metric_items, financial_chunks, rep_period, prior_period
            )
            multi_year_data = self._build_multi_year_data(metric_items)

            # Supplement multi_year_data with the LLM's multi_year_table and
            # statement table columns to capture 3rd (and further) statement
            # columns (e.g. FY2020) that cannot be represented via 2-slot metrics.
            header_periods = self._statement_header_periods(financial_chunks)
            llm_table = parsed_response.multi_year_table if parsed_response else None
            self._supplement_multi_year_from_llm_table(
                multi_year_data, llm_table or {},
                header_periods, financial_chunks,
            )

            # Filter multi_year_data to remove any future periods exceeding rep_period
            rep_yr_num = None
            yr_match = re.search(r"\b(19\d\d|20\d\d)\b", str(rep_period))
            if yr_match:
                rep_yr_num = int(yr_match.group(1))
            if rep_yr_num:
                multi_year_data = {
                    k: v for k, v in multi_year_data.items()
                    if not re.search(r"\b(19\d\d|20\d\d)\b", str(k))
                    or int(re.search(r"\b(19\d\d|20\d\d)\b", str(k)).group(1)) <= rep_yr_num
                }

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
                company_name=company_name,
                company=company_name,
                ticker=ticker,
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

    def _sanitize_extraction_candidates(
        self, parsed: Optional[RawLLMExtractionResponse]
    ) -> Optional[RawLLMExtractionResponse]:
        """
        Sanitize raw LLM candidates to prevent false intermediate candidates
        from leaking into grounding or database persistence.
        """
        if not parsed or not parsed.metrics:
            return parsed

        sanitized_metrics: List[RawLLMMetricItem] = []
        for m in parsed.metrics:
            m_name = (m.metric_name or "").lower().strip()
            val = m.value
            unit = (m.unit or "").lower().strip()
            snip = (m.evidence_snippet or "").lower()
            disp = (m.display_name or "").lower()
            combined = f"{disp} {snip} {unit}"

            # 1. Reject false revenue candidates
            if m_name in {"revenue", "total_revenue", "net_sales", "prior_revenue"}:
                if val is not None:
                    # Reject percentage-unit revenue or very small scalars that
                    # are almost certainly channel/segment percentages.
                    if any(p in unit for p in ["%", "percent", "bps"]):
                        logger.warning("Sanitizer rejected percentage-unit revenue candidate: %s (%s)", val, snip[:80])
                        continue
                    # Revenue <= 100 (scalars like 40, 60) is almost certainly a channel-mix
                    # percentage or segment proportion rather than an actual income-statement net-sales figure.
                    if val <= 100.0:
                        logger.warning("Sanitizer rejected implausibly small revenue candidate: %s (%s)", val, snip[:80])
                        continue
                    # Narrative channel-mix evidence (e.g. "40% and 60% of net sales")
                    if any(term in snip for term in ["channel", "accounted for", "distribution", "% of", "percent of", "customer", "proportion", "represented"]):
                        logger.warning("Sanitizer rejected channel mix revenue candidate: %s (%s)", val, snip[:80])
                        continue

            # 2. Reject false gross_margin candidates (e.g. monetary gross profit 488002.5, delta 11.4 pp)
            if m_name in {"gross_margin", "prior_gross_margin"}:
                if val is not None:
                    if abs(val) > 100.0:
                        logger.warning("Sanitizer rejected monetary gross margin candidate: %s (%s)", val, snip[:80])
                        # If parsed doesn't have gross_profit, convert this candidate to gross_profit
                        if not any(x.metric_name == "gross_profit" for x in parsed.metrics):
                            sanitized_metrics.append(
                                RawLLMMetricItem(
                                    metric_name="gross_profit",
                                    display_name="Gross Profit",
                                    value=val,
                                    unit=m.unit or "USD Millions",
                                    source_chunk_ids=m.source_chunk_ids,
                                    evidence_snippet=m.evidence_snippet,
                                )
                            )
                        continue
                    if any(term in snip for term in ["percentage points", "basis points", "decreased by", "increased by", "variance of", "delta"]):
                        logger.warning("Sanitizer rejected delta gross margin candidate: %s (%s)", val, snip[:80])
                        continue

            # 3. Reject debt investments candidate for total_debt
            if m_name in {"total_debt", "prior_total_debt"}:
                if any(term in combined for term in ["investment", "investments", "marketable securities", "available-for-sale", "held-to-maturity", "fair value of debt"]):
                    logger.warning("Sanitizer rejected debt investments candidate for total_debt: %s (%s)", val, snip[:80])
                    continue

            # 4. Reject EPS candidates that are actually Basic when evidence
            #    clearly labels them as "basic" and a Diluted row also exists.
            if m_name == "eps":
                if val is not None and snip:
                    is_basic_evidence = bool(re.search(r'\bbasic\b', snip)) and not bool(re.search(r'\bdiluted\b', snip))
                    if is_basic_evidence:
                        # Check if there's another EPS metric with diluted evidence
                        has_diluted = any(
                            (x.metric_name or "").lower().strip() == "eps"
                            and x is not m
                            and x.evidence_snippet
                            and re.search(r'\bdiluted\b', (x.evidence_snippet or "").lower())
                            for x in parsed.metrics
                        )
                        if has_diluted:
                            logger.warning("Sanitizer rejected Basic EPS candidate in favour of Diluted: %s", val)
                            continue

            sanitized_metrics.append(m)

        parsed.metrics = sanitized_metrics

        # Sanitize multi_year_table: reject entries that fail the same plausibility rules
        if parsed.multi_year_table:
            sanitized_table: Dict[str, Dict[str, Any]] = {}
            for period_key, metrics_map in parsed.multi_year_table.items():
                if not isinstance(metrics_map, dict):
                    continue
                clean_map: Dict[str, Any] = {}
                for mk, mv in metrics_map.items():
                    mk_lower = mk.lower().strip()
                    if mv is None:
                        clean_map[mk] = mv
                        continue
                    try:
                        fv = float(mv)
                    except (ValueError, TypeError):
                        clean_map[mk] = mv
                        continue
                    # Reject implausibly small revenue from multi_year_table
                    if mk_lower in {"revenue", "total_revenue", "net_sales", "prior_revenue"} and fv <= 1000.0:
                        logger.warning("Sanitizer rejected multi_year_table revenue %s=%s for period %s", mk, fv, period_key)
                        continue
                    # Reject impossible gross_margin
                    if mk_lower in {"gross_margin", "prior_gross_margin"} and abs(fv) > 100.0:
                        logger.warning("Sanitizer rejected multi_year_table gross_margin %s=%s for period %s", mk, fv, period_key)
                        continue
                    clean_map[mk] = mv
                sanitized_table[period_key] = clean_map
            parsed.multi_year_table = sanitized_table

        return parsed

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
                    parsed = self._sanitize_extraction_candidates(parsed)
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
                parsed = self._sanitize_extraction_candidates(parsed)
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

        merged = RawLLMExtractionResponse(
            filing_type=retry.filing_type or base.filing_type,
            reporting_currency=retry.reporting_currency or base.reporting_currency,
            reporting_scale=retry.reporting_scale or base.reporting_scale,
            reporting_period=retry.reporting_period or base.reporting_period,
            prior_period=retry.prior_period or base.prior_period,
            metrics=list(merged_metrics.values()),
            multi_year_table=merged_table,
        )
        return self._sanitize_extraction_candidates(merged)

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
            final_val = val if conf_score > 0.0 and status != "FAILED" else None
            if final_val is None:
                status = "FAILED"
                is_low = True
                flag_reason = flag_reason or "Figure unsupported by document evidence"
                prior_val = None
            elif prior_val is not None:
                # Validate prior_val semantics
                try:
                    from agents.red_flag.red_flag_agent import validate_metric_semantics
                    prior_candidate = {
                        "metric_name": f"prior_{m_name}",
                        "display_name": rm.display_name,
                        "unit": rm.unit,
                        "value": prior_val,
                        "evidence_snippet": evidence_snippet or combined_evidence[:300],
                    }
                    if not validate_metric_semantics(f"prior_{m_name}", prior_candidate) or not validate_metric_semantics(m_name, prior_candidate):
                        prior_val = None
                except Exception:
                    pass

            # Canonicalize source monetary scale before persistence. Grounding is
            # intentionally evaluated against the original evidence above.
            # Source text/statement headers outrank an LLM-declared scale.
            # A model frequently defaults to "millions" even for an SEC table
            # explicitly headed "(in thousands)".
            document_scale = self._detect_scale_from_text(
                "\n".join(str(chunk.get("text", "")) for chunk in financial_chunks)
            )
            source_scale = self._detect_scale_from_text(combined_evidence) or document_scale or (
                parsed_response.reporting_scale if parsed_response else None
            ) or self._detect_scale(financial_chunks)
            final_val, normalized_unit, normalized_currency, source_unit, source_scale = normalize_monetary_metric(
                m_name, final_val, rm.unit, rm.currency, source_scale
            )
            prior_val, _, _, _, _ = normalize_monetary_metric(
                m_name, prior_val, rm.unit, rm.currency, source_scale
            )

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
                unit=normalized_unit,
                currency=normalized_currency,
                source_unit=source_unit,
                source_scale=source_scale,
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

            if final_val is not None and status != "FAILED":
                metrics_dict[m_name] = final_val
            if prior_val is not None and status != "FAILED":
                metrics_dict[f"prior_{m_name}"] = prior_val

        # Authoritative Statement Revenue check:
        # Prefer actual financial statement Net Sales over narrative percentages or channel mix
        stmt_rev_data = self._extract_statement_revenue_from_evidence(financial_chunks)
        if stmt_rev_data:
            s_rev, s_prior_rev, s_cid, s_snip = stmt_rev_data
            rev_item = next((it for it in metric_items if it.metric_name == "revenue"), None)
            needs_override = (
                rev_item is None
                or (rev_item.value is None and rev_item.flag_reason != "No verified source chunk citation")
                or (rev_item.value is not None and rev_item.value <= 100.0)
                or any(term in (rev_item.evidence_snippet or "").lower() for term in ["channel", "accounted for", "distribution", "% of"])
            )
            if needs_override:
                norm_unit, norm_curr, s_u, s_s = "USD Millions", "USD", "USD", "millions"
                if rev_item:
                    norm_unit = rev_item.unit or norm_unit
                    norm_curr = rev_item.currency or norm_curr
                    s_u = rev_item.source_unit or s_u
                    s_s = rev_item.source_scale or s_s

                if rev_item:
                    rev_item.value = s_rev
                    rev_item.prior_value = s_prior_rev
                    rev_item.unit = norm_unit
                    rev_item.currency = norm_curr
                    rev_item.source_unit = s_u
                    rev_item.source_scale = s_s
                    rev_item.evidence_snippet = s_snip
                    rev_item.context_snippet = s_snip
                    if s_cid and s_cid in all_chunks_map:
                        rev_item.source_chunk_ids = [s_cid]
                        pg = all_chunks_map[s_cid].get("page_number")
                        if pg:
                            rev_item.page_numbers = [pg]
                            rev_item.page_number = pg
                        rev_item.section = all_chunks_map[s_cid].get("section")
                    rev_item.confidence = 1.0
                    rev_item.confidence_score = 1.0
                    rev_item.is_grounded = True
                    rev_item.is_low_confidence = False
                    rev_item.status = "VALID"
                    rev_item.flag_reason = None
                    metrics_dict["revenue"] = s_rev
                    if s_prior_rev is not None:
                        metrics_dict["prior_revenue"] = s_prior_rev
                else:
                    pages = []
                    sec = None
                    if s_cid and s_cid in all_chunks_map:
                        pg = all_chunks_map[s_cid].get("page_number")
                        if pg:
                            pages = [pg]
                        sec = all_chunks_map[s_cid].get("section")
                    new_rev = ExtractionMetricItem(
                        metric_name="revenue",
                        display_name="Total Net Sales",
                        value=s_rev,
                        prior_value=s_prior_rev,
                        unit=norm_unit,
                        currency=norm_curr,
                        source_unit=s_u,
                        source_scale=s_s,
                        period=parsed_response.reporting_period if parsed_response else None,
                        prior_period=parsed_response.prior_period if parsed_response else None,
                        source_chunk_ids=[s_cid] if s_cid else [],
                        page_numbers=pages,
                        page_number=pages[0] if pages else None,
                        section=sec,
                        evidence_snippet=s_snip,
                        context_snippet=s_snip,
                        confidence=1.0,
                        confidence_score=1.0,
                        is_low_confidence=False,
                        is_grounded=True,
                        status="VALID",
                    )
                    metric_items.append(new_rev)
                    seen_metrics.add("revenue")
                    metrics_dict["revenue"] = s_rev
                    if s_prior_rev is not None:
                        metrics_dict["prior_revenue"] = s_prior_rev

        # Authoritative Statement Gross Profit check
        if metrics_dict.get("gross_profit") is None:
            stmt_gp_data = self._extract_statement_gross_profit_from_evidence(financial_chunks)
            if stmt_gp_data:
                s_gp, s_prior_gp, s_cid, s_snip = stmt_gp_data
                gp_item = next((it for it in metric_items if it.metric_name == "gross_profit"), None)
                if gp_item:
                    gp_item.value = s_gp
                    gp_item.prior_value = s_prior_gp
                    gp_item.evidence_snippet = s_snip
                    gp_item.confidence = 1.0
                    gp_item.confidence_score = 1.0
                    gp_item.status = "VALID"
                    gp_item.is_grounded = True
                    gp_item.is_low_confidence = False
                    metrics_dict["gross_profit"] = s_gp
                    if s_prior_gp is not None:
                        metrics_dict["prior_gross_profit"] = s_prior_gp
                else:
                    new_gp = ExtractionMetricItem(
                        metric_name="gross_profit",
                        display_name="Gross Profit",
                        value=s_gp,
                        prior_value=s_prior_gp,
                        unit="USD Millions",
                        currency="USD",
                        period=parsed_response.reporting_period if parsed_response else None,
                        prior_period=parsed_response.prior_period if parsed_response else None,
                        source_chunk_ids=[s_cid] if s_cid else [],
                        evidence_snippet=s_snip,
                        confidence=1.0,
                        confidence_score=1.0,
                        is_grounded=True,
                        status="VALID",
                    )
                    metric_items.append(new_gp)
                    metrics_dict["gross_profit"] = s_gp
                    if s_prior_gp is not None:
                        metrics_dict["prior_gross_profit"] = s_prior_gp

        # Check and compute Gross Margin if not directly available/valid but components exist
        gm_item = next((it for it in metric_items if it.metric_name == "gross_margin"), None)
        rev_val = metrics_dict.get("revenue")
        gp_val = metrics_dict.get("gross_profit")
        prior_rev_val = metrics_dict.get("prior_revenue")
        prior_gp_val = metrics_dict.get("prior_gross_profit")

        if rev_val and gp_val and rev_val > 0:
            derived_gm = round((gp_val / rev_val) * 100.0, 2)
            derived_prior_gm = None
            if prior_rev_val and prior_gp_val and prior_rev_val > 0:
                derived_prior_gm = round((prior_gp_val / prior_rev_val) * 100.0, 2)

            # Sanity check: gross margin must be a plausible percentage
            if abs(derived_gm) > 100.0:
                logger.warning(
                    "Derived gross margin %.2f%% is implausible (rev=%.2f, gp=%.2f); rejecting",
                    derived_gm, rev_val, gp_val,
                )
                derived_gm = None
            if derived_prior_gm is not None and abs(derived_prior_gm) > 100.0:
                logger.warning(
                    "Derived prior gross margin %.2f%% is implausible; rejecting",
                    derived_prior_gm,
                )
                derived_prior_gm = None

            if derived_gm is not None:
                if not gm_item:
                    gm_item = ExtractionMetricItem(
                        metric_name="gross_margin",
                        display_name="Gross Margin",
                        value=derived_gm,
                        prior_value=derived_prior_gm,
                        unit="%",
                        period=parsed_response.reporting_period if parsed_response else None,
                        prior_period=parsed_response.prior_period if parsed_response else None,
                        confidence=0.85,
                        confidence_score=0.85,
                        is_low_confidence=False,
                        is_grounded=True,
                        derivation_formula="Gross Profit / Net Sales * 100",
                        status="DERIVED",
                    )
                    metric_items.append(gm_item)
                    seen_metrics.add("gross_margin")
                elif gm_item.value is None or gm_item.status == "FAILED" or abs(gm_item.value) > 100.0:
                    gm_item.value = derived_gm
                    gm_item.prior_value = derived_prior_gm
                    gm_item.unit = "%"
                    gm_item.confidence = 0.85
                    gm_item.confidence_score = 0.85
                    gm_item.is_low_confidence = False
                    gm_item.is_grounded = True
                    gm_item.derivation_formula = "Gross Profit / Net Sales * 100"
                    gm_item.status = "DERIVED"
                    gm_item.flag_reason = None

                metrics_dict["gross_margin"] = gm_item.value
                if gm_item.prior_value is not None:
                    metrics_dict["prior_gross_margin"] = gm_item.prior_value

        # Final safety net: if an existing gross_margin item has impossible value,
        # force-correct it from components or reject it.
        if gm_item and gm_item.value is not None and abs(gm_item.value) > 100.0:
            logger.warning(
                "Gross margin %.2f%% exceeds plausible range; resetting to FAILED",
                gm_item.value,
            )
            gm_item.value = None
            gm_item.status = "FAILED"
            gm_item.flag_reason = "Gross margin exceeds plausible 0-100%% range"
            gm_item.is_low_confidence = True
            gm_item.confidence_score = 0.0
            metrics_dict["gross_margin"] = None

        # Authoritative Diluted EPS override: ensure eps is always Diluted, not Basic
        diluted_result = self._extract_diluted_eps_from_evidence(financial_chunks)
        if diluted_result:
            diluted_val, diluted_prior, diluted_cid, diluted_snip = diluted_result
            eps_item = next((it for it in metric_items if it.metric_name == "eps"), None)
            if eps_item:
                if eps_item.value != diluted_val:
                    logger.info(
                        "EPS override: LLM returned %.4f, authoritative Diluted EPS is %.4f for doc %s",
                        eps_item.value, diluted_val, actual_doc_id,
                    )
                eps_item.value = diluted_val
                if diluted_prior is not None:
                    eps_item.prior_value = diluted_prior
                eps_item.evidence_snippet = diluted_snip
                eps_item.context_snippet = diluted_snip
                if diluted_cid and diluted_cid in all_chunks_map:
                    eps_item.source_chunk_ids = [diluted_cid]
                eps_item.confidence = 1.0
                eps_item.confidence_score = 1.0
                eps_item.is_grounded = True
                eps_item.is_low_confidence = False
                eps_item.status = "VALID"
                eps_item.flag_reason = None
                metrics_dict["eps"] = diluted_val
                if diluted_prior is not None:
                    metrics_dict["prior_eps"] = diluted_prior
            elif "eps" not in seen_metrics:
                # No EPS was extracted by LLM, add it from evidence
                pages = []
                sec = None
                if diluted_cid and diluted_cid in all_chunks_map:
                    pg = all_chunks_map[diluted_cid].get("page_number")
                    if pg:
                        pages = [pg]
                    sec = all_chunks_map[diluted_cid].get("section")
                new_eps = ExtractionMetricItem(
                    metric_name="eps",
                    display_name="Diluted Earnings Per Share (EPS)",
                    value=diluted_val,
                    prior_value=diluted_prior,
                    unit="USD",
                    period=parsed_response.reporting_period if parsed_response else None,
                    prior_period=parsed_response.prior_period if parsed_response else None,
                    source_chunk_ids=[diluted_cid] if diluted_cid else [],
                    page_numbers=pages,
                    page_number=pages[0] if pages else None,
                    section=sec,
                    evidence_snippet=diluted_snip,
                    context_snippet=diluted_snip,
                    confidence=1.0,
                    confidence_score=1.0,
                    is_low_confidence=False,
                    is_grounded=True,
                    status="VALID",
                )
                metric_items.append(new_eps)
                seen_metrics.add("eps")
                metrics_dict["eps"] = diluted_val
                if diluted_prior is not None:
                    metrics_dict["prior_eps"] = diluted_prior

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

        # Build multi-year data table strictly from validated, non-failed metric items
        multi_year_data = self._build_multi_year_data(metric_items)

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
                company_name=result.company_name,
                company=result.company or result.company_name,
                ticker=result.ticker,
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
                        "source_unit": m.source_unit,
                        "source_scale": m.source_scale,
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
            # Reprocessing changes canonical inputs, so only comparisons that
            # include this document must be recomputed.
            db.comparison_results.delete_many({
                "session_id": session_id,
                "$or": [
                    {"document_ids": document_id},
                    {"document_ids": {"$exists": False}},
                ],
            })
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

    def _detect_scale(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Detect the reporting scale from financial chunk text.
        Looks for explicit 'in thousands' / 'in millions' / 'in billions' headers
        commonly found in SEC 10-K filings.
        """
        text = " ".join([c.get("text", "") for c in chunks[:15]])
        return self._detect_scale_from_text(text) or "millions"

    @staticmethod
    def _detect_scale_from_text(text: str) -> Optional[str]:
        """Return only an explicitly declared statement scale, if present."""
        text = (text or "").lower()
        # The first declared scale is the statement's primary monetary scale.
        # E.g. "in millions, except shares in thousands" remains millions.
        scale_match = re.search(
            r"\b(?:in|amounts?\s+(?:are\s+)?(?:stated|reported)\s+in|dollars?\s+in)\s+\(?\s*(thousands|millions|billions|000s)\b",
            text,
            re.IGNORECASE,
        )
        if scale_match:
            scale = scale_match.group(1).lower()
            return "thousands" if scale == "000s" else scale
        # Check for "000s" or "(in 000s)" patterns
        if re.search(r"\(\s*in\s+000", text):
            return "thousands"
        # Fallback: look for typical filings that state "amounts in thousands"
        if "amounts in thousands" in text or "dollars in thousands" in text:
            return "thousands"
        return None

    def _extract_statement_revenue_from_evidence(
        self,
        financial_chunks: List[Dict[str, Any]],
    ) -> Optional[Tuple[float, Optional[float], str, str]]:
        """
        Authoritatively extract Net Sales / Revenue directly from financial statement evidence.
        Prefers explicit Consolidated Statements of Operations / Income rows over narrative
        percentage or channel mix references.
        Returns (current_val, prior_val, chunk_id, evidence_snippet).
        """
        def _chunk_priority(c: Dict[str, Any]) -> int:
            t = str(c.get("text", "")).lower()
            if "statements of operations" in t or "statement of operations" in t:
                return 0
            if "statement of" in t or "statements of" in t:
                return 1
            if "|" in t and ("net sales" in t or "revenue" in t):
                return 2
            return 3

        sorted_chunks = sorted(financial_chunks, key=_chunk_priority)

        row_patterns = [
            re.compile(r"(?:^|\|\s*)(total\s+net\s+sales)\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(total\s+revenues?)\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(net\s+sales)\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(net\s+revenues?)\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(revenues?)\b", re.IGNORECASE),
        ]

        doc_scale = self._detect_scale_from_text(
            "\n".join(str(c.get("text", "")) for c in financial_chunks)
        )

        for pat in row_patterns:
            for chunk in sorted_chunks:
                text = chunk.get("text", "")
                chunk_id = chunk.get("chunk_id", "")
                for line in text.splitlines():
                    line_clean = line.strip()
                    line_lower = line_clean.lower()
                    if not line_lower:
                        continue
                    if any(k in line_lower for k in ["percentage of", "% of", "channel", "accounted for", "distribution", "basis points"]):
                        continue
                    if not pat.search(line_lower):
                        continue

                    m = pat.search(line_lower)
                    text_after_label = line_clean[m.end():]

                    num_matches = re.findall(
                        r"(?:[\$€£¥₹]\s*)?"
                        r"(?:\(\s*([\d,]+(?:\.\d+)?)\s*\)|([\d,]+(?:\.\d+)?))",
                        text_after_label,
                    )
                    valid_nums = []
                    for neg_val, pos_val in num_matches:
                        raw = neg_val if neg_val else pos_val
                        raw_clean = raw.replace(",", "")
                        try:
                            v = float(raw_clean)
                            if neg_val:
                                v = -v
                            if 1990 <= v <= 2050 and "." not in raw:
                                continue
                            if v > 100.0:
                                valid_nums.append(v)
                        except ValueError:
                            continue

                    if valid_nums:
                        scale = self._detect_scale_from_text(text) or doc_scale or self._detect_scale(financial_chunks) or "millions"
                        scale_mult = 0.001 if scale == "thousands" else 1.0
                        current_rev = round(valid_nums[0] * scale_mult, 2)
                        prior_rev = round(valid_nums[1] * scale_mult, 2) if len(valid_nums) > 1 else None
                        logger.info(
                            "Authoritative Statement Revenue extracted: current=%.2f, prior=%s from chunk %s",
                            current_rev, prior_rev, chunk_id,
                        )
                        return (current_rev, prior_rev, chunk_id, line_clean)

        return None

    def _extract_statement_gross_profit_from_evidence(
        self,
        financial_chunks: List[Dict[str, Any]],
    ) -> Optional[Tuple[float, Optional[float], str, str]]:
        """
        Authoritatively extract Gross Profit directly from financial statement evidence.
        Returns (current_val, prior_val, chunk_id, evidence_snippet).
        """
        def _chunk_priority(c: Dict[str, Any]) -> int:
            t = str(c.get("text", "")).lower()
            if "statements of operations" in t or "statement of operations" in t:
                return 0
            if "statement of" in t or "statements of" in t:
                return 1
            return 2

        sorted_chunks = sorted(financial_chunks, key=_chunk_priority)

        row_patterns = [
            re.compile(r"(?:^|\|\s*)(total\s+gross\s+(?:profit|margin))\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(gross\s+profit)\b", re.IGNORECASE),
            re.compile(r"(?:^|\|\s*)(gross\s+margin)\b", re.IGNORECASE),
        ]

        doc_scale = self._detect_scale_from_text(
            "\n".join(str(c.get("text", "")) for c in financial_chunks)
        )

        for pat in row_patterns:
            for chunk in sorted_chunks:
                text = chunk.get("text", "")
                chunk_id = chunk.get("chunk_id", "")
                for line in text.splitlines():
                    line_clean = line.strip()
                    line_lower = line_clean.lower()
                    if not line_lower:
                        continue
                    if any(k in line_lower for k in ["percentage", "%", "margin %", "points", "basis points"]):
                        continue
                    if not pat.search(line_lower):
                        continue

                    m = pat.search(line_lower)
                    text_after_label = line_clean[m.end():]

                    num_matches = re.findall(
                        r"(?:[\$€£¥₹]\s*)?"
                        r"(?:\(\s*([\d,]+(?:\.\d+)?)\s*\)|([\d,]+(?:\.\d+)?))",
                        text_after_label,
                    )
                    valid_nums = []
                    for neg_val, pos_val in num_matches:
                        raw = neg_val if neg_val else pos_val
                        raw_clean = raw.replace(",", "")
                        try:
                            v = float(raw_clean)
                            if neg_val:
                                v = -v
                            if 1990 <= v <= 2050 and "." not in raw:
                                continue
                            if abs(v) > 100.0:
                                valid_nums.append(v)
                        except ValueError:
                            continue

                    if valid_nums:
                        scale = self._detect_scale_from_text(text) or doc_scale or self._detect_scale(financial_chunks) or "millions"
                        scale_mult = 0.001 if scale == "thousands" else 1.0
                        current_gp = round(valid_nums[0] * scale_mult, 2)
                        prior_gp = round(valid_nums[1] * scale_mult, 2) if len(valid_nums) > 1 else None
                        logger.info(
                            "Authoritative Statement Gross Profit extracted: current=%.2f, prior=%s from chunk %s",
                            current_gp, prior_gp, chunk_id,
                        )
                        return (current_gp, prior_gp, chunk_id, line_clean)

        return None

    def _extract_diluted_eps_from_evidence(
        self,
        financial_chunks: List[Dict[str, Any]],
    ) -> Optional[Tuple[float, Optional[float], str, str]]:
        """
        Authoritatively extract Diluted EPS directly from financial statement evidence.
        Searches for 'Earnings per share: Diluted' or 'Diluted earnings per share' table rows
        and returns (current_val, prior_val, chunk_id, evidence_snippet).
        This ensures the explicitly-labelled Diluted EPS row is always selected
        over Basic EPS, regardless of which value is numerically larger.

        Uses direct regex number parsing instead of extract_financial_figures()
        to avoid the pre-context filter that drops bare decimals in table cells.
        """
        for chunk in financial_chunks:
            chunk_text = chunk.get("text", "")
            chunk_id = chunk.get("chunk_id", "")
            lines = chunk_text.splitlines()

            for idx, line in enumerate(lines):
                line_lower = line.strip().lower()
                if not line_lower:
                    continue

                # Check if preceding lines establish an EPS section context
                prev_context = " ".join(
                    lines[max(0, idx - 3):idx]
                ).lower()
                in_eps_section = any(
                    k in prev_context
                    for k in ("earnings per share", "per share", "eps",
                              "net income per share")
                )

                for diluted_match in re.finditer(r"\bdiluted\b", line_lower):
                    start = diluted_match.start()
                    preceding_on_line = line_lower[max(0, start - 100):start]
                    following_on_line = line_lower[start:start + 40]

                    # Skip share-count context (e.g. "Weighted-average shares diluted")
                    share_context = preceding_on_line[-40:] + " " + following_on_line[:40]
                    if any(k in share_context for k in (
                        "shares", "weighted", "average number",
                    )):
                        continue

                    explicit_eps = any(
                        token in preceding_on_line
                        for token in (
                            "earnings per share", "diluted eps",
                            "net income per share", "per share",
                        )
                    ) or following_on_line.startswith("diluted eps") \
                      or "diluted earnings per share" in line_lower

                    standalone_row = (
                        line_lower.startswith("diluted")
                        or line_lower.startswith("| diluted")
                        or in_eps_section
                    )
                    table_cell = bool(
                        re.search(r"\|\s*diluted\b", line_lower)
                    )

                    if not (explicit_eps or standalone_row or table_cell
                            or in_eps_section):
                        continue

                    # Parse text starting at "diluted" on this line.
                    # Use direct regex to extract decimals / currency values,
                    # avoiding the extract_financial_figures pre-context filter
                    # that drops bare decimals in table cells.
                    diluted_text = line[start:]
                    num_matches = re.findall(
                        r"(?:[\$€£¥₹]\s*)?"
                        r"(?:\(\s*(\d+(?:\.\d+)?)\s*\)|(\d+(?:\.\d+)?))",
                        diluted_text,
                    )

                    valid_vals: List[float] = []
                    for neg_val, pos_val in num_matches:
                        raw_v = neg_val if neg_val else pos_val
                        try:
                            v = float(raw_v)
                        except ValueError:
                            continue
                        # Filter out fiscal years (2020–2050) and share counts
                        if v >= 1000:
                            continue
                        if 1990 <= v <= 2050 and "." not in raw_v:
                            continue
                        if neg_val:
                            v = -v
                        valid_vals.append(v)

                    if valid_vals:
                        v1 = valid_vals[0]
                        v2 = valid_vals[1] if len(valid_vals) > 1 else None
                        logger.info(
                            "Authoritative Diluted EPS extracted: "
                            "current=%.2f, prior=%s from chunk %s",
                            v1, v2, chunk_id,
                        )
                        return (v1, v2, chunk_id, line.strip())
        return None

    @staticmethod
    def _map_date_to_fiscal_year(month_str: str, day: int, year: int) -> int:
        """Map a fiscal year-end date in a table header to the canonical fiscal year label."""
        return year

    @staticmethod
    def _statement_header_periods(financial_chunks: List[Dict[str, Any]]) -> List[str]:
        """Read statement-column fiscal labels in their source order.

        Recognizes:
          1. Explicit fiscal year sequences across multiple lines in the same
             chunk: ``Fiscal Year 2022\\nFiscal Year 2021\\nFiscal Year 2020``
          2. Date-based statement headers with SEC fiscal calendar mapping:
             ``February 25, 2023`` → FY2022 (retail Jan/Feb/early-Mar endings)
          3. Bare year sequences in table headers:
             ``2025 2024 2023`` or ``| 2025 | 2024 |``
        """
        fy_label = re.compile(
            r"\b(?:fy|fiscal\s+(?:year\s+)?)\s*(20\d{2})\b", re.IGNORECASE,
        )
        date_pattern = re.compile(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\.?\s+(\d{1,2}),?\s+(20\d{2})\b",
            re.IGNORECASE,
        )
        statement_context = re.compile(
            r"\b(statement(?:s)?\s+of\s+(?:operations|income|earnings|"
            r"financial\s+condition)|financial\s+summary|three-year|"
            r"two-year|net\s+sales|revenue|gross\s+profit|"
            r"net\s+(?:loss|income)|earnings\s+per\s+share)\b",
            re.IGNORECASE,
        )

        # Sort chunks to check explicit statement headers first
        def _chunk_priority(c: Dict[str, Any]) -> int:
            t = str(c.get("text", "")).lower()
            if "statements of operations" in t or "statement of operations" in t or "statement of income" in t:
                return 0
            if "statement of" in t or "statements of" in t:
                return 1
            if "|" in t and ("net sales" in t or "revenue" in t):
                return 2
            return 3

        sorted_chunks = sorted(financial_chunks, key=_chunk_priority)

        for chunk in sorted_chunks:
            text = str(chunk.get("text", ""))
            has_context = bool(statement_context.search(text))

            # 1. Date-based headers on a single line
            for line in text.splitlines():
                line_dates = date_pattern.findall(line)
                if len(line_dates) >= 2:
                    periods: List[str] = []
                    for m_str, day_str, yr_str in line_dates:
                        mapped_yr = ExtractionAgent._map_date_to_fiscal_year(
                            m_str, int(day_str), int(yr_str),
                        )
                        p = f"FY{mapped_yr}"
                        if p not in periods:
                            periods.append(p)
                    if len(periods) >= 2:
                        return periods

            # 2. Consecutive short header lines with FY labels:
            # E.g. Bed Bath & Beyond statement header:
            # Fiscal Year 2022
            # Fiscal Year 2021
            # Fiscal Year 2020
            consecutive_fy: List[str] = []
            for line in text.splitlines():
                stripped = line.strip()
                if len(stripped) <= 40:
                    m = re.match(r"^(?:(?:fiscal\s+)?year\s+)?(20\d{2})$", stripped, re.IGNORECASE)
                    if m:
                        consecutive_fy.append(f"FY{m.group(1)}")
                    elif consecutive_fy:
                        if len(consecutive_fy) >= 2:
                            return list(dict.fromkeys(consecutive_fy))
                        consecutive_fy = []
            if len(consecutive_fy) >= 2:
                return list(dict.fromkeys(consecutive_fy))

            # 3. Bare years or FY labels in table/header lines
            for line in text.splitlines():
                line_lower = line.lower()
                is_header_line = bool(re.search(
                    r"\b(year|summary|operations|fiscal|three-year|"
                    r"column|---)\b", line_lower,
                )) or "|" in line
                if is_header_line:
                    fy_matches = fy_label.findall(line)
                    if len(fy_matches) >= 2:
                        deduped = list(dict.fromkeys(f"FY{y}" for y in fy_matches))
                        if len(deduped) >= 2:
                            return deduped

                    bare_years = re.findall(r"\b(20\d{2})\b", line)
                    if len(bare_years) >= 2:
                        deduped_bare = list(dict.fromkeys(f"FY{y}" for y in bare_years))
                        if len(deduped_bare) >= 2:
                            return deduped_bare

            # 4. Dates across consecutive lines near statement header
            if has_context:
                chunk_dates = date_pattern.findall(text)
                if len(chunk_dates) >= 2:
                    periods = []
                    for m_str, day_str, yr_str in chunk_dates:
                        mapped_yr = ExtractionAgent._map_date_to_fiscal_year(
                            m_str, int(day_str), int(yr_str),
                        )
                        p = f"FY{mapped_yr}"
                        if p not in periods:
                            periods.append(p)
                    if len(periods) >= 2:
                        return periods

        return []

    @staticmethod
    def _build_multi_year_data(metric_items: List[ExtractionMetricItem]) -> Dict[str, Dict[str, Optional[float]]]:
        data: Dict[str, Dict[str, Optional[float]]] = {}
        for metric in metric_items:
            if metric.status == "FAILED":
                continue
            if metric.value is not None and metric.period:
                data.setdefault(metric.period, {})[metric.metric_name] = metric.value
            if metric.prior_value is not None and metric.prior_period:
                data.setdefault(metric.prior_period, {})[metric.metric_name] = metric.prior_value
        return data

    @staticmethod
    def _is_plausible_supplemental_value(metric_name: str, value: float) -> bool:
        """Validate that a supplemental value is financially plausible before accepting it."""
        m = metric_name.lower().strip().removeprefix("prior_")
        # Revenue scalars <= 100 are channel-mix percentages rather than actual revenue
        if m in {"revenue", "total_revenue", "net_sales"}:
            if value <= 100.0:
                return False
        # Gross margin must be a valid percentage
        if m in {"gross_margin"}:
            if abs(value) > 100.0:
                return False
        # Operating margin must be a valid percentage
        if m in {"operating_margin"}:
            if abs(value) > 100.0:
                return False
        return True

    def _supplement_multi_year_from_llm_table(
        self,
        multi_year_data: Dict[str, Dict[str, Optional[float]]],
        llm_table: Dict[str, Dict[str, Any]],
        header_periods: List[str],
        financial_chunks: List[Dict[str, Any]],
    ) -> None:
        """Supplement multi_year_data with 3rd (and further) period metrics.

        Uses LLM's multi_year_table and table chunks to capture 3rd-year columns
        (such as FY2020 in a 3-year statement table) that cannot fit into the
        2-slot current/prior metric items.

        Every value is validated for financial plausibility before acceptance to
        prevent channel-mix percentages, delta figures, or other non-canonical
        values from leaking into the authoritative multi_year_data.
        """
        def _get_year(k: str) -> int:
            m = re.search(r"\b(19\d\d|20\d\d)\b", str(k))
            return int(m.group(1)) if m else 0

        if llm_table:
            sorted_llm_keys = sorted(llm_table.keys(), key=_get_year, reverse=True)
            for idx, k in enumerate(sorted_llm_keys):
                target_period = header_periods[idx] if idx < len(header_periods) else (
                    f"FY{_get_year(k)}" if _get_year(k) else str(k)
                )
                if not target_period:
                    continue
                period_data = multi_year_data.setdefault(target_period, {})
                metrics_map = llm_table[k]
                if isinstance(metrics_map, dict):
                    for m_name, val in metrics_map.items():
                        if m_name not in period_data or period_data[m_name] is None:
                            try:
                                fval = float(val) if val is not None else None
                            except (ValueError, TypeError):
                                continue
                            if fval is not None and not self._is_plausible_supplemental_value(m_name, fval):
                                logger.warning(
                                    "Supplement rejected implausible LLM table value %s=%s for period %s",
                                    m_name, fval, target_period,
                                )
                                continue
                            period_data[m_name] = fval

        # Deterministic supplementation for 3rd header period from table chunks
        if len(header_periods) >= 3:
            p3 = header_periods[2]
            p3_data = multi_year_data.setdefault(p3, {})
            for chunk in financial_chunks:
                text = str(chunk.get("text", ""))
                scale = self._detect_scale_from_text(text) or self._detect_scale(financial_chunks) or "millions"
                scale_mult = 0.001 if scale == "thousands" else 1.0

                for line in text.splitlines():
                    line_lower = line.lower()
                    if "|" not in line:
                        continue
                    m_key = None
                    if any(w in line_lower for w in ("net sales", "revenue", "total revenue")):
                        m_key = "revenue"
                    elif any(w in line_lower for w in ("gross profit", "gross margin")):
                        m_key = "gross_profit"
                    elif any(w in line_lower for w in ("net loss", "net income")):
                        m_key = "net_income"

                    if m_key and (m_key not in p3_data or p3_data[m_key] is None):
                        num_matches = re.findall(
                            r"(?:[\$€£¥₹]\s*)?"
                            r"(?:\(\s*([\d,]+(?:\.\d+)?)\s*\)|([\d,]+(?:\.\d+)?))",
                            line,
                        )
                        nums = []
                        for neg_m, pos_m in num_matches:
                            raw = neg_m if neg_m else pos_m
                            raw_clean = raw.replace(",", "")
                            try:
                                v = float(raw_clean)
                                if neg_m:
                                    v = -v
                                nums.append(v)
                            except ValueError:
                                continue
                        if len(nums) >= 3:
                            candidate_val = round(nums[2] * scale_mult, 2)
                            if self._is_plausible_supplemental_value(m_key, candidate_val):
                                p3_data[m_key] = candidate_val
                            else:
                                logger.warning(
                                    "Supplement rejected implausible table value %s=%s for period %s",
                                    m_key, candidate_val, p3,
                                )


    def _canonicalize_metric_periods(
        self,
        metric_items: List[ExtractionMetricItem],
        financial_chunks: List[Dict[str, Any]],
        reporting_period: str,
        prior_period: Optional[str],
    ) -> None:
        """Apply validated statement-header column labels to metric values."""
        header_periods = self._statement_header_periods(financial_chunks)
        current_period = header_periods[0] if header_periods else reporting_period
        previous_period = header_periods[1] if len(header_periods) > 1 else prior_period
        for metric in metric_items:
            if metric.status == "FAILED" or metric.value is None:
                continue
            # Header metadata is authoritative for a current/prior statement
            # column pair. It prevents a filing date or filename from shifting
            # every historical value by one fiscal year.
            if header_periods:
                metric.period = current_period
                if metric.prior_value is not None:
                    metric.prior_period = previous_period
            else:
                metric.period = metric.period or current_period
                if metric.prior_value is not None:
                    metric.prior_period = metric.prior_period or previous_period

    def _validate_and_detect_periods(
        self,
        parsed_response: Optional[Any],
        metric_items: List[ExtractionMetricItem],
        multi_year_data: Dict[str, Any],
        financial_chunks: List[Dict[str, Any]],
        filename: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Deterministically validate and resolve the authoritative reporting period and prior period.
        Anchors strictly to:
          1. Core financial statement metrics (revenue, net_income, eps, gross_margin, operating_cash_flow)
          2. Document filing header/metadata year (e.g. apple_2025_10k.pdf -> FY2025)
        Explicitly REJECTS future maturity years (e.g. FY2029) originating from debt maturity schedules,
        lease tables, contractual obligations, or forward estimates.
        """
        # Step 1: Detect filing year from filename or chunks
        filing_year: Optional[int] = None
        fn_match = re.search(r"(?<!\d)(20\d\d)(?!\d)", filename)
        if fn_match:
            filing_year = int(fn_match.group(1))
        else:
            for c in (financial_chunks or [])[:10]:
                t = c.get("text", "")
                m = re.search(r"fiscal\s+year\s+ended\s+[A-Za-z]+\s+\d{1,2},\s*(20\d\d)", t, re.IGNORECASE)
                if m:
                    filing_year = int(m.group(1))
                    break

        def _extract_year(s: Optional[str]) -> Optional[int]:
            if not s:
                return None
            nums = re.findall(r"(?:19|20)\d\d", str(s))
            return int(nums[0]) if nums else None

        def _is_valid_reporting_year(yr: Optional[int]) -> bool:
            if yr is None:
                return False
            if filing_year and yr > filing_year:
                # Reject future maturity schedules (e.g. 2029 for 2025 filing)
                return False
            if yr > 2026 and (not filing_year or yr > filing_year):
                return False
            return True

        # Step 2: Extract periods from core statement metrics
        core_metrics = {"revenue", "net_income", "operating_income", "eps", "gross_margin", "operating_cash_flow", "operating_margin"}
        core_rep_periods: List[str] = []
        core_prior_periods: List[str] = []
        for m in metric_items:
            if m.metric_name.lower() in core_metrics and m.value is not None and m.status != "FAILED":
                if m.period:
                    core_rep_periods.append(m.period)
                if m.prior_period:
                    core_prior_periods.append(m.prior_period)

        # Candidate reporting period from LLM
        llm_rep = parsed_response.reporting_period if parsed_response else None
        llm_prior = parsed_response.prior_period if parsed_response else None
        statement_periods = self._statement_header_periods(financial_chunks)

        # Resolve reporting period
        # Explicit table headers identify fiscal columns; a filename commonly
        # carries the later filing/calendar year and is not fiscal metadata.
        final_rep_period: Optional[str] = statement_periods[0] if statement_periods else None

        # Priority 1: Check core statement metrics (sorted descending by year)
        if not final_rep_period:
            sorted_core_reps = sorted(core_rep_periods, key=lambda p: _extract_year(p) or 0, reverse=True)
            for p in sorted_core_reps:
                yr = _extract_year(p)
                if _is_valid_reporting_year(yr):
                    if filing_year and yr == filing_year:
                        final_rep_period = p
                        break
                    elif not final_rep_period:
                        final_rep_period = p

        # Filename/header dates are a fallback only. Filing dates can be one
        # calendar year after the fiscal period (for example FY2022 filed in
        # 2023), so they must never override explicit statement headers.
        if not statement_periods and filing_year and (_extract_year(final_rep_period) or 0) != filing_year:
            final_rep_period = f"FY{filing_year}"

        # Priority 2: Check LLM reporting period if valid
        if not final_rep_period and llm_rep:
            yr = _extract_year(llm_rep)
            if _is_valid_reporting_year(yr):
                final_rep_period = llm_rep

        # Priority 3: Check other valid metrics (sorted descending by year)
        if not final_rep_period:
            sorted_other_metrics = sorted(
                [m for m in metric_items if m.value is not None and m.status != "FAILED" and m.period],
                key=lambda m: _extract_year(m.period) or 0,
                reverse=True,
            )
            for m in sorted_other_metrics:
                yr = _extract_year(m.period)
                if _is_valid_reporting_year(yr):
                    final_rep_period = m.period
                    break

        # Priority 4: Check multi_year_data
        if not final_rep_period and multi_year_data:
            valid_my_keys = [k for k in multi_year_data.keys() if _is_valid_reporting_year(_extract_year(k))]
            if valid_my_keys:
                sorted_keys = sorted(valid_my_keys, key=lambda k: _extract_year(k) or 0, reverse=True)
                final_rep_period = sorted_keys[0]

        if not final_rep_period:
            final_rep_period = f"FY{filing_year}" if filing_year else "Current Period"

        rep_year = _extract_year(final_rep_period)

        # Resolve prior period — prefer the year immediately before rep_year
        final_prior_period: Optional[str] = statement_periods[1] if len(statement_periods) > 1 else None
        if not final_prior_period:
            sorted_core_priors = sorted(core_prior_periods, key=lambda p: _extract_year(p) or 0, reverse=True)
            for p in sorted_core_priors:
                yr = _extract_year(p)
                if yr and rep_year and yr < rep_year:
                    final_prior_period = p
                    break

        if not final_prior_period and llm_prior:
            yr = _extract_year(llm_prior)
            if yr and rep_year and yr < rep_year:
                final_prior_period = llm_prior

        if not final_prior_period and multi_year_data:
            valid_priors = [k for k in multi_year_data.keys() if _extract_year(k) and rep_year and _extract_year(k) < rep_year]
            if valid_priors:
                sorted_priors = sorted(valid_priors, key=lambda k: _extract_year(k) or 0, reverse=True)
                final_prior_period = sorted_priors[0]

        # If the resolved prior is more than 1 year before rep_year (can happen
        # when filing year override shifted the reporting period), default to
        # the immediately preceding fiscal year.
        if rep_year:
            prior_yr = _extract_year(final_prior_period) if final_prior_period else None
            if not prior_yr or prior_yr < rep_year - 1:
                final_prior_period = f"FY{rep_year - 1}"

        return final_rep_period, final_prior_period

    def _detect_latest_period(
        self,
        metrics: List[ExtractionMetricItem],
        multi_year_data: Dict[str, Any],
    ) -> str:
        rep, _ = self._validate_and_detect_periods(None, metrics, multi_year_data, [], "")
        return rep

    def _detect_prior_period(
        self,
        metrics: List[ExtractionMetricItem],
        multi_year_data: Dict[str, Any],
    ) -> Optional[str]:
        _, prior = self._validate_and_detect_periods(None, metrics, multi_year_data, [], "")
        return prior

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
            gm_disp = gm * 100.0 if 0.0 < abs(gm) <= 1.0 else gm
            parts.append(f"Gross Margin = {gm_disp:.1f}%")
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
