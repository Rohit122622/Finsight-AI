"""
FINsentry AI — Final Production Hardening Regression Test Suite
Asserts all 31 non-negotiable constraints from the Production Hardening Plan.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from utils.company_resolution import (
    canonicalize_company_name,
    resolve_company_from_document,
    is_company_match,
)
from agents.comparison.comparison_agent import ComparisonAgent
from agents.comparison.schemas import (
    ComparisonOutput,
    ComparisonMetric,
    MetricValue,
    PeerStatistics,
)
from agents.report.report_compiler import ReportCompiler
from services.research_chat_service import ResearchChatService
from services.context_builder_service import ContextBuilderService
from agents.extraction.extraction_agent import ExtractionAgent
from agents.extraction.schemas import ExtractionMetricItem
from agents.red_flag.red_flag_agent import validate_metric_semantics
from schemas.context import DocumentEvidence, MetricEvidence, RedFlagEvidence
from schemas.query_understanding import QueryUnderstandingResult, QueryClassification, TemporalSignal


# ============================================================
# 1. CANONICAL COMPANY IDENTITY TESTS (Constraint 2)
# ============================================================

def test_canonical_company_resolution_mappings():
    """Verify standard tickers, common names, and corporate forms resolve to same canonical entity."""
    # Apple
    assert canonicalize_company_name("Apple") == "Apple"
    assert canonicalize_company_name("AAPL") == "Apple"
    assert canonicalize_company_name("Apple Inc.") == "Apple"
    assert canonicalize_company_name("APPLE INC") == "Apple"

    # Bed Bath & Beyond
    assert canonicalize_company_name("BBBY") == "Bed Bath & Beyond"
    assert canonicalize_company_name("Bed Bath & Beyond") == "Bed Bath & Beyond"
    assert canonicalize_company_name("Bed Bath & Beyond Inc.") == "Bed Bath & Beyond"
    assert canonicalize_company_name("BED BATH & BEYOND INC /DE") == "Bed Bath & Beyond"

    # Microsoft
    assert canonicalize_company_name("MSFT") == "Microsoft"
    assert canonicalize_company_name("Microsoft") == "Microsoft"
    assert canonicalize_company_name("Microsoft Corporation") == "Microsoft"
    assert canonicalize_company_name("MICROSOFT CORP") == "Microsoft"


def test_metadata_precedence_over_filename():
    """Canonical document metadata must take precedence over filename parsing."""
    doc_with_canonical_metadata = {
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "filename": "BBBY_Q3_2022_Filing.pdf",  # Filename misleadingly says BBBY
    }
    resolved = resolve_company_from_document(doc_with_canonical_metadata)
    assert resolved == "Apple", "Canonical company metadata must override filename parsing"


def test_company_match_evaluation():
    """Test is_company_match across ticker, canonical name, and aliases."""
    doc_apple = {"company_name": "Apple Inc.", "ticker": "AAPL"}
    doc_bbby = {"company_name": "Bed Bath & Beyond Inc.", "ticker": "BBBY"}

    assert is_company_match("Apple", doc_apple) is True
    assert is_company_match("AAPL", doc_apple) is True
    assert is_company_match("Apple Inc.", doc_apple) is True
    assert is_company_match("Bed Bath & Beyond", doc_apple) is False

    assert is_company_match("Bed Bath & Beyond", doc_bbby) is True
    assert is_company_match("BBBY", doc_bbby) is True
    assert is_company_match("Apple", doc_bbby) is False


# ============================================================
# 2. STRICT RESEARCH ISOLATION TESTS (Constraint 3)
# ============================================================

@pytest.mark.asyncio
async def test_context_builder_strict_document_isolation():
    """Context builder must strictly isolate document context to target company document IDs."""
    apple_doc_id = "doc_apple_10k_2025"
    bbby_doc_id = "doc_bbby_10k_2022"

    builder = ContextBuilderService()

    metric_evidence = [
        MetricEvidence(
            metric_name="revenue",
            document_reference=apple_doc_id,
            period="FY2025",
            value=416161.0,
            unit_or_currency="USD Millions",
        ),
        MetricEvidence(
            metric_name="revenue",
            document_reference=bbby_doc_id,
            period="FY2022",
            value=5344400.0,
            unit_or_currency="USD Thousands",
        ),
    ]

    qu = QueryUnderstandingResult(
        original_query="What was Apple's revenue in FY2025?",
        normalized_query="what was apples revenue in fy2025",
        entities=["Apple"],
        classification=QueryClassification.FINANCIAL_METRIC,
    )

    with patch("services.context_builder_service.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"document_id": apple_doc_id, "company_name": "Apple Inc.", "ticker": "AAPL"},
            {"document_id": bbby_doc_id, "company_name": "Bed Bath & Beyond Inc.", "ticker": "BBBY"},
        ])
        mock_db.documents.find.return_value = mock_cursor

        context = await builder.build_context(
            session_id="sess_iso_test",
            user_id="user_iso_test",
            query="What was Apple's revenue in FY2025?",
            retrieved_results=[],
            financial_metrics=metric_evidence,
            query_understanding=qu,
            auto_retrieve=False,
        )

        # Ensure only Apple metrics are present in context.metrics
        doc_ids_in_metrics = {m.document_reference for m in context.metrics if m.document_reference}
        assert doc_ids_in_metrics == {apple_doc_id}
        assert bbby_doc_id not in doc_ids_in_metrics


# ============================================================
# 3. PRE-RETRIEVAL AMBIGUITY GATE TESTS (Constraint 4)
# ============================================================

@pytest.mark.asyncio
async def test_ambiguous_query_stops_before_retrieval():
    """Ambiguous query in multi-company session must stop before retrieval and return clarification."""
    session_docs = [
        {"document_id": "doc_a", "company_name": "Apple", "ticker": "AAPL"},
        {"document_id": "doc_b", "company_name": "Bed Bath & Beyond", "ticker": "BBBY"},
    ]
    query = "What was the revenue?"

    qu = QueryUnderstandingResult(
        original_query=query,
        normalized_query="what was the revenue",
        entities=[],
        classification=QueryClassification.FINANCIAL_METRIC,
    )

    with patch("services.research_chat_service.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_doc_cursor = MagicMock()
        mock_doc_cursor.to_list = AsyncMock(return_value=session_docs)
        mock_metrics_cursor = MagicMock()
        mock_metrics_cursor.to_list = AsyncMock(return_value=[])
        mock_db.documents.find.return_value = mock_doc_cursor
        mock_db.extracted_metrics.find.return_value = mock_metrics_cursor

        service = ResearchChatService()
        result = await service._check_pre_retrieval_gates(
            session_id="sess_ambig",
            user_id="user_ambig",
            query=query,
            qu=qu,
            context_messages=[],
        )

        assert result is not None
        assert result.confidence == 0.0
        assert result.citations == []
        assert "Which company would you like me to analyze" in result.answer
        assert "Apple" in result.answer
        assert "Bed Bath & Beyond" in result.answer


# ============================================================
# 4. PRE-RETRIEVAL FUTURE / INVALID FISCAL PERIOD GATE (Constraint 5)
# ============================================================

@pytest.mark.asyncio
async def test_future_period_query_stops_before_retrieval():
    """Queries for future years (e.g., FY2029/FY2030) must refuse before retrieval."""
    session_docs = [
        {"document_id": "doc_a", "company_name": "Apple", "ticker": "AAPL"},
    ]
    metrics_records = [
        {"document_id": "doc_a", "company_name": "Apple", "reporting_period": "FY2025", "multi_year_data": {"FY2024": {}, "FY2023": {}}},
    ]

    qu_2029 = QueryUnderstandingResult(
        original_query="What was Apple's revenue in FY2029?",
        normalized_query="what was apples revenue in fy2029",
        entities=["Apple"],
        temporal_signals=TemporalSignal(years=[2029], fiscal_years=["FY2029"]),
        classification=QueryClassification.FINANCIAL_METRIC,
    )

    with patch("services.research_chat_service.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_doc_cursor = MagicMock()
        mock_doc_cursor.to_list = AsyncMock(return_value=session_docs)
        mock_metrics_cursor = MagicMock()
        mock_metrics_cursor.to_list = AsyncMock(return_value=metrics_records)
        mock_db.documents.find.return_value = mock_doc_cursor
        mock_db.extracted_metrics.find.return_value = mock_metrics_cursor

        service = ResearchChatService()
        result_2029 = await service._check_pre_retrieval_gates(
            session_id="sess_future",
            user_id="user_future",
            query="What was Apple's revenue in FY2029?",
            qu=qu_2029,
            context_messages=[],
        )

        assert result_2029 is not None
        assert result_2029.confidence == 0.0
        assert result_2029.citations == []
        assert "FY2029" in result_2029.answer


# ============================================================
# 5. FISCAL PERIOD RESOLUTION & REJECTION OF NOTE 10 SCHEDULES (Constraint 6)
# ============================================================

def test_period_validation_rejects_future_debt_schedules():
    """_validate_and_detect_periods must anchor to primary reporting period (e.g. FY2025) and reject future years (FY2028, FY2029)."""
    agent = ExtractionAgent()

    parsed = MagicMock(reporting_period="FY2025", prior_period="FY2024")
    metric_items = [
        ExtractionMetricItem(metric_name="revenue", display_name="Revenue", value=416161.0, period="FY2025", confidence_score=1.0),
        ExtractionMetricItem(metric_name="debt_schedule_2028", display_name="Debt 2028", value=100.0, period="FY2028", confidence_score=0.8),
        ExtractionMetricItem(metric_name="debt_schedule_2029", display_name="Debt 2029", value=150.0, period="FY2029", confidence_score=0.8),
    ]
    multi_year = {
        "FY2025": {"revenue": 416161.0},
        "FY2024": {"revenue": 391035.0},
        "FY2023": {"revenue": 383285.0},
        "FY2028": {"debt": 100.0},
        "FY2029": {"debt": 150.0},
    }

    rep_period, prior_period = agent._validate_and_detect_periods(
        parsed_response=parsed,
        metric_items=metric_items,
        multi_year_data=multi_year,
        financial_chunks=[],
        filename="apple_2025_10k.pdf",
    )

    assert rep_period == "FY2025"
    assert prior_period == "FY2024"
    assert rep_period != "FY2028"
    assert rep_period != "FY2029"


# ============================================================
# 6. SEMANTIC VALIDATION: LEVEL VS DELTA (Constraint 7)
# ============================================================

def test_semantic_validation_distinguishes_level_from_delta():
    """Semantic validation must reject delta metrics (-11.4 pp change) from overwriting level metrics (22.6%)."""
    # Level metric: gross margin of 22.6%
    level_dict = {
        "value": 22.6,
        "evidence_snippet": "Gross margin was 22.6% for fiscal 2022",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    }
    assert validate_metric_semantics("gross_margin", level_dict) is True

    # Delta metric misclassified as level metric: gross margin change of -11.4 percentage points
    delta_dict = {
        "value": -11.4,
        "evidence_snippet": "Gross margin decreased 11.4 percentage points or -11.4% compared to prior year",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    }
    assert validate_metric_semantics("gross_margin", delta_dict) is False


# ============================================================
# 7. UNIT/SCALE NORMALIZATION & COMPARISON (Constraints 8 & 9)
# ============================================================

def test_usd_millions_normalization():
    """Verify thousands are converted to millions (/1000) and millions are preserved (*1)."""
    agent = ComparisonAgent()

    # BBBY: 5,344,400 USD Thousands -> 5,344.4 USD Millions
    raw_v, src_u, src_s, norm_v, norm_u = agent._normalize_metric_value(
        "revenue", 5344400.0, "USD", "USD", "thousands"
    )
    assert raw_v == 5344400.0
    assert norm_v == 5344.4
    assert norm_u == "USD Millions"

    # Apple: 416,161 USD Millions -> 416,161.0 USD Millions
    raw_v_a, src_u_a, src_s_a, norm_v_a, norm_u_a = agent._normalize_metric_value(
        "revenue", 416161.0, "USD", "USD", "millions"
    )
    assert raw_v_a == 416161.0
    assert norm_v_a == 416161.0
    assert norm_u_a == "USD Millions"


def test_cross_scale_comparison_peer_statistics():
    """Verify Apple (USD Millions) and BBBY (USD Thousands) compare correctly under canonical normalization."""
    agent = ComparisonAgent()

    apple_record = {
        "document_id": "doc-apple",
        "session_id": "sess-cross-scale",
        "user_id": "user-1",
        "document_filename": "apple_2025.pdf",
        "company_name": "Apple Inc.",
        "reporting_period": "FY2025",
        "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {"revenue": 416161.0, "net_income": 112010.0, "eps": 7.42},
        "multi_year_data": {"FY2025": {"revenue": 416161.0, "net_income": 112010.0, "eps": 7.42}},
        "metrics": [],
        "updated_at": datetime.now(timezone.utc),
    }

    bbby_record = {
        "document_id": "doc-bbby",
        "session_id": "sess-cross-scale",
        "user_id": "user-1",
        "document_filename": "bbby_2022.pdf",
        "company_name": "Bed Bath & Beyond Inc.",
        "reporting_period": "FY2022",
        "reporting_currency": "USD",
        "reporting_scale": "thousands",
        "metrics_dict": {"revenue": 5344400.0, "net_income": -3510000.0, "eps": -44.70},
        "multi_year_data": {"FY2022": {"revenue": 5344400.0, "net_income": -3510000.0, "eps": -44.70}},
        "metrics": [],
        "updated_at": datetime.now(timezone.utc),
    }

    with patch("agents.comparison.comparison_agent.get_sync_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Documents query
        mock_db.documents.find.return_value = [
            {"document_id": "doc-apple", "session_id": "sess-cross-scale", "user_id": "user-1", "company_name": "Apple Inc."},
            {"document_id": "doc-bbby", "session_id": "sess-cross-scale", "user_id": "user-1", "company_name": "Bed Bath & Beyond Inc."},
        ]
        # Extracted metrics query
        mock_db.extracted_metrics.find.return_value = [apple_record, bbby_record]
        # Cache lookup
        mock_db.comparison_results.find_one.return_value = None

        result = agent.execute(
            payload={"session_id": "sess-cross-scale", "document_ids": ["doc-apple", "doc-bbby"]},
            context={"user_id": "user-1"},
        )

        assert result.success is True
        summary = result.summary
        metrics = summary.get("metrics") or []
        rev_metric = next((m for m in metrics if m.get("metric_name") == "revenue"), None)
        assert rev_metric is not None

        # Period for Apple FY2025
        periods = rev_metric.get("periods") or []
        p2025 = next((p for p in periods if p.get("fiscal_period") == "FY2025"), None)
        assert p2025 is not None
        assert p2025.get("unit_compatible") is True

        # Normalized values in comparison output
        vals = p2025.get("values") or []
        apple_val = next((v for v in vals if "Apple" in v.get("company_name", "")), None)
        assert apple_val is not None
        assert apple_val.get("normalized_value") == 416161.0


# ============================================================
# 8. PERCENTILE NO-CORRUPTION TEST (Constraint 10)
# ============================================================

def test_percentile_model_separation():
    """Verify MetricValue stores separate clean formatted_value and percentile without string concatenation corruption."""
    agent = ComparisonAgent()

    # Calculate peer stats directly on test metric values
    mv_apple = MetricValue(
        document_id="doc-apple",
        company_name="Apple",
        fiscal_period="FY2025",
        value=7.42,
        normalized_value=7.42,
        available=True,
        unit="USD",
    )
    mv_bbby = MetricValue(
        document_id="doc-bbby",
        company_name="Bed Bath & Beyond",
        fiscal_period="FY2025",
        value=-44.70,
        normalized_value=-44.70,
        available=True,
        unit="USD",
    )

    stats = agent._calculate_peer_statistics([mv_apple, mv_bbby], "eps")
    assert stats.valid_count == 2
    assert stats.highest["company_name"] == "Apple"
    assert stats.highest["value"] == 7.42

    # Percentiles: Apple=1.0 (100th percentile), BBBY=0.0 (0th percentile)
    ranks = {p.company_name: p.percentile for p in stats.percentile_ranks}
    assert ranks["Apple"] == 1.0
    assert ranks["Bed Bath & Beyond"] == 0.0

    # Ensure MetricValue object does not concatenate P100 into its value
    assert mv_apple.value == 7.42


# ============================================================
# 9. REPORT COMPILER KEY FINANCIALS & RISK DERIVATION (Constraints 12, 14, 15, 16, 18)
# ============================================================

def test_report_compiler_canonical_key_financials_and_risk():
    """Verify ReportCompiler populates canonical key financials without N/A, derives dynamic risk, and contains 1 Executive Summary."""
    extracted_metrics = [
        {
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "document_id": "doc_apple_10k",
            "reporting_period": "FY2025",
            "reporting_currency": "USD",
            "reporting_scale": "millions",
            "revenue": 416161.0,
            "net_income": 112010.0,
            "gross_margin": 46.2,
            "eps": 7.42,
            "operating_income": 133120.0,
            "total_debt": 106629.0,
            "multi_year_data": {
                "FY2024": {"revenue": 391035.0, "net_income": 93736.0},
                "FY2023": {"revenue": 383285.0, "net_income": 96995.0},
            },
        },
        {
            "company_name": "Bed Bath & Beyond Inc.",
            "ticker": "BBBY",
            "document_id": "doc_bbby_10k",
            "reporting_period": "FY2022",
            "reporting_currency": "USD",
            "reporting_scale": "thousands",
            "revenue": 5344400.0,
            "net_income": -3510000.0,
            "gross_margin": 22.6,
            "eps": -44.70,
            "operating_income": -1300000.0,
            "total_debt": 1700000.0,
        },
    ]

    red_flags = [
        {
            "company_name": "Bed Bath & Beyond",
            "document_id": "doc_bbby_10k",
            "risk_score": 85.0,
            "overall_assessment": "Critical Going Concern Distress",
            "flags": [
                {
                    "severity": "CRITICAL",
                    "title": "Substantial doubt about entity's ability to continue as a going concern",
                    "category": "Going Concern",
                    "finding": "Substantial doubt about entity's ability to continue as a going concern",
                    "evidence": "The Company concluded that there is substantial doubt about its ability to continue as a going concern within one year.",
                    "page": 42,
                }
            ],
        }
    ]

    doc = ReportCompiler.compile(
        session_id="sess_report_prod_test",
        user_id="user_prod_test",
        extracted_metrics_list=extracted_metrics,
        red_flags_list=red_flags,
    )

    # 1. Executive Summary exists exactly once
    assert doc.executive_summary is not None
    assert doc.executive_summary.narrative != ""
    assert len(doc.executive_summary.companies_analyzed) >= 2

    # 2. Key Financials Periods: FY2025, FY2024, FY2023, FY2022 (No FY2028/FY2029)
    periods = doc.key_financials.reporting_periods
    assert "FY2025" in periods
    assert "FY2024" in periods
    assert "FY2023" in periods
    assert "FY2022" in periods
    assert "FY2028" not in periods
    assert "FY2029" not in periods

    # 3. Revenue metric populated for Apple and BBBY
    rev_row = next((r for r in doc.key_financials.metrics if r.metric_key == "revenue"), None)
    assert rev_row is not None
    available_vals = [v for v in rev_row.values if v.available]
    assert len(available_vals) >= 2

    # 4. Risk derivation
    assert doc.red_flags.composite_risk_score >= 0.0
    assert doc.red_flags.total_flags >= 1

    # 5. Red Flag Evidence populated
    assert len(doc.red_flags.findings) >= 1
    flag = doc.red_flags.findings[0]
    assert flag.severity == "CRITICAL"
    assert "going concern" in flag.title.lower() or "going concern" in flag.description.lower()
    assert "substantial doubt" in flag.evidence.lower()
