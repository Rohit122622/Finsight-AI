"""
FinSentry AI — Email recipient resolution + status lifecycle tests (final fixes).

Verifies:
  A. Recipient resolved from the EXACT authenticated user record (A -> A email).
  B. NO arbitrary fallback: unknown user_id -> None -> email FAILED, send never attempted,
     and never sent to another user.
  C. Status lifecycle: sending -> sent (SENT only after the real send succeeds).
  D. Failure -> failed (SMTP error, missing config, artifact missing, recipient missing).

Uses mocked DB + mocked SMTP send; no real emails and no live Atlas writes.
"""

from unittest.mock import MagicMock, patch

import pytest

import workers.email_tasks as et
from services.email_service import EmailNotConfiguredError

USER_A = "user_A"
USER_B = "user_B"
EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"


# ---------------------------------------------------------------------------
# A. Recipient resolution — exact user only
# ---------------------------------------------------------------------------

def test_resolve_recipient_returns_exact_user_email():
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {"email": EMAIL_A}
    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False):
        assert et._resolve_user_email(USER_A) == EMAIL_A


def test_mask_email_never_reveals_full_local_part():
    masked = et._mask_email(EMAIL_A)
    assert masked == "a***@example.com"
    assert EMAIL_A not in masked
    assert et._mask_email(None) == "<none>"


# ---------------------------------------------------------------------------
# B. No arbitrary fallback when the exact user cannot be found
# ---------------------------------------------------------------------------

def test_no_fallback_when_user_missing_marks_failed_and_never_sends():
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = None  # exact user not found
    statuses = []
    mock_db.reports.update_one.side_effect = lambda flt, upd, **k: statuses.append(upd["$set"].get("email_status"))
    mock_db.analysis_reports.update_one.side_effect = lambda *a, **k: None

    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False), \
         patch("workers.email_tasks.r2_storage_service.get_bytes", return_value=b"%PDF-enc") as mock_get, \
         patch("workers.email_tasks.email_service.send_email_with_attachment") as mock_send:
        out = et.send_locked_pdf_email.run(
            kind="report", user_id=USER_A, session_id="s", ref_id="rep_x", object_key="k.pdf",
        )

    assert out["status"] == "failed"
    assert out["reason"] == "recipient_resolution_failed"
    mock_send.assert_not_called()      # never sends to anyone
    mock_get.assert_not_called()       # aborts before loading the artifact
    assert "failed" in statuses


def test_recipient_is_user_a_never_user_b():
    """The task resolves recipient for user_A only; user_B's email is never used."""
    def users_find_one(query):
        # exact-identity lookup by user_id field
        if query.get("user_id") == USER_A:
            return {"email": EMAIL_A}
        if query.get("user_id") == USER_B:
            return {"email": EMAIL_B}
        return None

    mock_db = MagicMock()
    mock_db.users.find_one.side_effect = users_find_one

    sent_to = {}
    def _send(**kwargs):
        sent_to["to"] = kwargs.get("to_email")
    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False), \
         patch("workers.email_tasks.r2_storage_service.get_bytes", return_value=b"%PDF-enc"), \
         patch("workers.email_tasks.email_service.send_email_with_attachment", side_effect=_send):
        et.send_locked_pdf_email.run(
            kind="report", user_id=USER_A, session_id="s", ref_id="rep_x", object_key="k.pdf",
        )

    assert sent_to["to"] == EMAIL_A
    assert sent_to["to"] != EMAIL_B


# ---------------------------------------------------------------------------
# C. Status lifecycle: sending -> sent (SENT only after real send returns)
# ---------------------------------------------------------------------------

def test_status_lifecycle_sending_then_sent_after_send_returns():
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {"email": EMAIL_A}
    events = []
    mock_db.reports.update_one.side_effect = lambda flt, upd, **k: events.append(("status", upd["$set"].get("email_status")))
    mock_db.analysis_reports.update_one.side_effect = lambda *a, **k: None

    def _send(**kwargs):
        events.append(("send", kwargs.get("to_email")))

    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False), \
         patch("workers.email_tasks.r2_storage_service.get_bytes", return_value=b"%PDF-enc"), \
         patch("workers.email_tasks.email_service.send_email_with_attachment", side_effect=_send):
        out = et.send_locked_pdf_email.run(
            kind="report", user_id=USER_A, session_id="s", ref_id="rep_x", object_key="k.pdf",
        )

    assert out["status"] == "sent"
    status_seq = [v for (t, v) in events if t == "status"]
    assert status_seq == ["sending", "sent"]
    # 'sent' must be recorded AFTER the actual send call.
    assert events.index(("send", EMAIL_A)) < events.index(("status", "sent"))


# ---------------------------------------------------------------------------
# D. Failure paths -> failed
# ---------------------------------------------------------------------------

def test_smtp_not_configured_marks_failed_no_retry():
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {"email": EMAIL_A}
    statuses = []
    mock_db.reports.update_one.side_effect = lambda flt, upd, **k: statuses.append(upd["$set"].get("email_status"))
    mock_db.analysis_reports.update_one.side_effect = lambda *a, **k: None

    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False), \
         patch("workers.email_tasks.r2_storage_service.get_bytes", return_value=b"%PDF-enc"), \
         patch("workers.email_tasks.email_service.send_email_with_attachment",
               side_effect=EmailNotConfiguredError("off")):
        out = et.send_locked_pdf_email.run(
            kind="report", user_id=USER_A, session_id="s", ref_id="rep_x", object_key="k.pdf",
        )

    assert out["status"] == "failed"
    assert out["reason"] == "smtp_not_configured"
    assert statuses[-1] == "failed"


def test_artifact_missing_marks_failed_and_does_not_send():
    mock_db = MagicMock()
    mock_db.users.find_one.return_value = {"email": EMAIL_A}
    statuses = []
    mock_db.reports.update_one.side_effect = lambda flt, upd, **k: statuses.append(upd["$set"].get("email_status"))
    mock_db.analysis_reports.update_one.side_effect = lambda *a, **k: None

    with patch.object(et, "get_sync_db", return_value=mock_db), \
         patch("bson.ObjectId.is_valid", return_value=False), \
         patch("workers.email_tasks.r2_storage_service.get_bytes", side_effect=Exception("missing")), \
         patch("workers.email_tasks.email_service.send_email_with_attachment") as mock_send:
        out = et.send_locked_pdf_email.run(
            kind="report", user_id=USER_A, session_id="s", ref_id="rep_x", object_key="k.pdf",
        )

    assert out["status"] == "failed"
    assert out["reason"] == "artifact_missing"
    mock_send.assert_not_called()
    assert statuses[-1] == "failed"
