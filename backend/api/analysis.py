"""
FastAPI router for Live Multi-Agent Financial Analysis and Reporting (Phase 2G).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from core.exceptions import (
    DocumentNotFoundException,
    JobNotFoundException,
    UnauthorizedDocumentAccessException,
    UnauthorizedJobAccessException,
)
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.job import JobResponse
from schemas.report import (
    AnalysisReportListResponse,
    AnalysisReportResponse,
    AnalysisRequest,
    LiveProgressResponse,
    RedFlagItemResponse,
)
from services.job_service import job_service
from services.live_analysis_service import live_analysis_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/analyze",
    summary="Trigger live multi-agent financial analysis pipeline",
    response_model=Any,
    status_code=status.HTTP_200_OK,
)
async def trigger_live_analysis(
    session_id: str = Path(..., description="Research session ID"),
    request: AnalysisRequest = AnalysisRequest(),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Trigger end-to-end multi-agent financial analysis across session documents.

    If async_mode is True (default), enqueues a Celery job and returns HTTP 202 with JobResponse.
    If async_mode is False, runs synchronously and returns full AnalysisReportResponse.
    """
    user_id = str(current_user.id)

    if request.async_mode:
        job = await live_analysis_service.run_live_analysis_async(
            session_id=session_id,
            user_id=user_id,
            query=request.query,
            focus_areas=request.focus_areas,
            report_title=request.report_title,
            baseline_entity=request.baseline_entity,
            comparison_entity=request.comparison_entity,
        )
        return job


    report = live_analysis_service.run_live_analysis_sync(
        session_id=session_id,
        user_id=user_id,
        query=request.query,
        focus_areas=request.focus_areas,
        report_title=request.report_title,
        baseline_entity=request.baseline_entity,
        comparison_entity=request.comparison_entity,
    )
    return report


@router.get(
    "/reports",
    response_model=AnalysisReportListResponse,
    summary="List all generated analysis reports for a session",
)
async def list_reports(
    session_id: str = Path(..., description="Research session ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve a paginated list of all analysis reports generated for this session.
    """
    reports, total = await live_analysis_service.list_reports(
        user_id=str(current_user.id),
        session_id=session_id,
        skip=skip,
        limit=limit,
    )
    return AnalysisReportListResponse(
        reports=[AnalysisReportResponse(**r.to_dict()) for r in reports],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/reports/{report_id}",
    response_model=AnalysisReportResponse,
    summary="Retrieve full generated analysis report",
)
async def get_report(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve complete analysis report including executive summary, red flags, metrics, and sections.
    """
    try:
        report = await live_analysis_service.get_report(
            report_id=report_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        return report
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this report is forbidden.",
        )


@router.delete(
    "/reports/{report_id}",
    summary="Delete an analysis report",
)
async def delete_report(
    session_id: str = Path(..., description="Research session ID"),
    report_id: str = Path(..., description="Report UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Delete an analysis report record from the database.
    """
    try:
        await live_analysis_service.delete_report(
            report_id=report_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        return {"success": True, "message": f"Report '{report_id}' deleted successfully."}
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this report is forbidden.",
        )


@router.get(
    "/red-flags",
    response_model=Dict[str, Any],
    summary="Retrieve structured RedFlagResult with lifecycle status for a session",
)
@router.get(
    "/analysis/red-flags",
    response_model=Dict[str, Any],
    summary="Retrieve structured RedFlagResult with lifecycle status for a session",
)
async def get_session_red_flags_structured(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve structured RedFlagResult with lifecycle status for the current session.
    Status: NOT_RUN | RUNNING | COMPLETED_WITH_FLAGS | COMPLETED_NO_FLAGS | FAILED
    """
    flags_data = await live_analysis_service.get_session_red_flags(
        user_id=str(current_user.id),
        session_id=session_id,
    )
    return flags_data


@router.get(
    "/progress/{job_id}",
    response_model=LiveProgressResponse,
    summary="Get real-time live progress for an analysis job by progress endpoint",
)
@router.get(
    "/jobs/{job_id}/live",
    response_model=LiveProgressResponse,
    summary="Get real-time live progress for an analysis job",
)
async def get_live_job_progress(
    session_id: str = Path(..., description="Research session ID"),
    job_id: str = Path(..., description="Job UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Get live progress milestone percentages and audit event logs for an active job.
    Supports both /progress/{job_id} and /jobs/{job_id}/live with strict session verification.
    """
    try:
        job = await job_service.get_job_by_id(job_id=job_id, user_id=str(current_user.id))


        if job.session_id and job.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job does not belong to the requested research session.",
            )

        elapsed = 0.0
        if job.started_at:
            from datetime import datetime, timezone
            start_dt = job.started_at
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)

            end_dt = job.completed_at
            if end_dt is not None:
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            else:
                end_dt = datetime.now(timezone.utc)

            elapsed = max(0.0, (end_dt - start_dt).total_seconds())


        last_msg = job.events[-1].get("message") if job.events else None

        return LiveProgressResponse(
            job_id=job.job_id,
            session_id=job.session_id or session_id,
            task_type=job.task_type,
            agent_name=job.agent_name,
            status=job.status,
            progress_percent=job.progress_percent,
            current_step=job.current_step,
            message=last_msg,
            events=job.events,
            elapsed_seconds=elapsed,
            result_ref=job.result_ref,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except JobNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    except UnauthorizedJobAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this job is forbidden.",
        )
