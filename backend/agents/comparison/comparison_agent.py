"""
FinSentry AI — Production Comparison Agent (Phase 2C — Multi-Company Peer Comparison).

Owner: Sivaram / FinSentry Engineering Team

Compares financial metrics across TWO OR MORE companies belonging to the SAME
research session using existing extracted_metrics records.

Architecture & Design:
  1. Consumes validated extracted_metrics from ExtractionAgent — never re-extracts from PDFs.
  2. All numerical calculations are deterministic Python — never delegates math to LLM.
  3. Supports 2, 3, 4+ companies in a single comparison.
  4. Enforces same-session validation — never mixes cross-session data.
  5. Aligns fiscal periods across companies using validated extraction metadata.
  6. Missing data remains None/unavailable — never zero-fills or fabricates.
  7. Genuine zero values are preserved and distinguished from missing.
  8. Peer statistics: average, highest, lowest, percentile rank.
  9. Percentile convention: (rank - 1) / (N - 1) for N >= 2; None for N < 2.
  10. Unit/scale safety: incompatible units are flagged, not silently combined.
  11. Provenance preserved from extracted_metrics where available.
  12. Chart-ready JSON output — frontend does not need to reshape data.
  13. Cached in comparison_results collection with stale-data invalidation.
  14. Idempotent — same inputs produce cache HIT, no duplicate records.
  15. Integrated via BaseAgent contract, agent_registry, CrewAI, Celery.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.base import AgentResult, BaseAgent
from agents.comparison.schemas import (
    CompanyInfo,
    ComparisonMetric,
    ComparisonMetricPeriod,
    ComparisonOutput,
    ComparisonRequest,
    ComparisonResultDocument,
    METRIC_DIRECTIONALITY,
    MetricValue,
    PeerStatistics,
    PercentileEntry,
)
from agents.registry import agent_registry
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException
from database.connection import get_sync_db

logger = logging.getLogger(__name__)


class ComparisonAgent(BaseAgent):
    """
    Agent responsible for deterministic multi-company financial metric comparison.

    Consumes existing extracted_metrics records and produces chart-ready
    peer comparison output with deterministic statistics.
    """

    def __init__(self, name: str = "ComparisonAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.COMPARISON)

    # =================================================================
    # BaseAgent contract
    # =================================================================

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute multi-company financial comparison.

        Payload:
            session_id: str (required)
            document_ids: List[str] (required, minimum 2)
            user_id: str (required in payload or context)

        Returns:
            AgentResult with chart-ready ComparisonOutput in summary.
        """
        start_time = time.time()
        context = context or {}

        session_id = payload.get("session_id")
        document_ids = payload.get("document_ids", [])
        user_id = context.get("user_id") or payload.get("user_id")

        # ----- Input validation -----
        if not session_id:
            raise NonRetryableAgentException(
                "Missing required parameter: 'session_id' must be provided."
            )
        if not user_id:
            raise NonRetryableAgentException(
                "Missing required parameter: 'user_id' must be provided."
            )

        # Track whether document_ids was explicitly provided by caller
        has_explicit_document_ids = "document_ids" in payload and payload["document_ids"] is not None

        # ----- Legacy compatibility: auto-discover documents -----
        # When called from live_analysis_service with baseline_entity/comparison_entity
        # but no document_ids, discover all session documents with extracted_metrics.
        if not document_ids or not isinstance(document_ids, list):
            try:
                db_discover = get_sync_db()
                session_metrics = list(
                    db_discover.extracted_metrics.find(
                        {"session_id": session_id},
                        {"document_id": 1},
                    )
                )
                document_ids = [r["document_id"] for r in session_metrics if r.get("document_id")]
                if document_ids:
                    logger.info(
                        "ComparisonAgent auto-discovered %d documents for session %s",
                        len(document_ids),
                        session_id,
                    )
            except Exception as exc:
                logger.warning("ComparisonAgent auto-discovery failed: %s", exc)
                document_ids = []

        if not document_ids:
            if has_explicit_document_ids:
                raise NonRetryableAgentException(
                    "Comparison requires at least 2 distinct companies/documents. Received 0 unique document ID(s)."
                )
            # Return graceful empty result for pipeline compatibility
            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary={
                    "session_id": session_id,
                    "companies": [],
                    "fiscal_periods": [],
                    "metrics": [],
                    "key_takeaways": [],
                    "metadata": {"message": "No documents with extracted metrics found in this session."},
                },
                result_ref=session_id,
                metadata={"cache_hit": False, "company_count": 0},
            )

        # Deduplicate while preserving order
        seen = set()
        unique_doc_ids: List[str] = []
        for did in document_ids:
            if did not in seen:
                seen.add(did)
                unique_doc_ids.append(did)
        document_ids = unique_doc_ids

        if len(document_ids) < 2:
            if has_explicit_document_ids:
                raise NonRetryableAgentException(
                    f"Comparison requires at least 2 distinct companies/documents. "
                    f"Received {len(document_ids)} unique document ID(s)."
                )
            # Single document in auto-discovery: return graceful result for pipeline compatibility
            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary={
                    "session_id": session_id,
                    "companies": [],
                    "fiscal_periods": [],
                    "metrics": [],
                    "key_takeaways": ["Comparison requires at least 2 documents — only 1 found in this session."],
                    "metadata": {"message": "Comparison requires at least 2 documents."},
                },
                result_ref=session_id,
                metadata={"cache_hit": False, "company_count": len(document_ids)},
            )

        logger.info(
            "ComparisonAgent starting: session=%s, documents=%d",
            session_id,
            len(document_ids),
        )

        try:
            db = get_sync_db()
        except Exception as exc:
            logger.error("ComparisonAgent failed to connect to MongoDB: %s", exc)
            raise RetryableAgentException(
                f"MongoDB connection failure: {exc}"
            )

        try:
            # ----- Step 1: Check cache -----
            doc_ids_hash = ComparisonResultDocument.compute_document_ids_hash(document_ids)
            data_version = self._compute_data_version(db, session_id, document_ids)

            cached = self._check_cache(db, session_id, doc_ids_hash, data_version)
            if cached is not None:
                latency_ms = (time.time() - start_time) * 1000
                logger.info(
                    "ComparisonAgent cache HIT: session=%s, latency=%.2fms",
                    session_id,
                    latency_ms,
                )
                return AgentResult(
                    success=True,
                    task_type=self.default_task_type.value,
                    agent_name=self.name,
                    summary=cached,
                    result_ref=session_id,
                    metadata={
                        "cache_hit": True,
                        "latency_ms": latency_ms,
                        "company_count": len(document_ids),
                    },
                )

            logger.info("ComparisonAgent cache MISS: computing comparison")

            # ----- Step 2: Validate documents belong to session -----
            self._validate_documents_in_session(db, session_id, document_ids, user_id)

            # ----- Step 3: Load extracted_metrics (bulk) -----
            metrics_records = self._load_extracted_metrics(db, session_id, document_ids)

            # ----- Step 4: Build company info -----
            companies = self._build_company_info(metrics_records)

            # ----- Step 5: Align fiscal periods -----
            all_periods, common_periods, company_only_periods, has_common_periods, comparison_note = (
                self._determine_period_alignment(metrics_records, companies)
            )

            # ----- Step 6: Align metric names -----
            all_metric_names = self._align_metric_names(metrics_records)

            # ----- Step 7: Build metric matrix + peer statistics -----
            comparison_metrics = self._build_comparison_metrics(
                metrics_records=metrics_records,
                companies=companies,
                fiscal_periods=all_periods,
                metric_names=all_metric_names,
            )

            # ----- Step 8: Assemble chart-ready output & deterministic insights -----
            summary_insights = self._build_summary_insights(
                companies=companies,
                common_periods=common_periods,
                company_only_periods=company_only_periods,
                comparison_metrics=comparison_metrics,
            )

            comparison_output = ComparisonOutput(
                session_id=session_id,
                companies=companies,
                fiscal_periods=all_periods,
                common_periods=common_periods,
                company_only_periods=company_only_periods,
                has_common_periods=has_common_periods,
                comparison_note=comparison_note,
                summary_insights=summary_insights,
                metrics=comparison_metrics,
                generated_at=datetime.now(timezone.utc),
                metadata={
                    "company_count": len(companies),
                    "period_count": len(all_periods),
                    "common_period_count": len(common_periods),
                    "has_common_periods": has_common_periods,
                    "metric_count": len(comparison_metrics),
                },
            )

            # ----- Step 9: Persist to comparison_results -----
            self._persist_comparison(
                db=db,
                session_id=session_id,
                user_id=user_id,
                document_ids=sorted(document_ids),
                doc_ids_hash=doc_ids_hash,
                data_version=data_version,
                comparison=comparison_output,
            )

            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "ComparisonAgent completed: session=%s, companies=%d, "
                "periods=%d, common_periods=%d, metrics=%d, latency=%.2fms",
                session_id,
                len(companies),
                len(all_periods),
                len(common_periods),
                len(comparison_metrics),
                latency_ms,
            )

            output_dict = comparison_output.model_dump(mode="json")

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=output_dict,
                result_ref=session_id,
                metadata={
                    "cache_hit": False,
                    "latency_ms": latency_ms,
                    "company_count": len(companies),
                    "period_count": len(all_periods),
                    "common_period_count": len(common_periods),
                    "has_common_periods": has_common_periods,
                    "metric_count": len(comparison_metrics),
                },
            )

        except NonRetryableAgentException:
            raise
        except Exception as exc:
            logger.error("ComparisonAgent error: %s", exc, exc_info=True)
            raise RetryableAgentException(
                f"ComparisonAgent transient failure: {exc}"
            )

    # =================================================================
    # Step 1: Cache management
    # =================================================================

    def _compute_data_version(
        self, db: Any, session_id: str, document_ids: List[str]
    ) -> str:
        """
        Compute a data version string from the latest extracted_metrics.updated_at
        across all requested documents. Used for stale-cache detection.
        """
        pipeline = [
            {
                "$match": {
                    "session_id": session_id,
                    "document_id": {"$in": document_ids},
                }
            },
            {"$group": {"_id": None, "max_updated": {"$max": "$updated_at"}}},
        ]
        result = list(db.extracted_metrics.aggregate(pipeline))
        if result and result[0].get("max_updated"):
            ts = result[0]["max_updated"]
            if isinstance(ts, datetime):
                return ts.isoformat()
            return str(ts)
        return "unknown"

    def _check_cache(
        self,
        db: Any,
        session_id: str,
        doc_ids_hash: str,
        data_version: str,
    ) -> Optional[Dict[str, Any]]:
        """Return cached comparison result if valid, otherwise None."""
        cached = db.comparison_results.find_one(
            {
                "session_id": session_id,
                "document_ids_hash": doc_ids_hash,
                "data_version": data_version,
            }
        )
        if cached and "comparison" in cached:
            return cached["comparison"]
        return None

    def _persist_comparison(
        self,
        db: Any,
        session_id: str,
        user_id: str,
        document_ids: List[str],
        doc_ids_hash: str,
        data_version: str,
        comparison: ComparisonOutput,
    ) -> None:
        """Persist comparison result using upsert to prevent duplicates."""
        try:
            doc = ComparisonResultDocument(
                session_id=session_id,
                user_id=user_id,
                document_ids=sorted(document_ids),
                document_ids_hash=doc_ids_hash,
                data_version=data_version,
                comparison=comparison,
                updated_at=datetime.now(timezone.utc),
            )
            db.comparison_results.update_one(
                {
                    "session_id": session_id,
                    "document_ids_hash": doc_ids_hash,
                },
                {"$set": doc.model_dump(mode="json")},
                upsert=True,
            )
            logger.info(
                "Persisted comparison_results: session=%s, hash=%s",
                session_id,
                doc_ids_hash[:12],
            )
        except Exception as exc:
            logger.warning(
                "Non-fatal: failed to persist comparison_results: %s", exc
            )

    # =================================================================
    # Step 2: Session/document validation
    # =================================================================

    def _validate_documents_in_session(
        self,
        db: Any,
        session_id: str,
        document_ids: List[str],
        user_id: str,
    ) -> None:
        """
        Validate that all requested documents exist, belong to the session,
        and are owned by the user.
        """
        docs = list(
            db.documents.find(
                {
                    "document_id": {"$in": document_ids},
                    "session_id": session_id,
                    "user_id": user_id,
                },
                {"document_id": 1},
            )
        )
        found_ids = {d["document_id"] for d in docs}
        missing = set(document_ids) - found_ids
        if missing:
            raise NonRetryableAgentException(
                f"The following document(s) do not belong to session '{session_id}' "
                f"or are not accessible: {sorted(missing)}"
            )

    # =================================================================
    # Step 3: Load extracted_metrics (bulk)
    # =================================================================

    def _load_extracted_metrics(
        self, db: Any, session_id: str, document_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Bulk-load extracted_metrics for all requested documents in one query.
        Raises if any document has no extracted metrics.
        """
        records = list(
            db.extracted_metrics.find(
                {
                    "session_id": session_id,
                    "document_id": {"$in": document_ids},
                }
            )
        )
        found_doc_ids = {r["document_id"] for r in records}
        missing = set(document_ids) - found_doc_ids
        if missing:
            raise NonRetryableAgentException(
                f"No extracted_metrics found for document(s): {sorted(missing)}. "
                f"Please run the Extraction Agent on these documents first."
            )
        return records

    # =================================================================
    # Step 4: Build company info
    # =================================================================

    def _build_company_info(
        self, metrics_records: List[Dict[str, Any]]
    ) -> List[CompanyInfo]:
        """Extract company identity from extracted_metrics records with canonical resolution."""
        from utils.company_resolution import canonicalize_company_name
        companies: List[CompanyInfo] = []
        for rec in metrics_records:
            filename = rec.get("document_filename", "") or ""
            raw_c_name = rec.get("company_name") or rec.get("company")
            company_name = canonicalize_company_name(raw_c_name) if raw_c_name else self._derive_company_name(filename)
            companies.append(
                CompanyInfo(
                    document_id=rec["document_id"],
                    company_name=company_name,
                    filing_type=rec.get("filing_type"),
                    reporting_currency=rec.get("reporting_currency"),
                    reporting_scale=rec.get("reporting_scale"),
                )
            )
        return companies

    @staticmethod
    def _derive_company_name(filename: str) -> str:
        """
        Derive a canonical, human-readable company name from the document filename.

        Examples:
            apple_2025_annual_report.pdf → Apple
            bbby_distress_10k.pdf → Bed Bath & Beyond
            Microsoft_10K_2024.pdf → Microsoft
        """
        if not filename:
            return "Unknown Company"
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

    # =================================================================
    # Step 5: Align fiscal periods
    # =================================================================

    def _extract_company_periods(
        self, record: Dict[str, Any], max_reporting_year: int
    ) -> List[str]:
        """Extract valid fiscal periods for a single company record."""
        periods: set = set()
        rp = record.get("reporting_period")
        if rp and self._is_valid_fiscal_period(rp, max_year=max_reporting_year):
            periods.add(rp)

        pp = record.get("prior_period")
        if pp and self._is_valid_fiscal_period(pp, max_year=max_reporting_year):
            periods.add(pp)

        myd = record.get("multi_year_data", {})
        if isinstance(myd, dict):
            for key in myd.keys():
                if self._is_valid_fiscal_period(key, max_year=max_reporting_year):
                    periods.add(key)

        for m in record.get("metrics", []):
            if isinstance(m, dict):
                mp = m.get("period")
                if mp and self._is_valid_fiscal_period(mp, max_year=max_reporting_year):
                    periods.add(mp)
                mpp = m.get("prior_period")
                if mpp and self._is_valid_fiscal_period(mpp, max_year=max_reporting_year):
                    periods.add(mpp)

        return sorted(periods, key=self._period_sort_key, reverse=True)

    def _determine_period_alignment(
        self,
        metrics_records: List[Dict[str, Any]],
        companies: List[CompanyInfo],
    ) -> Tuple[List[str], List[str], Dict[str, List[str]], bool, Optional[str]]:
        """
        Determine canonical fiscal period alignment across participating companies.

        Returns:
            all_periods: All valid fiscal periods across all companies (sorted chronologically desc).
            common_periods: Fiscal periods represented by >= 2 participating companies (true peer comparison periods).
            company_only_periods: Dict of {company_name: [periods]} for periods represented by only 1 company.
            has_common_periods: True if common_periods is non-empty.
            comparison_note: Contextual note explaining peer availability.
        """
        max_reporting_year = 0
        for rec in metrics_records:
            rp = rec.get("reporting_period")
            if rp:
                y = self._period_sort_key(rp)
                if y > max_reporting_year:
                    max_reporting_year = y

        if max_reporting_year == 0:
            max_reporting_year = 2026

        company_periods_map: Dict[str, List[str]] = {}
        all_periods_set: set = set()

        for comp, rec in zip(companies, metrics_records):
            comp_pers = self._extract_company_periods(rec, max_reporting_year)
            company_periods_map[comp.document_id] = comp_pers
            all_periods_set.update(comp_pers)

        all_periods = sorted(all_periods_set, key=self._period_sort_key, reverse=True)

        # Common periods = periods present in >= 2 distinct participating company documents
        common_periods = []
        for p in all_periods:
            count = sum(1 for pers in company_periods_map.values() if p in pers)
            if count >= 2:
                common_periods.append(p)

        # Company-only periods = periods present in only 1 participating company document
        company_only_periods: Dict[str, List[str]] = {}
        for comp in companies:
            pers = company_periods_map.get(comp.document_id, [])
            comp_only = [p for p in pers if p not in common_periods]
            if comp_only:
                company_only_periods[comp.company_name] = comp_only

        has_common_periods = len(common_periods) > 0

        comparison_note = None
        if not has_common_periods:
            c_names = [c.company_name for c in companies]
            comparison_note = (
                f"No common fiscal reporting periods are available across the selected companies "
                f"({', '.join(c_names)}); peer-relative statistics are unavailable."
            )

        return all_periods, common_periods, company_only_periods, has_common_periods, comparison_note

    def _align_fiscal_periods(
        self, metrics_records: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Collect and align all valid fiscal periods from validated extraction metadata.

        Uses reporting_period, prior_period, and multi_year_data keys.
        Only includes periods that match recognized fiscal year patterns and are <= max reporting period.
        Excludes future debt maturity and contractual commitment years (e.g. FY2028, FY2029).
        """
        max_reporting_year = 0
        for rec in metrics_records:
            rp = rec.get("reporting_period")
            if rp:
                y = self._period_sort_key(rp)
                if y > max_reporting_year:
                    max_reporting_year = y

        if max_reporting_year == 0:
            max_reporting_year = 2026

        periods: set = set()
        for rec in metrics_records:
            periods.update(self._extract_company_periods(rec, max_reporting_year))

        # Sort chronologically (extract year, sort descending for most recent first)
        sorted_periods = sorted(periods, key=self._period_sort_key, reverse=True)
        return sorted_periods

    @staticmethod
    def _is_valid_fiscal_period(period: str, max_year: int = 2026) -> bool:
        """Check if a string represents a recognized fiscal period within max_year."""
        if not period or not isinstance(period, str):
            return False
        # Match patterns: FY2024, FY2025, CY2023, 2024, FY 2024, etc.
        if not re.match(r"^(?:FY|CY|fy|cy)?\s*(?:19|20)\d{2}$", period.strip()):
            return False
        match = re.search(r"(19|20)\d{2}", period)
        if match:
            year = int(match.group())
            if year > max_year or year < 1990:
                return False
        return True

    @staticmethod
    def _period_sort_key(period: str) -> int:
        """Extract year number for sorting."""
        match = re.search(r"(19|20)\d{2}", period)
        return int(match.group()) if match else 0

    # =================================================================
    # Step 6: Align metric names
    # =================================================================

    def _align_metric_names(
        self, metrics_records: List[Dict[str, Any]]
    ) -> List[str]:
        """Collect all unique canonical metric names across all companies (excluding prior_* internal fields)."""
        names: set = set()
        for rec in metrics_records:
            md = rec.get("metrics_dict", {})
            if isinstance(md, dict):
                names.update(md.keys())

            myd = rec.get("multi_year_data", {})
            if isinstance(myd, dict):
                for period_data in myd.values():
                    if isinstance(period_data, dict):
                        names.update(period_data.keys())

            for m in rec.get("metrics", []):
                if isinstance(m, dict) and m.get("metric_name"):
                    names.add(m["metric_name"])

        # Filter out prior_ prefixed internal fields and non-canonical helper fields
        filtered_names = set()
        for n in names:
            if not n or not isinstance(n, str):
                continue
            n_clean = n.strip()
            n_lower = n_clean.lower()
            if n_lower.startswith("prior_") or n_lower.startswith("prior "):
                continue
            if n_lower in {
                "filing_type", "document_filename", "reporting_scale",
                "reporting_currency", "reporting_period", "prior_period",
                "company_name", "document_id", "session_id",
            }:
                continue
            filtered_names.add(n_clean)

        # Sort for deterministic output
        return sorted(filtered_names)

    # =================================================================
    # Step 7: Build metric matrix + peer statistics
    # =================================================================

    def _normalize_metric_value(
        self,
        metric_name: str,
        raw_val: Optional[float],
        unit: Optional[str],
        currency: Optional[str],
        scale: Optional[str],
    ) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[float], Optional[str]]:
        """
        Normalize raw values to canonical scale:
        - USD absolute metrics -> USD Millions (thousands / 1000.0, billions * 1000.0, millions * 1.0)
        - INR absolute metrics -> INR Crores (lakhs / 100.0, crores * 1.0)
        - Margins, Ratios, EPS, YoY changes -> Preserved as-is
        """
        if raw_val is None:
            return None, unit, scale, None, unit

        curr_clean = (currency or "USD").upper().strip()
        scale_clean = (scale or "millions").lower().strip()
        unit_clean = str(unit or "").strip()

        # 1. Ratio / Percentage / Per-Share metrics
        if not self._is_absolute_metric(metric_name):
            norm_u = unit or ("%" if "margin" in metric_name or "pct" in metric_name or "percent" in metric_name else "Ratio")
            return raw_val, unit, scale, raw_val, norm_u

        # 2. Absolute Monetary Metrics
        if curr_clean in {"USD", "$", "US$"}:
            # A metric-level canonical unit is authoritative. Record-level
            # reporting_scale describes the source filing and must not trigger
            # a second conversion after extraction has normalized the value.
            if "million" in unit_clean.lower():
                norm_val = round(raw_val, 4)
                src_u = unit
            elif "thousand" in scale_clean or "thousand" in unit_clean.lower() or " k" in unit_clean.lower():
                norm_val = round(raw_val / 1000.0, 4)
                src_u = unit or "USD Thousands"
            elif "billion" in scale_clean or "billion" in unit_clean.lower() or " b" in unit_clean.lower():
                norm_val = round(raw_val * 1000.0, 4)
                src_u = unit or "USD Billions"
            elif "unit" in scale_clean or "dollars" in scale_clean:
                norm_val = round(raw_val / 1000000.0, 4)
                src_u = unit or "USD"
            elif abs(raw_val) >= 1_000_000 and self._is_absolute_metric(metric_name):
                # Filing values reported in thousands without explicit thousand metadata (e.g. BBBY $5,344,400 thousand)
                norm_val = round(raw_val / 1000.0, 4)
                src_u = unit or "USD Thousands"
            else:
                norm_val = round(raw_val, 4)
                src_u = unit or "USD Millions"
            return raw_val, src_u, scale, norm_val, "USD Millions"

        elif curr_clean in {"INR", "₹", "RS"}:
            if "lakh" in scale_clean:
                norm_val = round(raw_val / 100.0, 4)
            else:
                norm_val = round(raw_val, 4)
            return raw_val, unit or "INR Crores", scale, norm_val, "INR Crores"

        return raw_val, unit, scale, raw_val, f"{curr_clean} {scale_clean.title()}"

    def _build_comparison_metrics(
        self,
        metrics_records: List[Dict[str, Any]],
        companies: List[CompanyInfo],
        fiscal_periods: List[str],
        metric_names: List[str],
    ) -> List[ComparisonMetric]:
        """Build the full metric comparison matrix with peer statistics and canonical unit normalization."""
        result: List[ComparisonMetric] = []

        # Build lookup: doc_id -> record
        rec_by_doc: Dict[str, Dict[str, Any]] = {
            r["document_id"]: r for r in metrics_records
        }

        for metric_name in metric_names:
            display_name = self._get_display_name(metrics_records, metric_name)
            metric_periods: List[ComparisonMetricPeriod] = []

            for period in fiscal_periods:
                values: List[MetricValue] = []
                currency_set: set = set()

                for company in companies:
                    rec = rec_by_doc.get(company.document_id, {})
                    val, unit, currency, provenance = self._lookup_metric_value(
                        rec, metric_name, period
                    )
                    scale = rec.get("reporting_scale")

                    raw_v, src_u, src_s, norm_v, norm_u = self._normalize_metric_value(
                        metric_name, val, unit, currency, scale
                    )

                    available = norm_v is not None
                    if available and currency:
                        currency_set.add(currency.upper().strip())

                    values.append(
                        MetricValue(
                            document_id=company.document_id,
                            company_name=company.company_name,
                            fiscal_period=period,
                            value=norm_v,
                            available=available,
                            unit=norm_u or unit,
                            currency=currency,
                            provenance=provenance,
                            raw_value=raw_v,
                            source_unit=src_u,
                            source_scale=src_s,
                            normalized_value=norm_v,
                            normalized_unit=norm_u,
                        )
                    )

                # Check unit compatibility (currencies must match for absolute metrics)
                unit_compatible = True
                unit_mismatch_detail = None
                if self._is_absolute_metric(metric_name):
                    if len(currency_set) > 1:
                        unit_compatible = False
                        unit_mismatch_detail = (
                            f"Incompatible currencies: {sorted(currency_set)}. "
                            f"Cannot compare across different currencies."
                        )

                # Calculate peer statistics only if units are compatible
                if unit_compatible:
                    peer_stats = self._calculate_peer_statistics(
                        values, metric_name
                    )
                else:
                    peer_stats = PeerStatistics(valid_count=0)
                    for v in values:
                        v.available = False

                metric_periods.append(
                    ComparisonMetricPeriod(
                        fiscal_period=period,
                        values=values,
                        peer_statistics=peer_stats,
                        unit_compatible=unit_compatible,
                        unit_mismatch_detail=unit_mismatch_detail,
                    )
                )

            # Only include metrics that have at least one available value
            has_any_value = any(
                any(v.available for v in mp.values)
                for mp in metric_periods
            )
            if has_any_value:
                result.append(
                    ComparisonMetric(
                        metric_name=metric_name,
                        display_name=display_name,
                        periods=metric_periods,
                    )
                )

        return result

    def _lookup_metric_value(
        self,
        record: Dict[str, Any],
        metric_name: str,
        fiscal_period: str,
    ) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        Lookup a specific metric value for a specific fiscal period from an extracted_metrics record.

        Returns: (value, unit, currency, provenance)
        value is None if unavailable — never fabricated.
        """
        if not record:
            return None, None, None, None

        reporting_period = record.get("reporting_period", "")
        prior_period = record.get("prior_period", "")
        reporting_currency = record.get("reporting_currency")

        # Try multi_year_data first (most structured source)
        myd = record.get("multi_year_data", {})
        if isinstance(myd, dict) and fiscal_period in myd:
            period_data = myd[fiscal_period]
            if isinstance(period_data, dict) and metric_name in period_data:
                raw_val = period_data[metric_name]
                if raw_val is not None:
                    try:
                        val = float(raw_val)
                        unit = self._get_metric_unit(record, metric_name)
                        prov = self._get_provenance(record, metric_name)
                        return val, unit, reporting_currency, prov
                    except (ValueError, TypeError):
                        pass

        # Try metrics list
        for m in record.get("metrics", []):
            if not isinstance(m, dict):
                continue
            if m.get("metric_name") != metric_name:
                continue

            m_period = m.get("period", "")
            m_prior = m.get("prior_period", "")

            if fiscal_period == m_period and m.get("value") is not None:
                try:
                    val = float(m["value"])
                    unit = m.get("unit") or self._get_metric_unit(record, metric_name)
                    currency = m.get("currency") or reporting_currency
                    prov = self._get_provenance(record, metric_name)
                    return val, unit, currency, prov
                except (ValueError, TypeError):
                    pass

            if fiscal_period == m_prior and m.get("prior_value") is not None:
                try:
                    val = float(m["prior_value"])
                    unit = m.get("unit") or self._get_metric_unit(record, metric_name)
                    currency = m.get("currency") or reporting_currency
                    prov = self._get_provenance(record, metric_name)
                    return val, unit, currency, prov
                except (ValueError, TypeError):
                    pass

        # Try metrics_dict for current/prior period
        md = record.get("metrics_dict", {})
        if isinstance(md, dict):
            if fiscal_period == reporting_period and metric_name in md:
                raw_val = md[metric_name]
                if raw_val is not None:
                    try:
                        val = float(raw_val)
                        unit = self._get_metric_unit(record, metric_name)
                        prov = self._get_provenance(record, metric_name)
                        return val, unit, reporting_currency, prov
                    except (ValueError, TypeError):
                        pass

            # Check prior value via prior_ prefixed keys
            if fiscal_period == prior_period:
                prior_key = f"prior_{metric_name}"
                if prior_key in md and md[prior_key] is not None:
                    try:
                        val = float(md[prior_key])
                        unit = self._get_metric_unit(record, metric_name)
                        prov = self._get_provenance(record, metric_name)
                        return val, unit, reporting_currency, prov
                    except (ValueError, TypeError):
                        pass

        # Not found — return None (never fabricate)
        return None, None, None, None

    @staticmethod
    def _get_metric_unit(record: Dict[str, Any], metric_name: str) -> Optional[str]:
        """Determine unit for a metric from the record metadata."""
        # Check individual metric items
        for m in record.get("metrics", []):
            if isinstance(m, dict) and m.get("metric_name") == metric_name:
                unit = m.get("unit")
                if unit:
                    return unit

        # Fallback to record-level scale
        scale = record.get("reporting_scale")
        if scale:
            return scale
        return None

    @staticmethod
    def _get_provenance(record: Dict[str, Any], metric_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve provenance information for a metric if available."""
        prov_map = record.get("provenance_map", {})
        if isinstance(prov_map, dict) and metric_name in prov_map:
            return prov_map[metric_name]
        return None

    @staticmethod
    def _get_display_name(
        metrics_records: List[Dict[str, Any]], metric_name: str
    ) -> Optional[str]:
        """Find the display name for a metric from any record."""
        for rec in metrics_records:
            for m in rec.get("metrics", []):
                if isinstance(m, dict) and m.get("metric_name") == metric_name:
                    dn = m.get("display_name")
                    if dn:
                        return dn
        return None

    @staticmethod
    def _is_absolute_metric(metric_name: str) -> bool:
        """
        Determine if a metric represents an absolute monetary value
        (requiring currency/scale compatibility) vs a ratio/percentage/per-share metric.
        """
        ratio_or_pershare_metrics = {
            "gross_margin", "operating_margin", "net_margin",
            "debt_to_equity", "current_ratio", "quick_ratio",
            "return_on_equity", "return_on_assets",
            "yoy_revenue_change", "yoy_net_income_change",
            "eps", "diluted_eps", "basic_eps", "earnings_per_share",
        }
        name_lower = metric_name.lower()
        if name_lower in ratio_or_pershare_metrics:
            return False
        if "margin" in name_lower or "ratio" in name_lower or "percent" in name_lower or "eps" in name_lower or "per_share" in name_lower:
            return False
        return True

    # =================================================================
    # Peer statistics calculation (deterministic Python)
    # =================================================================

    @staticmethod
    def _calculate_peer_statistics(
        values: List[MetricValue], metric_name: str
    ) -> PeerStatistics:
        """
        Calculate deterministic peer statistics for a set of metric values.

        Rules:
        - If valid_count (N) < 2:
            peer_average = None (unavailable)
            highest = None (unavailable)
            lowest = None (unavailable)
            percentile_ranks = [PercentileEntry(..., percentile=None)]
            valid_count = N (0 or 1)
        - If valid_count (N) >= 2:
            peer_average = round(sum(valid_values) / N, 4)
            highest = {"document_id": doc_id, "company_name": comp, "value": val}
            lowest = {"document_id": doc_id, "company_name": comp, "value": val}
            percentile_ranks = (rank - 1) / (N - 1) with minimum-rank tie handling.
        """
        valid_entries = [
            (v.document_id, v.company_name, v.value)
            for v in values
            if v.available and v.value is not None
        ]
        n = len(valid_entries)

        if n < 2:
            # Single-company or zero-company: peer statistics (average, highest, lowest, percentile) are strictly unavailable
            percentile_ranks = [
                PercentileEntry(
                    document_id=v.document_id,
                    company_name=v.company_name,
                    percentile=None,
                )
                for v in values
            ]
            return PeerStatistics(
                valid_count=n,
                peer_average=None,
                highest=None,
                lowest=None,
                percentile_ranks=percentile_ranks,
            )

        # N >= 2: Valid multi-company peer benchmarking
        total = sum(entry[2] for entry in valid_entries)
        peer_avg = total / n

        # Sort by value ascending for ranking
        sorted_entries = sorted(valid_entries, key=lambda x: x[2])

        # Lowest and highest
        lowest_entry = sorted_entries[0]
        highest_entry = sorted_entries[-1]

        highest = {
            "document_id": highest_entry[0],
            "company_name": highest_entry[1],
            "value": highest_entry[2],
        }
        lowest = {
            "document_id": lowest_entry[0],
            "company_name": lowest_entry[1],
            "value": lowest_entry[2],
        }

        # Percentile ranks (N >= 2) with minimum-rank convention for ties
        ranks: Dict[str, int] = {}
        i = 0
        while i < n:
            tie_value = sorted_entries[i][2]
            tie_start = i
            while i < n and sorted_entries[i][2] == tie_value:
                i += 1
            for j in range(tie_start, i):
                doc_id = sorted_entries[j][0]
                ranks[doc_id] = tie_start + 1

        percentile_ranks: List[PercentileEntry] = []
        for v in values:
            if v.available and v.value is not None and v.document_id in ranks:
                rank = ranks[v.document_id]
                pctile = (rank - 1) / (n - 1)
                percentile_ranks.append(
                    PercentileEntry(
                        document_id=v.document_id,
                        company_name=v.company_name,
                        percentile=round(pctile, 6),
                    )
                )
            else:
                percentile_ranks.append(
                    PercentileEntry(
                        document_id=v.document_id,
                        company_name=v.company_name,
                        percentile=None,
                    )
                )

        return PeerStatistics(
            valid_count=n,
            peer_average=round(peer_avg, 4),
            highest=highest,
            lowest=lowest,
            percentile_ranks=percentile_ranks,
        )

    # =================================================================
    # Step 8: Deterministic summary insights
    # =================================================================

    @classmethod
    def _build_summary_insights(
        cls,
        companies: List[CompanyInfo],
        common_periods: List[str],
        company_only_periods: Dict[str, List[str]],
        comparison_metrics: List[ComparisonMetric],
    ) -> List[str]:
        """
        Generate deterministic summary takeaways for the multi-company comparison.
        Zero LLM calls, zero fabricated benchmarks.
        """
        insights: List[str] = []
        c_names = [c.company_name for c in companies]

        if not common_periods:
            insights.append(
                f"No common fiscal reporting periods are available across {', '.join(c_names)} for direct peer benchmarking."
            )
            period_details = []
            for c in companies:
                c_pers = company_only_periods.get(c.company_name, [])
                if c_pers:
                    period_details.append(f"{c.company_name} ({', '.join(c_pers)})")
            if period_details:
                insights.append(
                    f"Reported periods are company-specific: {'; '.join(period_details)}."
                )
            insights.append(
                "Peer-relative statistics (Peer Average, Highest/Lowest, Percentiles) require at least 2 companies sharing a common fiscal period and are unavailable."
            )
            return insights

        insights.append(
            f"Comparison aligned across {len(common_periods)} common fiscal period(s): {', '.join(common_periods)}."
        )

        # Highlight top metrics with valid peer averages in the most recent common period
        primary_period = common_periods[0]
        highlighted = 0
        for m in comparison_metrics:
            if highlighted >= 3:
                break
            for p in m.periods:
                if p.fiscal_period == primary_period and p.peer_statistics.valid_count >= 2:
                    p_stat = p.peer_statistics
                    if p_stat.peer_average is not None and p_stat.highest is not None:
                        d_name = m.display_name or m.metric_name.replace("_", " ").title()
                        hi_comp = p_stat.highest["company_name"]
                        hi_val = p_stat.highest["value"]
                        insights.append(
                            f"In {primary_period}, {hi_comp} led peers in {d_name} at {hi_val:,.1f} (Peer Average: {p_stat.peer_average:,.1f})."
                        )
                        highlighted += 1
                        break

        return insights


# =====================================================================
# Module-level agent instance + registry registration
# =====================================================================

comparison_agent = ComparisonAgent()
agent_registry.register(comparison_agent, overwrite=True)
