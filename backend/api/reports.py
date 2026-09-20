"""
FinSentry AI — Report Generation & Download API Router.

Owner: Vanshika / FinSentry Engineering Team

Provides REST endpoints for:
  1. POST /api/v1/sessions/{session_id}/report — Generate deterministic PDF report (sync or async)
  2. GET  /api/v1/sessions/{session_id}/reports — List reports for session
  3. GET  /api/v1/sessions/{session_id}/reports/{report_id} — Retrieve report metadata
  4. GET  /api/v1/sessions/{session_id}/reports/{report_id}/download — Secure PDF download / presigned redirect
"""

import io
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse

from agents.report.schemas import ReportGenerateRequest, ReportGenerateResponse
from core.constants import AgentTaskType
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from services.job_service import job_service
from services.report_service import report_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/report",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Generate deterministic institutional PDF report",
)
async def generate_report(
    session_id: str = Path(..., description="Research session ID"),
    request: ReportGenerateRequest = ReportGenerateRequest(),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Trigger deterministic report compilation for the research session.
    Compiles already-persisted agent outputs into an analyst-style PDF stored in R2.
    Supports synchronous and asynchronous (Celery) execution.
    """
    user_id = str(current_user.id)
    title = request.report_title or "Financial Research & Institutional Audit Report"
    version = request.report_version or "v1.0"

    if request.async_mode:
        # Dispatch background Celery job with idempotency
        idempotency_key = f"report:{session_id}:{user_id}:{version}"
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="ReportAgent",
            task_type=AgentTaskType.REPORT_GENERATION.value,
            payload={
                "session_id": session_id,
                "user_id": user_id,
                "report_title": title,
                "report_version": version,
            },
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        return {
            "status": "QUEUED",
            "job_id": job.job_id,
            "session_id": session_id,
            "message": "Report generation job queued in Celery worker.",
        }

    # Synchronous compilation
    try:
        summary = report_service.generate_report_sync(
            session_id=session_id,
            user_id=user_id,
            report_title=title,
            report_version=version,
        )
        return summary
    except Exception as exc:
        logger.error("Report generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation error: {exc}",
        )


@router.get(
    "/reports",
    response_model=Dict[str, Any],
    summary="List all reports for session",
)
async def list_reports(
    session_id: str = Path(..., description="Research session ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    List reports belonging to this session and authenticated user.
    """
    user_id = str(current_user.id)
    reports, total = await report_service.list_reports_async(
        session_id=session_id, user_id=user_id, skip=skip, limit=limit
    )
    return {
        "session_id": session_id,
        "reports": reports,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/reports/{report_id}",
    response_model=Dict[str, Any],
    summary="Get report metadata",
)
async def get_report(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve report metadata and status.
    """
    user_id = str(current_user.id)
    report = await report_service.get_report_async(
        session_id=session_id, user_id=user_id, report_id=report_id
    )
    return report


@router.get(
    "/reports/{report_id}/password",
    response_model=Dict[str, Any],
    summary="Reveal the locked-PDF password (authenticated owner only)",
)
async def reveal_report_password(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Return the PDF password required to open the encrypted report.
    Only the authenticated owner of the report/session may retrieve it.
    """
    user_id = str(current_user.id)
    password = await report_service.reveal_password_async(
        session_id=session_id, user_id=user_id, report_id=report_id
    )
    return {"report_id": report_id, "password": password}


@router.post(
    "/reports/{report_id}/email/retry",
    response_model=Dict[str, Any],
    summary="Retry emailing the encrypted report to the authenticated user",
)
async def retry_report_email(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Re-queue the report email using the already-persisted encrypted PDF.
    Does NOT regenerate the report. Recipient is the authenticated user's registered email.
    """
    user_id = str(current_user.id)
    email_status = await report_service.retry_email_async(
        session_id=session_id, user_id=user_id, report_id=report_id
    )
    return {"report_id": report_id, "email_status": email_status}


@router.get(
    "/reports/company/{document_id}",
    response_model=Dict[str, Any],
    summary="Per-company (single-document) report content — company-isolated",
)
async def get_company_report(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """Return the individual company report content (only that document's metrics + red flags)."""
    user_id = str(current_user.id)
    return await report_service.get_company_report_content_async(
        session_id=session_id, user_id=user_id, document_id=document_id
    )


@router.get(
    "/reports/company/{document_id}/download",
    summary="Download UNLOCKED per-company report PDF (owner only)",
)
async def download_company_report_pdf(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """Compile the per-company report on demand and stream UNLOCKED bytes (not persisted)."""
    user_id = str(current_user.id)
    pdf = await report_service.get_company_report_pdf_unlocked_async(
        session_id=session_id, user_id=user_id, document_id=document_id
    )
    filename = f"FinSentry_CompanyReport_{document_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/reports/company/{document_id}/download/locked",
    summary="Download LOCKED per-company report PDF (owner only)",
)
async def download_company_report_locked_pdf(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Compile the per-company report and stream LOCKED (AES-256) bytes, encrypted with the
    same revealable session report password.
    """
    user_id = str(current_user.id)
    pdf = await report_service.get_company_report_pdf_locked_async(
        session_id=session_id, user_id=user_id, document_id=document_id
    )
    filename = f"FinSentry_CompanyReport_LOCKED_{document_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/reports/{report_id}/download",
    summary="Download UNLOCKED report PDF (owner only)",
)
async def download_report_pdf(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Normal download: returns the UNLOCKED report PDF. The canonical persisted artifact is the
    AES-256 encrypted PDF; this endpoint decrypts it IN MEMORY (server-side protected password)
    and streams unlocked bytes to the authenticated owner. Unlocked bytes are NEVER persisted.
    """
    user_id = str(current_user.id)
    try:
        unlocked = await report_service.get_report_unlocked_bytes_async(
            session_id=session_id, user_id=user_id, report_id=report_id
        )
    except Exception as exc:
        logger.error("Failed to prepare unlocked report PDF: %s", type(exc).__name__)
        raise
    filename = f"FinSentry_Report_{session_id[:8]}_{report_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(unlocked),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/reports/{report_id}/download/locked",
    summary="Download LOCKED (password-protected AES-256) report PDF (owner only)",
)
async def download_report_locked_pdf(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Locked download: returns the persisted ENCRYPTED bytes directly (never decrypted).
    Byte-identical to the email attachment.
    """
    user_id = str(current_user.id)
    encrypted = await report_service.get_report_locked_bytes_async(
        session_id=session_id, user_id=user_id, report_id=report_id
    )
    filename = f"FinSentry_Report_LOCKED_{session_id[:8]}_{report_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(encrypted),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
