"""
FinSentry AI — Comparison Agent Comprehensive Test Suite.

Owner: Sivaram / FinSentry Engineering Team

Unit and integration tests verifying production Comparison Agent requirements:
  1. Two-company comparison
  2. Three-company comparison
  3. Four-company comparison
  4. Same-session validation
  5. Cross-session rejection
  6. Minimum-company validation (< 2)
  7. Metric alignment across companies
  8. Fiscal-period alignment
  9. Missing metric handling (unavailable)
  10. Missing != zero distinction
  11. Genuine zero preservation
  12. Peer average (deterministic)
  13. Average excludes missing values
  14. Highest value identification
  15. Lowest value identification
  16. Percentile ranking ((rank-1)/(N-1))
  17. Percentile ties (minimum-rank)
  18. Single-valid-company percentile (None)
  19. Unit mismatch detection
  20. Cache miss (first execution)
  21. Cache hit (second execution)
  22. Input ordering does not create duplicate cache
  23. Stale cache invalidation
  24. Chart-ready schema validation
  25. Provenance preservation
  26. Invalid company/document rejection
  27. Duplicate company handling
  28. MongoDB error handling
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agents.base import AgentResult
from agents.comparison.comparison_agent import ComparisonAgent
from agents.comparison.schemas import (
    CompanyInfo,
    ComparisonMetric,
    ComparisonMetricPeriod,
    ComparisonOutput,
    ComparisonResultDocument,
    MetricValue,
    PeerStatistics,
    PercentileEntry,
)
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException


# =====================================================================
# Test fixtures
# =====================================================================


def _make_extracted_metric(
    document_id: str,
    session_id: str,
    user_id: str = "user-1",
    filename: str = "company_report.pdf",
    reporting_period: str = "FY2025",
    prior_period: str = "FY2024",
    reporting_currency: str = "USD",
    reporting_scale: str = "millions",
    filing_type: str = "US 10-K",
    metrics_dict: Optional[Dict[str, Optional[float]]] = None,
    multi_year_data: Optional[Dict[str, Dict[str, Optional[float]]]] = None,
    metrics: Optional[List[Dict[str, Any]]] = None,
    provenance_map: Optional[Dict[str, Any]] = None,
    updated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a test extracted_metrics record matching the production schema."""
    return {
        "document_id": document_id,
        "session_id": session_id,
        "user_id": user_id,
        "document_filename": filename,
        "filing_type": filing_type,
        "reporting_currency": reporting_currency,
        "reporting_scale": reporting_scale,
        "reporting_period": reporting_period,
        "prior_period": prior_period,
        "metrics_dict": metrics_dict or {},
        "multi_year_data": multi_year_data or {},
        "metrics": metrics or [],
        "provenance_map": provenance_map or {},
        "confidence_scores": {},
        "updated_at": updated_at or datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }


def _make_document(
    document_id: str, session_id: str, user_id: str = "user-1"
) -> Dict[str, Any]:
    """Create a minimal test document record."""
    return {
        "document_id": document_id,
        "session_id": session_id,
        "user_id": user_id,
    }


# Standard test records
APPLE_METRIC = _make_extracted_metric(
    document_id="doc-apple",
    session_id="session-1",
    filename="apple_2025_annual_report.pdf",
    reporting_period="FY2025",
    prior_period="FY2024",
    reporting_currency="USD",
    reporting_scale="millions",
    metrics_dict={
        "revenue": 416161.0,
        "net_income": 105474.0,
        "gross_margin": 0.465,
        "eps": 6.97,
        "debt_to_equity": 4.65,
    },
    multi_year_data={
        "FY2025": {"revenue": 416161.0, "net_income": 105474.0, "gross_margin": 0.465, "eps": 6.97},
        "FY2024": {"revenue": 391035.0, "net_income": 93736.0, "gross_margin": 0.462, "eps": 6.08},
    },
    metrics=[
        {"metric_name": "revenue", "value": 416161.0, "prior_value": 391035.0,
         "period": "FY2025", "prior_period": "FY2024", "unit": "millions",
         "display_name": "Total Revenue", "confidence_score": 1.0,
         "source_chunk_ids": ["chunk-a1"], "page_numbers": [42]},
        {"metric_name": "net_income", "value": 105474.0, "prior_value": 93736.0,
         "period": "FY2025", "prior_period": "FY2024", "unit": "millions",
         "display_name": "Net Income", "confidence_score": 1.0,
         "source_chunk_ids": ["chunk-a2"], "page_numbers": [43]},
        {"metric_name": "gross_margin", "value": 0.465, "period": "FY2025",
         "unit": "%", "display_name": "Gross Margin", "confidence_score": 0.9},
        {"metric_name": "eps", "value": 6.97, "period": "FY2025",
         "unit": "USD", "display_name": "Earnings Per Share", "confidence_score": 1.0},
    ],
    provenance_map={
        "revenue": {"source_chunk_ids": ["chunk-a1"], "page_numbers": [42], "evidence_snippet": "Total net sales $416,161"},
        "net_income": {"source_chunk_ids": ["chunk-a2"], "page_numbers": [43], "evidence_snippet": "Net income $105,474"},
    },
)

MSFT_METRIC = _make_extracted_metric(
    document_id="doc-msft",
    session_id="session-1",
    filename="microsoft_2025_10k.pdf",
    reporting_period="FY2025",
    prior_period="FY2024",
    reporting_currency="USD",
    reporting_scale="millions",
    metrics_dict={
        "revenue": 281724.0,
        "net_income": 97680.0,
        "gross_margin": 0.695,
        "eps": 13.05,
        "debt_to_equity": 0.34,
    },
    multi_year_data={
        "FY2025": {"revenue": 281724.0, "net_income": 97680.0, "gross_margin": 0.695, "eps": 13.05},
        "FY2024": {"revenue": 245122.0, "net_income": 88136.0, "gross_margin": 0.694, "eps": 11.80},
    },
    metrics=[
        {"metric_name": "revenue", "value": 281724.0, "prior_value": 245122.0,
         "period": "FY2025", "prior_period": "FY2024", "unit": "millions",
         "display_name": "Total Revenue", "confidence_score": 1.0},
        {"metric_name": "net_income", "value": 97680.0, "prior_value": 88136.0,
         "period": "FY2025", "prior_period": "FY2024", "unit": "millions",
         "display_name": "Net Income", "confidence_score": 1.0},
    ],
)

BBBY_METRIC = _make_extracted_metric(
    document_id="doc-bbby",
    session_id="session-1",
    filename="bbby_distress_10k.pdf",
    reporting_period="FY2022",
    prior_period="FY2021",
    reporting_currency="USD",
    reporting_scale="millions",
    metrics_dict={
        "revenue": 5344.685,
        "net_income": -559.624,
        "gross_margin": 0.284,
    },
    multi_year_data={
        "FY2022": {"revenue": 5344.685, "net_income": -559.624, "gross_margin": 0.284},
        "FY2021": {"revenue": 7867.7, "net_income": -150.8, "gross_margin": 0.338},
    },
    metrics=[
        {"metric_name": "revenue", "value": 5344.685, "period": "FY2022",
         "unit": "millions", "display_name": "Net Sales"},
    ],
)


# Document stubs
APPLE_DOC = _make_document("doc-apple", "session-1")
MSFT_DOC = _make_document("doc-msft", "session-1")
BBBY_DOC = _make_document("doc-bbby", "session-1")


class MockCollection:
    """Mock MongoDB collection with basic find/find_one/aggregate/update_one."""

    def __init__(self, docs: Optional[List[Dict[str, Any]]] = None):
        self._docs = list(docs or [])
        self._stored: List[Dict[str, Any]] = []

    def find(self, query: Dict[str, Any], projection: Optional[Dict] = None):
        results = []
        for doc in self._docs:
            if self._matches(doc, query):
                if projection:
                    results.append({k: doc.get(k) for k in projection if k in doc})
                else:
                    results.append(dict(doc))
        return results

    def find_one(self, query: Dict[str, Any]):
        for doc in self._docs + self._stored:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def aggregate(self, pipeline: List[Dict]):
        # Simplified aggregation for $match + $group with $max
        match_stage = None
        for stage in pipeline:
            if "$match" in stage:
                match_stage = stage["$match"]
                break

        matched = [d for d in self._docs if self._matches(d, match_stage or {})]
        if not matched:
            return []

        max_updated = None
        for d in matched:
            ut = d.get("updated_at")
            if ut and (max_updated is None or ut > max_updated):
                max_updated = ut
        return [{"_id": None, "max_updated": max_updated}]

    def update_one(self, query, update, upsert=False):
        for i, doc in enumerate(self._stored):
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                return MagicMock(upserted_id=None, modified_count=1)
        if upsert and "$set" in update:
            new_doc = {**query, **update["$set"]}
            self._stored.append(new_doc)
            return MagicMock(upserted_id="new-id", modified_count=0)
        return MagicMock(upserted_id=None, modified_count=0)

    def count_documents(self, query: Dict[str, Any] = None) -> int:
        if query is None:
            return len(self._stored)
        return sum(1 for d in self._stored if self._matches(d, query))

    @staticmethod
    def _matches(doc: Dict, query: Dict) -> bool:
        for key, condition in query.items():
            if isinstance(condition, dict):
                if "$in" in condition:
                    if doc.get(key) not in condition["$in"]:
                        return False
            else:
                if doc.get(key) != condition:
                    return False
        return True


class MockDB:
    """Mock MongoDB database with the collections used by ComparisonAgent."""

    def __init__(
        self,
        extracted_metrics_docs=None,
        documents_docs=None,
        comparison_results_docs=None,
    ):
        self.extracted_metrics = MockCollection(extracted_metrics_docs or [])
        self.documents = MockCollection(documents_docs or [])
        self.comparison_results = MockCollection(comparison_results_docs or [])


# =====================================================================
# Test class
# =====================================================================


class TestComparisonAgent:
    """Comprehensive test suite for ComparisonAgent."""

    def setup_method(self):
        self.agent = ComparisonAgent(name="ComparisonAgent")

    # -----------------------------------------------------------------
    # Test 1: Two-company basic comparison
    # -----------------------------------------------------------------
    def test_two_company_basic_comparison(self):
        """Two companies produce a valid comparison with peer statistics."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        assert result.success is True
        assert result.task_type == "COMPARISON"
        summary = result.summary
        assert summary["session_id"] == "session-1"
        assert len(summary["companies"]) == 2
        assert len(summary["metrics"]) > 0

    # -----------------------------------------------------------------
    # Test 2: Three-company comparison
    # -----------------------------------------------------------------
    def test_three_company_comparison(self):
        """Three companies produce a valid comparison."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft", "doc-bbby"]},
                context={"user_id": "user-1"},
            )
        assert result.success is True
        assert len(result.summary["companies"]) == 3

    # -----------------------------------------------------------------
    # Test 3: Four-company comparison
    # -----------------------------------------------------------------
    def test_four_company_comparison(self):
        """Four companies produce a valid comparison."""
        fourth = _make_extracted_metric(
            document_id="doc-amzn", session_id="session-1",
            filename="amazon_2025_10k.pdf",
            metrics_dict={"revenue": 638000.0, "net_income": 59248.0},
            multi_year_data={"FY2025": {"revenue": 638000.0, "net_income": 59248.0}},
        )
        fourth_doc = _make_document("doc-amzn", "session-1")
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC, BBBY_METRIC, fourth],
            documents_docs=[APPLE_DOC, MSFT_DOC, BBBY_DOC, fourth_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft", "doc-bbby", "doc-amzn"]},
                context={"user_id": "user-1"},
            )
        assert result.success is True
        assert len(result.summary["companies"]) == 4

    # -----------------------------------------------------------------
    # Test 4: Same-session validation
    # -----------------------------------------------------------------
    def test_same_session_validation(self):
        """All documents must belong to the requested session."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        assert result.success is True

    # -----------------------------------------------------------------
    # Test 5: Cross-session company rejection
    # -----------------------------------------------------------------
    def test_cross_session_rejection(self):
        """Document from a different session must be rejected."""
        # doc-msft is in session-2, not session-1
        wrong_session_doc = _make_document("doc-msft", "session-2")
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC],
            documents_docs=[APPLE_DOC, wrong_session_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            with pytest.raises(NonRetryableAgentException, match="do not belong to session"):
                self.agent.execute(
                    payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                    context={"user_id": "user-1"},
                )

    # -----------------------------------------------------------------
    # Test 6: Minimum company validation (< 2)
    # -----------------------------------------------------------------
    def test_minimum_company_validation(self):
        """Fewer than 2 documents must be rejected."""
        with pytest.raises(NonRetryableAgentException, match="at least 2"):
            self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple"]},
                context={"user_id": "user-1"},
            )

    # -----------------------------------------------------------------
    # Test 7: Metric alignment
    # -----------------------------------------------------------------
    def test_metric_alignment(self):
        """Metrics from all companies are aligned into the comparison."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        metric_names = [m["metric_name"] for m in result.summary["metrics"]]
        assert "revenue" in metric_names
        assert "net_income" in metric_names

    # -----------------------------------------------------------------
    # Test 8: Fiscal period alignment
    # -----------------------------------------------------------------
    def test_fiscal_period_alignment(self):
        """Fiscal periods from all companies are aligned."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        periods = result.summary["fiscal_periods"]
        assert "FY2025" in periods
        assert "FY2024" in periods

    # -----------------------------------------------------------------
    # Test 9: Missing metric handling
    # -----------------------------------------------------------------
    def test_missing_metric_unavailable(self):
        """Missing metrics are represented as unavailable, not zero."""
        # BBBY has revenue but no EPS
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-bbby"]},
                context={"user_id": "user-1"},
            )

        # Find 'eps' metric
        eps_metric = None
        for m in result.summary["metrics"]:
            if m["metric_name"] == "eps":
                eps_metric = m
                break

        if eps_metric:
            # BBBY should not have EPS in FY2025 (BBBY uses FY2022)
            for period_data in eps_metric["periods"]:
                for v in period_data["values"]:
                    if v["document_id"] == "doc-bbby":
                        assert v["available"] is False
                        assert v["value"] is None

    # -----------------------------------------------------------------
    # Test 10: Missing != zero distinction
    # -----------------------------------------------------------------
    def test_missing_not_equal_to_zero(self):
        """Missing data (None) and genuine zero (0.0) must be distinct."""
        zero_company = _make_extracted_metric(
            document_id="doc-zero",
            session_id="session-1",
            filename="zero_company.pdf",
            metrics_dict={"revenue": 0.0, "net_income": None},
            multi_year_data={"FY2025": {"revenue": 0.0}},
        )
        zero_doc = _make_document("doc-zero", "session-1")
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, zero_company],
            documents_docs=[APPLE_DOC, zero_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-zero"]},
                context={"user_id": "user-1"},
            )

        rev_metric = None
        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                rev_metric = m
                break
        assert rev_metric is not None

        # Find FY2025 period
        for period_data in rev_metric["periods"]:
            if period_data["fiscal_period"] == "FY2025":
                for v in period_data["values"]:
                    if v["document_id"] == "doc-zero":
                        assert v["value"] == 0.0
                        assert v["available"] is True  # Zero is a valid value

    # -----------------------------------------------------------------
    # Test 11: Genuine zero preserved
    # -----------------------------------------------------------------
    def test_genuine_zero_preserved(self):
        """Actual zero values must remain zero, not treated as missing."""
        zero_rev = _make_extracted_metric(
            document_id="doc-zr",
            session_id="session-1",
            filename="zero_revenue.pdf",
            metrics_dict={"revenue": 0.0},
            multi_year_data={"FY2025": {"revenue": 0.0}},
        )
        zero_doc = _make_document("doc-zr", "session-1")
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, zero_rev],
            documents_docs=[APPLE_DOC, zero_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-zr"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for period_data in m["periods"]:
                    if period_data["fiscal_period"] == "FY2025":
                        for v in period_data["values"]:
                            if v["document_id"] == "doc-zr":
                                assert v["value"] == 0.0
                                assert v["available"] is True

    # -----------------------------------------------------------------
    # Test 12: Peer average (deterministic)
    # -----------------------------------------------------------------
    def test_peer_average_deterministic(self):
        """Peer average is calculated deterministically from valid values."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        avg = p["peer_statistics"]["peer_average"]
                        expected = (416161.0 + 281724.0) / 2
                        assert abs(avg - expected) < 0.1

    # -----------------------------------------------------------------
    # Test 13: Average excludes missing values
    # -----------------------------------------------------------------
    def test_average_excludes_missing(self):
        """Peer average must not include missing values (no zero-filling)."""
        partial = _make_extracted_metric(
            document_id="doc-partial",
            session_id="session-1",
            filename="partial_company.pdf",
            metrics_dict={},
            multi_year_data={"FY2025": {}},  # No revenue
        )
        partial_doc = _make_document("doc-partial", "session-1")
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC, partial],
            documents_docs=[APPLE_DOC, MSFT_DOC, partial_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft", "doc-partial"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        stats = p["peer_statistics"]
                        # Average should be (416161 + 281724) / 2, NOT / 3
                        assert stats["valid_count"] == 2
                        expected = (416161.0 + 281724.0) / 2
                        assert abs(stats["peer_average"] - expected) < 0.1

    # -----------------------------------------------------------------
    # Test 14: Highest value
    # -----------------------------------------------------------------
    def test_highest_value(self):
        """Highest value is correctly identified."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        assert p["peer_statistics"]["highest"]["value"] == 416161.0

    # -----------------------------------------------------------------
    # Test 15: Lowest value
    # -----------------------------------------------------------------
    def test_lowest_value(self):
        """Lowest value is correctly identified."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        assert p["peer_statistics"]["lowest"]["value"] == 281724.0

    # -----------------------------------------------------------------
    # Test 16: Percentile ranking
    # -----------------------------------------------------------------
    def test_percentile_ranking(self):
        """Percentile ranks follow (rank-1)/(N-1) convention."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft", "doc-bbby"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        stats = p["peer_statistics"]
                        # Only Apple and MSFT have FY2025 revenue; N=2
                        # Sorted ascending: MSFT=281724 (rank=1), Apple=416161 (rank=2)
                        # MSFT percentile = (1-1)/(2-1) = 0.0
                        # Apple percentile = (2-1)/(2-1) = 1.0
                        pctiles = {
                            e["document_id"]: e["percentile"]
                            for e in stats["percentile_ranks"]
                            if e["percentile"] is not None
                        }
                        if "doc-msft" in pctiles:
                            assert pctiles["doc-msft"] == 0.0
                        if "doc-apple" in pctiles:
                            assert pctiles["doc-apple"] == 1.0

    # -----------------------------------------------------------------
    # Test 17: Percentile ties
    # -----------------------------------------------------------------
    def test_percentile_ties(self):
        """Tied values receive the same rank (minimum-rank convention)."""
        tied_a = _make_extracted_metric(
            document_id="doc-ta", session_id="session-1",
            filename="tied_a.pdf",
            metrics_dict={"revenue": 100.0},
            multi_year_data={"FY2025": {"revenue": 100.0}},
        )
        tied_b = _make_extracted_metric(
            document_id="doc-tb", session_id="session-1",
            filename="tied_b.pdf",
            metrics_dict={"revenue": 100.0},
            multi_year_data={"FY2025": {"revenue": 100.0}},
        )
        tied_c = _make_extracted_metric(
            document_id="doc-tc", session_id="session-1",
            filename="tied_c.pdf",
            metrics_dict={"revenue": 200.0},
            multi_year_data={"FY2025": {"revenue": 200.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[tied_a, tied_b, tied_c],
            documents_docs=[
                _make_document("doc-ta", "session-1"),
                _make_document("doc-tb", "session-1"),
                _make_document("doc-tc", "session-1"),
            ],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-ta", "doc-tb", "doc-tc"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        pctiles = {
                            e["document_id"]: e["percentile"]
                            for e in p["peer_statistics"]["percentile_ranks"]
                            if e["percentile"] is not None
                        }
                        # Sorted: 100, 100, 200 => ranks: 1, 1, 3
                        # doc-ta: (1-1)/(3-1) = 0.0
                        # doc-tb: (1-1)/(3-1) = 0.0  (tied)
                        # doc-tc: (3-1)/(3-1) = 1.0
                        assert pctiles.get("doc-ta") == 0.0
                        assert pctiles.get("doc-tb") == 0.0
                        assert pctiles.get("doc-tc") == 1.0

    # -----------------------------------------------------------------
    # Test 18: Single valid company percentile
    # -----------------------------------------------------------------
    def test_single_valid_company_percentile(self):
        """Single valid company for a metric should have percentile = None."""
        only_apple = _make_extracted_metric(
            document_id="doc-only", session_id="session-1",
            filename="only_company.pdf",
            metrics_dict={},
            multi_year_data={"FY2025": {}},  # No revenue in FY2025
        )
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, only_apple],
            documents_docs=[APPLE_DOC, _make_document("doc-only", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-only"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        stats = p["peer_statistics"]
                        if stats["valid_count"] == 1:
                            assert stats["peer_average"] is None
                            assert stats["highest"] is None
                            assert stats["lowest"] is None
                            for pe in stats["percentile_ranks"]:
                                assert pe["percentile"] is None

    # -----------------------------------------------------------------
    # Test 19: Unit mismatch detection
    # -----------------------------------------------------------------
    def test_unit_mismatch_detection(self):
        """Incompatible currencies must be flagged, not silently combined."""
        inr_company = _make_extracted_metric(
            document_id="doc-inr", session_id="session-1",
            filename="indian_company.pdf",
            reporting_currency="INR",
            reporting_scale="crores",
            metrics_dict={"revenue": 50000.0},
            multi_year_data={"FY2025": {"revenue": 50000.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, inr_company],
            documents_docs=[APPLE_DOC, _make_document("doc-inr", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-inr"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        assert p["unit_compatible"] is False
                        assert p["unit_mismatch_detail"] is not None

    # -----------------------------------------------------------------
    # Test 20: Cache miss (first execution)
    # -----------------------------------------------------------------
    def test_cache_miss_first_execution(self):
        """First execution should be a cache miss."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        assert result.metadata.get("cache_hit") is False

    # -----------------------------------------------------------------
    # Test 21: Cache hit (second execution)
    # -----------------------------------------------------------------
    def test_cache_hit_second_execution(self):
        """Second execution with same inputs should be a cache hit."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result1 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
            assert result1.metadata["cache_hit"] is False

            result2 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
            assert result2.metadata["cache_hit"] is True

    # -----------------------------------------------------------------
    # Test 22: Input ordering does not create duplicate cache
    # -----------------------------------------------------------------
    def test_input_ordering_no_duplicate_cache(self):
        """Different ordering of document_ids must produce same cache key."""
        hash1 = ComparisonResultDocument.compute_document_ids_hash(["doc-apple", "doc-msft"])
        hash2 = ComparisonResultDocument.compute_document_ids_hash(["doc-msft", "doc-apple"])
        assert hash1 == hash2

    # -----------------------------------------------------------------
    # Test 23: Stale cache invalidation
    # -----------------------------------------------------------------
    def test_stale_cache_invalidation(self):
        """Changed extracted_metrics must invalidate cached comparison."""
        old_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

        apple_old = dict(APPLE_METRIC)
        apple_old["updated_at"] = old_time
        msft_old = dict(MSFT_METRIC)
        msft_old["updated_at"] = old_time

        old_hash = ComparisonResultDocument.compute_document_ids_hash(["doc-apple", "doc-msft"])
        cached_doc = {
            "session_id": "session-1",
            "document_ids_hash": old_hash,
            "data_version": old_time.isoformat(),
            "comparison": {"session_id": "session-1", "companies": [], "metrics": []},
        }

        apple_new = dict(APPLE_METRIC)
        apple_new["updated_at"] = new_time
        msft_new = dict(MSFT_METRIC)
        msft_new["updated_at"] = new_time

        db = MockDB(
            extracted_metrics_docs=[apple_new, msft_new],
            documents_docs=[APPLE_DOC, MSFT_DOC],
            comparison_results_docs=[cached_doc],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        assert result.metadata["cache_hit"] is False

    # -----------------------------------------------------------------
    # Test 24: Chart-ready schema validation
    # -----------------------------------------------------------------
    def test_chart_ready_schema(self):
        """Output conforms to chart-ready schema structure."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        summary = result.summary
        assert "session_id" in summary
        assert "companies" in summary
        assert "fiscal_periods" in summary
        assert "common_periods" in summary
        assert "company_only_periods" in summary
        assert "has_common_periods" in summary
        assert "summary_insights" in summary
        assert "metrics" in summary
        assert "generated_at" in summary

    # -----------------------------------------------------------------
    # Test 25: Provenance preservation
    # -----------------------------------------------------------------
    def test_provenance_preservation(self):
        """Provenance from extracted_metrics is preserved in comparison output."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        found_provenance = False
        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    for v in p["values"]:
                        if v["document_id"] == "doc-apple" and v.get("provenance"):
                            found_provenance = True
                            assert "source_chunk_ids" in v["provenance"]
        assert found_provenance is True

    # -----------------------------------------------------------------
    # Test 26: Invalid company/document rejection
    # -----------------------------------------------------------------
    def test_invalid_document_rejection(self):
        """Non-existent document ID must be rejected."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC],
            documents_docs=[APPLE_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            with pytest.raises(NonRetryableAgentException, match="do not belong"):
                self.agent.execute(
                    payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-nonexistent"]},
                    context={"user_id": "user-1"},
                )

    # -----------------------------------------------------------------
    # Test 27: Duplicate company handling
    # -----------------------------------------------------------------
    def test_duplicate_company_deduplication(self):
        """Duplicate document IDs should be deduplicated."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1",
                         "document_ids": ["doc-apple", "doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
        assert result.success is True
        assert len(result.summary["companies"]) == 2

    # -----------------------------------------------------------------
    # Test 28: MongoDB error handling
    # -----------------------------------------------------------------
    def test_mongodb_connection_error(self):
        """MongoDB connection failure raises RetryableAgentException."""
        with patch("agents.comparison.comparison_agent.get_sync_db", side_effect=Exception("Connection refused")):
            with pytest.raises(RetryableAgentException, match="MongoDB connection"):
                self.agent.execute(
                    payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                    context={"user_id": "user-1"},
                )

    # -----------------------------------------------------------------
    # Test 29: Missing session_id
    # -----------------------------------------------------------------
    def test_missing_session_id(self):
        """Missing session_id must be rejected."""
        with pytest.raises(NonRetryableAgentException, match="session_id"):
            self.agent.execute(
                payload={"document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

    # -----------------------------------------------------------------
    # Test 30: Missing user_id
    # -----------------------------------------------------------------
    def test_missing_user_id(self):
        """Missing user_id must be rejected."""
        with pytest.raises(NonRetryableAgentException, match="user_id"):
            self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={},
            )

    # -----------------------------------------------------------------
    # Test 31: No extracted metrics for a document
    # -----------------------------------------------------------------
    def test_no_extracted_metrics(self):
        """Document with no extracted_metrics must be reported clearly."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            with pytest.raises(NonRetryableAgentException, match="No extracted_metrics"):
                self.agent.execute(
                    payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                    context={"user_id": "user-1"},
                )

    # -----------------------------------------------------------------
    # Test 32: Identical values (all same)
    # -----------------------------------------------------------------
    def test_all_identical_values(self):
        """All companies with identical values get identical percentiles."""
        same_a = _make_extracted_metric(
            document_id="doc-sa", session_id="session-1",
            filename="same_a.pdf",
            metrics_dict={"revenue": 500.0},
            multi_year_data={"FY2025": {"revenue": 500.0}},
        )
        same_b = _make_extracted_metric(
            document_id="doc-sb", session_id="session-1",
            filename="same_b.pdf",
            metrics_dict={"revenue": 500.0},
            multi_year_data={"FY2025": {"revenue": 500.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[same_a, same_b],
            documents_docs=[
                _make_document("doc-sa", "session-1"),
                _make_document("doc-sb", "session-1"),
            ],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-sa", "doc-sb"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        stats = p["peer_statistics"]
                        for pe in stats["percentile_ranks"]:
                            if pe["percentile"] is not None:
                                assert pe["percentile"] == 0.0

    # -----------------------------------------------------------------
    # Test 33: ComparisonResultDocument hash is deterministic
    # -----------------------------------------------------------------
    def test_document_ids_hash_deterministic(self):
        """Same set of document IDs always produces the same hash."""
        ids = ["doc-c", "doc-a", "doc-b"]
        h1 = ComparisonResultDocument.compute_document_ids_hash(ids)
        h2 = ComparisonResultDocument.compute_document_ids_hash(list(reversed(ids)))
        h3 = ComparisonResultDocument.compute_document_ids_hash(sorted(ids))
        assert h1 == h2 == h3

    # -----------------------------------------------------------------
    # Test 34: No fabricated citations
    # -----------------------------------------------------------------
    def test_no_fabricated_citations(self):
        """Comparison should not create provenance that doesn't exist in source."""
        no_prov = _make_extracted_metric(
            document_id="doc-np", session_id="session-1",
            filename="no_prov.pdf",
            metrics_dict={"revenue": 999.0},
            multi_year_data={"FY2025": {"revenue": 999.0}},
            provenance_map={},
        )
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, no_prov],
            documents_docs=[APPLE_DOC, _make_document("doc-np", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-np"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "revenue":
                for p in m["periods"]:
                    for v in p["values"]:
                        if v["document_id"] == "doc-np":
                            assert v.get("provenance") is None

    # -----------------------------------------------------------------
    # Test 35: BaseAgent contract
    # -----------------------------------------------------------------
    def test_base_agent_contract(self):
        """ComparisonAgent conforms to BaseAgent contract."""
        assert isinstance(self.agent, ComparisonAgent)
        assert self.agent.name == "ComparisonAgent"
        assert self.agent.default_task_type == AgentTaskType.COMPARISON

    # -----------------------------------------------------------------
    # Test 36: Agent registry integration
    # -----------------------------------------------------------------
    def test_agent_registry_integration(self):
        """ComparisonAgent is registered in the agent registry."""
        from agents.registry import agent_registry
        agent = agent_registry.get("ComparisonAgent")
        assert isinstance(agent, ComparisonAgent)

    # -----------------------------------------------------------------
    # Test 37: Fiscal period validation
    # -----------------------------------------------------------------
    def test_fiscal_period_validation(self):
        """Only valid fiscal periods are included."""
        assert ComparisonAgent._is_valid_fiscal_period("FY2025") is True
        assert ComparisonAgent._is_valid_fiscal_period("FY2024") is True
        assert ComparisonAgent._is_valid_fiscal_period("CY2023") is True
        assert ComparisonAgent._is_valid_fiscal_period("2022") is True
        assert ComparisonAgent._is_valid_fiscal_period("") is False
        assert ComparisonAgent._is_valid_fiscal_period(None) is False
        assert ComparisonAgent._is_valid_fiscal_period("Q1 2025") is False
        assert ComparisonAgent._is_valid_fiscal_period("random text") is False

    # -----------------------------------------------------------------
    # Test 38: Negative values handled correctly
    # -----------------------------------------------------------------
    def test_negative_values(self):
        """Negative values (e.g. net loss) are preserved and compared correctly."""
        loss_a = _make_extracted_metric(
            document_id="doc-la", session_id="session-1",
            filename="loss_a.pdf",
            metrics_dict={"net_income": -100.0},
            multi_year_data={"FY2025": {"net_income": -100.0}},
        )
        loss_b = _make_extracted_metric(
            document_id="doc-lb", session_id="session-1",
            filename="loss_b.pdf",
            metrics_dict={"net_income": -50.0},
            multi_year_data={"FY2025": {"net_income": -50.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[loss_a, loss_b],
            documents_docs=[
                _make_document("doc-la", "session-1"),
                _make_document("doc-lb", "session-1"),
            ],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-la", "doc-lb"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            if m["metric_name"] == "net_income":
                for p in m["periods"]:
                    if p["fiscal_period"] == "FY2025":
                        stats = p["peer_statistics"]
                        assert stats["peer_average"] == -75.0
                        assert stats["lowest"]["value"] == -100.0
                        assert stats["highest"]["value"] == -50.0

    # =================================================================
    # Dedicated Regression Tests for Period Semantics & Peer Benchmarking
    # =================================================================

    # -----------------------------------------------------------------
    # Regression 1: Disjoint fiscal periods (Apple + BBBY)
    # -----------------------------------------------------------------
    def test_regression_disjoint_fiscal_periods(self):
        """Apple (FY2025, FY2024) and BBBY (FY2022, FY2021) share NO common periods."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-bbby"]},
                context={"user_id": "user-1"},
            )

        summary = result.summary
        assert summary["common_periods"] == []
        assert summary["has_common_periods"] is False
        assert summary["comparison_note"] is not None
        assert "Apple" in summary["company_only_periods"]
        assert "FY2025" in summary["company_only_periods"]["Apple"]
        assert "FY2024" in summary["company_only_periods"]["Apple"]

        for m in summary["metrics"]:
            for p in m["periods"]:
                stats = p["peer_statistics"]
                assert stats["valid_count"] in (0, 1)
                assert stats["peer_average"] is None
                assert stats["highest"] is None
                assert stats["lowest"] is None
                for pe in stats["percentile_ranks"]:
                    assert pe["percentile"] is None

    # -----------------------------------------------------------------
    # Regression 2: Two companies sharing one fiscal period
    # -----------------------------------------------------------------
    def test_regression_one_shared_period(self):
        """Companies sharing only FY2025 compute peer statistics ONLY for FY2025."""
        comp_a = _make_extracted_metric(
            document_id="doc-a", session_id="session-1",
            filename="comp_a.pdf",
            reporting_period="FY2025",
            prior_period="FY2024",
            metrics_dict={"revenue": 1000.0},
            multi_year_data={"FY2025": {"revenue": 1000.0}, "FY2024": {"revenue": 900.0}},
        )
        comp_b = _make_extracted_metric(
            document_id="doc-b", session_id="session-1",
            filename="comp_b.pdf",
            reporting_period="FY2025",
            prior_period="FY2023",
            metrics_dict={"revenue": 2000.0},
            multi_year_data={"FY2025": {"revenue": 2000.0}, "FY2023": {"revenue": 1800.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[comp_a, comp_b],
            documents_docs=[_make_document("doc-a", "session-1"), _make_document("doc-b", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-a", "doc-b"]},
                context={"user_id": "user-1"},
            )

        summary = result.summary
        assert summary["common_periods"] == ["FY2025"]
        assert summary["has_common_periods"] is True

        rev_m = next(m for m in summary["metrics"] if m["metric_name"] == "revenue")
        p2025 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        assert p2025["peer_statistics"]["valid_count"] == 2
        assert p2025["peer_statistics"]["peer_average"] == 1500.0
        assert p2025["peer_statistics"]["highest"]["value"] == 2000.0
        assert p2025["peer_statistics"]["lowest"]["value"] == 1000.0

        p2024 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2024")
        assert p2024["peer_statistics"]["valid_count"] == 1
        assert p2024["peer_statistics"]["peer_average"] is None
        assert p2024["peer_statistics"]["highest"] is None
        assert p2024["peer_statistics"]["lowest"] is None

    # -----------------------------------------------------------------
    # Regression 3: Shared period with one metric missing
    # -----------------------------------------------------------------
    def test_regression_shared_period_one_metric_missing(self):
        """Period is shared, but a metric missing for 1 company produces peer_average=None for that metric."""
        comp_a = _make_extracted_metric(
            document_id="doc-a", session_id="session-1",
            filename="comp_a.pdf",
            metrics_dict={"revenue": 1000.0, "eps": 5.0},
            multi_year_data={"FY2025": {"revenue": 1000.0, "eps": 5.0}},
        )
        comp_b = _make_extracted_metric(
            document_id="doc-b", session_id="session-1",
            filename="comp_b.pdf",
            metrics_dict={"revenue": 2000.0},  # No eps
            multi_year_data={"FY2025": {"revenue": 2000.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[comp_a, comp_b],
            documents_docs=[_make_document("doc-a", "session-1"), _make_document("doc-b", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-a", "doc-b"]},
                context={"user_id": "user-1"},
            )

        summary = result.summary
        assert "FY2025" in summary["common_periods"]

        rev_m = next(m for m in summary["metrics"] if m["metric_name"] == "revenue")
        p_rev = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        assert p_rev["peer_statistics"]["valid_count"] == 2
        assert p_rev["peer_statistics"]["peer_average"] == 1500.0

        eps_m = next((m for m in summary["metrics"] if m["metric_name"] == "eps"), None)
        if eps_m:
            p_eps = next(p for p in eps_m["periods"] if p["fiscal_period"] == "FY2025")
            assert p_eps["peer_statistics"]["valid_count"] == 1
            assert p_eps["peer_statistics"]["peer_average"] is None
            assert p_eps["peer_statistics"]["highest"] is None
            assert p_eps["peer_statistics"]["lowest"] is None

    # -----------------------------------------------------------------
    # Regression 4: Genuine zero value
    # -----------------------------------------------------------------
    def test_regression_genuine_zero_peer_stats(self):
        """Genuine 0.0 is preserved and factored into peer average and rankings."""
        comp_a = _make_extracted_metric(
            document_id="doc-a", session_id="session-1",
            filename="comp_a.pdf",
            metrics_dict={"revenue": 100.0},
            multi_year_data={"FY2025": {"revenue": 100.0}},
        )
        comp_b = _make_extracted_metric(
            document_id="doc-b", session_id="session-1",
            filename="comp_b.pdf",
            metrics_dict={"revenue": 0.0},
            multi_year_data={"FY2025": {"revenue": 0.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[comp_a, comp_b],
            documents_docs=[_make_document("doc-a", "session-1"), _make_document("doc-b", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-a", "doc-b"]},
                context={"user_id": "user-1"},
            )

        rev_m = next(m for m in result.summary["metrics"] if m["metric_name"] == "revenue")
        p2025 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        assert p2025["peer_statistics"]["valid_count"] == 2
        assert p2025["peer_statistics"]["peer_average"] == 50.0
        assert p2025["peer_statistics"]["lowest"]["value"] == 0.0
        assert p2025["peer_statistics"]["highest"]["value"] == 100.0

    # -----------------------------------------------------------------
    # Regression 5: Three companies where only two have metric data
    # -----------------------------------------------------------------
    def test_regression_three_companies_partial_metric(self):
        """Three companies in comparison, only 2 report metric -> average divided by 2, not 3."""
        comp_a = _make_extracted_metric(
            document_id="doc-a", session_id="session-1",
            filename="comp_a.pdf",
            metrics_dict={"revenue": 100.0},
            multi_year_data={"FY2025": {"revenue": 100.0}},
        )
        comp_b = _make_extracted_metric(
            document_id="doc-b", session_id="session-1",
            filename="comp_b.pdf",
            metrics_dict={"revenue": 200.0},
            multi_year_data={"FY2025": {"revenue": 200.0}},
        )
        comp_c = _make_extracted_metric(
            document_id="doc-c", session_id="session-1",
            filename="comp_c.pdf",
            metrics_dict={},
            multi_year_data={"FY2025": {}},
        )
        db = MockDB(
            extracted_metrics_docs=[comp_a, comp_b, comp_c],
            documents_docs=[
                _make_document("doc-a", "session-1"),
                _make_document("doc-b", "session-1"),
                _make_document("doc-c", "session-1"),
            ],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-a", "doc-b", "doc-c"]},
                context={"user_id": "user-1"},
            )

        rev_m = next(m for m in result.summary["metrics"] if m["metric_name"] == "revenue")
        p2025 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        stats = p2025["peer_statistics"]
        assert stats["valid_count"] == 2
        assert stats["peer_average"] == 150.0

    # -----------------------------------------------------------------
    # Regression 6: Single-company period must not produce peer average
    # -----------------------------------------------------------------
    def test_regression_single_company_period_no_peer_stats(self):
        """Any period with valid_count < 2 must strictly have peer_average=None."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-bbby"]},
                context={"user_id": "user-1"},
            )

        for m in result.summary["metrics"]:
            for p in m["periods"]:
                assert p["peer_statistics"]["peer_average"] is None
                assert p["peer_statistics"]["highest"] is None
                assert p["peer_statistics"]["lowest"] is None

    # -----------------------------------------------------------------
    # Regression 7: Zero common periods metadata
    # -----------------------------------------------------------------
    def test_regression_zero_common_periods_metadata(self):
        """When zero common periods exist, has_common_periods=False and comparison_note is set."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, BBBY_METRIC],
            documents_docs=[APPLE_DOC, BBBY_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-bbby"]},
                context={"user_id": "user-1"},
            )

        summary = result.summary
        assert summary["has_common_periods"] is False
        assert summary["common_periods"] == []
        assert "No common fiscal reporting periods" in summary["comparison_note"]
        assert len(summary["summary_insights"]) > 0

    # -----------------------------------------------------------------
    # Regression 8: Reverse document order / cache hit
    # -----------------------------------------------------------------
    def test_regression_reverse_document_order_cache_hit(self):
        """Comparing [doc-a, doc-b] then [doc-b, doc-a] yields exact cache hit and identical summary."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            res1 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
            assert res1.metadata["cache_hit"] is False

            res2 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-msft", "doc-apple"]},
                context={"user_id": "user-1"},
            )
            assert res2.metadata["cache_hit"] is True
            assert res1.summary["common_periods"] == res2.summary["common_periods"]

    # -----------------------------------------------------------------
    # Regression 9: Stale cache after extracted_metrics update
    # -----------------------------------------------------------------
    def test_regression_stale_cache_invalidation(self):
        """Cache is invalidated when extracted_metrics.updated_at changes."""
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 2, 1, tzinfo=timezone.utc)
        a1 = dict(APPLE_METRIC)
        a1["updated_at"] = t1
        m1 = dict(MSFT_METRIC)
        m1["updated_at"] = t1

        db = MockDB(
            extracted_metrics_docs=[a1, m1],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            res1 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
            assert res1.metadata["cache_hit"] is False

            # Update timestamp
            a1["updated_at"] = t2
            res2 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )
            assert res2.metadata["cache_hit"] is False

    # -----------------------------------------------------------------
    # Regression 10: Different sessions cannot collide
    # -----------------------------------------------------------------
    def test_regression_different_sessions_cannot_collide(self):
        """Same documents in session-1 vs session-2 produce distinct cache entries."""
        db = MockDB(
            extracted_metrics_docs=[
                _make_extracted_metric("doc-a", "session-1"),
                _make_extracted_metric("doc-b", "session-1"),
                _make_extracted_metric("doc-a", "session-2"),
                _make_extracted_metric("doc-b", "session-2"),
            ],
            documents_docs=[
                _make_document("doc-a", "session-1"),
                _make_document("doc-b", "session-1"),
                _make_document("doc-a", "session-2"),
                _make_document("doc-b", "session-2"),
            ],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            res1 = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-a", "doc-b"]},
                context={"user_id": "user-1"},
            )
            res2 = self.agent.execute(
                payload={"session_id": "session-2", "document_ids": ["doc-a", "doc-b"]},
                context={"user_id": "user-1"},
            )
            assert res1.metadata["cache_hit"] is False
            assert res2.metadata["cache_hit"] is False

    # -----------------------------------------------------------------
    # Regression 11: Different document sets cannot collide
    # -----------------------------------------------------------------
    def test_regression_different_document_sets_cannot_collide(self):
        """Comparison of [A, B] and [A, B, C] have different hashes."""
        h_ab = ComparisonResultDocument.compute_document_ids_hash(["doc-a", "doc-b"])
        h_abc = ComparisonResultDocument.compute_document_ids_hash(["doc-a", "doc-b", "doc-c"])
        assert h_ab != h_abc

    # -----------------------------------------------------------------
    # Regression 12: Frontend/API schema compatibility
    # -----------------------------------------------------------------
    def test_regression_frontend_schema_compatibility(self):
        """ComparisonOutput model validates all fields expected by frontend."""
        output = ComparisonOutput(
            session_id="session-1",
            companies=[CompanyInfo(document_id="doc-1", company_name="Apple")],
            fiscal_periods=["FY2025"],
            common_periods=["FY2025"],
            company_only_periods={},
            has_common_periods=True,
            comparison_note=None,
            summary_insights=["Insight 1"],
            metrics=[],
        )
        dump = output.model_dump(mode="json")
        assert "common_periods" in dump
        assert "company_only_periods" in dump
        assert "has_common_periods" in dump
        assert "comparison_note" in dump
        assert "summary_insights" in dump

    # -----------------------------------------------------------------
    # Regression 13: Comparison PDF with no common periods
    # -----------------------------------------------------------------
    def test_regression_comparison_pdf_no_common_periods(self):
        """Comparison PDF builder generates valid PDF with notice when no common periods exist."""
        from agents.comparison.pdf_builder import comparison_pdf_builder
        comp_data = {
            "session_id": "session-1",
            "companies": [{"document_id": "doc-a", "company_name": "Apple"}, {"document_id": "doc-b", "company_name": "BBBY"}],
            "fiscal_periods": ["FY2025", "FY2022"],
            "common_periods": [],
            "has_common_periods": False,
            "comparison_note": "No common fiscal reporting periods exist.",
            "metrics": [
                {
                    "metric_name": "revenue",
                    "display_name": "Revenue",
                    "periods": [
                        {
                            "fiscal_period": "FY2025",
                            "values": [{"company_name": "Apple", "value": 416161.0, "available": True}],
                            "peer_statistics": {"valid_count": 1, "peer_average": None, "highest": None, "lowest": None},
                        }
                    ],
                }
            ],
        }
        pdf_bytes = comparison_pdf_builder.build_pdf(comp_data)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500

    # -----------------------------------------------------------------
    # Regression 14: Comparison PDF with common periods
    # -----------------------------------------------------------------
    def test_regression_comparison_pdf_with_common_periods(self):
        """Comparison PDF builder generates valid PDF when common periods exist."""
        from agents.comparison.pdf_builder import comparison_pdf_builder
        comp_data = {
            "session_id": "session-1",
            "companies": [{"document_id": "doc-a", "company_name": "Apple"}, {"document_id": "doc-b", "company_name": "MSFT"}],
            "fiscal_periods": ["FY2025"],
            "common_periods": ["FY2025"],
            "has_common_periods": True,
            "metrics": [
                {
                    "metric_name": "revenue",
                    "display_name": "Revenue",
                    "periods": [
                        {
                            "fiscal_period": "FY2025",
                            "values": [
                                {"company_name": "Apple", "value": 416161.0, "available": True},
                                {"company_name": "MSFT", "value": 281724.0, "available": True},
                            ],
                            "peer_statistics": {
                                "valid_count": 2,
                                "peer_average": 348942.5,
                                "highest": {"company_name": "Apple", "value": 416161.0},
                                "lowest": {"company_name": "MSFT", "value": 281724.0},
                            },
                        }
                    ],
                }
            ],
            "summary_insights": ["Apple led peers in Revenue."],
        }
        pdf_bytes = comparison_pdf_builder.build_pdf(comp_data)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500

    # -----------------------------------------------------------------
    # Regression 15: Report Compiler with no common periods
    # -----------------------------------------------------------------
    def test_regression_report_compiler_no_common_periods(self):
        """Report Compiler compiles cleanly when comparison has no common periods."""
        from agents.report.report_compiler import ReportCompiler
        comp_doc = {
            "session_id": "session-1",
            "comparison": {
                "session_id": "session-1",
                "companies": [{"company_name": "Apple"}, {"company_name": "BBBY"}],
                "fiscal_periods": ["FY2025", "FY2022"],
                "common_periods": [],
                "has_common_periods": False,
                "metrics": [
                    {
                        "metric_name": "revenue",
                        "display_name": "Revenue",
                        "periods": [
                            {
                                "fiscal_period": "FY2025",
                                "values": [{"company_name": "Apple", "value": 416161.0, "available": True}],
                                "peer_statistics": {"valid_count": 1, "peer_average": None},
                            }
                        ],
                    }
                ],
            },
        }
        report = ReportCompiler.compile(
            session_id="session-1",
            user_id="user-1",
            documents=[APPLE_DOC, BBBY_DOC],
            extracted_metrics_list=[APPLE_METRIC, BBBY_METRIC],
            comparison_results_list=[comp_doc],
        )
        assert report.comparison.is_available is True
        assert report.executive_summary is not None

    # -----------------------------------------------------------------
    # Regression 16: Report Compiler with common periods
    # -----------------------------------------------------------------
    def test_regression_report_compiler_with_common_periods(self):
        """Report Compiler compiles comparison highlights when peer average is available."""
        from agents.report.report_compiler import ReportCompiler
        comp_doc = {
            "session_id": "session-1",
            "comparison": {
                "session_id": "session-1",
                "companies": [{"company_name": "Apple"}, {"company_name": "MSFT"}],
                "fiscal_periods": ["FY2025"],
                "common_periods": ["FY2025"],
                "has_common_periods": True,
                "metrics": [
                    {
                        "metric_name": "revenue",
                        "display_name": "Revenue",
                        "periods": [
                            {
                                "fiscal_period": "FY2025",
                                "values": [
                                    {"company_name": "Apple", "value": 416161.0, "available": True},
                                    {"company_name": "MSFT", "value": 281724.0, "available": True},
                                ],
                                "peer_statistics": {
                                    "valid_count": 2,
                                    "peer_average": 348942.5,
                                    "highest": {"company_name": "Apple", "value": 416161.0},
                                    "lowest": {"company_name": "MSFT", "value": 281724.0},
                                },
                            }
                        ],
                    }
                ],
            },
        }
        report = ReportCompiler.compile(
            session_id="session-1",
            user_id="user-1",
            documents=[APPLE_DOC, MSFT_DOC],
            extracted_metrics_list=[APPLE_METRIC, MSFT_METRIC],
            comparison_results_list=[comp_doc],
        )
        assert report.comparison.is_available is True
        assert len(report.executive_summary.comparison_highlights) > 0

    # -----------------------------------------------------------------
    # Regression 17: Provenance survives normalization
    # -----------------------------------------------------------------
    def test_regression_provenance_survives_normalization(self):
        """Raw values, source scale, and provenance are retained alongside normalized values."""
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, MSFT_METRIC],
            documents_docs=[APPLE_DOC, MSFT_DOC],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-msft"]},
                context={"user_id": "user-1"},
            )

        rev_m = next(m for m in result.summary["metrics"] if m["metric_name"] == "revenue")
        p2025 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        apple_v = next(v for v in p2025["values"] if v["document_id"] == "doc-apple")
        assert apple_v["normalized_value"] == 416161.0
        assert apple_v["normalized_unit"] == "USD Millions"
        assert apple_v["provenance"] is not None
        assert "evidence_snippet" in apple_v["provenance"]

    # -----------------------------------------------------------------
    # Regression 18: Incompatible currencies remain unavailable
    # -----------------------------------------------------------------
    def test_regression_incompatible_currencies_remain_unavailable(self):
        """Cross-currency comparison leaves peer stats unavailable."""
        inr_comp = _make_extracted_metric(
            document_id="doc-inr", session_id="session-1",
            filename="reliance_2025.pdf",
            reporting_currency="INR",
            reporting_scale="crores",
            metrics_dict={"revenue": 100000.0},
            multi_year_data={"FY2025": {"revenue": 100000.0}},
        )
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, inr_comp],
            documents_docs=[APPLE_DOC, _make_document("doc-inr", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-inr"]},
                context={"user_id": "user-1"},
            )

        rev_m = next(m for m in result.summary["metrics"] if m["metric_name"] == "revenue")
        p2025 = next(p for p in rev_m["periods"] if p["fiscal_period"] == "FY2025")
        assert p2025["unit_compatible"] is False
        assert p2025["peer_statistics"]["valid_count"] == 0
        assert p2025["peer_statistics"]["peer_average"] is None

    # -----------------------------------------------------------------
    # Regression 19: Percentage and per-share metrics not scale-converted
    # -----------------------------------------------------------------
    def test_regression_percentage_and_per_share_not_scale_converted(self):
        """Gross margin and EPS are not divided or multiplied by 1000."""
        agent = ComparisonAgent()
        raw_v, src_u, src_s, norm_v, norm_u = agent._normalize_metric_value(
            metric_name="gross_margin",
            raw_val=0.465,
            unit="%",
            currency="USD",
            scale="thousands",
        )
        assert norm_v == 0.465
        assert norm_u == "%"

        raw_eps, _, _, norm_eps, norm_eps_u = agent._normalize_metric_value(
            metric_name="eps",
            raw_val=6.97,
            unit="USD/share",
            currency="USD",
            scale="thousands",
        )
        assert norm_eps == 6.97
        assert norm_eps_u == "USD/share"

    # -----------------------------------------------------------------
    # Regression 20: No future or debt-maturity periods in comparison
    # -----------------------------------------------------------------
    def test_regression_no_future_or_debt_maturity_periods(self):
        """Future periods (e.g. FY2028, FY2029) from note disclosures are excluded."""
        debt_comp = _make_extracted_metric(
            document_id="doc-debt", session_id="session-1",
            reporting_period="FY2025",
            prior_period="FY2024",
            metrics_dict={"revenue": 500.0},
            multi_year_data={
                "FY2025": {"revenue": 500.0},
                "FY2028": {"debt_maturity": 200.0},  # Future maturity year
                "FY2029": {"debt_maturity": 300.0},  # Future maturity year
            },
        )
        db = MockDB(
            extracted_metrics_docs=[APPLE_METRIC, debt_comp],
            documents_docs=[APPLE_DOC, _make_document("doc-debt", "session-1")],
        )
        with patch("agents.comparison.comparison_agent.get_sync_db", return_value=db):
            result = self.agent.execute(
                payload={"session_id": "session-1", "document_ids": ["doc-apple", "doc-debt"]},
                context={"user_id": "user-1"},
            )

        periods = result.summary["fiscal_periods"]
        assert "FY2028" not in periods
        assert "FY2029" not in periods
        assert "FY2025" in periods
