"""
FinSentry AI — Celery email tasks for delivering locked (encrypted) PDFs.

Flow (never blocks the agent request):
    authenticated user -> DB user record -> registered email -> this task -> SMTP

SECURITY INVARIANTS:
  - Recipient is resolved from the DB user record (user_id), NEVER from the frontend.
  - The attached PDF is the SAME persisted encrypted artifact used for download.
  - The PDF password is NEVER included in the email or logged.
"""

from __future__ import annotations

import logging
from typing import Optional

from bson import ObjectId

from database.connection import get_sync_db
from services.email_service import (
    build_comparison_email,
    build_report_email,
    email_service,
    EmailNotConfiguredError,
)
from services.r2_storage_service import r2_storage_service
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _set_email_status(kind: str, session_id: str, ref_id: str, status: str) -> None:
    """Persist email_status on the relevant record(s). Best-effort, never raises."""
    try:
        db = get_sync_db()
        if kind == "report":
            db.reports.update_one({"report_id": ref_id}, {"$set": {"email_status": status}})
            db.analysis_reports.update_one({"report_id": ref_id}, {"$set": {"email_status": status}})
        elif kind == "comparison":
            query = {"session_id": session_id}
            if ref_id:
                query["document_ids_hash"] = ref_id
            db.comparison_results.update_one(query, {"$set": {"email_status": status}})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not update email_status=%s for %s: %s", status, kind, type(exc).__name__)


def _mask_email(email: Optional[str]) -> str:
    """Mask an email for safe diagnostic logging: 'r***@domain'."""
    if not email or "@" not in email:
        return "<none>"
    name, domain = email.split("@", 1)
    return (name[:1] if name else "") + "***@" + domain


def _resolve_user_email(user_id: str) -> Optional[str]:
    """
    Resolve the recipient STRICTLY from the exact authenticated user record.

    Lookup order is exact-identity only:
      1. users._id == ObjectId(user_id)
      2. users.user_id == user_id   (non-ObjectId identity schemes)

    There is intentionally NO fallback to the first user, to SMTP_FROM_EMAIL, or to any
    other arbitrary record. If the exact user cannot be found, returns None and the caller
    marks the email FAILED (never sends to a different user).
    """
    db = get_sync_db()
    doc = None
    if ObjectId.is_valid(user_id):
        doc = db.users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        doc = db.users.find_one({"user_id": user_id})
    return (doc or {}).get("email")


@celery_app.task(
    bind=True,
    name="workers.email_tasks.send_locked_pdf_email",
    max_retries=3,
    default_retry_delay=30,
)
def send_locked_pdf_email(
    self,
    kind: str,
    user_id: str,
    session_id: str,
    ref_id: str,
    object_key: str,
) -> dict:
    """
    Email the persisted encrypted PDF to the authenticated user's registered address.

    kind: "report" | "comparison"
    ref_id: report_id (report) or document_ids_hash (comparison)
    object_key: storage key of the ENCRYPTED PDF artifact
    """
    _set_email_status(kind, session_id, ref_id, "sending")

    # Resolve recipient STRICTLY from the exact authenticated user record (no fallback).
    recipient = _resolve_user_email(user_id)
    # Sanitized diagnostic (never logs full email unless masked, never logs secrets).
    logger.info("email task=%s user_id=%s recipient=%s", kind, user_id, _mask_email(recipient))
    if not recipient:
        logger.error(
            "Email FAILED: could not resolve exact authenticated user email (task=%s user_id=%s)",
            kind, user_id,
        )
        _set_email_status(kind, session_id, ref_id, "failed")
        return {"status": "failed", "reason": "recipient_resolution_failed"}

    # Load the SAME encrypted artifact used for download.
    try:
        pdf_bytes = r2_storage_service.get_bytes(object_key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Email FAILED: could not load encrypted PDF (task=%s type=%s)", kind, type(exc).__name__)
        _set_email_status(kind, session_id, ref_id, "failed")
        return {"status": "failed", "reason": "artifact_missing"}

    if kind == "report":
        subject, body = build_report_email()
        filename = f"FinSentry_Report_{ref_id[:8]}.pdf"
    else:
        subject, body = build_comparison_email()
        filename = f"FinSentry_Comparison_{session_id[:8]}.pdf"

    try:
        message_id = email_service.send_email_with_attachment(
            to_email=recipient,
            subject=subject,
            body_text=body,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )
    except EmailNotConfiguredError:
        logger.error("EMAIL_FAILED task=%s user_id=%s reason=smtp_not_configured", kind, user_id)
        _set_email_status(kind, session_id, ref_id, "failed")
        return {"status": "failed", "reason": "smtp_not_configured"}
    except Exception as exc:  # noqa: BLE001
        logger.error("EMAIL_FAILED task=%s user_id=%s reason=%s", kind, user_id, type(exc).__name__)
        _set_email_status(kind, session_id, ref_id, "failed")
        raise self.retry(exc=exc)

    # SMTP accepted the message for delivery (submission succeeded).
    logger.info(
        "EMAIL_SUBMITTED task=%s user_id=%s recipient=%s message_id=%s",
        kind, user_id, _mask_email(recipient), message_id,
    )
    _set_email_status(kind, session_id, ref_id, "sent")
    return {"status": "sent", "message_id": message_id}


@celery_app.task(
    bind=True,
    name="workers.email_tasks.finalize_comparison_email",
    max_retries=12,
    default_retry_delay=5,
)
def finalize_comparison_email(self, user_id: str, session_id: str) -> dict:
    """
    Finalize the ENCRYPTED comparison PDF and queue its email immediately after an
    asynchronous comparison completes.

    Waits (bounded retries) for the ComparisonAgent to persist comparison_results, then
    runs the canonical idempotent finalizer (build -> encrypt -> persist -> queue email).
    """
    db = get_sync_db()
    record = db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id}, sort=[("updated_at", -1)]
    )
    if not record or not record.get("comparison"):
        # Comparison not persisted yet — wait and retry.
        raise self.retry()

    from services.comparison_pdf_service import finalize_comparison_locked_pdf_sync

    result = finalize_comparison_locked_pdf_sync(user_id, session_id)
    return {"status": "finalized", "email_status": result.get("email_status")}
