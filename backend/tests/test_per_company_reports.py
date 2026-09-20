"""
FinSentry AI — Per-company (single-document) report isolation tests.

Verifies:
  * An individual company report consumes ONLY that document's metrics + red flags
    (no cross-company financial or red-flag leakage).
  * Per-company UNLOCKED download is not encrypted; LOCKED download is AES-256 and
    opens with the revealable session password.
  * Ownership: a document not owned by the user yields ReportNotFoundException.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.report_service import ReportService
from core.exceptions import ReportNotFoundException
from utils.pdf_security import (
    is_pdf_encrypted,
    can_open_with_password,
    generate_pdf_password,
    encrypt_password_at_rest,
)

SESSION = "sess_pcr"
USER = "user_pcr"


def _apple_metrics():
    return {
        "session_id": SESSION, "user_id": USER, "document_id": "doc_apple",
        "company_name": "Apple", "reporting_period": "FY2025", "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {"revenue": 416161.0, "net_income": 112010.0, "eps": 7.46},
        "multi_year_data": {"FY2024": {"revenue": 391035.0, "eps": 6.08}},
        "updated_at": datetime.now(timezone.utc),
    }


def _bbby_metrics():
    return {
        "session_id": SESSION, "user_id": USER, "document_id": "doc_bbby",
        "company_name": "Bed Bath & Beyond", "reporting_period": "FY2022", "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {"revenue": 5344.4, "gross_profit": 1207.9, "net_income": -3506.7},
        "multi_year_data": {},
        "updated_at": datetime.now(timezone.utc),
    }


def _bbby_flags():
    return {
        "session_id": SESSION, "user_id": USER, "document_id": "doc_bbby",
        "company_name": "Bed Bath & Beyond", "risk_score": 75.0, "total_flags": 1,
        "high_severity_count": 1,
        "flags": [{
            "title": "Going Concern Doubt", "severity": "CRITICAL", "category": "Solvency Risk",
            "description": "Substantial doubt about ability to continue as a going concern.",
            "evidence": "Auditor going concern qualification.", "page_number": 28,
        }],
    }


def _mock_db(doc, em, rf, session_report=None):
    db = MagicMock()
    db.documents.find_one = AsyncMock(return_value=doc)
    c_em = MagicMock(); c_em.to_list = AsyncMock(return_value=em)
    db.extracted_metrics.find.return_value = c_em
    c_rf = MagicMock(); c_rf.to_list = AsyncMock(return_value=rf)
    db.red_flags.find.return_value = c_rf
    db.reports.find_one = AsyncMock(return_value=session_report)
    return db


# ---------------------------------------------------------------------------
# Content isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apple_report_contains_only_apple_data():
    doc = {"document_id": "doc_apple", "session_id": SESSION, "user_id": USER, "company_name": "Apple"}
    db = _mock_db(doc, [_apple_metrics()], [])  # no red flags for Apple
    with patch("database.connection.mongodb.get_db", return_value=db):
        data = await ReportService.get_company_report_content_async(SESSION, USER, "doc_apple")
    blob = json.dumps(data)
    assert data["company_name"] == "Apple"
    assert "Bed Bath" not in blob            # no BBBY company leakage
    assert "5,344.4" not in blob and "5344.4" not in blob  # no BBBY revenue
    assert "3,506.7" not in blob and "3506.7" not in blob  # no BBBY net income
    # Apple's own figures are present
    assert "416,161" in blob or "416161" in blob


@pytest.mark.asyncio
async def test_bbby_report_contains_only_bbby_data_and_its_red_flags():
    doc = {"document_id": "doc_bbby", "session_id": SESSION, "user_id": USER, "company_name": "Bed Bath & Beyond"}
    db = _mock_db(doc, [_bbby_metrics()], [_bbby_flags()])
    with patch("database.connection.mongodb.get_db", return_value=db):
        data = await ReportService.get_company_report_content_async(SESSION, USER, "doc_bbby")
    blob = json.dumps(data)
    assert "Bed Bath" in (data.get("company_name") or "")
    # No Apple financial leakage
    assert "416,161" not in blob and "416161" not in blob
    assert "7.46" not in blob
    # BBBY red flags present
    assert data["red_flags"]["composite_risk_score"] == 75.0
    assert any("Going Concern" in (f.get("title") or "") for f in data["red_flags"]["findings"])


# ---------------------------------------------------------------------------
# Per-company download semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_unlocked_download_is_not_encrypted():
    doc = {"document_id": "doc_apple", "session_id": SESSION, "user_id": USER, "company_name": "Apple"}
    db = _mock_db(doc, [_apple_metrics()], [])
    with patch("database.connection.mongodb.get_db", return_value=db):
        pdf = await ReportService.get_company_report_pdf_unlocked_async(SESSION, USER, "doc_apple")
    assert pdf[:5] == b"%PDF-"
    assert is_pdf_encrypted(pdf) is False


@pytest.mark.asyncio
async def test_company_locked_download_is_encrypted_with_session_password():
    password = generate_pdf_password()
    session_report = {"session_id": SESSION, "user_id": USER, "pdf_locked": True,
                      "pdf_password_enc": encrypt_password_at_rest(password)}
    doc = {"document_id": "doc_apple", "session_id": SESSION, "user_id": USER, "company_name": "Apple"}
    db = _mock_db(doc, [_apple_metrics()], [], session_report=session_report)
    with patch("database.connection.mongodb.get_db", return_value=db):
        pdf = await ReportService.get_company_report_pdf_locked_async(SESSION, USER, "doc_apple")
    assert is_pdf_encrypted(pdf) is True
    assert can_open_with_password(pdf, password) is True
    assert can_open_with_password(pdf, "FS-0000-0000-0000") is False


@pytest.mark.asyncio
async def test_company_locked_download_requires_session_report():
    doc = {"document_id": "doc_apple", "session_id": SESSION, "user_id": USER, "company_name": "Apple"}
    db = _mock_db(doc, [_apple_metrics()], [], session_report=None)  # no session password
    with patch("database.connection.mongodb.get_db", return_value=db):
        with pytest.raises(ReportNotFoundException):
            await ReportService.get_company_report_pdf_locked_async(SESSION, USER, "doc_apple")


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_report_ownership_enforced():
    # documents.find_one is queried with user_id; a non-owner gets None -> not found.
    db = _mock_db(None, [], [])
    with patch("database.connection.mongodb.get_db", return_value=db):
        with pytest.raises(ReportNotFoundException):
            await ReportService.get_company_report_content_async(SESSION, "user_OTHER", "doc_apple")
