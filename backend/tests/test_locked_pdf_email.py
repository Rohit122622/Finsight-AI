"""
FinSentry AI — Locked PDF + Email feature tests (Part L).

Covers encryption correctness, unique/secret passwords, at-rest protection,
same-artifact (download == email) bytes, email content rules, recipient sourcing,
and "no password in logs". Infra-light: no live SMTP and no seeded DB required.
"""

import io
import logging
import re
import inspect
import uuid

import pytest
from reportlab.pdfgen import canvas

from utils.pdf_security import (
    generate_pdf_password,
    encrypt_pdf_bytes,
    can_open_with_password,
    is_pdf_encrypted,
    encrypt_password_at_rest,
    decrypt_password_at_rest,
)


PWD_RE = re.compile(r"^FS-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")


def _make_pdf(text: str = "FinSentry test document") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, text)
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Password generation
# ---------------------------------------------------------------------------

def test_password_format_matches_spec():
    for _ in range(20):
        assert PWD_RE.match(generate_pdf_password())


def test_password_is_unique_per_report():
    passwords = {generate_pdf_password() for _ in range(200)}
    # Extremely unlikely to collide; guarantees per-report uniqueness in practice.
    assert len(passwords) == 200


def test_password_uses_unambiguous_alphabet():
    body = generate_pdf_password()[3:].replace("-", "")
    assert not set(body) & set("01OIL")


# ---------------------------------------------------------------------------
# Encryption correctness
# ---------------------------------------------------------------------------

def test_plain_pdf_is_not_encrypted():
    assert is_pdf_encrypted(_make_pdf()) is False


def test_encrypted_pdf_is_encrypted():
    enc = encrypt_pdf_bytes(_make_pdf(), generate_pdf_password())
    assert is_pdf_encrypted(enc) is True


def test_correct_password_opens_and_wrong_fails():
    pw = generate_pdf_password()
    enc = encrypt_pdf_bytes(_make_pdf(), pw)
    assert can_open_with_password(enc, pw) is True
    assert can_open_with_password(enc, "FS-0000-0000-0000") is False


def test_encrypted_bytes_differ_from_plaintext():
    plain = _make_pdf()
    enc = encrypt_pdf_bytes(plain, generate_pdf_password())
    assert enc != plain
    assert b"FinSentry test document" not in enc  # content not in cleartext


# ---------------------------------------------------------------------------
# Password at-rest protection
# ---------------------------------------------------------------------------

def test_password_at_rest_roundtrip_and_opaque():
    pw = generate_pdf_password()
    token = encrypt_password_at_rest(pw)
    assert token != pw
    assert pw not in token
    assert decrypt_password_at_rest(token) == pw


def test_decrypt_invalid_token_returns_none():
    assert decrypt_password_at_rest("not-a-valid-token") is None
    assert decrypt_password_at_rest("") is None


# ---------------------------------------------------------------------------
# Same artifact used for download and email
# ---------------------------------------------------------------------------

def test_download_and_email_use_identical_stored_bytes():
    """
    Download and email both read the SAME persisted object_key. Verify the storage
    layer returns byte-identical content on repeated reads (no divergent artifacts).
    """
    from services.r2_storage_service import r2_storage_service

    key = f"reports/_test/{uuid.uuid4().hex}.pdf"
    enc = encrypt_pdf_bytes(_make_pdf(), generate_pdf_password())
    r2_storage_service.upload_bytes(key=key, data=enc, content_type="application/pdf")
    try:
        download_bytes = r2_storage_service.get_bytes(key)   # what /download streams
        email_bytes = r2_storage_service.get_bytes(key)      # what the email task attaches
        assert download_bytes == email_bytes == enc
        assert is_pdf_encrypted(download_bytes) is True
    finally:
        r2_storage_service.delete_object(key)


# ---------------------------------------------------------------------------
# Email content rules (no password inside email; correct subjects)
# ---------------------------------------------------------------------------

def test_email_subjects_match_spec():
    from services.email_service import build_comparison_email, build_report_email

    assert build_comparison_email()[0] == "FinSentry AI — Your Comparison Report"
    assert build_report_email()[0] == "FinSentry AI — Your Financial Report"


def test_email_body_never_contains_password_and_explains_retrieval():
    from services.email_service import build_comparison_email, build_report_email

    for subject, body in (build_comparison_email(), build_report_email()):
        assert not PWD_RE.search(body)          # no password pattern
        assert "FS-" not in body                # no password token
        assert "password-protected" in body.lower()
        assert "retrieve" in body.lower()       # tells user to retrieve it in-app


# ---------------------------------------------------------------------------
# Recipient sourcing: task cannot accept a frontend-supplied email
# ---------------------------------------------------------------------------

def test_email_task_has_no_recipient_parameter():
    """
    The Celery email task must resolve the recipient from the DB user record, so it
    must NOT expose any recipient/email parameter that a caller could override.
    """
    from workers.email_tasks import send_locked_pdf_email

    params = set(inspect.signature(send_locked_pdf_email.run).parameters)
    for forbidden in {"to_email", "email", "recipient", "recipient_email"}:
        assert forbidden not in params
    # It DOES take user_id (used to look up the registered email server-side).
    assert "user_id" in params


# ---------------------------------------------------------------------------
# No password in logs
# ---------------------------------------------------------------------------

def test_password_not_emitted_to_logs(caplog):
    caplog.set_level(logging.DEBUG)
    pw = generate_pdf_password()
    enc = encrypt_pdf_bytes(_make_pdf(), pw)
    token = encrypt_password_at_rest(pw)
    _ = decrypt_password_at_rest(token)
    _ = can_open_with_password(enc, pw)
    assert pw not in caplog.text
