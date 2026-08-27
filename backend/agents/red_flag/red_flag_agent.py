"""
FinSentry AI — Production Red Flag Agent (Phase 2C / Master Architecture).

Author: Sajjan Pawar / FinSentry Engineering Team

Proactively scans company financial information for forensic anomalies, solvency risks,
and disclosure concerns without requiring explicit user prompts.

Architecture:
  1. Deterministic Quantitative Rule Engine (Debt surge, margin compression, OCF divergence)
  2. Targeted Qualitative LLM Analysis via Hybrid RetrievalService (Going concern, litigation, restatements)
  3. NLP & FinBERT Sentiment Extension Point
  4. Deterministic Severity Rubric (LOW, MEDIUM, HIGH)
  5. Semantic Deduplication with Multi-Source Citation Preservation
  6. Explainable One-Sentence Non-Finance Summaries
  7. Deterministic Weighted Risk Score Formula (Max 100)
  8. Anti-Leakage Grounding (Stripping internal chunk IDs from user-facing text)
  9. MongoDB Persistence (red_flags collection) & Celery Registry Contract
"""

import asyncio
import concurrent.futures
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




DEBT_GROWTH_MEDIUM_THRESHOLD = 0.20
DEBT_GROWTH_HIGH_THRESHOLD = 0.40
MARGIN_DROP_MEDIUM_THRESHOLD = 0.05
MARGIN_DROP_HIGH_THRESHOLD = 0.10
LEVERAGE_DE_HIGH_THRESHOLD = 4.0
LEVERAGE_GROWTH_HIGH_THRESHOLD = 0.50
LEVERAGE_GROWTH_MED_THRESHOLD = 0.25



QUALITATIVE_QUERIES = [
    "auditor qualifications going concern opinion adverse audit opinion explanatory paragraph",
    "pending litigation legal proceedings DOJ SEC regulatory investigations material lawsuits",
    "related-party transactions loans to directors executive dealings affiliated entity transactions",
    "executive management turnover CEO CFO resignations unexpected departure key officers",
    "restatement of financial results revised financial statements prior period errors misstatements",
    "material weaknesses internal control over financial reporting significant deficiencies SOX 404",
    "debt covenant violations debt restructuring defaults credit rating downgrades liquidity risk",
]


class RedFlagAgent(BaseAgent):
    """
    Production-grade Red Flag Agent for forensic accounting and financial risk detection.
    """

    def __init__(self, name: str = "RedFlagAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.RED_FLAG_ANALYSIS)



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
                    parts = [p for p in base.replace("_", " ").replace("-", " ").split() if p.lower() not in {"10k", "10q", "annual", "report", "filing", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "pdf", "txt", "md"}]
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


            if not metrics_input and session_id:
                try:
                    db_sync = get_sync_db()
                    db_metrics = list(db_sync.extracted_metrics.find({"session_id": session_id}))
                    if db_metrics:
                        metrics_input = db_metrics
                except Exception as m_exc:
                    logger.debug("Database metric lookup notice: %s", m_exc)

            normalized_metrics = self._extract_normalized_metrics(metrics_input)
            quant_flags = self.scan_quantitative_metrics(normalized_metrics)
            all_flags.extend(quant_flags)
            quant_count = len(quant_flags)
            logger.info("Quantitative rule engine produced %d flags", quant_count)


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


            deduped_flags = self._deduplicate_flags(all_flags)


            sanitized_flags = self._sanitize_flags(deduped_flags)


            high_count = sum(1 for f in sanitized_flags if f.severity == "HIGH")
            risk_score = self._compute_deterministic_risk_score(sanitized_flags)


            overall_assessment = self._build_overall_assessment(
                company_name=company_name,
                flags=sanitized_flags,
                risk_score=risk_score,
                quant_count=quant_count,
                qual_count=qual_count,
            )


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


            self._persist_to_db(session_id, red_flag_res)

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



    def scan_quantitative_metrics(self, metrics: Dict[str, Any]) -> List[RedFlagItem]:
        """
        Run deterministic, explainable quantitative checks on extracted numeric metrics.
        Thresholds are fixed by forensic audit standards and never decided by the LLM.
        """
        flags: List[RedFlagItem] = []
        if not metrics:
            return flags


        debt = metrics.get("total_debt")
        prior_debt = metrics.get("prior_total_debt")
        if debt is not None and prior_debt is not None and prior_debt > 0:
            growth = (debt - prior_debt) / prior_debt
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
                        evidence_snippet=f"total_debt={debt:g}, prior_total_debt={prior_debt:g}",
                        recommendation="Review debt maturity profiles, interest coverage ratios, and refinancing constraints.",
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
                        evidence_snippet=f"total_debt={debt:g}, prior_total_debt={prior_debt:g}",
                        recommendation="Monitor leverage trajectories and liquidity reserves.",
                    )
                )


        margin = metrics.get("gross_margin")
        prior_margin = metrics.get("prior_gross_margin")
        if margin is not None and prior_margin is not None:
            drop = prior_margin - margin
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
                        evidence_snippet=f"gross_margin={margin:.3f}, prior_gross_margin={prior_margin:.3f}",
                        recommendation="Investigate product pricing, inventory write-downs, or supply chain inflation.",
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
                        evidence_snippet=f"gross_margin={margin:.3f}, prior_gross_margin={prior_margin:.3f}",
                        recommendation="Analyze margin pressure by segment or geography.",
                    )
                )


        op_margin = metrics.get("operating_margin")
        prior_op_margin = metrics.get("prior_operating_margin")
        if op_margin is not None and prior_op_margin is not None:
            op_drop = prior_op_margin - op_margin
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
                        evidence_snippet=f"operating_margin={op_margin:.3f}, prior_operating_margin={prior_op_margin:.3f}",
                        recommendation="Audit SG&A overhead and operational efficiency.",
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
                        evidence_snippet=f"operating_margin={op_margin:.3f}, prior_operating_margin={prior_op_margin:.3f}",
                        recommendation="Review operating expense trends.",
                    )
                )


        ocf = metrics.get("operating_cash_flow")
        if ocf is not None and ocf < 0:
            net_income = metrics.get("net_income")
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
                        evidence_snippet=f"operating_cash_flow={ocf:g}, net_income={net_income:g}",
                        recommendation="Perform forensic analysis on accounts receivable, inventory build, and non-cash revenue recognition.",
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
                        evidence_snippet=f"operating_cash_flow={ocf:g}",
                        recommendation="Assess cash runway and near-term financing requirements.",
                    )
                )


        equity = metrics.get("total_equity")
        prior_equity = metrics.get("prior_total_equity")
        if debt is not None and equity is not None and equity > 0:
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
                            evidence_snippet=f"debt_to_equity={de_ratio:.2f}, prior_debt_to_equity={prior_de:.2f}",
                            recommendation="Review capital structure and covenant compliance.",
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
                            evidence_snippet=f"debt_to_equity={de_ratio:.2f}, prior_debt_to_equity={prior_de:.2f}",
                            recommendation="Monitor leverage trajectories.",
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
                        evidence_snippet=f"total_debt={debt:g}, total_equity={equity:g}, ratio={de_ratio:.2f}",
                        recommendation="Evaluate debt service capabilities under stressed scenarios.",
                    )
                )

        return flags



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


                    deterministic_sev = self._evaluate_qualitative_severity(title, desc, cat, raw_sev)


                    if nlp_service.is_available and quote:
                        nlp_res = nlp_service.analyze_risk_sentiment(quote)
                        if nlp_res and nlp_res.get("sentiment") == "negative" and nlp_res.get("score", 0.0) > 0.85:
                            if deterministic_sev == "LOW":
                                deterministic_sev = "MEDIUM"

                    flags.append(
                        RedFlagItem(
                            severity=deterministic_sev,
                            category=cat,
                            title=title,
                            description=desc,
                            source="QUALITATIVE",
                            evidence_snippet=quote,
                            recommendation=item.get("recommendation"),
                            page_number=meta.get("page_number"),
                            section=meta.get("section"),
                            document_filename=meta.get("document_filename"),
                            document_id=meta.get("document_id"),
                            source_chunk_ids=[meta["chunk_id"]] if meta.get("chunk_id") else [],
                        )
                    )

            except Exception as exc:
                logger.warning("Qualitative query '%s' encountered non-fatal error: %s", query, exc)

        return flags



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


                if severity_rank.get(flag.severity, 1) > severity_rank.get(existing.severity, 1):
                    existing.severity = flag.severity


                for cid in flag.source_chunk_ids:
                    if cid and cid not in existing.source_chunk_ids:
                        existing.source_chunk_ids.append(cid)


                if not existing.page_number and flag.page_number:
                    existing.page_number = flag.page_number
                if not existing.section and flag.section:
                    existing.section = flag.section


                if len(flag.evidence_snippet or "") > len(existing.evidence_snippet or ""):
                    existing.evidence_snippet = flag.evidence_snippet
            else:
                seen_keys[key] = len(deduped)
                deduped.append(flag)

        return deduped

    def _sanitize_flags(self, flags: List[RedFlagItem]) -> List[RedFlagItem]:
        """
        Sanitize all free-text fields so raw chunk IDs or internal ObjectIDs never reach user output.
        """
        for f in flags:
            f.title = sanitize_user_facing_text(f.title)
            f.description = sanitize_user_facing_text(f.description)
            if f.evidence_snippet:
                f.evidence_snippet = sanitize_user_facing_text(f.evidence_snippet)
            if f.recommendation:
                f.recommendation = sanitize_user_facing_text(f.recommendation)
        return flags



    @staticmethod
    def _evaluate_qualitative_severity(
        title: str, description: str, category: str, raw_severity: str
    ) -> str:
        """
        Deterministic severity rubric based on financial risk severity standards.
        Allowed values: LOW, MEDIUM, HIGH.
        """
        combined = f"{title} {description} {category}".lower()


        high_patterns = [
            r"going[\s\-]concern",
            r"auditor qualification",
            r"adverse audit opinion",
            r"restatement",
            r"material misstatement",
            r"accounting fraud",
            r"covenant breach",
            r"debt default",
            r"bankruptcy",
            r"insolvency",
            r"severe cash burn",
        ]
        for pat in high_patterns:
            if re.search(pat, combined):
                return "HIGH"


        med_patterns = [
            r"material weakness",
            r"internal control deficiency",
            r"doj|sec investigation",
            r"material litigation",
            r"cfo resignation",
            r"ceo resignation",
            r"executive turnover",
            r"related[\s\-]party",
            r"supplier concentration",
            r"debt surge",
            r"margin compression",
        ]
        for pat in med_patterns:
            if re.search(pat, combined):
                return "MEDIUM"


        if raw_severity in ["HIGH", "CRITICAL"]:
            return "HIGH"
        elif raw_severity == "MEDIUM":
            return "MEDIUM"
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



    @staticmethod
    def _extract_normalized_metrics(metrics: Optional[Any]) -> Dict[str, Optional[float]]:
        """
        Extract and normalize metrics dictionary with robust alias handling.
        """
        if not metrics:
            return {}

        raw_dict: Dict[str, Any] = {}
        if isinstance(metrics, dict):
            raw_dict = metrics
        elif isinstance(metrics, list):
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for item in metrics:
                if isinstance(item, dict) and "metric_name" in item:
                    m_name = str(item["metric_name"]).lower().strip()
                    grouped.setdefault(m_name, []).append(item)

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
            "prior_revenue": ["prior_revenue", "revenue_prior", "prior_net_sales", "net_sales_prior"],
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

        return normalized



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
    def _persist_to_db(session_id: str, result: RedFlagResult) -> None:
        """Persist structured red flag analysis results to MongoDB."""
        try:
            db = get_sync_db()
            db.red_flags.update_one(
                {"session_id": session_id},
                {"$set": result.model_dump()},
                upsert=True,
            )
            logger.info("Persisted red flags analysis result to MongoDB for session %s", session_id)
        except Exception as exc:
            logger.warning("Non-fatal error persisting red flags to MongoDB: %s", exc)




red_flag_agent = RedFlagAgent()
agent_registry.register(red_flag_agent, overwrite=True)
