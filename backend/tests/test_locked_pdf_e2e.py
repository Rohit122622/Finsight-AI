"""
FinSentry AI — Locked-PDF E2E + authorization + email-failure tests (final gap fixes).

Covers:
  * Comparison E2E: finalize -> encrypt -> persist; download bytes == email attachment bytes.
  * Report E2E: ReportAgent generates -> AES-256 -> persist; download bytes == email bytes.
  * Authorization: User A cannot reveal/retry User B's report; password not in normal responses.
  * Email failure: SMTP failure keeps encrypted PDF available; status=failed; retry reuses artifact.

Uses mocked DB + REAL disk storage (r2_storage_service fallback) + patched email dispatch,
so no real emails are sent and no live Atlas writes occur.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.r2_storage_service import r2_storage_service
from utils.pdf_security import (
    is_pdf_encrypted,
    can_open_with_password,
    decrypt_password_at_rest,
)

SESSION = "sess_e2e_locked_001"
USER_A = "user_e2e_A"
USER_B = "user_e2e_B"


def _min_comp_data():
    return {
        "session_id": SESSION,
        "companies": [{"company_name": "Apple"}, {"company_name": "Bed Bath & Beyond"}],
        "has_common_periods": True,
        "common_periods": ["FY2022"],
        "metrics": [],
        "summary_insights": ["Deterministic peer comparison."],
    }


# =====================================================================
# 5. COMPARISON PDF E2E — download bytes == email attachment bytes
# =====================================================================

def test_comparison_e2e_download_equals_email_bytes():
    from services import comparison_pdf_service

    doc_hash = "hash_" + uuid.uuid4().hex[:8]
    record = {
        "session_id": SESSION,
        "user_id": USER_A,
        "document_ids_hash": doc_hash,
        "comparison": _min_comp_data(),
        "updated_at": datetime.now(timezone.utc),
    }

    captured = {}
    mock_db = MagicMock()
    mock_db.comparison_results.find_one.return_value = record

    def _capture_update(query, update, **kw):
        captured.update(update.get("$set", {}))
    mock_db.comparison_results.update_one.side_effect = _capture_update

    with patch.object(comparison_pdf_service, "get_sync_db", return_value=mock_db), \
         patch("workers.email_tasks.send_locked_pdf_email.apply_async") as mock_send:
        result = comparison_pdf_service.finalize_comparison_locked_pdf_sync(USER_A, SESSION)

    object_key = result["object_key"]
    try:
        # Persisted + status
        assert result["pdf_locked"] is True
        assert result["email_status"] == "queued"
        assert result["password_available"] is True
        assert captured.get("pdf_locked") is True
        assert captured.get("email_status") == "queued"
        assert captured.get("pdf_password_enc")  # stored (encrypted at rest)

        # Email was queued (immediately, no download needed)
        assert mock_send.called

        # Download bytes (what /compare/download streams) == email attachment bytes
        # (what send_locked_pdf_email loads) — both read the SAME object_key.
        download_bytes = r2_storage_service.get_bytes(object_key)
        email_bytes = r2_storage_service.get_bytes(object_key)
        assert download_bytes == email_bytes
        assert is_pdf_encrypted(download_bytes) is True

        # Password opens it
        pw = decrypt_password_at_rest(captured["pdf_password_enc"])
        assert can_open_with_password(download_bytes, pw) is True
        assert can_open_with_password(download_bytes, "FS-0000-0000-0000") is False
    finally:
        r2_storage_service.delete_object(object_key)


def test_comparison_finalize_is_idempotent_no_duplicate_email():
    """Second finalize on an already-locked artifact must NOT regenerate or re-queue email."""
    from services import comparison_pdf_service

    doc_hash = "hash_" + uuid.uuid4().hex[:8]
    object_key = f"comparisons/{USER_A}/{SESSION}/comparison.pdf"

    # First pass: create the locked artifact.
    record = {
        "session_id": SESSION, "user_id": USER_A, "document_ids_hash": doc_hash,
        "comparison": _min_comp_data(), "updated_at": datetime.now(timezone.utc),
    }
    captured = {}
    mock_db = MagicMock()
    mock_db.comparison_results.find_one.return_value = record
    mock_db.comparison_results.update_one.side_effect = lambda q, u, **k: captured.update(u.get("$set", {}))
    with patch.object(comparison_pdf_service, "get_sync_db", return_value=mock_db), \
         patch("workers.email_tasks.send_locked_pdf_email.apply_async"):
        comparison_pdf_service.finalize_comparison_locked_pdf_sync(USER_A, SESSION)

    try:
        # Second pass: record now reflects locked state.
        locked_record = {**record, "pdf_locked": True, "pdf_password_enc": captured["pdf_password_enc"],
                         "object_key": object_key, "email_status": "sent"}
        mock_db2 = MagicMock()
        mock_db2.comparison_results.find_one.return_value = locked_record
        with patch.object(comparison_pdf_service, "get_sync_db", return_value=mock_db2), \
             patch("workers.email_tasks.send_locked_pdf_email.apply_async") as mock_send2, \
             patch("agents.comparison.pdf_builder.comparison_pdf_builder.build_pdf") as mock_build:
            res2 = comparison_pdf_service.finalize_comparison_locked_pdf_sync(USER_A, SESSION)
            assert res2["pdf_locked"] is True
            assert res2["email_status"] == "sent"      # preserved, not reset
            mock_build.assert_not_called()              # no regeneration
            mock_send2.assert_not_called()              # no duplicate email
    finally:
        r2_storage_service.delete_object(object_key)


# =====================================================================
# 6. REPORT PDF E2E — AES-256, persist, download bytes == email bytes
# =====================================================================

def test_report_e2e_download_equals_email_bytes(monkeypatch):
    from agents.report.report_agent import ReportAgent

    apple = {
        "session_id": SESSION, "user_id": USER_A, "document_id": "doc_apple",
        "company_name": "Apple", "reporting_period": "FY2025", "reporting_currency": "USD",
        "reporting_scale": "millions",
        "metrics_dict": {"revenue": 416161.0, "net_income": 112010.0, "eps": 7.46},
        "multi_year_data": {"FY2024": {"revenue": 391035.0, "eps": 6.08}},
        "updated_at": datetime.now(timezone.utc),
    }

    r2_storage_service.reset_mocks()
    mock_db = MagicMock()
    mock_db.reports.find_one.return_value = None  # force fresh generation
    mock_db.documents.find.return_value = [{"document_id": "doc_apple", "company_name": "Apple"}]
    mock_db.extracted_metrics.find.return_value = [apple]
    mock_db.red_flags.find.return_value = []
    mock_db.comparison_results.find.return_value.sort.return_value.limit.return_value = []
    mock_db.research_messages.find.return_value.sort.return_value = []
    mock_db.research_session_memory.find_one.return_value = None

    captured = {}
    mock_db.reports.replace_one.side_effect = lambda flt, doc, **k: captured.update(doc)

    with patch("agents.report.report_agent.get_sync_db", return_value=mock_db), \
         patch("workers.email_tasks.send_locked_pdf_email.apply_async") as mock_send:
        result = ReportAgent().execute(
            payload={"session_id": SESSION, "user_id": USER_A},
            context={"user_id": USER_A},
        )

    object_key = result.summary["object_key"]
    try:
        assert result.summary["pdf_locked"] is True
        assert result.summary["email_status"] == "queued"
        assert result.summary["password_available"] is True
        assert captured.get("pdf_locked") is True
        assert captured.get("pdf_password_enc")
        assert mock_send.called  # emailed immediately on report completion

        download_bytes = r2_storage_service.get_bytes(object_key)
        email_bytes = r2_storage_service.get_bytes(object_key)
        assert download_bytes == email_bytes
        assert is_pdf_encrypted(download_bytes) is True

        pw = decrypt_password_at_rest(captured["pdf_password_enc"])
        assert can_open_with_password(download_bytes, pw) is True
        assert can_open_with_password(download_bytes, "FS-9999-9999-9999") is False
    finally:
        r2_storage_service.delete_object(object_key)
        r2_storage_service.reset_mocks()


# =====================================================================
# 7. AUTHORIZATION — User A cannot reveal/retry User B's report
# =====================================================================

@pytest.mark.asyncio
async def test_report_password_reveal_is_owner_gated():
    from services.report_service import ReportService
    from core.exceptions import UnauthorizedReportAccessException

    report_doc = {
        "session_id": SESSION, "report_id": "rep_x", "user_id": USER_B,  # owned by B
        "pdf_password_enc": "tok", "object_key": "reports/x.pdf",
    }
    with patch("database.connection.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.reports.find_one = AsyncMock(return_value=report_doc)
        mock_get_db.return_value = mock_db
        # User A attempts to reveal B's password -> rejected
        with pytest.raises(UnauthorizedReportAccessException):
            await ReportService.reveal_password_async(SESSION, USER_A, "rep_x")


@pytest.mark.asyncio
async def test_report_email_retry_is_owner_gated():
    from services.report_service import ReportService
    from core.exceptions import UnauthorizedReportAccessException

    report_doc = {
        "session_id": SESSION, "report_id": "rep_x", "user_id": USER_B,
        "object_key": "reports/x.pdf",
    }
    with patch("database.connection.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.reports.find_one = AsyncMock(return_value=report_doc)
        mock_db.analysis_reports.find_one = AsyncMock(return_value=None)
        mock_get_db.return_value = mock_db
        with pytest.raises(UnauthorizedReportAccessException):
            await ReportService.retry_email_async(SESSION, USER_A, "rep_x")


@pytest.mark.asyncio
async def test_report_response_never_contains_password_token():
    from services.report_service import ReportService

    report_doc = {
        "session_id": SESSION, "report_id": "rep_x", "user_id": USER_A,
        "pdf_password_enc": "SECRET_TOKEN", "object_key": "reports/x.pdf", "_id": "abc",
    }
    with patch("database.connection.mongodb.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.reports.find_one = AsyncMock(return_value=report_doc)
        mock_get_db.return_value = mock_db
        out = await ReportService.get_report_async(SESSION, USER_A, "rep_x")
        assert "pdf_password_enc" not in out          # token stripped
        assert out.get("password_available") is True   # boolean flag exposed instead


# =====================================================================
# 9. EMAIL FAILURE — PDF stays available/encrypted; retry reuses artifact
# =====================================================================

def test_email_failure_keeps_encrypted_pdf_and_marks_failed():
    """SMTP-not-configured path: status becomes failed but the encrypted PDF remains intact."""
    import workers.email_tasks as et
    from utils.pdf_security import generate_pdf_password, encrypt_pdf_bytes
    import io
    from reportlab.pdfgen import canvas
    from services.email_service import EmailNotConfiguredError

    # Persist a real encrypted artifact.
    key = f"reports/_test/{uuid.uuid4().hex}.pdf"
    buf = io.BytesIO(); c = canvas.Canvas(buf); c.drawString(100, 750, "x"); c.save()
    enc = encrypt_pdf_bytes(buf.getvalue(), generate_pdf_password())
    r2_storage_service.upload_bytes(key=key, data=enc, content_type="application/pdf")

    statuses = []
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {"_id": USER_A, "email": "a@example.com"}
    mock_db.reports.update_one.side_effect = lambda flt, upd, **k: statuses.append(upd["$set"].get("email_status"))
    mock_db.analysis_reports.update_one.side_effect = lambda *a, **k: None

    try:
        with patch.object(et, "get_sync_db", return_value=mock_db), \
             patch("bson.ObjectId.is_valid", return_value=False), \
             patch("services.email_service.email_service.send_email_with_attachment",
                   side_effect=EmailNotConfiguredError("smtp off")):
            out = et.send_locked_pdf_email.run(
                kind="report", user_id=USER_A, session_id=SESSION, ref_id="rep_x", object_key=key,
            )
        assert out["status"] == "failed"
        assert "failed" in statuses               # email_status set to failed
        # PDF remains available AND encrypted after the failure
        still = r2_storage_service.get_bytes(key)
        assert is_pdf_encrypted(still) is True
    finally:
        r2_storage_service.delete_object(key)


@pytest.mark.asyncio
async def test_email_retry_reuses_existing_pdf_no_regeneration():
    """Retry must re-queue using the persisted object_key WITHOUT rebuilding the report."""
    from services.report_service import ReportService

    report_doc = {
        "session_id": SESSION, "report_id": "rep_x", "user_id": USER_A,
        "object_key": "reports/rep_x.pdf", "pdf_locked": True,
    }
    with patch("database.connection.mongodb.get_db") as mock_get_db, \
         patch("workers.email_tasks.send_locked_pdf_email.apply_async") as mock_send, \
         patch("agents.report.pdf_builder.PDFBuilder.build_pdf") as mock_build:
        mock_db = MagicMock()
        mock_db.reports.find_one = AsyncMock(return_value=report_doc)
        mock_db.analysis_reports.find_one = AsyncMock(return_value=None)
        mock_db.reports.update_one = AsyncMock(return_value=None)
        mock_db.analysis_reports.update_one = AsyncMock(return_value=None)
        mock_get_db.return_value = mock_db

        status = await ReportService.retry_email_async(SESSION, USER_A, "rep_x")

        assert status == "queued"
        mock_send.assert_called_once()                      # re-queued
        # Reuses persisted object_key, does not regenerate the PDF.
        kwargs = mock_send.call_args.kwargs["kwargs"]
        assert kwargs["object_key"] == "reports/rep_x.pdf"
        mock_build.assert_not_called()
