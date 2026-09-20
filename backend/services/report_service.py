"""
FinSentry AI — Report Service.

Owner: Vanshika / FinSentry Engineering Team

Provides service-layer operations for triggering deterministic report generation,
listing reports, retrieving reports, and generating secure presigned download links.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from agents.registry import agent_registry
from core.exceptions import ReportNotFoundException, UnauthorizedReportAccessException
from database.connection import get_sync_db, mongodb
from services.r2_storage_service import r2_storage_service

logger = logging.getLogger(__name__)


class ReportService:
    """Service managing report lifecycle and access security."""

    @classmethod
    def generate_report_sync(
        cls,
        session_id: str,
        user_id: str,
        report_title: str = "Financial Research & Institutional Audit Report",
        report_version: str = "v1.0",
    ) -> Dict[str, Any]:
        """
        Execute ReportAgent synchronously to produce the PDF report.
        """
        report_agent = agent_registry.get("ReportAgent")
        result = report_agent.execute(
            payload={
                "session_id": session_id,
                "user_id": user_id,
                "report_title": report_title,
                "report_version": report_version,
            },
            context={"user_id": user_id},
        )
        if not result.success:
            raise RuntimeError(f"Report generation failed: {result.summary}")
        return result.summary

    @classmethod
    async def get_report_async(
        cls, session_id: str, user_id: str, report_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve report by report_id enforcing user and session ownership.
        """
        db = mongodb.get_db()
        report = await db.reports.find_one({"session_id": session_id, "report_id": report_id})
        if not report:
            # Check compatibility mirror
            report = await db.analysis_reports.find_one({"session_id": session_id, "report_id": report_id})

        if not report:
            raise ReportNotFoundException(f"Report '{report_id}' not found for session '{session_id}'.")

        if report.get("user_id") and report.get("user_id") != user_id:
            raise UnauthorizedReportAccessException("You do not have permission to access this report.")

        if "_id" in report:
            report["_id"] = str(report["_id"])

        # Never leak the stored password token; expose a boolean flag instead.
        report["password_available"] = bool(report.get("pdf_password_enc"))
        report.pop("pdf_password_enc", None)
        return report

    @classmethod
    async def reveal_password_async(
        cls, session_id: str, user_id: str, report_id: str
    ) -> str:
        """
        Return the plaintext PDF password for the authenticated OWNER only.

        Reads the encrypted token directly (bypassing the sanitized getter),
        after enforcing session + user ownership.
        """
        from utils.pdf_security import decrypt_password_at_rest

        db = mongodb.get_db()
        report = await db.reports.find_one({"session_id": session_id, "report_id": report_id})
        if not report:
            report = await db.analysis_reports.find_one({"session_id": session_id, "report_id": report_id})
        if not report:
            raise ReportNotFoundException(f"Report '{report_id}' not found for session '{session_id}'.")
        if report.get("user_id") and report.get("user_id") != user_id:
            raise UnauthorizedReportAccessException("You do not have permission to access this report.")

        token = report.get("pdf_password_enc")
        password = decrypt_password_at_rest(token) if token else None
        if not password:
            raise ReportNotFoundException("No PDF password is available for this report.")
        return password

    @classmethod
    async def retry_email_async(
        cls, session_id: str, user_id: str, report_id: str
    ) -> str:
        """
        Re-queue the report email using the already-persisted encrypted PDF.
        Enforces ownership. Returns the new email_status ('queued' or 'failed').
        Never regenerates the report.
        """
        report = await cls.get_report_async(session_id=session_id, user_id=user_id, report_id=report_id)
        object_key = report.get("object_key") or f"reports/{user_id}/{session_id}/{report_id}.pdf"

        db = mongodb.get_db()
        try:
            from workers.email_tasks import send_locked_pdf_email

            send_locked_pdf_email.apply_async(
                kwargs={
                    "kind": "report",
                    "user_id": user_id,
                    "session_id": session_id,
                    "ref_id": report_id,
                    "object_key": object_key,
                }
            )
            new_status = "queued"
        except Exception:
            new_status = "failed"

        await db.reports.update_one({"report_id": report_id}, {"$set": {"email_status": new_status}})
        await db.analysis_reports.update_one({"report_id": report_id}, {"$set": {"email_status": new_status}})
        return new_status

    @classmethod
    async def list_reports_async(
        cls, session_id: str, user_id: str, skip: int = 0, limit: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List all reports for a session with pagination.
        """
        db = mongodb.get_db()
        cursor = db.reports.find({"session_id": session_id, "user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        reports = await cursor.to_list(length=limit)

        # Fallback to analysis_reports if empty
        if not reports:
            cursor_compat = db.analysis_reports.find({"session_id": session_id, "user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
            reports = await cursor_compat.to_list(length=limit)
            total = await db.analysis_reports.count_documents({"session_id": session_id, "user_id": user_id})
        else:
            total = await db.reports.count_documents({"session_id": session_id, "user_id": user_id})

        for r in reports:
            if "_id" in r:
                r["_id"] = str(r["_id"])
            r["password_available"] = bool(r.get("pdf_password_enc"))
            r.pop("pdf_password_enc", None)

        return reports, total

    @classmethod
    async def get_report_download_async(
        cls, session_id: str, user_id: str, report_id: str
    ) -> Tuple[str, Optional[bytes]]:
        """
        Generate presigned download URL or retrieve raw PDF bytes from R2.
        Enforces user ownership.
        """
        report = await cls.get_report_async(session_id=session_id, user_id=user_id, report_id=report_id)
        object_key = report.get("object_key") or f"reports/{user_id}/{session_id}/{report_id}.pdf"

        # Retrieve bytes directly from storage (disk or R2)
        pdf_bytes = None
        try:
            pdf_bytes = r2_storage_service.get_bytes(object_key)
        except Exception as exc:
            logger.warning("Could not fetch raw bytes from R2 for %s: %s", object_key, exc)

        # Generate presigned URL if possible
        presigned_url = None
        try:
            presigned_url = r2_storage_service.generate_presigned_url(object_key, expires_in_seconds=3600)
        except Exception as exc:
            logger.warning("Could not generate presigned URL for %s: %s", object_key, exc)

        return presigned_url, pdf_bytes

    @classmethod
    async def _load_locked(cls, session_id: str, user_id: str, report_id: str):
        """
        Owner-enforced load of (object_key, encrypted_bytes, plaintext_password).
        Reads the password token directly (bypassing the sanitized getter) after
        verifying session + user ownership.
        """
        from utils.pdf_security import decrypt_password_at_rest

        db = mongodb.get_db()
        report = await db.reports.find_one({"session_id": session_id, "report_id": report_id})
        if not report:
            report = await db.analysis_reports.find_one({"session_id": session_id, "report_id": report_id})
        if not report:
            raise ReportNotFoundException(f"Report '{report_id}' not found for session '{session_id}'.")
        if report.get("user_id") and report.get("user_id") != user_id:
            raise UnauthorizedReportAccessException("You do not have permission to access this report.")

        object_key = report.get("object_key") or f"reports/{user_id}/{session_id}/{report_id}.pdf"
        encrypted_bytes = r2_storage_service.get_bytes(object_key)
        password = decrypt_password_at_rest(report.get("pdf_password_enc"))
        return object_key, encrypted_bytes, password

    @classmethod
    async def get_report_locked_bytes_async(cls, session_id: str, user_id: str, report_id: str) -> bytes:
        """Return the persisted ENCRYPTED PDF bytes (owner-enforced). Never decrypted."""
        _key, encrypted_bytes, _pw = await cls._load_locked(session_id, user_id, report_id)
        return encrypted_bytes

    @classmethod
    async def get_report_unlocked_bytes_async(cls, session_id: str, user_id: str, report_id: str) -> bytes:
        """
        Return UNLOCKED PDF bytes by decrypting the persisted encrypted artifact IN MEMORY
        (owner-enforced). The unlocked bytes are never persisted.
        """
        from utils.pdf_security import decrypt_pdf_bytes

        _key, encrypted_bytes, password = await cls._load_locked(session_id, user_id, report_id)
        if not password:
            raise ReportNotFoundException("Report PDF password unavailable; cannot produce unlocked copy.")
        return decrypt_pdf_bytes(encrypted_bytes, password)

    # =====================================================================
    # PER-COMPANY (single-document) reports — reuse ReportCompiler + PDFBuilder.
    # These are compiled on demand and company-isolated: an individual company
    # report consumes ONLY that document's extracted metrics + red flags.
    # =====================================================================

    @classmethod
    async def _gather_company_inputs_async(cls, session_id: str, user_id: str, document_id: str):
        """
        Owner-scoped gather of a single document's inputs. Verifies the document belongs
        to the authenticated user + session. Returns (documents, extracted_metrics, red_flags).
        """
        db = mongodb.get_db()

        doc = await db.documents.find_one(
            {"document_id": document_id, "session_id": session_id, "user_id": user_id}
        )
        if not doc:
            raise ReportNotFoundException(
                f"Document '{document_id}' not found for session '{session_id}'."
            )

        em = await db.extracted_metrics.find(
            {"document_id": document_id, "session_id": session_id, "user_id": user_id}
        ).to_list(length=50)
        rf = await db.red_flags.find(
            {"document_id": document_id, "session_id": session_id, "user_id": user_id}
        ).to_list(length=50)
        return [doc], em, rf

    @classmethod
    async def _compile_company_report_async(cls, session_id: str, user_id: str, document_id: str):
        """Compile a single-company ReportDocument (no comparison, no cross-company research)."""
        from agents.report.report_compiler import ReportCompiler

        documents, em, rf = await cls._gather_company_inputs_async(session_id, user_id, document_id)
        company = (
            (rf[0].get("company_name") if rf else None)
            or (em[0].get("company_name") if em else None)
            or (documents[0].get("company_name") if documents else None)
            or "Company"
        )
        report_doc = ReportCompiler.compile(
            session_id=session_id,
            user_id=user_id,
            report_title=f"{company} — Financial Analysis Report",
            report_version="company-" + str(document_id)[:8],
            documents=documents,
            extracted_metrics_list=em,
            red_flags_list=rf,
            comparison_results_list=[],   # single company → comparison cleanly omitted
            research_messages_list=[],    # avoid cross-company research leakage
        )
        return report_doc, company

    @classmethod
    async def get_company_report_content_async(cls, session_id: str, user_id: str, document_id: str) -> Dict[str, Any]:
        """Return the per-company report content (JSON) for display. Owner-enforced."""
        report_doc, company = await cls._compile_company_report_async(session_id, user_id, document_id)
        data = report_doc.model_dump(mode="json")
        data["company_name"] = company
        data["document_id"] = document_id
        return data

    @classmethod
    async def get_company_report_pdf_unlocked_async(cls, session_id: str, user_id: str, document_id: str) -> bytes:
        """Compile + build the per-company PDF and return UNLOCKED bytes (in memory; not persisted)."""
        from agents.report.pdf_builder import PDFBuilder

        report_doc, _company = await cls._compile_company_report_async(session_id, user_id, document_id)
        return PDFBuilder.build_pdf(report_doc)

    @classmethod
    async def get_company_report_pdf_locked_async(cls, session_id: str, user_id: str, document_id: str) -> bytes:
        """
        Compile + build the per-company PDF and return LOCKED (AES-256) bytes, encrypted with the
        SAME session report password so the user can open it with the revealable password.
        Requires the session (combined) report to exist (so a revealable password is available).
        """
        from agents.report.pdf_builder import PDFBuilder
        from utils.pdf_security import encrypt_pdf_bytes, decrypt_password_at_rest

        db = mongodb.get_db()
        session_report = await db.reports.find_one(
            {"session_id": session_id, "user_id": user_id, "pdf_locked": True},
            sort=[("created_at", -1)],
        )
        password = decrypt_password_at_rest((session_report or {}).get("pdf_password_enc")) if session_report else None
        if not password:
            raise ReportNotFoundException(
                "Generate the session report first to enable locked individual downloads."
            )
        report_doc, _company = await cls._compile_company_report_async(session_id, user_id, document_id)
        unlocked = PDFBuilder.build_pdf(report_doc)
        return encrypt_pdf_bytes(unlocked, password)


report_service = ReportService()
