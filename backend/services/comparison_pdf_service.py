"""
FinSentry AI — Comparison locked-PDF finalization (canonical, synchronous).

Single source of truth for: build -> AES-256 encrypt -> persist ONLY the encrypted
artifact -> queue the automatic email of that same artifact. Idempotent: an existing
locked artifact is reused (no regeneration, no duplicate email) which preserves the
comparison cache/idempotency guarantees.

Used by:
  * the synchronous POST /compare path (via a thin async wrapper),
  * the /compare/download safety net,
  * the asynchronous Celery finalize task (immediate email after async comparison).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from database.connection import get_sync_db
from services.r2_storage_service import r2_storage_service
from utils.pdf_security import (
    encrypt_pdf_bytes,
    encrypt_password_at_rest,
    generate_pdf_password,
)

logger = logging.getLogger(__name__)


def finalize_comparison_locked_pdf_sync(user_id: str, session_id: str, queue_email: bool = True) -> Dict[str, Any]:
    """
    Ensure an encrypted comparison PDF exists + is persisted, then (optionally) queue email.

    Returns a status dict: pdf_available, pdf_locked, email_status, password_available, object_key.
    Never raises for email/broker problems — those degrade to email_status='failed'.
    """
    from agents.comparison.pdf_builder import comparison_pdf_builder

    db = get_sync_db()
    record = db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id}, sort=[("updated_at", -1)]
    )
    if not record or not record.get("comparison"):
        return {"pdf_available": False, "pdf_locked": False, "email_status": None, "password_available": False}

    object_key = f"comparisons/{user_id}/{session_id}/comparison.pdf"
    doc_ids_hash = record.get("document_ids_hash")
    update_query: Dict[str, Any] = {"session_id": session_id}
    if doc_ids_hash:
        update_query["document_ids_hash"] = doc_ids_hash

    try:
        exists = r2_storage_service.object_exists(object_key)
    except Exception:
        exists = False

    # Idempotent reuse: existing locked artifact -> no regeneration, no duplicate email.
    if record.get("pdf_locked") and record.get("pdf_password_enc") and exists:
        return {
            "pdf_available": True,
            "pdf_locked": True,
            "email_status": record.get("email_status") or "queued",
            "password_available": True,
            "object_key": object_key,
        }

    # Build -> encrypt in-memory -> persist ONLY the encrypted artifact.
    comp_data = record.get("comparison")
    unlocked = comparison_pdf_builder.build_pdf(comparison_data=comp_data, title="Comparative Financial Audit")
    password = generate_pdf_password()
    password_enc = encrypt_password_at_rest(password)
    encrypted = encrypt_pdf_bytes(unlocked, password)
    del unlocked
    r2_storage_service.upload_bytes(key=object_key, data=encrypted, content_type="application/pdf")

    db.comparison_results.update_one(
        update_query,
        {"$set": {
            "pdf_locked": True,
            "pdf_password_enc": password_enc,
            "object_key": object_key,
            "email_status": "queued",
        }},
    )

    email_status = "queued"
    if queue_email:
        try:
            from workers.email_tasks import send_locked_pdf_email

            send_locked_pdf_email.apply_async(kwargs={
                "kind": "comparison",
                "user_id": user_id,
                "session_id": session_id,
                "ref_id": doc_ids_hash or "",
                "object_key": object_key,
            })
        except Exception:  # noqa: BLE001 - never block comparison success
            email_status = "failed"
            db.comparison_results.update_one(update_query, {"$set": {"email_status": email_status}})

    return {
        "pdf_available": True,
        "pdf_locked": True,
        "email_status": email_status,
        "password_available": True,
        "object_key": object_key,
    }
