"""
FinSentry AI — PDF download semantics tests (unlocked vs locked).

Verifies:
  * Normal download = UNLOCKED (decrypted in memory, opens without a password).
  * Locked download = ENCRYPTED bytes (requires the password).
  * Unlocked download NEVER persists plaintext (no storage write during unlocked read).
  * Locked download bytes are byte-identical to the persisted encrypted artifact (== email attachment).
  * Ownership: User A can read A's unlocked/locked bytes; User B is forbidden.

Uses a real encrypted artifact on disk (r2 fallback) + mocked DB doc; owner-enforced.
"""

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from reportlab.pdfgen import canvas

from services.r2_storage_service import r2_storage_service
from services.report_service import ReportService
from core.exceptions import UnauthorizedReportAccessException
from utils.pdf_security import (
    generate_pdf_password,
    encrypt_pdf_bytes,
    encrypt_password_at_rest,
    is_pdf_encrypted,
    can_open_with_password,
)

SESSION = "sess_dl_semantics"
USER_A = "user_dl_A"
USER_B = "user_dl_B"


def _make_encrypted_artifact():
    """Persist a real AES-256 encrypted PDF and return (object_key, password, encrypted_bytes)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "FinSentry download-semantics test")
    c.save()
    password = generate_pdf_password()
    encrypted = encrypt_pdf_bytes(buf.getvalue(), password)
    key = f"reports/_dltest/{uuid.uuid4().hex}.pdf"
    r2_storage_service.upload_bytes(key=key, data=encrypted, content_type="application/pdf")
    return key, password, encrypted


def _report_doc(object_key, password, owner=USER_A):
    return {
        "session_id": SESSION,
        "report_id": "rep_dl",
        "user_id": owner,
        "object_key": object_key,
        "pdf_password_enc": encrypt_password_at_rest(password),
    }


# ---------------------------------------------------------------------------
# Locked download = encrypted bytes; byte-identical to persisted artifact (== email)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locked_download_returns_encrypted_bytes_matching_persisted():
    key, password, encrypted = _make_encrypted_artifact()
    try:
        with patch("database.connection.mongodb.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.reports.find_one = AsyncMock(return_value=_report_doc(key, password))
            mock_get_db.return_value = mock_db
            locked = await ReportService.get_report_locked_bytes_async(SESSION, USER_A, "rep_dl")

        assert locked == encrypted                       # byte-identical to persisted (== email attachment)
        assert is_pdf_encrypted(locked) is True          # requires a password
        assert can_open_with_password(locked, password) is True
        assert can_open_with_password(locked, "FS-0000-0000-0000") is False
    finally:
        r2_storage_service.delete_object(key)


# ---------------------------------------------------------------------------
# Normal download = unlocked; opens without a password; not persisted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unlocked_download_is_not_encrypted_and_not_persisted():
    key, password, _encrypted = _make_encrypted_artifact()
    try:
        with patch("database.connection.mongodb.get_db") as mock_get_db, \
             patch("services.r2_storage_service.r2_storage_service.upload_bytes") as mock_upload:
            mock_db = MagicMock()
            mock_db.reports.find_one = AsyncMock(return_value=_report_doc(key, password))
            mock_get_db.return_value = mock_db
            unlocked = await ReportService.get_report_unlocked_bytes_async(SESSION, USER_A, "rep_dl")

        assert is_pdf_encrypted(unlocked) is False       # opens without a password
        assert unlocked[:5] == b"%PDF-"                  # valid PDF
        # The unlocked bytes must NOT be written anywhere (decrypt happens in memory).
        mock_upload.assert_not_called()
    finally:
        r2_storage_service.delete_object(key)


# ---------------------------------------------------------------------------
# Ownership: User B cannot read User A's unlocked/locked bytes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_user_locked_download_forbidden():
    key, password, _ = _make_encrypted_artifact()
    try:
        with patch("database.connection.mongodb.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.reports.find_one = AsyncMock(return_value=_report_doc(key, password, owner=USER_A))
            mock_db.analysis_reports.find_one = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_db
            with pytest.raises(UnauthorizedReportAccessException):
                await ReportService.get_report_locked_bytes_async(SESSION, USER_B, "rep_dl")
    finally:
        r2_storage_service.delete_object(key)


@pytest.mark.asyncio
async def test_cross_user_unlocked_download_forbidden():
    key, password, _ = _make_encrypted_artifact()
    try:
        with patch("database.connection.mongodb.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.reports.find_one = AsyncMock(return_value=_report_doc(key, password, owner=USER_A))
            mock_db.analysis_reports.find_one = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_db
            with pytest.raises(UnauthorizedReportAccessException):
                await ReportService.get_report_unlocked_bytes_async(SESSION, USER_B, "rep_dl")
    finally:
        r2_storage_service.delete_object(key)


@pytest.mark.asyncio
async def test_owner_can_read_both_unlocked_and_locked():
    key, password, encrypted = _make_encrypted_artifact()
    try:
        with patch("database.connection.mongodb.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.reports.find_one = AsyncMock(return_value=_report_doc(key, password))
            mock_get_db.return_value = mock_db
            locked = await ReportService.get_report_locked_bytes_async(SESSION, USER_A, "rep_dl")
            unlocked = await ReportService.get_report_unlocked_bytes_async(SESSION, USER_A, "rep_dl")

        assert is_pdf_encrypted(locked) is True
        assert is_pdf_encrypted(unlocked) is False
        # locked (== email attachment) and unlocked are intentionally different byte streams
        assert locked != unlocked
        assert locked == encrypted
    finally:
        r2_storage_service.delete_object(key)


# ---------------------------------------------------------------------------
# Comparison unlocked vs locked (via canonical decrypt util) — same guarantees
# ---------------------------------------------------------------------------

def test_comparison_locked_vs_unlocked_semantics():
    from utils.pdf_security import decrypt_pdf_bytes

    key, password, encrypted = _make_encrypted_artifact()
    try:
        locked = r2_storage_service.get_bytes(key)          # /compare/download/locked returns this
        unlocked = decrypt_pdf_bytes(locked, password)      # /compare/download decrypts in memory
        assert locked == encrypted
        assert is_pdf_encrypted(locked) is True
        assert is_pdf_encrypted(unlocked) is False
        assert unlocked[:5] == b"%PDF-"
        assert can_open_with_password(locked, password) is True
    finally:
        r2_storage_service.delete_object(key)
