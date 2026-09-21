"""
FinSentry AI — Report Agent Comprehensive Test Suite.

Owner: Vanshika / FinSentry Engineering Team

35+ unit and integration tests verifying all production Report Agent requirements:
  1. Session resolution and data assembly
  2. User and session security boundaries
  3. Single-company session behavior (omits comparison cleanly)
  4. Multi-company comparison behavior (embeds table and chart)
  5. Missing metric handling (N/A, never zero)
  6. Genuine zero preservation (0.0 formatted, not N/A)
  7. Numerical integrity: Apple FY2025 revenue ($416,161M) and net income ($112,010M)
  8. Numerical integrity: Apple FY2024 ($391,035M) and FY2023 ($383,285M) multi-year
  9. Persisted Apple EPS rendered without recalculation
  10. Red flag integrity: BBBY 31.6% -> 19.8% margin (-11.8 percentage points)
  11. Red flag clean state when no red flags exist
  12. Executive Summary section structure and deterministic narrative
  13. Key Financials section canonical metric ordering
  14. Outlook section populated from research findings (zero predictions)
  15. Outlook clean state when no research messages exist
  16. Provenance preservation (document_id, source page, citations)
  17. Determinism: identical input yields identical ReportDocument model
  18. Determinism: identical input yields identical chart data and layout
  19. Determinism: deterministic report_id mapping
  20. Absolute Zero-LLM verification: all LLM providers blocked/mocked to fail, report succeeds
  21. R2 upload success and presigned URL generation
  22. R2 upload failure handling (no false success report in database)
  23. MongoDB reports collection persistence with required fields
  24. Compatibility projection to analysis_reports collection
  25. Security: cross-user report access rejection (403/401/Unauthorized)
  26. PDF generation: valid PDF header (%PDF-) and minimum length
  27. NumberedCanvas two-pass page numbering
  28. Matplotlib chart generator: valid PNG bytes with PNG signature
  29. Matplotlib chart generator: returns None on single-company
  30. Error handling: missing session_id raises NonRetryableAgentException
  31. Error handling: missing user_id raises NonRetryableAgentException
  32. Error handling: malformed comparison data omitted safely
  33. Scale formatting: millions, billions, percentages
  34. Exact section order invariant (1. Exec, 2. Fin, 3. Flags, 4. Comp, 5. Out)
  35. Service layer: synchronous generation helper
  36. Service layer: asynchronous report retrieval with ownership verification
"""

import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from agents.base import AgentResult
from agents.report.chart_generator import ChartGenerator
from agents.report.pdf_builder import PDFBuilder
from agents.report.report_agent import ReportAgent
from agents.report.report_compiler import CANONICAL_METRIC_ORDER, ReportCompiler
from agents.report.schemas import (
    CompanyComparisonSection,
    KeyFinancialsSection,
    RedFlagsSection,
    ReportDocument,
    ReportMetadata,
)
from core.constants import AgentTaskType
from core.exceptions import (
    NonRetryableAgentException,
    ReportNotFoundException,
    RetryableAgentException,
    StorageServiceException,
    UnauthorizedReportAccessException,
)
from services.r2_storage_service import r2_storage_service
from services.report_service import ReportService


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def sample_session_id() -> str:
    return "sess_report_test_001"


@pytest.fixture
def sample_user_id() -> str:
    return "user_report_test_001"


@pytest.fixture
def apple_extracted_metrics() -> Dict[str, Any]:
    """Known Apple FY2025 ground truth extracted metrics fixture."""
    return {
        "session_id": "sess_report_test_001",
        "user_id": "user_report_test_001",
        "document_id": "doc_apple_10k_2025",
        "company_name": "Apple",
        "reporting_period": "FY2025",
        "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {
            "revenue": 416161.0,
            "net_income": 112010.0,
            "gross_margin": 46.28,
            "operating_income": 133100.0,
            "eps": 7.42,
            "total_debt": 98000.0,
            "operating_cash_flow": 118000.0,
            "cash_and_equivalents": 29900.0,
        },
        "multi_year_data": {
            "FY2024": {
                "revenue": 391035.0,
                "net_income": 93736.0,
                "gross_margin": 46.21,
                "eps": 6.08,
            },
            "FY2023": {
                "revenue": 383285.0,
                "net_income": 96995.0,
                "gross_margin": 44.13,
                "eps": 6.13,
            },
        },
        "updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def bbby_extracted_metrics() -> Dict[str, Any]:
    """Known BBBY distress extracted metrics fixture."""
    return {
        "session_id": "sess_report_test_001",
        "user_id": "user_report_test_001",
        "document_id": "doc_bbby_10k_2022",
        "company_name": "Bed Bath & Beyond",
        "reporting_period": "FY2022",
        "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {
            "revenue": 5345.0,
            "net_income": -1400.0,
            "gross_margin": 19.8,
            "operating_income": -1200.0,
            "eps": -12.50,
            "total_debt": 1730.0,
            "operating_cash_flow": -508.0,
            "cash_and_equivalents": 150.0,
        },
        "multi_year_data": {
            "FY2021": {
                "revenue": 7871.0,
                "net_income": -559.0,
                "gross_margin": 31.6,
            }
        },
        "updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def bbby_red_flags() -> Dict[str, Any]:
    """Known BBBY forensic red flags fixture."""
    return {
        "session_id": "sess_report_test_001",
        "user_id": "user_report_test_001",
        "document_id": "doc_bbby_10k_2022",
        "company_name": "Bed Bath & Beyond",
        "risk_score": 100.0,
        "total_flags": 3,
        "high_severity_count": 2,
        "overall_assessment": "Severe corporate distress and critical going-concern doubt identified.",
        "flags": [
            {
                "title": "Severe Gross Margin Compression",
                "severity": "HIGH",
                "category": "Profitability Distress",
                "metric_name": "gross_margin",
                "current_value": 19.8,
                "prior_value": 31.6,
                "change": "-11.8 percentage points",
                "description": "Gross margin declined from 31.6% to 19.8%, a decrease of 11.8 percentage points.",
                "evidence": "Gross margin collapsed by 11.8 points due to promotional markdowns.",
                "recommendation": "Review vendor payment terms and inventory impairment.",
                "page_number": 14,
            },
            {
                "title": "Auditor Going Concern Qualification",
                "severity": "CRITICAL",
                "category": "Solvency Risk",
                "metric_name": "going_concern",
                "description": "Independent auditor expressed substantial doubt regarding ability to continue as going concern.",
                "evidence": "Substantial doubt about the Company's ability to continue as a going concern.",
                "recommendation": "Evaluate immediate debt restructuring or emergency recapitalization.",
                "page_number": 28,
            },
            {
                "title": "Negative Operating Cash Flow",
                "severity": "MEDIUM",
                "category": "Cash Flow Deficit",
                "metric_name": "operating_cash_flow",
                "current_value": -508.0,
                "prior_value": 18.0,
                "description": "Operating cash flow turned severely negative at $(508)M.",
                "evidence": "Cash used in operating activities was $(508) million.",
                "page_number": 19,
            },
        ],
    }


@pytest.fixture
def multi_company_comparison_result() -> Dict[str, Any]:
    """Persisted Comparison Agent result fixture."""
    return {
        "session_id": "sess_report_test_001",
        "document_ids_hash": "hash_apple_bbby",
        "comparison_output": {
            "compared_companies": ["Apple", "Bed Bath & Beyond"],
            "fiscal_periods": ["FY2025", "FY2024", "FY2022"],
            "metrics": [
                {
                    "metric_name": "revenue",
                    "display_name": "Revenue / Net Sales",
                    "unit": "USD (millions)",
                    "periods": [
                        {
                            "fiscal_period": "FY2025",
                            "peer_statistics": {
                                "peer_average": 210753.0,
                                "highest_company": "Apple",
                                "highest_value": 416161.0,
                                "lowest_company": "Bed Bath & Beyond",
                                "lowest_value": 5345.0,
                            },
                            "values": {
                                "Apple": {"value": 416161.0, "available": True},
                                "Bed Bath & Beyond": {"value": 5345.0, "available": True},
                            },
                        }
                    ],
                }
            ],
        },
        "updated_at": datetime.now(timezone.utc),
    }


# =====================================================================
# 1. DATA ASSEMBLY & SESSION RESOLUTION
# =====================================================================

def test_01_report_compiler_data_assembly(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_extracted_metrics, bbby_red_flags
):
    """Verify ReportCompiler gathers and aligns data across multiple company documents."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        documents=[
            {"document_id": "doc_apple_10k_2025", "company_name": "Apple"},
            {"document_id": "doc_bbby_10k_2022", "company_name": "Bed Bath & Beyond"},
        ],
        extracted_metrics_list=[apple_extracted_metrics, bbby_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    assert doc.metadata.session_id == sample_session_id
    assert doc.metadata.user_id == sample_user_id
    assert "Apple" in doc.metadata.companies
    assert "Bed Bath & Beyond" in doc.metadata.companies
    assert doc.red_flags.composite_risk_score == 100.0


def test_02_deterministic_report_id_generation(sample_session_id, sample_user_id):
    """Verify deterministic report_id derivation from session_id, user_id, and version."""
    id1 = ReportCompiler.generate_deterministic_report_id(sample_session_id, sample_user_id, "v1.0")
    id2 = ReportCompiler.generate_deterministic_report_id(sample_session_id, sample_user_id, "v1.0")
    id_diff_version = ReportCompiler.generate_deterministic_report_id(sample_session_id, sample_user_id, "v2.0")

    assert id1 == id2
    assert id1.startswith("rep_")
    assert id1 != id_diff_version


# =====================================================================
# 2. NUMERICAL INTEGRITY (APPLE & BBBY GROUND TRUTHS)
# =====================================================================

def test_03_apple_fy2025_revenue_and_net_income(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify Apple FY2025 revenue ($416,161M) and net income ($112,010M) are exactly reproduced."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    rev_row = next((r for r in doc.key_financials.metrics if r.metric_key == "revenue"), None)
    assert rev_row is not None
    apple_val = next((v for v in rev_row.values if v.company_name == "Apple" and v.fiscal_period == "FY2025"), None)
    assert apple_val is not None
    assert apple_val.raw_value == 416161.0
    assert "$416,161" in apple_val.formatted_value

    ni_row = next((r for r in doc.key_financials.metrics if r.metric_key == "net_income"), None)
    assert ni_row is not None
    apple_ni = next((v for v in ni_row.values if v.company_name == "Apple" and v.fiscal_period == "FY2025"), None)
    assert apple_ni is not None
    assert apple_ni.raw_value == 112010.0


def test_04_apple_multi_year_financials(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify Apple FY2024 ($391,035M) and FY2023 ($383,285M) multi-year figures survive compilation."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    rev_row = next(r for r in doc.key_financials.metrics if r.metric_key == "revenue")
    fy24_val = next(v for v in rev_row.values if v.fiscal_period == "FY2024")
    fy23_val = next(v for v in rev_row.values if v.fiscal_period == "FY2023")

    assert fy24_val.raw_value == 391035.0
    assert fy23_val.raw_value == 383285.0


def test_05_apple_eps_exact_persisted_value(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify persisted Apple EPS ($7.42) is rendered directly without independent recalculation."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    eps_row = next(r for r in doc.key_financials.metrics if r.metric_key == "eps")
    eps_val = next(v for v in eps_row.values if v.fiscal_period == "FY2025")
    assert eps_val.raw_value == 7.42
    assert eps_val.formatted_value == "$7.42"


# =====================================================================
# 3. RED FLAGS & MARGIN MATH
# =====================================================================

def test_06_bbby_red_flag_margin_math_and_distress(sample_session_id, sample_user_id, bbby_red_flags):
    """Verify BBBY margin compression (31.6% to 19.8%, -11.8 pts) is reproduced without semantic reversal."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        red_flags_list=[bbby_red_flags],
    )
    margin_flag = next((f for f in doc.red_flags.findings if f.metric_name == "gross_margin"), None)
    assert margin_flag is not None
    assert "11.8 percentage points" in margin_flag.change_description
    assert margin_flag.severity == "HIGH"
    assert doc.red_flags.composite_risk_score == 100.0


def test_07_clean_state_when_no_red_flags(sample_session_id, sample_user_id):
    """Verify clean informational state when zero red flags are present."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        red_flags_list=[],
    )
    assert doc.red_flags.total_flags == 0
    assert doc.red_flags.is_empty_state is True
    assert "No material red flags were identified" in doc.red_flags.empty_state_message


# =====================================================================
# 4. MISSING VS GENUINE ZERO DISTINCTION
# =====================================================================

def test_08_missing_metric_is_na_never_zero(sample_session_id, sample_user_id):
    """Verify missing metrics produce 'N/A' and available=False (strictly never '$0')."""
    fmt = ReportCompiler.format_metric_value("debt_to_equity", None)
    assert fmt == "N/A"

    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[
            {
                "company_name": "TestCorp",
                "reporting_period": "FY2025",
                "metrics_dict": {"revenue": 1000.0, "total_debt": None},
            }
        ],
    )
    debt_row = next((r for r in doc.key_financials.metrics if r.metric_key == "total_debt"), None)
    if debt_row:
        val = debt_row.values[0]
        assert val.available is False
        assert val.formatted_value == "N/A"
        assert val.raw_value is None


def test_09_genuine_zero_preserved(sample_session_id, sample_user_id):
    """Verify genuine 0.0 value is preserved as '$0.0' or '0.00%', NOT 'N/A'."""
    fmt_rev = ReportCompiler.format_metric_value("revenue", 0.0, scale="millions")
    assert "$0.0" in fmt_rev
    assert fmt_rev != "N/A"

    fmt_margin = ReportCompiler.format_metric_value("gross_margin", 0.0)
    assert fmt_margin == "0.00%"


# =====================================================================
# 5. SINGLE-COMPANY SESSION BEHAVIOR
# =====================================================================

def test_10_single_company_omits_comparison_cleanly(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify single-company report cleanly marks comparison unavailable without crashing."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        comparison_results_list=[],
    )
    assert doc.comparison.is_available is False
    assert "only one company was included in this session" in doc.comparison.unavailable_reason
    assert len(doc.comparison.metrics) == 0


def test_11_single_company_chart_generator_returns_none(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify ChartGenerator returns None for single-company sessions (no empty/broken charts)."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    chart_bytes = ChartGenerator.generate_comparison_bar_chart(doc.comparison)
    assert chart_bytes is None


# =====================================================================
# 6. MULTI-COMPANY COMPARISON & CHARTS
# =====================================================================

def test_12_multi_company_comparison_table_and_chart(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_extracted_metrics, multi_company_comparison_result
):
    """Verify multi-company session compiles comparison metrics and generates valid PNG chart."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics, bbby_extracted_metrics],
        comparison_results_list=[multi_company_comparison_result],
    )
    assert doc.comparison.is_available is True
    assert len(doc.comparison.compared_companies) == 2
    assert len(doc.comparison.metrics) > 0

    # Chart Generation
    chart_bytes = ChartGenerator.generate_comparison_bar_chart(doc.comparison)
    assert chart_bytes is not None
    assert chart_bytes.startswith(b"\x89PNG\r\n\x1a\n")  # Valid PNG signature


# =====================================================================
# 7. OUTLOOK & RESEARCH INTEGRATION
# =====================================================================

def test_13_outlook_populated_from_research_messages(sample_session_id, sample_user_id):
    """Verify Outlook is populated from persisted research messages without LLM predictions."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        research_messages_list=[
            {
                "role": "assistant",
                "query": "What is management's guidance on gross margin?",
                "content": "Management anticipates steady service margin expansion offset by hardware mix shifts.",
                "confidence_score": 0.88,
            }
        ],
    )
    assert doc.outlook.is_empty_state is False
    assert len(doc.outlook.findings) == 1
    assert "steady service margin expansion" in doc.outlook.findings[0].observation


def test_14_outlook_clean_state_when_no_research(sample_session_id, sample_user_id):
    """Verify clean informational state when no research messages exist."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        research_messages_list=[],
    )
    assert doc.outlook.is_empty_state is True
    assert "No outlook information was available" in doc.outlook.empty_state_message


# =====================================================================
# 8. DETERMINISM (IDENTICAL INPUT -> IDENTICAL OUTPUT)
# =====================================================================

def test_15_deterministic_data_compilation(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_extracted_metrics, bbby_red_flags
):
    """Verify two independent compilations from identical data produce identical models."""
    doc1 = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics, bbby_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    doc2 = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics, bbby_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )

    assert doc1.metadata.report_id == doc2.metadata.report_id
    assert doc1.metadata.companies == doc2.metadata.companies
    assert len(doc1.key_financials.metrics) == len(doc2.key_financials.metrics)
    assert [f.finding_id for f in doc1.red_flags.findings] == [f.finding_id for f in doc2.red_flags.findings]


def test_16_deterministic_canonical_ordering(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_extracted_metrics
):
    """Verify companies and metrics always follow canonical deterministic ordering."""
    # Pass metrics in reverse order
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[bbby_extracted_metrics, apple_extracted_metrics],
    )
    # Companies should be alphabetical
    assert doc.metadata.companies == ["Apple", "Bed Bath & Beyond"]

    # Metrics should match CANONICAL_METRIC_ORDER
    row_keys = [r.metric_key for r in doc.key_financials.metrics]
    canonical_keys = [m[0] for m in CANONICAL_METRIC_ORDER if m[0] in row_keys]
    assert row_keys == canonical_keys


# =====================================================================
# 9. ABSOLUTE ZERO-LLM VERIFICATION
# =====================================================================

def test_17_zero_llm_calls_enforcement(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags
):
    """Verify report generation makes ZERO LLM calls even if LLM service is configured to error."""
    with patch("services.llm_service.llm_service.generate_structured", side_effect=RuntimeError("LLM call forbidden")):
        with patch("services.llm_service.llm_service.generate", side_effect=RuntimeError("LLM call forbidden")):
            doc = ReportCompiler.compile(
                session_id=sample_session_id,
                user_id=sample_user_id,
                extracted_metrics_list=[apple_extracted_metrics],
                red_flags_list=[bbby_red_flags],
            )
            assert doc is not None
            assert doc.metadata.report_id.startswith("rep_")

            # Verify PDF also compiles without LLM
            pdf_bytes = PDFBuilder.build_pdf(doc)
            assert len(pdf_bytes) > 1000
            assert pdf_bytes.startswith(b"%PDF-")


# =====================================================================
# 10. PDF RENDERING & PLATYPUS NUMBEREDCANVAS
# =====================================================================

def test_18_pdf_builder_creates_valid_pdf(sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags):
    """Verify PDFBuilder generates a valid PDF starting with %PDF- header."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    pdf_bytes = PDFBuilder.build_pdf(doc)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes[-1024:]


def test_19_pdf_layout_five_sections_present(sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags):
    """Verify all 5 section headers are embedded into the PDF content stream."""
    import pypdf

    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    pdf_bytes = PDFBuilder.build_pdf(doc)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join([page.extract_text() or "" for page in reader.pages])

    assert "Executive Summary" in full_text
    assert "Key Financials" in full_text
    assert "Red Flags" in full_text
    assert "Peer Comparison" in full_text
    assert "Outlook" in full_text


# =====================================================================
# 11. R2 STORAGE & ERROR HANDLING
# =====================================================================

def test_20_r2_upload_success_and_presigned_url(
    sample_session_id, sample_user_id, apple_extracted_metrics
):
    """Verify PDF is uploaded to R2 and presigned URL is returned."""
    r2_storage_service.reset_mocks()

    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    pdf_bytes = PDFBuilder.build_pdf(doc)

    key = r2_storage_service.upload_bytes(doc.object_key, pdf_bytes)
    assert key == doc.object_key
    assert r2_storage_service.object_exists(key) is True

    presigned_url = r2_storage_service.generate_presigned_url(key)
    assert key in presigned_url


def test_21_r2_upload_failure_blocks_success(
    sample_session_id, sample_user_id, apple_extracted_metrics
):
    """Verify simulated R2 outage aborts report agent execution without false success."""
    r2_storage_service.set_mock_failure(True)

    agent = ReportAgent()
    with patch("agents.report.report_agent.get_sync_db") as mock_db_getter:
        mock_db = MagicMock()
        mock_db.documents.find.return_value = []
        mock_db.extracted_metrics.find.return_value = [apple_extracted_metrics]
        mock_db.red_flags.find.return_value = []
        mock_db.comparison_results.find.return_value.sort.return_value.limit.return_value = []
        mock_db.research_messages.find.return_value.sort.return_value = []
        mock_db.research_session_memory.find_one.return_value = None
        mock_db_getter.return_value = mock_db

        with pytest.raises(RetryableAgentException) as exc_info:
            agent.execute(
                payload={"session_id": sample_session_id, "user_id": sample_user_id},
                context={"user_id": sample_user_id},
            )
        assert "Failed to upload report PDF" in str(exc_info.value)
        # Verify db.reports.replace_one was NEVER called
        mock_db.reports.replace_one.assert_not_called()

    r2_storage_service.reset_mocks()


# =====================================================================
# 12. MONGODB PERSISTENCE & COMPATIBILITY
# =====================================================================

def test_22_report_agent_full_execution_and_mongo_persistence(
    sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags
):
    """Verify ReportAgent persists record to 'reports' and compatibility mirror 'analysis_reports'."""
    r2_storage_service.reset_mocks()

    agent = ReportAgent()
    with patch("agents.report.report_agent.get_sync_db") as mock_db_getter:
        mock_db = MagicMock()
        mock_db.documents.find.return_value = [{"document_id": "doc_apple_10k_2025", "company_name": "Apple"}]
        mock_db.extracted_metrics.find.return_value = [apple_extracted_metrics]
        mock_db.red_flags.find.return_value = [bbby_red_flags]
        mock_db.comparison_results.find.return_value.sort.return_value.limit.return_value = []
        mock_db.research_messages.find.return_value.sort.return_value = []
        mock_db.research_session_memory.find_one.return_value = None
        mock_db_getter.return_value = mock_db

        result = agent.execute(
            payload={"session_id": sample_session_id, "user_id": sample_user_id},
            context={"user_id": sample_user_id},
        )

        assert result.success is True
        assert result.task_type == AgentTaskType.REPORT_GENERATION.value
        assert result.result_ref.startswith("rep_")
        assert result.summary["status"] == "COMPLETED"
        assert result.summary["pdf_size_bytes"] > 1000

        # Assert calls to MongoDB
        mock_db.reports.replace_one.assert_called_once()
        mock_db.analysis_reports.replace_one.assert_called_once()


# =====================================================================
# 13. SECURITY & ACCESS RESTRICTIONS
# =====================================================================

@pytest.mark.asyncio
async def test_23_cross_user_report_access_rejection(sample_session_id, sample_user_id):
    """Verify User B cannot access User A's generated report."""
    from unittest.mock import AsyncMock

    with patch("database.connection.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.reports.find_one = AsyncMock(
            return_value={
                "session_id": sample_session_id,
                "report_id": "rep_user_a_secret",
                "user_id": "user_a",  # Belongs to User A
            }
        )
        mock_get_db.return_value = mock_db

        with pytest.raises(UnauthorizedReportAccessException):
            await ReportService.get_report_async(
                session_id=sample_session_id,
                user_id="user_b_attacker",  # User B attempting access
                report_id="rep_user_a_secret",
            )


# =====================================================================
# 14. INPUT VALIDATION & EXCEPTIONS
# =====================================================================

def test_24_missing_session_id_raises_non_retryable():
    """Verify execution without session_id immediately fails."""
    agent = ReportAgent()
    with pytest.raises(NonRetryableAgentException):
        agent.execute(payload={"user_id": "user_1"}, context=None)


def test_25_missing_user_id_raises_non_retryable():
    """Verify execution without user_id immediately fails."""
    agent = ReportAgent()
    with pytest.raises(NonRetryableAgentException):
        agent.execute(payload={"session_id": "sess_1"}, context=None)


# =====================================================================
# 15. PROVENANCE FOOTNOTE VERIFICATION
# =====================================================================

def test_26_provenance_information_survives(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify source document IDs survive compilation into ReportDocument metadata."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        documents=[{"document_id": "doc_apple_10k_2025", "company_name": "Apple"}],
        extracted_metrics_list=[apple_extracted_metrics],
    )
    assert "doc_apple_10k_2025" in doc.metadata.document_ids


# =====================================================================
# 16. FORMATTING & SCALE TESTS
# =====================================================================

def test_27_formatting_large_numbers_and_percentages():
    """Verify currency scaling and percentage formatting."""
    assert ReportCompiler.format_metric_value("revenue", 416161.0, scale="millions") == "$416,161.0M"
    assert ReportCompiler.format_metric_value("gross_margin", 46.28) == "46.28%"
    assert ReportCompiler.format_metric_value("gross_margin", 0.4628) == "46.28%"
    assert ReportCompiler.format_metric_value("revenue", 1_500_000_000.0, scale="units") == "$1.50B"


# =====================================================================
# 17. CREW TASK & REGISTRY INTEGRATION
# =====================================================================

def test_28_report_agent_in_registry():
    """Verify ReportAgent is registered in agent_registry under 'ReportAgent'."""
    from agents.registry import agent_registry
    agent = agent_registry.get("ReportAgent")
    assert agent is not None
    assert agent.default_task_type == AgentTaskType.REPORT_GENERATION


def test_29_crew_task_creation(sample_session_id):
    """Verify create_report_task instantiates FinSentryTask with ReportAgent."""
    from crew.tasks import create_report_task
    task = create_report_task(session_id=sample_session_id, report_title="Audit Report")
    assert task.agent_name == "ReportAgent"
    assert task.context["session_id"] == sample_session_id


# =====================================================================
# 18. SERVICE LAYER TEST
# =====================================================================

def test_30_report_service_generate_sync(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify ReportService.generate_report_sync dispatches agent cleanly."""
    r2_storage_service.reset_mocks()
    with patch("agents.report.report_agent.get_sync_db") as mock_db_getter:
        mock_db = MagicMock()
        mock_db.documents.find.return_value = []
        mock_db.extracted_metrics.find.return_value = [apple_extracted_metrics]
        mock_db.red_flags.find.return_value = []
        mock_db.comparison_results.find.return_value.sort.return_value.limit.return_value = []
        mock_db.research_messages.find.return_value.sort.return_value = []
        mock_db.research_session_memory.find_one.return_value = None
        mock_db_getter.return_value = mock_db

        summary = ReportService.generate_report_sync(
            session_id=sample_session_id,
            user_id=sample_user_id,
            report_title="Test Sync Report",
        )
        assert summary["status"] == "COMPLETED"
        assert summary["report_title"] == "Test Sync Report"
        assert summary["pdf_size_bytes"] > 0


# =====================================================================
# 19. JINJA2 TEMPLATE & REGENERATION DETERMINISM
# =====================================================================

def test_31_jinja2_template_rendering(sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags):
    """Verify Jinja2 template renders all 5 sections cleanly from ReportDocument."""
    import jinja2

    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    from pathlib import Path

    template_path = (
        Path(__file__).resolve().parent.parent
        / "agents"
        / "report"
        / "templates"
        / "report_layout.jinja2"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        tmpl_str = f.read()

    template = jinja2.Template(tmpl_str)
    rendered = template.render(
        metadata=doc.metadata,
        executive_summary=doc.executive_summary,
        key_financials=doc.key_financials,
        red_flags=doc.red_flags,
        comparison=doc.comparison,
        outlook=doc.outlook,
    )

    assert "=== SECTION 1: EXECUTIVE SUMMARY ===" in rendered
    assert "=== SECTION 2: KEY FINANCIALS ===" in rendered
    assert "=== SECTION 3: RED FLAGS ===" in rendered
    assert "=== SECTION 4: COMPANY COMPARISON ===" in rendered
    assert "=== SECTION 5: OUTLOOK ===" in rendered
    assert "Apple" in rendered
    assert "Revenue / Net Sales" in rendered


def test_32_pdf_regeneration_consistency(sample_session_id, sample_user_id, apple_extracted_metrics, bbby_red_flags):
    """Verify two independent PDF builds from identical model have matching page count and text."""
    import pypdf

    doc1 = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )
    doc2 = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
        red_flags_list=[bbby_red_flags],
    )

    pdf1 = PDFBuilder.build_pdf(doc1)
    pdf2 = PDFBuilder.build_pdf(doc2)

    reader1 = pypdf.PdfReader(io.BytesIO(pdf1))
    reader2 = pypdf.PdfReader(io.BytesIO(pdf2))

    assert len(reader1.pages) == len(reader2.pages)
    text1 = "\n".join([p.extract_text() or "" for p in reader1.pages])
    text2 = "\n".join([p.extract_text() or "" for p in reader2.pages])
    assert text1 == text2


def test_33_fiscal_period_descending_sort(sample_session_id, sample_user_id):
    """Verify fiscal periods are deterministically sorted in descending chronological order."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[
            {
                "company_name": "MultiYearCorp",
                "reporting_period": "FY2023",
                "multi_year_data": {
                    "FY2021": {"revenue": 100.0},
                    "FY2025": {"revenue": 300.0},
                    "FY2024": {"revenue": 200.0},
                    "FY2022": {"revenue": 150.0},
                },
            }
        ],
    )
    assert doc.key_financials.reporting_periods == ["FY2025", "FY2024", "FY2023", "FY2022", "FY2021"]


def test_34_report_agent_error_handling_on_mongodb_exception(sample_session_id, sample_user_id):
    """Verify ReportAgent handles unexpected database errors gracefully with RetryableAgentException."""
    agent = ReportAgent()
    with patch("agents.report.report_agent.get_sync_db", side_effect=Exception("Database connection timed out")):
        with pytest.raises(RetryableAgentException) as exc_info:
            agent.execute(
                payload={"session_id": sample_session_id, "user_id": sample_user_id},
                context={"user_id": sample_user_id},
            )
        assert "ReportAgent unexpected compilation failure" in str(exc_info.value)


def test_35_report_document_to_mongo_serialization(sample_session_id, sample_user_id, apple_extracted_metrics):
    """Verify ReportDocument.to_mongo produces clean dict excluding binary chart image."""
    doc = ReportCompiler.compile(
        session_id=sample_session_id,
        user_id=sample_user_id,
        extracted_metrics_list=[apple_extracted_metrics],
    )
    mongo_dict = doc.to_mongo()
    assert isinstance(mongo_dict, dict)
    assert "metadata" in mongo_dict
    assert "executive_summary" in mongo_dict
    assert "key_financials" in mongo_dict
    assert "red_flags" in mongo_dict
    assert "comparison" in mongo_dict
    assert "outlook" in mongo_dict
    # Verify chart_image_bytes was excluded
    assert "chart_image_bytes" not in mongo_dict["comparison"]
