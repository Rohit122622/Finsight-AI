"""
FinSentry AI — Production Red Flag Agent (Phase 2C / Master Architecture).

Author: Sajjan Pawar / FinSentry Engineering Team

Proactively scans company financial information for forensic anomalies, solvency risks,
and disclosure concerns without requiring explicit user prompts.

Architecture:
  1. Deterministic Quantitative Rule Engine (Debt surge, margin compression, OCF divergence, revenue contraction)
  2. Targeted Qualitative LLM Analysis via Hybrid RetrievalService (Going concern, litigation, restatements, internal controls)
  3. NLP & FinBERT Sentiment Extension Point
  4. Fixed Deterministic Severity Rubric (LOW, MEDIUM, HIGH)
  5. Semantic Deduplication with Multi-Source Citation Preservation
  6. Explainable One-Sentence Non-Finance Summaries
  7. Quantitative and Qualitative Source Chunk Provenance Resolution
  8. Deterministic Weighted Risk Score Formula (Max 100)
  9. Anti-Leakage Grounding (Stripping internal chunk IDs from user-facing text)
  10. MongoDB Persistence (red_flags collection) & Celery Registry Contract
"""

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from database.connection import get_sync_db, mongodb
from schemas.agent_results import RedFlagItem, RedFlagResult
from schemas.retrieval import MetadataFilter, RetrievalMode, RetrievalRequest
from services.llm_service import llm_service
from services.nlp_service import nlp_service
from services.retrieval_service import retrieval_service
from utils.financial_grounding import extract_financial_figures, sanitize_user_facing_text

logger = logging.getLogger(__name__)

# =====================================================================
# Deterministic Financial Risk Threshold Constants
# =====================================================================
DEBT_GROWTH_MEDIUM_THRESHOLD = 0.20       # 20% YoY debt growth
DEBT_GROWTH_HIGH_THRESHOLD = 0.40         # 40% YoY debt growth
MARGIN_DROP_MEDIUM_THRESHOLD = 0.05       # 5% gross/operating margin drop
MARGIN_DROP_HIGH_THRESHOLD = 0.10         # 10% gross/operating margin drop
REVENUE_DROP_MEDIUM_THRESHOLD = 0.05      # 5% YoY revenue decline
REVENUE_DROP_HIGH_THRESHOLD = 0.15        # 15% YoY revenue decline
LEVERAGE_DE_HIGH_THRESHOLD = 4.0          # Debt-to-Equity > 4.0
LEVERAGE_GROWTH_HIGH_THRESHOLD = 0.50     # 50% YoY D/E growth
LEVERAGE_GROWTH_MED_THRESHOLD = 0.25      # 25% YoY D/E growth

QUALITATIVE_QUERIES = [
    "auditor qualifications going concern opinion adverse audit opinion explanatory paragraph substantial doubt",
    "pending litigation legal proceedings DOJ SEC regulatory investigations material lawsuits",
    "related-party transactions loans to directors executive dealings affiliated entity transactions",
    "executive management turnover CEO CFO resignations unexpected departure key officers",
    "restatement of financial results revised financial statements prior period errors misstatements",
    "material weaknesses internal control over financial reporting significant deficiencies SOX 404",
    "debt covenant violations debt restructuring defaults credit rating downgrades liquidity risk credit agreement breach",
]


class RedFlagAgent(BaseAgent):
    """
    Production-grade Red Flag Agent for forensic accounting and financial risk detection.
    """

    def __init__(self, name: str = "RedFlagAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.RED_FLAG_ANALYSIS)

    # =====================================================================
    # BaseAgent Execution Interface
    # =====================================================================

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Synchronous execution entrypoint conforming to FinSentry BaseAgent and Celery contracts.
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
    # Core Asynchronous Forensic Pipeline
    # =====================================================================

    async def execute_async(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Asynchronous multi-stage forensic audit pipeline.
        """
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        company_name = payload.get("company_name") or payload.get("entity_name")
        if not company_name and session_id:
            try:
                db_sync = get_sync_db()
                doc_record = db_sync.documents.find_one({"session_id": session_id})
                if doc_record:
                    fn = doc_record.get("filename", "")
                    base = fn.split(".")[0]
                    parts = [
                        p
                        for p in base.replace("_", " ").replace("-", " ").split()
                        if p.lower()
                        not in {
                            "10k",
                            "10q",
                            "annual",
                            "report",
                            "filing",
                            "2020",
                            "2021",
                            "2022",
                            "2023",
                            "2024",
                            "2025",
                            "2026",
                            "pdf",
                            "txt",
                            "md",
                        }
                    ]
                    if parts:
                        company_name = " ".join(parts).title()
            except Exception:
                pass
        if not company_name:
            company_name = "the company"

        metrics_input = payload.get("metrics") or payload.get("extracted_metrics")
        risk_focus = payload.get("risk_focus")
        document_ids = payload.get("document_ids") or (
            [payload["document_id"]] if payload.get("document_id") else None
        )

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id' and 'user_id' must be provided."
            )

        logger.info(
            "RedFlagAgent initiating forensic scan for session %s (user: %s, company: %s)",
            session_id,
            user_id,
            company_name,
        )

        try:
            if mongodb._database is None:
                try:
                    await mongodb.connect()
                except Exception as db_exc:
                    logger.debug("MongoDB auto-connect notice: %s", db_exc)

            all_flags: List[RedFlagItem] = []

            # -------------------------------------------------------------
            # Step 1: Resolve Quantitative Metrics & Provenance
            # -------------------------------------------------------------
            if not metrics_input and session_id:
                try:
                    db_sync = get_sync_db()
                    db_metrics = list(db_sync.extracted_metrics.find({"session_id": session_id}))
                    if db_metrics:
                        metrics_input = db_metrics
                except Exception as m_exc:
                    logger.debug("Database metric lookup notice: %s", m_exc)

            normalized_metrics, initial_provenance = self._extract_normalized_metrics_with_provenance(metrics_input)

            # Resolve quantitative provenance back to indexed document chunks
            prov_map = self._resolve_quantitative_provenance(
                session_id=session_id,
                user_id=user_id,
                document_ids=document_ids,
                metrics=normalized_metrics,
                initial_provenance=initial_provenance,
            )

            quant_flags = self.scan_quantitative_metrics(normalized_metrics, provenance_map=prov_map)
            all_flags.extend(quant_flags)
            quant_count = len(quant_flags)
            logger.info("Quantitative rule engine produced %d flags with chunk provenance", quant_count)

            # -------------------------------------------------------------
            # Step 2: Targeted Qualitative LLM Analysis with Grounding
            # -------------------------------------------------------------
            qual_flags = await self.scan_qualitative_documents(
                session_id=session_id,
                user_id=user_id,
                company_name=company_name,
                risk_focus=risk_focus,
                document_ids=document_ids,
            )
            all_flags.extend(qual_flags)
            qual_count = len(qual_flags)
            logger.info("Qualitative document scan produced %d flags", qual_count)

            # -------------------------------------------------------------
            # Step 3: Semantic Deduplication with Provenance Union
            # -------------------------------------------------------------
            deduped_flags = self._deduplicate_flags(all_flags)

            # -------------------------------------------------------------
            # Step 4: Anti-Leakage Grounding Sanitization
            # -------------------------------------------------------------
            sanitized_flags = self._sanitize_flags(deduped_flags)

            # -------------------------------------------------------------
            # Step 5: Deterministic Scoring & Executive Assessment
            # -------------------------------------------------------------
            high_count = sum(1 for f in sanitized_flags if f.severity == "HIGH")
            risk_score = self._compute_deterministic_risk_score(sanitized_flags)

            overall_assessment = self._build_overall_assessment(
                company_name=company_name,
                flags=sanitized_flags,
                risk_score=risk_score,
                quant_count=quant_count,
                qual_count=qual_count,
            )

            primary_doc_id = document_ids[0] if document_ids else None
            red_flag_res = RedFlagResult(
                agent_name=self.name,
                session_id=session_id,
                company_name=company_name,
                total_flags=len(sanitized_flags),
                high_severity_count=high_count,
                flags=sanitized_flags,
                risk_score=risk_score,
                overall_assessment=overall_assessment,
                quantitative_flags_count=quant_count,
                qualitative_flags_count=len(sanitized_flags) - quant_count,
                metadata={
                    "total_analyzed": len(all_flags),
                    "deduplicated_count": len(sanitized_flags),
                    "document_ids": document_ids,
                    "finbert_active": nlp_service.is_available,
                },
            )

            # -------------------------------------------------------------
            # Step 6: MongoDB Persistence
            # -------------------------------------------------------------
            self._persist_to_db(session_id, red_flag_res, user_id=user_id, document_id=primary_doc_id)

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=red_flag_res.model_dump(),
                result_ref=session_id,
                metadata={
                    "total_flags": red_flag_res.total_flags,
                    "high_severity_count": red_flag_res.high_severity_count,
                    "risk_score": red_flag_res.risk_score,
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("Error in RedFlagAgent execution: %s", exc, exc_info=True)
            raise RetryableAgentException(f"RedFlagAgent transient failure: {exc}")

    # =====================================================================
    # Stage 1: Deterministic Quantitative Risk Rules
    # =====================================================================

    def scan_quantitative_metrics(
        self,
        metrics: Dict[str, Any],
        provenance_map: Optional[Dict[str, Any]] = None,
    ) -> List[RedFlagItem]:
        """
        Run deterministic, explainable quantitative checks on extracted numeric metrics.
        Thresholds are fixed by forensic audit standards and never decided by the LLM.
        Every flag attaches exact source_chunk_ids and page/section provenance where available.
        """
        flags: List[RedFlagItem] = []
        if not metrics:
            return flags

        prov_map = provenance_map or {}

        def _get_prov(m_key: str) -> Dict[str, Any]:
            p = prov_map.get(m_key)
            if p:
                return p
            # Fallback alias check
            for k, v in prov_map.items():
                if m_key in k or k in m_key:
                    return v
            return {}

        def _build_flag_meta(m_key: str, default_evidence: str) -> Dict[str, Any]:
            p = _get_prov(m_key)
            cids = p.get("source_chunk_ids") or ([p["chunk_id"]] if p.get("chunk_id") else [])
            return {
                "source_chunk_ids": cids,
                "page_number": p.get("page_number"),
                "section": p.get("section"),
                "document_filename": p.get("document_filename"),
                "document_id": p.get("document_id"),
                "evidence_snippet": p.get("evidence_snippet") or default_evidence,
            }

        # -------------------------------------------------------------
        # Rule 1: Total Debt Growth (Surge)
        # -------------------------------------------------------------
        debt = metrics.get("total_debt")
        prior_debt = metrics.get("prior_total_debt")
        if debt is not None and prior_debt is not None and prior_debt > 0:
            growth = (debt - prior_debt) / prior_debt
            meta = _build_flag_meta("total_debt", f"total_debt={debt:g}, prior_total_debt={prior_debt:g}")
            if growth >= DEBT_GROWTH_HIGH_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Solvency",
                        title="Significant Debt Growth",
                        description=(
                            f"Total debt surged {growth:.1%} year-over-year (from {prior_debt:g} to {debt:g}), "
                            f"exceeding the {DEBT_GROWTH_HIGH_THRESHOLD:.0%} severe growth threshold."
                        ),
                        source="QUANTITATIVE",
                        metric_name="total_debt",
                        recommendation="Review debt maturity profiles, interest coverage ratios, and refinancing constraints.",
                        **meta,
                    )
                )
            elif growth >= DEBT_GROWTH_MEDIUM_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="MEDIUM",
                        category="Solvency",
                        title="Rising Debt",
                        description=(
                            f"Total debt grew {growth:.1%} year-over-year (from {prior_debt:g} to {debt:g}), "
                            f"exceeding the {DEBT_GROWTH_MEDIUM_THRESHOLD:.0%} monitoring threshold."
                        ),
                        source="QUANTITATIVE",
                        metric_name="total_debt",
                        recommendation="Monitor leverage trajectories and liquidity reserves.",
                        **meta,
                    )
                )

        # -------------------------------------------------------------
        # Rule 2: Gross Margin Compression
        # -------------------------------------------------------------
        margin = metrics.get("gross_margin")
        prior_margin = metrics.get("prior_gross_margin")
        if margin is not None and prior_margin is not None:
            drop = prior_margin - margin
            meta = _build_flag_meta("gross_margin", f"gross_margin={margin:.3f}, prior_gross_margin={prior_margin:.3f}")
            if drop >= MARGIN_DROP_HIGH_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Profitability",
                        title="Severe Gross Margin Compression",
                        description=(
                            f"Gross margin compressed sharply by {drop * 100:.1f} percentage points (from "
                            f"{prior_margin * 100:.1f}% to {margin * 100:.1f}%), signaling acute pricing pressure or rising cost structure."
                        ),
                        source="QUANTITATIVE",
                        metric_name="gross_margin",
                        recommendation="Investigate product pricing, inventory write-downs, or supply chain inflation.",
                        **meta,
                    )
                )
            elif drop >= MARGIN_DROP_MEDIUM_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="MEDIUM",
                        category="Profitability",
                        title="Falling Gross Margin",
                        description=(
                            f"Gross margin declined by {drop * 100:.1f} percentage points (from "
                            f"{prior_margin * 100:.1f}% to {margin * 100:.1f}%), exceeding the 5% margin compression threshold."
                        ),
                        source="QUANTITATIVE",
                        metric_name="gross_margin",
                        recommendation="Analyze margin pressure by segment or geography.",
                        **meta,
                    )
                )

        # -------------------------------------------------------------
        # Rule 3: Operating Margin Compression
        # -------------------------------------------------------------
        op_margin = metrics.get("operating_margin")
        prior_op_margin = metrics.get("prior_operating_margin")
        if op_margin is not None and prior_op_margin is not None:
            op_drop = prior_op_margin - op_margin
            meta = _build_flag_meta("operating_margin", f"operating_margin={op_margin:.3f}, prior_operating_margin={prior_op_margin:.3f}")
            if op_drop >= MARGIN_DROP_HIGH_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Profitability",
                        title="Severe Operating Margin Compression",
                        description=(
                            f"Operating margin fell {op_drop * 100:.1f} percentage points (from "
                            f"{prior_op_margin * 100:.1f}% to {op_margin * 100:.1f}%), indicating severe operational cost inflation."
                        ),
                        source="QUANTITATIVE",
                        metric_name="operating_margin",
                        recommendation="Audit SG&A overhead and operational efficiency.",
                        **meta,
                    )
                )
            elif op_drop >= MARGIN_DROP_MEDIUM_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="MEDIUM",
                        category="Profitability",
                        title="Declining Operating Margin",
                        description=(
                            f"Operating margin declined {op_drop * 100:.1f} percentage points (from "
                            f"{prior_op_margin * 100:.1f}% to {op_margin * 100:.1f}%)."
                        ),
                        source="QUANTITATIVE",
                        metric_name="operating_margin",
                        recommendation="Review operating expense trends.",
                        **meta,
                    )
                )

        # -------------------------------------------------------------
        # Rule 4: Operating Cash Flow Anomaly & Divergence
        # -------------------------------------------------------------
        ocf = metrics.get("operating_cash_flow")
        if ocf is not None and ocf < 0:
            net_income = metrics.get("net_income")
            meta = _build_flag_meta("operating_cash_flow", f"operating_cash_flow={ocf:g}")
            if net_income is not None and net_income > 0:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Accounting",
                        title="Operating Cash Flow Divergence",
                        description=(
                            f"Operating cash flow is negative ({ocf:g}) despite positive reported net income ({net_income:g}), "
                            "indicating potential earnings quality risk, aggressive accruals, or working capital deterioration."
                        ),
                        source="QUANTITATIVE",
                        metric_name="operating_cash_flow",
                        recommendation="Perform forensic analysis on accounts receivable, inventory build, and non-cash revenue recognition.",
                        **meta,
                    )
                )
            else:
                flags.append(
                    RedFlagItem(
                        severity="MEDIUM",
                        category="Solvency",
                        title="Negative Operating Cash Flow",
                        description=f"Operating cash flow is negative at {ocf:g}, indicating ongoing operational cash burn.",
                        source="QUANTITATIVE",
                        metric_name="operating_cash_flow",
                        recommendation="Assess cash runway and near-term financing requirements.",
                        **meta,
                    )
                )

        # -------------------------------------------------------------
        # Rule 5: Debt-to-Equity & Balance Sheet Leverage
        # -------------------------------------------------------------
        equity = metrics.get("total_equity")
        prior_equity = metrics.get("prior_total_equity")
        de_meta = _build_flag_meta("debt_to_equity", f"total_debt={debt}, total_equity={equity}")
        if not de_meta.get("source_chunk_ids"):
            # fallback to debt or equity chunks
            debt_prov = _get_prov("total_debt")
            eq_prov = _get_prov("total_equity")
            de_meta["source_chunk_ids"] = debt_prov.get("source_chunk_ids") or eq_prov.get("source_chunk_ids") or []
            de_meta["page_number"] = debt_prov.get("page_number") or eq_prov.get("page_number")
            de_meta["section"] = debt_prov.get("section") or eq_prov.get("section")
            de_meta["document_filename"] = debt_prov.get("document_filename") or eq_prov.get("document_filename")
            de_meta["document_id"] = debt_prov.get("document_id") or eq_prov.get("document_id")

        if equity is not None and equity < 0:
            flags.append(
                RedFlagItem(
                    severity="HIGH",
                    category="Solvency",
                    title="Negative Stockholders' Equity Deficit",
                    description=(
                        f"Stockholders' equity is negative at {equity:g}, indicating cumulative losses exceeding invested capital "
                        "and severe balance sheet distress."
                    ),
                    source="QUANTITATIVE",
                    metric_name="total_equity",
                    recommendation="Evaluate debt restructuring options and emergency recapitalization capacity.",
                    **de_meta,
                )
            )
        elif debt is not None and equity is not None and equity > 0:
            de_ratio = debt / equity
            if prior_debt is not None and prior_equity is not None and prior_equity > 0:
                prior_de = prior_debt / prior_equity
                de_growth = (de_ratio - prior_de) / prior_de if prior_de > 0 else 0.0
                if de_growth >= LEVERAGE_GROWTH_HIGH_THRESHOLD:
                    flags.append(
                        RedFlagItem(
                            severity="HIGH",
                            category="Solvency",
                            title="Deteriorating Debt-to-Equity Leverage",
                            description=(
                                f"Debt-to-equity ratio worsened by {de_growth:.1%} year-over-year (from "
                                f"{prior_de:.2f} to {de_ratio:.2f}), reflecting increased balance sheet vulnerability."
                            ),
                            source="QUANTITATIVE",
                            metric_name="debt_to_equity",
                            recommendation="Review capital structure and covenant compliance.",
                            **de_meta,
                        )
                    )
                elif de_growth >= LEVERAGE_GROWTH_MED_THRESHOLD:
                    flags.append(
                        RedFlagItem(
                            severity="MEDIUM",
                            category="Solvency",
                            title="Rising Debt-to-Equity Ratio",
                            description=(
                                f"Debt-to-equity ratio rose {de_growth:.1%} year-over-year (from "
                                f"{prior_de:.2f} to {de_ratio:.2f})."
                            ),
                            source="QUANTITATIVE",
                            metric_name="debt_to_equity",
                            recommendation="Monitor leverage trajectories.",
                            **de_meta,
                        )
                    )
            elif de_ratio > LEVERAGE_DE_HIGH_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Solvency",
                        title="Excessive Balance Sheet Leverage",
                        description=f"Debt-to-equity ratio is high at {de_ratio:.2f}, indicating substantial financial leverage.",
                        source="QUANTITATIVE",
                        metric_name="debt_to_equity",
                        recommendation="Evaluate debt service capabilities under stressed scenarios.",
                        **de_meta,
                    )
                )

        # -------------------------------------------------------------
        # Rule 6: Revenue Contraction (Top-line Erosion)
        # -------------------------------------------------------------
        rev = metrics.get("revenue")
        prior_rev = metrics.get("prior_revenue")
        if rev is not None and prior_rev is not None and prior_rev > 0 and rev < prior_rev:
            rev_drop = (prior_rev - rev) / prior_rev
            rev_meta = _build_flag_meta("revenue", f"revenue={rev:g}, prior_revenue={prior_rev:g}")
            if rev_drop >= REVENUE_DROP_HIGH_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="HIGH",
                        category="Profitability",
                        title="Severe Revenue Contraction",
                        description=(
                            f"Total revenue contracted by {rev_drop:.1%} year-over-year (from {prior_rev:g} to {rev:g}), "
                            "indicating severe top-line erosion, customer attrition, or structural demand contraction."
                        ),
                        source="QUANTITATIVE",
                        metric_name="revenue",
                        recommendation="Audit customer retention, segment sales performance, and competitive pricing pressures.",
                        **rev_meta,
                    )
                )
            elif rev_drop >= REVENUE_DROP_MEDIUM_THRESHOLD:
                flags.append(
                    RedFlagItem(
                        severity="MEDIUM",
                        category="Profitability",
                        title="Declining Revenue",
                        description=(
                            f"Total revenue declined by {rev_drop:.1%} year-over-year (from {prior_rev:g} to {rev:g}), "
                            "signaling slowing sales momentum or macroeconomic headwinds."
                        ),
                        source="QUANTITATIVE",
                        metric_name="revenue",
                        recommendation="Analyze sales performance across business units and geographies.",
                        **rev_meta,
                    )
                )

        return flags

    # =====================================================================
    # Stage 2: Targeted Qualitative LLM Analysis
    # =====================================================================

    async def scan_qualitative_documents(
        self,
        session_id: str,
        user_id: str,
        company_name: str,
        risk_focus: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[RedFlagItem]:
        """
        Execute targeted qualitative queries via RetrievalService and synthesize
        grounded red flag items using LLM inference with anti-hallucination constraints.
        Every qualitative flag attaches exact source_chunk_ids from retrieved chunks.
        """
        flags: List[RedFlagItem] = []
        queries = list(QUALITATIVE_QUERIES)
        if risk_focus and risk_focus.strip():
            queries.append(risk_focus.strip())

        filters = MetadataFilter(document_ids=document_ids) if document_ids else None

        for query in queries:
            try:
                req = RetrievalRequest(
                    query=query,
                    top_k=3,
                    score_threshold=0.0,
                    mode=RetrievalMode.HYBRID,
                    filters=filters,
                )
                ret_resp = await retrieval_service.retrieve(
                    session_id=session_id,
                    user_id=user_id,
                    request=req,
                )

                if not ret_resp.results:
                    continue

                snippets: List[str] = []
                chunk_id_map: Dict[str, Dict[str, Any]] = {}
                for idx, r in enumerate(ret_resp.results, start=1):
                    tag = f"SOURCE_{idx}"
                    chunk_id_map[tag] = {
                        "chunk_id": r.chunk_id,
                        "document_id": r.document_id,
                        "document_filename": r.document_filename or "Document",
                        "page_number": r.page_number,
                        "section": r.section,
                        "text": r.source_text,
                    }
                    meta_hdr = f"[{tag} | Filename: {r.document_filename or 'Doc'} | Page: {r.page_number or 'N/A'} | Section: {r.section or 'N/A'}]"
                    snippets.append(f"{meta_hdr}\n{r.source_text}")

                context_text = "\n\n---\n\n".join(snippets)

                prompt = self._build_qualitative_prompt(company_name, query, context_text)
                system_prompt = (
                    "You are an expert forensic accountant and institutional risk auditor. "
                    "Analyze the provided document excerpts strictly for verified red flags. "
                    "CRITICAL: Do NOT invent, assume, or fabricate any red flag not directly supported by the text. "
                    "If the excerpts do not contain genuine red flags for the focus area, return an empty list."
                )

                llm_out = llm_service.generate_structured(
                    prompt=prompt,
                    system_prompt=system_prompt,
                )

                raw_items = llm_out.get("flags", []) if isinstance(llm_out, dict) else []
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue

                    title = item.get("title", "").strip()
                    desc = item.get("description", "").strip()
                    cat = item.get("category", "Operational").strip()
                    raw_sev = str(item.get("severity", "MEDIUM")).upper()
                    quote = item.get("evidence_snippet") or item.get("evidence") or ""
                    source_tag = str(item.get("source_tag") or "SOURCE_1").strip()

                    meta = chunk_id_map.get(source_tag) or (
                        list(chunk_id_map.values())[0] if chunk_id_map else {}
                    )

                    if not title or not desc:
                        continue

                    # Fixed deterministic severity rubric - LLM cannot arbitrarily override
                    deterministic_sev = self._evaluate_qualitative_severity(title, desc, cat, raw_sev)

                    # FinBERT sentiment check (optional escalation)
                    if nlp_service.is_available and quote:
                        nlp_res = nlp_service.analyze_risk_sentiment(quote)
                        if nlp_res and nlp_res.get("sentiment") == "negative" and nlp_res.get("score", 0.0) > 0.85:
                            if deterministic_sev == "LOW":
                                deterministic_sev = "MEDIUM"

                    chunk_id = meta.get("chunk_id")
                    source_chunk_ids = [chunk_id] if chunk_id else []

                    flags.append(
                        RedFlagItem(
                            severity=deterministic_sev,
                            category=cat,
                            title=title,
                            description=desc,
                            source="QUALITATIVE",
                            evidence_snippet=quote or meta.get("text", "")[:200],
                            recommendation=item.get("recommendation"),
                            page_number=meta.get("page_number"),
                            section=meta.get("section"),
                            document_filename=meta.get("document_filename"),
                            document_id=meta.get("document_id"),
                            source_chunk_ids=source_chunk_ids,
                        )
                    )

            except Exception as exc:
                logger.warning("Qualitative query '%s' encountered non-fatal error: %s", query, exc)

        return flags

    # =====================================================================
    # Stage 3: Quantitative Provenance Resolution
    # =====================================================================

    def _resolve_quantitative_provenance(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        initial_provenance: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Safely resolve quantitative metrics back to indexed document chunks
        using existing document/chunk metadata and financial evidence.
        Never fabricates fake source_chunk_ids.
        """
        provenance_map: Dict[str, Dict[str, Any]] = dict(initial_provenance or {})
        if not session_id:
            return provenance_map

        try:
            db_sync = get_sync_db()
            query: Dict[str, Any] = {"session_id": session_id}
            if document_ids:
                query["document_id"] = {"$in": document_ids}

            docs = list(db_sync.documents.find(query))
            if not docs:
                return provenance_map

            all_chunks: List[Dict[str, Any]] = []
            for doc in docs:
                doc_id = doc.get("document_id") or str(doc.get("_id"))
                filename = doc.get("filename", "")
                for ch in doc.get("chunks", []):
                    ch_copy = dict(ch)
                    ch_copy["document_id"] = doc_id
                    ch_copy["document_filename"] = filename
                    all_chunks.append(ch_copy)

            if not all_chunks:
                return provenance_map

            metric_search_specs = {
                "total_debt": {
                    "keywords": ["total debt", "long-term debt", "borrowings", "senior notes", "term debt", "commercial paper", "total liabilities", "credit facility"],
                    "sections": ["financials", "balance_sheet", "md_and_a", "auditor_notes", "footnotes"],
                },
                "prior_total_debt": {
                    "keywords": ["total debt", "long-term debt", "borrowings", "prior year debt"],
                    "sections": ["financials", "balance_sheet", "md_and_a"],
                },
                "gross_margin": {
                    "keywords": ["gross margin", "gross profit", "cost of sales", "cost of goods sold", "gross margin percentage"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "prior_gross_margin": {
                    "keywords": ["gross margin", "gross profit", "prior gross margin"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "operating_margin": {
                    "keywords": ["operating margin", "operating income", "operating loss", "operating profit"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "prior_operating_margin": {
                    "keywords": ["operating margin", "operating income", "prior operating margin"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "operating_cash_flow": {
                    "keywords": ["operating cash flow", "cash flows from operating activities", "operating activities", "cash provided by operating", "cash used in operating", "net cash from operating"],
                    "sections": ["financials", "cash_flows", "md_and_a"],
                },
                "revenue": {
                    "keywords": ["revenue", "net sales", "total net sales", "total revenue", "sales"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "prior_revenue": {
                    "keywords": ["revenue", "net sales", "total net sales", "prior revenue", "prior sales"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "net_income": {
                    "keywords": ["net income", "net loss", "net earnings", "profit after tax"],
                    "sections": ["financials", "income_statement", "md_and_a"],
                },
                "total_equity": {
                    "keywords": ["stockholders' equity", "shareholders' equity", "total equity", "total shareholders' equity", "deficit", "accumulated deficit"],
                    "sections": ["financials", "balance_sheet", "md_and_a"],
                },
                "debt_to_equity": {
                    "keywords": ["debt-to-equity", "total debt", "stockholders' equity", "leverage", "senior notes"],
                    "sections": ["financials", "balance_sheet", "md_and_a"],
                },
            }

            for metric_key, config in metric_search_specs.items():
                if metric_key in provenance_map and provenance_map[metric_key].get("chunk_id"):
                    continue

                val = (metrics or {}).get(metric_key)
                keywords = config["keywords"]
                pref_sections = config["sections"]

                best_chunk = None
                best_score = -1
                best_snippet = None

                for ch in all_chunks:
                    text = ch.get("text", "")
                    text_lower = text.lower()
                    sec = (ch.get("section") or "").lower()

                    score = 0
                    if any(ps in sec for ps in pref_sections):
                        score += 4

                    for kw in keywords:
                        if kw in text_lower:
                            score += 6
                            break

                    if val is not None:
                        val_strs = [str(val)]
                        if isinstance(val, (int, float)):
                            val_strs.append(f"{val:,.0f}")
                            val_strs.append(f"{val:,.1f}")
                            if abs(val) <= 1.0:
                                val_strs.append(f"{val * 100:.1f}%")
                                val_strs.append(f"{val * 100:.0f}%")
                        for vs in val_strs:
                            if vs in text:
                                score += 8
                                break

                    if score > best_score and score >= 6:
                        best_score = score
                        best_chunk = ch
                        lines = [line.strip() for line in text.split("\n") if line.strip()]
                        matching_lines = [line for line in lines if any(kw in line.lower() for kw in keywords)]
                        best_snippet = "\n".join(matching_lines[:3]) if matching_lines else text[:200]

                if best_chunk:
                    cid = best_chunk.get("chunk_id")
                    if cid:
                        provenance_map[metric_key] = {
                            "chunk_id": cid,
                            "source_chunk_ids": [cid],
                            "page_number": best_chunk.get("page_number"),
                            "section": best_chunk.get("section"),
                            "document_filename": best_chunk.get("document_filename"),
                            "document_id": best_chunk.get("document_id"),
                            "evidence_snippet": best_snippet or best_chunk.get("text", "")[:200],
                        }

        except Exception as exc:
            logger.debug("Quantitative provenance resolution notice: %s", exc)

        return provenance_map

    # =====================================================================
    # Stage 4: Semantic Deduplication & Citation Union
    # =====================================================================

    def _deduplicate_flags(self, flags: List[RedFlagItem]) -> List[RedFlagItem]:
        """
        Semantically group and deduplicate flags addressing the same underlying issue,
        preserving all supporting chunk IDs and highest severity.
        """
        if not flags:
            return []

        deduped: List[RedFlagItem] = []
        seen_keys: Dict[str, int] = {}

        severity_rank = {"HIGH": 3, "CRITICAL": 3, "MEDIUM": 2, "LOW": 1}

        for flag in flags:
            clean_title = re.sub(r"[^a-zA-Z0-9\s]", "", flag.title.lower())
            words = sorted(list(set(clean_title.split()[:4])))
            key = f"{flag.category.lower()}:{':'.join(words)}"

            if key in seen_keys:
                existing_idx = seen_keys[key]
                existing = deduped[existing_idx]

                # Promote to highest severity
                if severity_rank.get(flag.severity, 1) > severity_rank.get(existing.severity, 1):
                    existing.severity = flag.severity

                # Union all chunk IDs
                for cid in flag.source_chunk_ids:
                    if cid and cid not in existing.source_chunk_ids:
                        existing.source_chunk_ids.append(cid)

                # Preserve metadata
                if not existing.page_number and flag.page_number:
                    existing.page_number = flag.page_number
                if not existing.section and flag.section:
                    existing.section = flag.section
                if not existing.document_filename and flag.document_filename:
                    existing.document_filename = flag.document_filename
                if not existing.document_id and flag.document_id:
                    existing.document_id = flag.document_id

                if len(flag.evidence_snippet or "") > len(existing.evidence_snippet or ""):
                    existing.evidence_snippet = flag.evidence_snippet
            else:
                seen_keys[key] = len(deduped)
                deduped.append(flag)

        return deduped

    # =====================================================================
    # Stage 5: Anti-Leakage Grounding Sanitization
    # =====================================================================

    def _sanitize_flags(self, flags: List[RedFlagItem]) -> List[RedFlagItem]:
        """
        Sanitize all free-text fields so raw chunk IDs or internal ObjectIDs never reach user output.
        """
        id_pattern = re.compile(
            r"(?:\[|\()?\b(?:chunk_[\w\-]+|chk-[\w\-]+|doc-[\w\-]+|[a-f0-9]{24})\b(?:\:\d+)?(?:\]|\))?",
            re.IGNORECASE,
        )
        for f in flags:
            f.title = id_pattern.sub("", sanitize_user_facing_text(f.title)).strip(" ()[]:-")
            f.description = id_pattern.sub("", sanitize_user_facing_text(f.description)).strip()
            # Clean duplicate spaces and orphaned punctuation
            f.title = re.sub(r"\s{2,}", " ", f.title).strip()
            f.description = re.sub(r"\s{2,}", " ", f.description).strip()
            f.description = re.sub(r"\s+([,\.\?!;:])", r"\1", f.description)
            if f.evidence_snippet:
                f.evidence_snippet = sanitize_user_facing_text(f.evidence_snippet)
            if f.recommendation:
                f.recommendation = sanitize_user_facing_text(f.recommendation)
        return flags

    # =====================================================================
    # Stage 6: Fixed Deterministic Severity Rubric
    # =====================================================================

    @staticmethod
    def _evaluate_qualitative_severity(
        title: str, description: str, category: str, raw_severity: str = "LOW"
    ) -> str:
        """
        Deterministic severity rubric based on financial risk severity standards.
        Allowed values: LOW, MEDIUM, HIGH.
        Fixed deterministic rubric strictly overrides arbitrary LLM severity assignments.
        """
        combined = f"{title} {description} {category}".lower()

        # HIGH SEVERITY PATTERNS: Fatal/Existential audit, forensic, and solvency risks
        high_patterns = [
            r"going[\s\-]concern",
            r"substantial\s+doubt",
            r"ability\s+to\s+continue\s+as\s+a\s+going\s+concern",
            r"auditor\s+qualification",
            r"adverse\s+audit\s+opinion",
            r"disclaimer\s+of\s+opinion",
            r"restatement",
            r"restated\s+(?:financials|earnings|financial\s+statements)",
            r"material\s+misstatement",
            r"accounting\s+fraud",
            r"covenant\s+breach",
            r"covenant\s+violation",
            r"debt\s+default",
            r"default\s+on\s+debt",
            r"bankruptcy",
            r"insolvency",
            r"severe\s+cash\s+burn",
            r"liquidity\s+crisis",
        ]
        for pat in high_patterns:
            if re.search(pat, combined):
                return "HIGH"

        # MEDIUM SEVERITY PATTERNS: Material compliance, governance, internal control, or investigation risks
        med_patterns = [
            r"material\s+weakness",
            r"internal\s+control\s+(?:deficiency|weakness)",
            r"significant\s+deficiency",
            r"sox\s+404",
            r"doj|sec\s+investigation",
            r"regulatory\s+investigation",
            r"formal\s+investigation",
            r"material\s+litigation",
            r"class\s+action\s+lawsuit",
            r"cfo\s+resignation",
            r"ceo\s+resignation",
            r"executive\s+turnover",
            r"related[\s\-]party",
            r"loans?\s+to\s+directors",
            r"supplier\s+concentration",
            r"customer\s+concentration",
            r"credit\s+rating\s+downgrade",
            r"credit\s+facility\s+restriction",
            r"debt\s+surge",
            r"margin\s+compression",
            r"declining\s+revenue",
        ]
        for pat in med_patterns:
            if re.search(pat, combined):
                return "MEDIUM"

        # LOW SEVERITY: Routine disclosures, general risk factor language
        return "LOW"

    @staticmethod
    def _compute_deterministic_risk_score(flags: List[RedFlagItem]) -> float:
        """
        Calculate composite risk score (0.0 to 100.0) with fixed weights:
          HIGH = 15 points
          MEDIUM = 5 points
          LOW = 2 points
        """
        score = 0.0
        for f in flags:
            sev = f.severity.upper()
            if sev in ["HIGH", "CRITICAL"]:
                score += 15.0
            elif sev == "MEDIUM":
                score += 5.0
            elif sev == "LOW":
                score += 2.0
        return min(100.0, float(score))

    # =====================================================================
    # Helpers
    # =====================================================================

    def _extract_normalized_metrics_with_provenance(
        self, metrics: Optional[Any]
    ) -> Tuple[Dict[str, Optional[float]], Dict[str, Dict[str, Any]]]:
        """
        Extract and normalize metrics dictionary with robust alias handling,
        while extracting any existing provenance metadata.
        """
        if not metrics:
            return {}, {}

        raw_dict: Dict[str, Any] = {}
        provenance: Dict[str, Dict[str, Any]] = {}

        if isinstance(metrics, dict):
            raw_dict = metrics
        elif isinstance(metrics, list):
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for item in metrics:
                if isinstance(item, dict) and "metric_name" in item:
                    m_name = str(item["metric_name"]).lower().strip()
                    grouped.setdefault(m_name, []).append(item)
                    # Extract provenance if available
                    cids = item.get("source_chunk_ids") or ([item["chunk_id"]] if item.get("chunk_id") else [])
                    if cids or item.get("context_snippet") or item.get("page_number"):
                        provenance[m_name] = {
                            "source_chunk_ids": cids,
                            "chunk_id": cids[0] if cids else None,
                            "page_number": item.get("page_number"),
                            "section": item.get("section"),
                            "document_id": item.get("document_id"),
                            "document_filename": item.get("document_filename"),
                            "evidence_snippet": item.get("context_snippet") or item.get("evidence_snippet"),
                        }

            for m_name, items in grouped.items():
                def _sort_key(it: Dict[str, Any]) -> int:
                    yr = it.get("fiscal_year") or it.get("year") or it.get("period")
                    if isinstance(yr, int):
                        return yr
                    if isinstance(yr, str):
                        nums = re.findall(r"\b(19\d\d|20\d\d)\b", yr)
                        if nums:
                            return int(nums[0])
                    return 0

                sorted_items = sorted(items, key=_sort_key, reverse=True)
                if sorted_items:
                    raw_dict[m_name] = sorted_items[0].get("value")
                    if len(sorted_items) > 1:
                        raw_dict[f"prior_{m_name}"] = sorted_items[1].get("value")

        def _to_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
                try:
                    num = float(cleaned)
                    if "%" in val:
                        num = num / 100.0
                    return num
                except ValueError:
                    figs = extract_financial_figures(val)
                    if figs:
                        return float(figs[0].numeric_value)
            return None

        normalized: Dict[str, Optional[float]] = {}

        key_mappings = {
            "revenue": ["revenue", "net_sales", "total_revenue", "sales", "turnover", "total_net_sales"],
            "prior_revenue": ["prior_revenue", "revenue_prior", "prior_net_sales", "net_sales_prior", "prior_sales"],
            "total_debt": ["total_debt", "debt", "borrowings", "long_term_debt", "total_liabilities_and_debt", "short_and_long_term_debt", "total_borrowings", "current_debt"],
            "prior_total_debt": ["prior_total_debt", "total_debt_prior", "prior_debt", "previous_debt"],
            "gross_margin": ["gross_margin", "gross_profit_margin", "gm", "gross_margin_percentage"],
            "prior_gross_margin": ["prior_gross_margin", "gross_margin_prior", "prior_gm", "prior_gross_profit_margin"],
            "operating_margin": ["operating_margin", "ebit_margin", "op_margin", "operating_profit_margin"],
            "prior_operating_margin": ["prior_operating_margin", "operating_margin_prior"],
            "operating_cash_flow": ["operating_cash_flow", "operating_cf", "cfo", "cash_flow_from_operations", "net_cash_from_operating_activities", "net_cash_provided_by_operating_activities", "cash_generated_from_operations", "operating_cashflow"],
            "net_income": ["net_income", "net_profit", "earnings", "net_earnings", "profit_after_tax"],
            "total_equity": ["total_equity", "stockholders_equity", "shareholders_equity", "equity", "total_shareholders_equity"],
            "prior_total_equity": ["prior_total_equity", "equity_prior", "prior_equity"],
            "total_assets": ["total_assets", "assets"],
        }

        for target_key, aliases in key_mappings.items():
            for alias in aliases:
                alias_clean = alias.lower().replace(" ", "_")
                val = raw_dict.get(alias) if alias in raw_dict else raw_dict.get(alias_clean)
                if val is None:
                    alias_spaced = alias.replace("_", " ")
                    val = raw_dict.get(alias_spaced)
                if val is not None:
                    parsed = _to_float(val)
                    if parsed is not None:
                        normalized[target_key] = parsed
                        break

        return normalized, provenance

    @staticmethod
    def _extract_normalized_metrics(metrics: Optional[Any]) -> Dict[str, Optional[float]]:
        """Backwards-compatible wrapper."""
        agent = RedFlagAgent()
        norm, _ = agent._extract_normalized_metrics_with_provenance(metrics)
        return norm

    @staticmethod
    def _build_qualitative_prompt(company_name: str, query: str, context: str) -> str:
        return f"""Focus Audit Area: {query}
Target Company: {company_name}

Document Excerpts:
\"\"\"
{context}
\"\"\"

Instructions:
1. Examine the excerpts above for verified financial, audit, or legal red flags related to '{query}'.
2. Each red flag must be directly cited from an excerpt.
3. If no red flag exists, return an empty list for 'flags'.
4. For each flag, specify:
   - title: concise title of the red flag
   - description: one clear sentence explaining why this is a risk
   - category: one of 'Accounting', 'Solvency', 'Governance', 'Legal', 'Disclosure', 'Operational', 'Profitability'
   - severity: 'LOW', 'MEDIUM', or 'HIGH'
   - evidence_snippet: exact quote from the excerpt supporting the flag
   - source_tag: the tag matching the excerpt (e.g., 'SOURCE_1', 'SOURCE_2')
   - recommendation: brief actionable recommendation

Return ONLY a JSON object with schema:
{{
  "flags": [
    {{
      "title": "...",
      "description": "...",
      "category": "...",
      "severity": "LOW|MEDIUM|HIGH",
      "evidence_snippet": "...",
      "source_tag": "SOURCE_1",
      "recommendation": "..."
    }}
  ]
}}"""

    @staticmethod
    def _build_overall_assessment(
        company_name: str,
        flags: List[RedFlagItem],
        risk_score: float,
        quant_count: int,
        qual_count: int,
    ) -> str:
        if not flags:
            return (
                f"Forensic screening for {company_name} completed with zero material red flags detected. "
                "Financial metrics and qualitative disclosures meet standard institutional risk benchmarks."
            )

        high_flags = [f.title for f in flags if f.severity == "HIGH"]
        summary_intro = (
            f"Forensic risk assessment for {company_name} identified {len(flags)} risk anomaly flags "
            f"({quant_count} quantitative, {qual_count} qualitative) resulting in a composite risk score of {risk_score:.1f}/100."
        )
        if high_flags:
            return f"{summary_intro} Key high-priority concerns include: {', '.join(high_flags)}."
        return f"{summary_intro} All identified items remain within manageable monitoring parameters."

    @staticmethod
    def _persist_to_db(
        session_id: str,
        result: RedFlagResult,
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> None:
        """Persist structured red flag analysis results to MongoDB."""
        try:
            db = get_sync_db()
            data = result.model_dump()
            if user_id:
                data["user_id"] = user_id
            if document_id:
                data["document_id"] = document_id
            data["updated_at"] = datetime.now(timezone.utc)

            db.red_flags.update_one(
                {"session_id": session_id},
                {"$set": data},
                upsert=True,
            )
            logger.info("Persisted red flags analysis result to MongoDB for session %s", session_id)
        except Exception as exc:
            logger.warning("Non-fatal error persisting red flags to MongoDB: %s", exc)


red_flag_agent = RedFlagAgent()
agent_registry.register(red_flag_agent, overwrite=True)
