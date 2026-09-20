"""
FinSentry AI — Red Flag Document Isolation Test Suite.

Tests for the exact manual failure: Apple and BBBY in the same session
must produce separate red_flags records with complete document isolation.

Test coverage:
  1. Apple and BBBY same session → separate red_flags records
  2. Apple retrieval returns ONLY Apple findings
  3. BBBY retrieval returns ONLY BBBY findings
  4. Apple cannot receive BBBY risk score
  5. BBBY cannot receive Apple risk score
  6. Finding document_id matches requested document_id
  7. Finding filename matches the requested document
  8. Company name matches the requested document
  9. Session-only lookup with multiple documents → per-document breakdown
  10. Stale/cache cross-contamination prevented
  11. Margin delta (11.4 pp) rejected as margin LEVEL
  12. Standard BBBY fixture: 31.6% → 19.8%, decrease = 11.8 pp
  13. Existing Red Flag tests remain passing (inherits from existing suite)
  14. Margin from/to extraction guard
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from agents.red_flag.red_flag_agent import RedFlagAgent, validate_metric_semantics
from database.connection import mongodb
from schemas.agent_results import RedFlagItem, RedFlagResult


# =====================================================================
# Fixture Helpers
# =====================================================================

APPLE_SESSION_ID = "test-session-isolation-001"
APPLE_DOC_ID = "doc-apple-10k-2025"
APPLE_COMPANY = "Apple Inc"
APPLE_FILENAME = "Apple_2025_Form_10K.pdf"

BBBY_DOC_ID = "doc-bbby-10k-2023"
BBBY_COMPANY = "Bed Bath & Beyond Inc"
BBBY_FILENAME = "BBBY_2023_Form_10K.pdf"


def _make_apple_result() -> RedFlagResult:
    """Create a mock Apple RedFlagResult."""
    return RedFlagResult(
        agent_name="RedFlagAgent",
        session_id=APPLE_SESSION_ID,
        user_id="user-001",
        document_id=APPLE_DOC_ID,
        company_name=APPLE_COMPANY,
        total_flags=1,
        high_severity_count=0,
        flags=[
            RedFlagItem(
                severity="MEDIUM",
                category="Profitability",
                title="Revenue Concentration Risk",
                description="iPhone revenue accounts for over 50% of total net sales.",
                source="QUALITATIVE",
                document_filename=APPLE_FILENAME,
                document_id=APPLE_DOC_ID,
            )
        ],
        risk_score=5.0,
        overall_assessment="Apple Inc: Minimal risk detected. 1 medium-priority finding.",
    )


def _make_bbby_result() -> RedFlagResult:
    """Create a mock BBBY RedFlagResult."""
    return RedFlagResult(
        agent_name="RedFlagAgent",
        session_id=APPLE_SESSION_ID,  # SAME session
        user_id="user-001",
        document_id=BBBY_DOC_ID,
        company_name=BBBY_COMPANY,
        total_flags=5,
        high_severity_count=3,
        flags=[
            RedFlagItem(
                severity="HIGH",
                category="Solvency",
                title="Going Concern Qualification",
                description="Auditor issued going concern opinion citing substantial doubt.",
                source="QUALITATIVE",
                document_filename=BBBY_FILENAME,
                document_id=BBBY_DOC_ID,
            ),
            RedFlagItem(
                severity="HIGH",
                category="Solvency",
                title="Negative Stockholders' Equity Deficit",
                description="Stockholders' equity is negative at -$1,100M.",
                source="QUANTITATIVE",
                metric_name="total_equity",
                document_filename=BBBY_FILENAME,
                document_id=BBBY_DOC_ID,
            ),
            RedFlagItem(
                severity="HIGH",
                category="Profitability",
                title="Severe Gross Margin Compression",
                description="Gross margin declined from 31.6% to 19.8%, a decrease of 11.8 percentage points.",
                source="QUANTITATIVE",
                metric_name="gross_margin",
                document_filename=BBBY_FILENAME,
                document_id=BBBY_DOC_ID,
            ),
            RedFlagItem(
                severity="MEDIUM",
                category="Solvency",
                title="Debt Covenant Breach",
                description="The company breached minimum liquidity covenants.",
                source="QUALITATIVE",
                document_filename=BBBY_FILENAME,
                document_id=BBBY_DOC_ID,
            ),
            RedFlagItem(
                severity="HIGH",
                category="Profitability",
                title="Severe Revenue Contraction",
                description="Revenue declined 32% year-over-year.",
                source="QUANTITATIVE",
                metric_name="revenue",
                document_filename=BBBY_FILENAME,
                document_id=BBBY_DOC_ID,
            ),
        ],
        risk_score=65.0,
        overall_assessment="Bed Bath & Beyond Inc: Critical distress detected. 3 high-severity findings.",
    )


# =====================================================================
# 1. Apple + BBBY same session → separate red_flags records
# =====================================================================

@pytest.mark.asyncio
async def test_separate_red_flag_records_per_document():
    """Apple and BBBY in the same session produce separate red_flags records."""
    await mongodb.connect()
    db = mongodb.get_db()

    # Clean up
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    # Persist both
    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()

    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    # Verify two separate records exist
    records = await db.red_flags.find({"session_id": APPLE_SESSION_ID}).to_list(length=100)
    assert len(records) == 2, f"Expected 2 separate red_flags records, got {len(records)}"

    doc_ids = {r.get("document_id") for r in records}
    assert APPLE_DOC_ID in doc_ids
    assert BBBY_DOC_ID in doc_ids

    # Clean up
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 2. Apple retrieval returns ONLY Apple findings
# =====================================================================

@pytest.mark.asyncio
async def test_apple_retrieval_returns_only_apple_findings():
    """Apple retrieval returns ONLY Apple findings, zero BBBY."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    # Retrieve Apple-specific
    apple_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID})
    assert apple_rec is not None
    assert apple_rec["company_name"] == APPLE_COMPANY
    assert apple_rec["document_id"] == APPLE_DOC_ID

    for flag in apple_rec["flags"]:
        assert flag.get("document_filename") != BBBY_FILENAME, "Apple record must not contain BBBY filenames"
        assert flag.get("document_id") != BBBY_DOC_ID, "Apple record must not contain BBBY document_id"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 3. BBBY retrieval returns ONLY BBBY findings
# =====================================================================

@pytest.mark.asyncio
async def test_bbby_retrieval_returns_only_bbby_findings():
    """BBBY retrieval returns ONLY BBBY findings, zero Apple."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    bbby_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": BBBY_DOC_ID})
    assert bbby_rec is not None
    assert bbby_rec["company_name"] == BBBY_COMPANY
    assert bbby_rec["document_id"] == BBBY_DOC_ID

    for flag in bbby_rec["flags"]:
        assert flag.get("document_filename") != APPLE_FILENAME, "BBBY record must not contain Apple filenames"
        assert flag.get("document_id") != APPLE_DOC_ID, "BBBY record must not contain Apple document_id"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 4. Apple cannot receive BBBY risk score
# =====================================================================

@pytest.mark.asyncio
async def test_apple_cannot_receive_bbby_risk_score():
    """Apple-specific risk score must differ from BBBY's."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    apple_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID})
    assert apple_rec["risk_score"] == 5.0, f"Apple risk score should be 5.0, got {apple_rec['risk_score']}"
    assert apple_rec["risk_score"] != 65.0, "Apple must NOT receive BBBY's 65.0 risk score"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 5. BBBY cannot receive Apple risk score
# =====================================================================

@pytest.mark.asyncio
async def test_bbby_cannot_receive_apple_risk_score():
    """BBBY-specific risk score must be its own, not Apple's."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    bbby_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": BBBY_DOC_ID})
    assert bbby_rec["risk_score"] == 65.0, f"BBBY risk score should be 65.0, got {bbby_rec['risk_score']}"
    assert bbby_rec["risk_score"] != 5.0, "BBBY must NOT receive Apple's 5.0 risk score"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 6. Finding document_id matches requested document_id
# =====================================================================

@pytest.mark.asyncio
async def test_finding_document_id_matches_requested():
    """Every flag in a document-specific record has the correct document_id."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    bbby_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": BBBY_DOC_ID})
    for flag in bbby_rec["flags"]:
        assert flag.get("document_id") == BBBY_DOC_ID, \
            f"Flag '{flag.get('title')}' has document_id={flag.get('document_id')}, expected {BBBY_DOC_ID}"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 7. Finding filename matches the requested document
# =====================================================================

@pytest.mark.asyncio
async def test_finding_filename_matches_requested_document():
    """Every flag in a document-specific record has the correct filename."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)

    apple_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID})
    for flag in apple_rec["flags"]:
        if flag.get("document_filename"):
            assert flag["document_filename"] == APPLE_FILENAME

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 8. Company name matches the requested document
# =====================================================================

@pytest.mark.asyncio
async def test_company_name_matches_requested_document():
    """Company name in the record matches the target document."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    apple_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID})
    assert apple_rec["company_name"] == APPLE_COMPANY

    bbby_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": BBBY_DOC_ID})
    assert bbby_rec["company_name"] == BBBY_COMPANY

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 9. Session-only lookup with multiple documents → structured response
# =====================================================================

@pytest.mark.asyncio
async def test_session_lookup_multiple_docs_returns_breakdown():
    """Session-only lookup with multiple documents does not silently select wrong company."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    from services.live_analysis_service import LiveAnalysisService
    service = LiveAnalysisService(db=db)

    # Session-only lookup (no document_id)
    result = await service.get_session_red_flags(
        user_id="user-001",
        session_id=APPLE_SESSION_ID,
    )

    assert result["status"] in ["COMPLETED_WITH_FLAGS", "COMPLETED_NO_FLAGS"]
    # Should have a 'documents' breakdown
    assert "documents" in result, "Multi-document session must return 'documents' breakdown"
    assert len(result["documents"]) == 2

    doc_ids_in_breakdown = {d["document_id"] for d in result["documents"]}
    assert APPLE_DOC_ID in doc_ids_in_breakdown
    assert BBBY_DOC_ID in doc_ids_in_breakdown

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 10. Stale/cache cross-contamination prevention
# =====================================================================

@pytest.mark.asyncio
async def test_document_specific_lookup_prevents_cross_contamination():
    """Document-specific lookup never returns the other document's data."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    apple_result = _make_apple_result()
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    from services.live_analysis_service import LiveAnalysisService
    service = LiveAnalysisService(db=db)

    # Request Apple specifically
    apple_resp = await service.get_session_red_flags(
        user_id="user-001",
        session_id=APPLE_SESSION_ID,
        document_id=APPLE_DOC_ID,
    )
    assert apple_resp["risk_score"] == 5.0
    assert apple_resp.get("company_name") == APPLE_COMPANY
    for flag in apple_resp["flags"]:
        assert flag.get("document_id") != BBBY_DOC_ID, "Apple response must not contain BBBY flags"

    # Request BBBY specifically
    bbby_resp = await service.get_session_red_flags(
        user_id="user-001",
        session_id=APPLE_SESSION_ID,
        document_id=BBBY_DOC_ID,
    )
    assert bbby_resp["risk_score"] == 65.0
    assert bbby_resp.get("company_name") == BBBY_COMPANY
    for flag in bbby_resp["flags"]:
        assert flag.get("document_id") != APPLE_DOC_ID, "BBBY response must not contain Apple flags"

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 11. Margin delta rejection as margin LEVEL
# =====================================================================

def test_margin_delta_11_4pp_rejected_as_level():
    """
    Margin delta value of 11.4 from 'dropped by 11.4 percentage points from 34.0% to 22.6%'
    must be rejected when it's being considered as a gross_margin level.
    """
    result = validate_metric_semantics("gross_margin", {
        "value": 11.4,
        "evidence_snippet": "Gross margin dropped by 11.4 percentage points from 34.0% to 22.6%",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    })
    assert result is False, "11.4 percentage-point delta must be rejected as a margin level"


def test_margin_delta_from_to_range_rejected():
    """
    Value that matches the computed delta of a from/to range must be rejected.
    Evidence: 'from 34.0% to 22.6%' → delta = 11.4
    If value = 11.4, it's the delta, not a level.
    """
    result = validate_metric_semantics("gross_margin", {
        "value": 11.4,
        "evidence_snippet": "Gross margin declined from 34.0% to 22.6% during the fiscal year",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    })
    assert result is False, "Value matching from/to delta must be rejected"


def test_valid_margin_level_accepted():
    """A genuine margin level of 22.6% with from/to evidence must be accepted."""
    result = validate_metric_semantics("gross_margin", {
        "value": 22.6,
        "evidence_snippet": "Gross margin declined from 34.0% to 22.6% during the fiscal year",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    })
    assert result is True, "Genuine margin level 22.6% must be accepted"


def test_valid_prior_margin_level_accepted():
    """A genuine prior margin level of 34.0% with from/to evidence must be accepted."""
    result = validate_metric_semantics("prior_gross_margin", {
        "value": 34.0,
        "evidence_snippet": "Gross margin declined from 34.0% to 22.6% during the fiscal year",
        "display_name": "Prior Gross Margin",
        "metric_name": "prior_gross_margin",
    })
    assert result is True, "Genuine prior margin level 34.0% must be accepted"


# =====================================================================
# 12. Standard BBBY fixture: 31.6% → 19.8%, decrease = 11.8 pp
# =====================================================================

def test_bbby_standard_fixture_margin_levels():
    """
    Standard BBBY fixture verifies:
      31.6% → 19.8%
      decrease = 11.8 percentage points
    """
    agent = RedFlagAgent()

    # BBBY margins: prior 31.6%, current 19.8%
    metrics = {
        "gross_margin": 0.198,           # 19.8%
        "prior_gross_margin": 0.316,     # 31.6%
    }

    flags = agent.scan_quantitative_metrics(metrics)
    assert len(flags) == 1
    flag = flags[0]

    assert flag.severity == "HIGH"
    assert "Severe Gross Margin Compression" in flag.title

    # Verify correct margin levels in description
    assert "31.6%" in flag.description
    assert "19.8%" in flag.description
    assert "11.8 percentage points" in flag.description

    # Must NOT say margin dropped to 11.8%
    assert "to 11.8%" not in flag.description


def test_bbby_margin_delta_value_rejected_as_level():
    """The 11.8pp delta value must be rejected when offered as a gross_margin candidate."""
    result = validate_metric_semantics("gross_margin", {
        "value": 11.8,
        "evidence_snippet": "Gross profit margin decreased by 11.8 percentage points from 31.6% to 19.8%",
        "display_name": "Gross Margin",
        "metric_name": "gross_margin",
    })
    assert result is False, "11.8pp delta must be rejected as a margin level"


# =====================================================================
# 13. MongoDB upsert does NOT overwrite across documents
# =====================================================================

@pytest.mark.asyncio
async def test_upsert_does_not_overwrite_different_document():
    """
    Persisting BBBY after Apple must NOT overwrite Apple's record.
    Each document gets its own record.
    """
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    # Persist Apple first
    apple_result = _make_apple_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)

    # Then persist BBBY
    bbby_result = _make_bbby_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, bbby_result, user_id="user-001", document_id=BBBY_DOC_ID)

    # Both must still exist
    apple_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID})
    bbby_rec = await db.red_flags.find_one({"session_id": APPLE_SESSION_ID, "document_id": BBBY_DOC_ID})

    assert apple_rec is not None, "Apple record must not be overwritten by BBBY"
    assert bbby_rec is not None, "BBBY record must exist"

    assert apple_rec["company_name"] == APPLE_COMPANY
    assert bbby_rec["company_name"] == BBBY_COMPANY
    assert apple_rec["risk_score"] == 5.0
    assert bbby_rec["risk_score"] == 65.0

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})


# =====================================================================
# 14. Re-upsert same document updates correctly
# =====================================================================

@pytest.mark.asyncio
async def test_re_upsert_same_document_updates_in_place():
    """Re-running analysis on the same document updates its record, not creating a duplicate."""
    await mongodb.connect()
    db = mongodb.get_db()
    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})

    # First run
    apple_result = _make_apple_result()
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)

    # Second run with updated score
    apple_result.risk_score = 10.0
    apple_result.total_flags = 2
    RedFlagAgent._persist_to_db(APPLE_SESSION_ID, apple_result, user_id="user-001", document_id=APPLE_DOC_ID)

    records = await db.red_flags.find({"session_id": APPLE_SESSION_ID, "document_id": APPLE_DOC_ID}).to_list(length=100)
    assert len(records) == 1, "Re-upsert must update, not duplicate"
    assert records[0]["risk_score"] == 10.0
    assert records[0]["total_flags"] == 2

    await db.red_flags.delete_many({"session_id": APPLE_SESSION_ID})
