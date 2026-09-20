"""
FinSentry AI — Report Compiler Service.

Owner: Vanshika / FinSentry Engineering Team

Pure-Python deterministic data compiler.
Assembles already-persisted agent outputs into a validated ReportDocument model.

CRITICAL INVARIANTS:
  1. ZERO LLM calls.
  2. Missing != zero (Missing is strictly 'N/A', genuine 0.0 is preserved).
  3. Authoritative sources:
     - extracted_metrics (Key Financials)
     - red_flags (Red Flags & Risk Score)
     - comparison_results (Company Comparison)
     - research_messages / research_session_memory (Outlook)
  4. Deterministic ordering across all lists (companies, metrics, periods, flags).
  5. Deterministic report_id derived from (session_id, user_id, report_version).
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.report.schemas import (
    CompanyComparisonSection,
    CompanyMetricRow,
    ComparisonMetricItem,
    ExecutiveSummarySection,
    KeyFinancialsSection,
    MetricValueItem,
    OutlookFinding,
    OutlookSection,
    RedFlagFinding,
    RedFlagsSection,
    ReportDocument,
    ReportMetadata,
)

logger = logging.getLogger(__name__)

# Canonical ordering for financial metrics in Key Financials table
CANONICAL_METRIC_ORDER: List[Tuple[str, str, str]] = [
    ("revenue", "Revenue / Net Sales", "Income Statement"),
    ("gross_profit", "Gross Profit", "Income Statement"),
    ("gross_margin", "Gross Margin (%)", "Profitability"),
    ("operating_income", "Operating Income (EBIT)", "Income Statement"),
    ("operating_margin", "Operating Margin (%)", "Profitability"),
    ("net_income", "Net Income", "Income Statement"),
    ("net_margin", "Net Margin (%)", "Profitability"),
    ("eps", "Diluted Earnings Per Share (EPS)", "Per Share"),
    ("total_debt", "Total Debt", "Balance Sheet / Leverage"),
    ("debt_to_equity", "Debt-to-Equity Ratio", "Solvency"),
    ("operating_cash_flow", "Operating Cash Flow", "Cash Flow"),
    ("free_cash_flow", "Free Cash Flow", "Cash Flow"),
    ("cash_and_equivalents", "Cash & Cash Equivalents", "Liquidity"),
]

SEVERITY_WEIGHTS: Dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


class ReportCompiler:
    """
    Deterministic compiler that transforms persisted MongoDB state into a typed ReportDocument.
    """

    @classmethod
    def generate_deterministic_report_id(cls, session_id: str, user_id: str, report_version: str = "v1.0") -> str:
        """
        Generate a deterministic report ID derived from session_id, user_id, and version.
        Ensures identical inputs map to the exact same logical report identity.
        """
        seed = f"{session_id}:{user_id}:{report_version}".encode("utf-8")
        hash_hex = hashlib.sha256(seed).hexdigest()[:16]
        return f"rep_{hash_hex}"

    @classmethod
    def _derive_company_name(cls, filename: str) -> str:
        """Derive a canonical, readable company name from a document filename."""
        if not filename:
            return "Company"
        from utils.company_resolution import canonicalize_company_name
        can_name = canonicalize_company_name(filename)
        if can_name and can_name != "Company":
            return can_name
        name = filename.rsplit(".", 1)[0] if "." in filename else filename
        parts = re.split(r"[_\-\s]+", name)
        if parts:
            candidate = parts[0].strip()
            if candidate:
                can_part = canonicalize_company_name(candidate)
                if can_part and can_part != "Company":
                    return can_part
                return candidate.title()
        return canonicalize_company_name(name) or name.title()

    @classmethod
    def compile(
        cls,
        session_id: str,
        user_id: str,
        report_title: str = "Financial Research & Institutional Audit Report",
        report_version: str = "v1.0",
        documents: Optional[List[Dict[str, Any]]] = None,
        extracted_metrics_list: Optional[List[Dict[str, Any]]] = None,
        red_flags_list: Optional[List[Dict[str, Any]]] = None,
        comparison_results_list: Optional[List[Dict[str, Any]]] = None,
        research_messages_list: Optional[List[Dict[str, Any]]] = None,
        research_memory: Optional[Dict[str, Any]] = None,
    ) -> ReportDocument:
        """
        Compile all persisted outputs into a validated ReportDocument.
        """
        documents = documents or []
        extracted_metrics_list = extracted_metrics_list or []
        red_flags_list = red_flags_list or []
        comparison_results_list = comparison_results_list or []
        research_messages_list = research_messages_list or []

        # 1. Resolve Companies and Documents deterministically
        from utils.company_resolution import canonicalize_company_name, resolve_company_from_document
        doc_ids_set: Set[str] = set()
        companies_set: Set[str] = set()

        for doc in documents:
            if doc.get("document_id"):
                doc_ids_set.add(doc["document_id"])
            c_name = resolve_company_from_document(doc)
            if not c_name or c_name == "Company":
                c_name = doc.get("company_name") or doc.get("metadata", {}).get("company_name")
                if not c_name:
                    fname = doc.get("filename") or doc.get("original_filename") or doc.get("document_filename")
                    if fname:
                        c_name = cls._derive_company_name(fname)
            if c_name:
                companies_set.add(canonicalize_company_name(c_name.strip()))

        for em in extracted_metrics_list:
            if em.get("document_id"):
                doc_ids_set.add(em["document_id"])
            c_name = resolve_company_from_document(em)
            if not c_name or c_name == "Company":
                c_name = em.get("company_name") or em.get("company")
                if not c_name:
                    fname = em.get("document_filename")
                    if fname:
                        c_name = cls._derive_company_name(fname)
            if c_name:
                companies_set.add(canonicalize_company_name(c_name.strip()))

        for rf in red_flags_list:
            if rf.get("document_id"):
                doc_ids_set.add(rf["document_id"])
            c_name = rf.get("company_name")
            if c_name:
                companies_set.add(canonicalize_company_name(c_name.strip()))

        for cr in comparison_results_list:
            comp_obj = cr.get("comparison") or cr.get("comparison_output") or cr if isinstance(cr, dict) else {}
            comps = comp_obj.get("companies") or comp_obj.get("compared_companies") or []
            if isinstance(comps, list):
                for c in comps:
                    if isinstance(c, dict) and c.get("company_name"):
                        companies_set.add(canonicalize_company_name(c["company_name"].strip()))
                    elif isinstance(c, str) and c.strip():
                        companies_set.add(canonicalize_company_name(c.strip()))

        # Alphabetical deterministic sorting
        sorted_companies = sorted(list(companies_set)) if companies_set else ["Company"]
        sorted_doc_ids = sorted(list(doc_ids_set))

        report_id = cls.generate_deterministic_report_id(session_id, user_id, report_version)

        # 2. Compile Key Financials Section (Section 2)
        key_financials = cls._compile_key_financials(sorted_companies, extracted_metrics_list)

        # 3. Compile Red Flags Section (Section 3)
        red_flags_section = cls._compile_red_flags(red_flags_list)

        # 4. Compile Company Comparison Section (Section 4)
        comparison_section = cls._compile_comparison(sorted_companies, comparison_results_list)

        # 5. Compile Outlook Section (Section 5)
        outlook_section = cls._compile_outlook(research_messages_list, research_memory)

        # 6. Compile Executive Summary (Section 1) using strictly synthesized persisted data
        exec_summary = cls._compile_executive_summary(
            companies=sorted_companies,
            key_financials=key_financials,
            red_flags=red_flags_section,
            comparison=comparison_section,
            outlook=outlook_section,
        )

        metadata = ReportMetadata(
            report_id=report_id,
            session_id=session_id,
            user_id=user_id,
            document_ids=sorted_doc_ids,
            companies=sorted_companies,
            report_title=report_title,
            report_version=report_version,
            generated_at=datetime.now(timezone.utc),
        )

        return ReportDocument(
            metadata=metadata,
            executive_summary=exec_summary,
            key_financials=key_financials,
            red_flags=red_flags_section,
            comparison=comparison_section,
            outlook=outlook_section,
            object_key=f"reports/{user_id}/{session_id}/report-{report_version}.pdf",
            status="COMPLETED",
        )    # -------------------------------------------------------------------------
    # Helper: Format Metric Values cleanly (Missing != Zero)
    # -------------------------------------------------------------------------
    @classmethod
    def format_metric_value(cls, metric_key: str, val: Optional[float], scale: str = "millions") -> str:
        """
        Format a metric value strictly preserving missing vs zero.
        """
        if val is None:
            return "N/A"

        # Percentage metrics
        if "margin" in metric_key or "ratio" in metric_key or "percent" in metric_key:
            # Check if 0.0 <= val <= 1.0 or already percentage
            display_val = val if abs(val) > 1.0 or val == 0.0 else val * 100.0
            return f"{display_val:.2f}%"

        # EPS
        if metric_key == "eps":
            return f"${val:.2f}"

        # General currency scale — Canonical report representation is USD Millions
        scale_lower = (scale or "millions").lower().strip()
        if scale_lower in ["thousand", "thousands"]:
            # Convert USD thousands to USD millions for canonical report representation
            val_in_millions = val / 1000.0
            return f"${val_in_millions:,.1f}M"

        if scale_lower in ["billion", "billions"]:
            val_in_millions = val * 1000.0
            return f"${val_in_millions:,.1f}M"

        if scale_lower in ["unit", "units", "dollars"]:
            if abs(val) >= 1_000_000_000:
                return f"${val / 1_000_000_000:,.2f}B"
            return f"${val / 1_000_000:,.1f}M"

        # Values reported in thousands but defaulted to millions scale (e.g. BBBY $5,344,400 thousand)
        if abs(val) >= 1_000_000 and not any(k in metric_key for k in ["share", "count", "number"]):
            val_in_millions = val / 1000.0
            return f"${val_in_millions:,.1f}M"

        return f"${val:,.1f}M"

    # -------------------------------------------------------------------------
    # Section 2: Key Financials Compilation
    # -------------------------------------------------------------------------
    @classmethod
    def _compile_key_financials(
        cls,
        companies: List[str],
        extracted_metrics_list: List[Dict[str, Any]],
    ) -> KeyFinancialsSection:
        """
        Extract and align metrics across companies and fiscal periods strictly from extracted_metrics.
        """
        import re
        from utils.company_resolution import is_company_match

        periods_set: Set[str] = set()
        company_metrics_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        provenance_notes: List[str] = []

        def _extract_year_num(s: Any) -> Optional[int]:
            if not s:
                return None
            m = re.search(r"(?:19|20)\d\d", str(s))
            return int(m.group(0)) if m else None

        # Compute max valid reporting year from reporting periods and multi_year_data
        max_reporting_year = 0
        for em in extracted_metrics_list:
            rp_yr = _extract_year_num(em.get("reporting_period"))
            if rp_yr and rp_yr > max_reporting_year:
                max_reporting_year = rp_yr
            multi_year = em.get("multi_year_data") or {}
            if isinstance(multi_year, dict):
                for yr_str in multi_year.keys():
                    my_yr = _extract_year_num(yr_str)
                    if my_yr and my_yr > max_reporting_year:
                        max_reporting_year = my_yr
        if max_reporting_year == 0:
            max_reporting_year = 2026

        for em in extracted_metrics_list:
            # Resolve canonical company name matching one of the session companies
            from utils.company_resolution import canonicalize_company_name
            c_name = None
            for comp in companies:
                if is_company_match(comp, em):
                    c_name = comp
                    break
            if not c_name:
                raw_c = em.get("company_name") or em.get("company")
                c_name = canonicalize_company_name(raw_c) if raw_c else (companies[0] if len(companies) == 1 else "Company")
            c_name = canonicalize_company_name(c_name.strip())

            period = em.get("reporting_period") or "Current"
            p_yr = _extract_year_num(period)
            if not p_yr or p_yr <= max_reporting_year:
                periods_set.add(period)

            # Gather primary metrics
            metrics_dict = dict(em.get("metrics_dict") or {})
            metrics_list = em.get("metrics") or []
            if isinstance(metrics_list, list):
                for item in metrics_list:
                    if isinstance(item, dict):
                        m_k = item.get("metric_name") or item.get("name") or item.get("key")
                        if m_k and item.get("value") is not None and m_k not in metrics_dict:
                            metrics_dict[m_k] = item.get("value")

            # Fallback top-level fields
            for top_key in ["revenue", "net_income", "gross_margin", "eps", "operating_income", "debt_to_equity", "operating_cash_flow", "total_debt"]:
                if top_key in em and em[top_key] is not None and top_key not in metrics_dict:
                    metrics_dict[top_key] = em[top_key]

            company_metrics_map[(c_name, period)] = {
                "metrics": metrics_dict,
                "scale": em.get("reporting_scale", "millions"),
                "currency": em.get("reporting_currency", "USD"),
                "document_id": em.get("document_id"),
            }

            # Multi-year statements support
            multi_year = em.get("multi_year_data") or {}
            if isinstance(multi_year, dict):
                for yr_str, yr_data in multi_year.items():
                    if isinstance(yr_data, dict):
                        yr_num = _extract_year_num(yr_str)
                        if not yr_num or yr_num <= max_reporting_year:
                            periods_set.add(yr_str)
                            # The period-keyed table is the canonical result
                            # of extraction.  It must override the legacy
                            # top-level metrics_dict even for the reporting
                            # period; otherwise old raw-thousands values can
                            # leak into a newly generated report.
                            company_metrics_map[(c_name, yr_str)] = {
                                "metrics": yr_data,
                                "scale": "millions",
                                "currency": em.get("reporting_currency", "USD"),
                                "document_id": em.get("document_id"),
                            }

        # Chronological descending sort for periods (e.g. FY2025 -> FY2024 -> FY2023)
        sorted_periods = sorted(
            list(periods_set),
            reverse=True,
            key=lambda p: int("".join(c for c in p if c.isdigit())) if any(c.isdigit() for c in p) else 0,
        )
        if not sorted_periods:
            sorted_periods = ["FY2025"]

        # Build table rows for canonical metrics
        rows: List[CompanyMetricRow] = []
        for idx, (m_key, m_display, m_cat) in enumerate(CANONICAL_METRIC_ORDER):
            row_values: List[MetricValueItem] = []
            has_any_data = False

            for comp in companies:
                for per in sorted_periods:
                    data = company_metrics_map.get((comp, per), {})
                    m_dict = data.get("metrics", {})
                    raw_val = m_dict.get(m_key)

                    # Also check aliases
                    if raw_val is None and m_key == "revenue":
                        raw_val = m_dict.get("net_sales") or m_dict.get("total_net_sales") or m_dict.get("total_revenue")
                    elif raw_val is None and m_key == "gross_profit":
                        raw_val = m_dict.get("gross_profit")
                    elif raw_val is None and m_key == "operating_income":
                        raw_val = m_dict.get("operating_profit") or m_dict.get("ebit")
                    elif raw_val is None and m_key == "operating_cash_flow":
                        raw_val = m_dict.get("cash_from_operations") or m_dict.get("operating_cashflow") or m_dict.get("cash_provided_by_operating_activities")
                    elif raw_val is None and m_key == "cash_and_equivalents":
                        raw_val = m_dict.get("cash") or m_dict.get("cash_and_cash_equivalents")
                    elif raw_val is None and m_key == "total_debt":
                        raw_val = m_dict.get("debt") or m_dict.get("total_borrowings") or m_dict.get("term_debt")

                    is_avail = raw_val is not None
                    if is_avail:
                        has_any_data = True

                    fmt_val = cls.format_metric_value(m_key, raw_val, scale=data.get("scale", "millions"))
                    row_values.append(
                        MetricValueItem(
                            company_name=comp,
                            fiscal_period=per,
                            raw_value=float(raw_val) if raw_val is not None else None,
                            formatted_value=fmt_val,
                            available=is_avail,
                            unit=data.get("currency", "USD"),
                            scale=data.get("scale", "millions"),
                            document_id=data.get("document_id"),
                        )
                    )

            # Always include core financial rows or rows that have at least one data point
            if has_any_data or m_key in ["revenue", "net_income", "gross_margin", "eps", "operating_income"]:
                rows.append(
                    CompanyMetricRow(
                        metric_key=m_key,
                        display_name=m_display,
                        category=m_cat,
                        order_index=idx,
                        values=row_values,
                    )
                )

        return KeyFinancialsSection(
            companies=companies,
            reporting_periods=sorted_periods,
            metrics=rows,
            provenance_notes=provenance_notes,
        )

    # -------------------------------------------------------------------------
    # Section 3: Red Flags Compilation
    # -------------------------------------------------------------------------
    @classmethod
    def _compile_red_flags(cls, red_flags_list: List[Dict[str, Any]]) -> RedFlagsSection:
        """
        Compile forensic red flags strictly from persisted Red Flag Agent records.
        """
        findings: List[RedFlagFinding] = []
        max_risk_score = 0.0
        high_severity_count = 0
        overall_assessments: List[str] = []

        for rf_doc in red_flags_list:
            score = float(rf_doc.get("risk_score", 0.0))
            if score > max_risk_score:
                max_risk_score = score
            if rf_doc.get("overall_assessment"):
                overall_assessments.append(rf_doc["overall_assessment"])

            c_name = rf_doc.get("company_name", "Company")
            doc_id = rf_doc.get("document_id")
            flags = rf_doc.get("flags") or []

            for idx, f in enumerate(flags):
                if not isinstance(f, dict):
                    continue
                sev = str(f.get("severity", "MEDIUM")).upper()
                if sev in ["HIGH", "CRITICAL"]:
                    high_severity_count += 1

                findings.append(
                    RedFlagFinding(
                        finding_id=f"flag_{c_name}_{idx+1}",
                        company_name=c_name,
                        title=f.get("title", "Risk Anomaly"),
                        severity=sev,
                        category=f.get("category", "General"),
                        metric_name=f.get("metric_name"),
                        current_value=str(f.get("current_value")) if f.get("current_value") is not None else None,
                        prior_value=str(f.get("prior_value")) if f.get("prior_value") is not None else None,
                        change_description=f.get("change") or f.get("variance"),
                        description=f.get("description", ""),
                        evidence=f.get("evidence") or f.get("evidence_snippet", ""),
                        recommendation=f.get("recommendation"),
                        source_page=f.get("page_number") or f.get("source_page"),
                        section=f.get("section"),
                        document_id=doc_id or f.get("document_id"),
                    )
                )

        # Deterministic sorting: severity desc, then company, then title
        sorted_findings = sorted(
            findings,
            key=lambda x: (-SEVERITY_WEIGHTS.get(x.severity, 1), x.company_name, x.title),
        )

        is_empty = len(sorted_findings) == 0
        assessment = (
            overall_assessments[0]
            if overall_assessments
            else ("High financial vulnerability detected across disclosures." if max_risk_score >= 50.0 else "Normal financial risk profile.")
        )

        return RedFlagsSection(
            total_flags=len(sorted_findings),
            high_severity_count=high_severity_count,
            composite_risk_score=max_risk_score,
            overall_assessment=assessment,
            findings=sorted_findings,
            is_empty_state=is_empty,
        )

    # -------------------------------------------------------------------------
    # Section 4: Company Comparison Compilation
    # -------------------------------------------------------------------------
    @classmethod
    def _compile_comparison(
        cls,
        companies: List[str],
        comparison_results_list: List[Dict[str, Any]],
    ) -> CompanyComparisonSection:
        """
        Compile peer comparison strictly from comparison_results.
        Enforces single-company graceful omission.
        """
        # Single-company condition
        if len(companies) < 2 or not comparison_results_list:
            return CompanyComparisonSection(
                is_available=False,
                unavailable_reason="Company comparison is unavailable because only one company was included in this session.",
                compared_companies=companies,
                metrics=[],
            )

        comp_doc = comparison_results_list[0]
        # Check if ComparisonResult or ComparisonOutput model dict
        comp_output = comp_doc.get("comparison") or comp_doc.get("comparison_output") or comp_doc

        compared_comps_raw = comp_output.get("compared_companies") or comp_output.get("companies") or companies
        compared_comps: List[str] = []
        if isinstance(compared_comps_raw, list):
            for c in compared_comps_raw:
                if isinstance(c, dict):
                    c_name = c.get("company_name") or c.get("name") or c.get("ticker") or ""
                    if c_name:
                        compared_comps.append(c_name)
                elif isinstance(c, str) and c:
                    compared_comps.append(c)
        if not compared_comps:
            compared_comps = companies

        fiscal_pers = comp_output.get("fiscal_periods") or []

        metrics_items: List[ComparisonMetricItem] = []
        raw_metrics = comp_output.get("metrics") or []

        for m in raw_metrics:
            if not isinstance(m, dict):
                continue
            m_key = m.get("metric_name", "")
            d_name = m.get("display_name") or m_key.replace("_", " ").title()
            per_data_list = m.get("periods") or []

            for p_entry in per_data_list:
                if not isinstance(p_entry, dict):
                    continue
                period_name = p_entry.get("fiscal_period", "FY2025")
                stats = p_entry.get("peer_statistics") or {}
                vals = p_entry.get("values") or []

                # Map company values
                c_vals: Dict[str, Optional[float]] = {}
                if isinstance(vals, list):
                    for v_item in vals:
                        if isinstance(v_item, dict):
                            c_name = v_item.get("company_name") or v_item.get("company")
                            if c_name:
                                c_vals[c_name] = v_item.get("value")
                elif isinstance(vals, dict):
                    for c_k, c_v in vals.items():
                        if isinstance(c_v, dict):
                            c_vals[c_k] = c_v.get("value")
                        elif isinstance(c_v, (int, float)):
                            c_vals[c_k] = float(c_v)
                        else:
                            c_vals[c_k] = None

                # Extract peer statistics
                peer_avg = stats.get("peer_average")
                
                highest_comp = None
                highest_val = None
                if isinstance(stats.get("highest"), dict):
                    highest_comp = stats["highest"].get("company_name")
                    highest_val = stats["highest"].get("value")
                else:
                    highest_comp = stats.get("highest_company")
                    highest_val = stats.get("highest_value")

                lowest_comp = None
                lowest_val = None
                if isinstance(stats.get("lowest"), dict):
                    lowest_comp = stats["lowest"].get("company_name")
                    lowest_val = stats["lowest"].get("value")
                else:
                    lowest_comp = stats.get("lowest_company")
                    lowest_val = stats.get("lowest_value")

                p_ranks = stats.get("percentile_ranks") or []
                p_ranks_clean: Dict[str, Optional[float]] = {}
                if isinstance(p_ranks, list):
                    for pr in p_ranks:
                        if isinstance(pr, dict):
                            pr_name = pr.get("company_name") or pr.get("company") or ""
                            if pr_name:
                                p_ranks_clean[pr_name] = pr.get("percentile")
                elif isinstance(p_ranks, dict):
                    p_ranks_clean = p_ranks

                metrics_items.append(
                    ComparisonMetricItem(
                        metric_name=m_key,
                        display_name=d_name,
                        fiscal_period=period_name,
                        unit=m.get("unit", "USD"),
                        peer_average=peer_avg,
                        highest_company=highest_comp,
                        highest_value=highest_val,
                        lowest_company=lowest_comp,
                        lowest_value=lowest_val,
                        company_values=c_vals,
                        percentile_ranks=p_ranks_clean,
                    )
                )

        # Deterministic sorting
        sorted_metrics = sorted(metrics_items, key=lambda x: (x.metric_name, x.fiscal_period))

        return CompanyComparisonSection(
            is_available=True,
            compared_companies=sorted(list(set(compared_comps))),
            fiscal_periods=sorted(list(set(fiscal_pers)), reverse=True),
            metrics=sorted_metrics,
        )

    # -------------------------------------------------------------------------
    # Section 5: Outlook Compilation (Strictly Grounded, Zero Hallucination)
    # -------------------------------------------------------------------------
    @classmethod
    def _compile_outlook(
        cls,
        research_messages_list: List[Dict[str, Any]],
        research_memory: Optional[Dict[str, Any]] = None,
    ) -> OutlookSection:
        """
        Compile outlook strictly from persisted research findings.
        Zero LLM calls, zero speculative forecasting.
        """
        findings: List[OutlookFinding] = []

        for msg in research_messages_list:
            if msg.get("role") == "assistant" and msg.get("content"):
                content = str(msg["content"]).strip()
                query = msg.get("query") or msg.get("user_query")

                # Detect outlook/trend relevance
                is_outlook_relevant = any(
                    kw in content.lower() or (query and kw in query.lower())
                    for kw in ["outlook", "guidance", "trend", "risk", "forward", "strategy", "concern", "growth"]
                )

                if is_outlook_relevant or len(findings) < 3:
                    findings.append(
                        OutlookFinding(
                            topic=query if query else "Research Finding",
                            observation=content,
                            source_query=query,
                            confidence_score=float(msg.get("confidence_score", 1.0)),
                            company_name=msg.get("company_name"),
                        )
                    )

        if not findings and research_memory:
            active_topics = research_memory.get("active_topics") or []
            for top in active_topics:
                findings.append(
                    OutlookFinding(
                        topic=str(top),
                        observation=f"Active research focus identified during analysis session: {top}",
                    )
                )

        is_empty = len(findings) == 0
        return OutlookSection(
            findings=findings[:5],  # Take up to 5 authoritative findings
            is_empty_state=is_empty,
        )

    # -------------------------------------------------------------------------
    # Section 1: Executive Summary Compilation (Deterministic Synthesis)
    # -------------------------------------------------------------------------
    @classmethod
    def _compile_executive_summary(
        cls,
        companies: List[str],
        key_financials: KeyFinancialsSection,
        red_flags: RedFlagsSection,
        comparison: CompanyComparisonSection,
        outlook: OutlookSection,
    ) -> ExecutiveSummarySection:
        """
        Deterministically assemble the Executive Summary using strictly existing findings.
        """
        strengths: List[str] = []
        weaknesses: List[str] = []
        red_flags_summary: List[str] = []
        comparison_highlights: List[str] = []
        research_highlights: List[str] = []

        # 1. Strengths & Weaknesses from Financials
        for row in key_financials.metrics:
            if row.metric_key == "revenue":
                for v in row.values:
                    if v.available and v.raw_value and v.raw_value > 0:
                        strengths.append(f"{v.company_name} demonstrated revenue scale of {v.formatted_value} in {v.fiscal_period}.")
            elif row.metric_key == "gross_margin":
                for v in row.values:
                    if v.available and v.raw_value is not None:
                        if v.raw_value >= 40.0:
                            strengths.append(f"{v.company_name} maintains healthy gross margin efficiency at {v.formatted_value}.")
                        elif v.raw_value < 25.0:
                            weaknesses.append(f"{v.company_name} experienced compressed gross margins at {v.formatted_value}.")
            elif row.metric_key == "net_income":
                for v in row.values:
                    if v.available and v.raw_value is not None and v.raw_value < 0:
                        weaknesses.append(f"{v.company_name} reported net losses of {v.formatted_value} in {v.fiscal_period}.")

        # 2. Forensic Red Flags Summary
        for f in red_flags.findings[:4]:
            red_flags_summary.append(f"[{f.severity}] {f.company_name}: {f.title} ({f.description})")

        # 3. Comparison Highlights
        if comparison.is_available:
            for m in comparison.metrics[:3]:
                if m.highest_company and m.highest_value is not None and m.peer_average is not None:
                    comparison_highlights.append(
                        f"In {m.display_name} ({m.fiscal_period}), {m.highest_company} led peers at {m.highest_value:,.1f} (Peer Average: {m.peer_average:,.1f})."
                    )

        # 4. Research Highlights
        for o in outlook.findings[:2]:
            research_highlights.append(f"{o.topic}: {o.observation[:160]}...")

        # Formulate concise deterministic narrative
        narrative_lines = [
            f"This institutional financial research report presents comprehensive due diligence for {', '.join(companies)} across reporting periods {', '.join(key_financials.reporting_periods)}.",
            f"Forensic risk scoring evaluated the target session at a composite score of {red_flags.composite_risk_score:.1f}/100 with {red_flags.total_flags} detected risk anomalies ({red_flags.high_severity_count} high severity).",
        ]
        if red_flags.composite_risk_score >= 50.0:
            narrative_lines.append("Heightened financial vigilance is warranted due to material qualitative or quantitative distress indicators.")
        else:
            narrative_lines.append("Target entities exhibit stable baseline disclosures with no critical distress disqualifiers identified.")

        return ExecutiveSummarySection(
            companies_analyzed=companies,
            reporting_periods=key_financials.reporting_periods,
            overall_risk_score=red_flags.composite_risk_score,
            overall_risk_assessment=red_flags.overall_assessment,
            key_strengths=strengths[:4],
            key_weaknesses=weaknesses[:4],
            major_red_flags_summary=red_flags_summary,
            comparison_highlights=comparison_highlights,
            key_research_takeaways=research_highlights,
            narrative=" ".join(narrative_lines),
        )
