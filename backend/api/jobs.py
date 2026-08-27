"""
FastAPI router for asynchronous agent job submission and status monitoring.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.exceptions import (
    AgentNotFoundException,
    BrokerUnavailableException,
    JobNotFoundException,
    UnauthorizedJobAccessException,
)
from database.redis_client import redis_manager
from middleware.auth_middleware import get_current_user
from models.user import UserModel
from schemas.job import JobCreateRequest, JobResponse, JobStatusResponse
from services.job_service import job_service
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an asynchronous agent job",
)
async def submit_job(
    request: JobCreateRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Enqueue an asynchronous agent job for Celery worker processing.

    Returns HTTP 503 if the message broker is offline; never executes synchronously.
    """
    try:
        job = await job_service.create_and_dispatch_job(
            user_id=str(current_user.id),
            agent_name=request.agent_name,
            task_type=request.task_type,
            payload=request.payload,
            session_id=request.session_id,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
        )
        return job
    except AgentNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except BrokerUnavailableException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Message broker unreachable: {exc.message}",
        )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Retrieve full job details",
)
async def get_job(
    job_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Query persistent job state and results in MongoDB. Enforces tenant ownership.
    """
    try:
        job = await job_service.get_job_by_id(job_id=job_id, user_id=str(current_user.id))
        return job
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


@router.get(
    "/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Lightweight job status poll",
)
async def get_job_status(
    job_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Lightweight endpoint for frontend status polling.
    """
    try:
        job = await job_service.get_job_by_id(job_id=job_id, user_id=str(current_user.id))
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            retry_count=job.retry_count,
            error=job.error,
            completed_at=job.completed_at,
            result_summary=job.result_summary,
            result_ref=job.result_ref,
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


@router.get(
    "",
    response_model=List[JobResponse],
    summary="List all jobs for current user",
)
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    List user-submitted jobs with pagination.
    """
    return await job_service.list_user_jobs(
        user_id=str(current_user.id), skip=skip, limit=limit
    )


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a running or queued job",
)
async def cancel_job(
    job_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Cancel a queued or in-progress job.
    """
    try:
        return await job_service.cancel_job(job_id=job_id, user_id=str(current_user.id))
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



@router.get(
    "/health/broker",
    summary="Check Redis message broker connectivity",
)
async def check_broker_health() -> Dict[str, Any]:
    """
    Diagnostic probe for Redis broker connectivity.
    """
    return redis_manager.get_health_status()


@router.get(
    "/health/workers",
    summary="Inspect active Celery worker heartbeats",
)
async def check_workers_health() -> Dict[str, Any]:
    """
    Ping Celery workers to detect active instances.
    """
    broker_healthy = redis_manager.ping()
    if not broker_healthy:
        return {
            "broker_connected": False,
            "workers_available": 0,
            "active_workers": [],
            "status": "broker_offline",
        }

    try:

        pong = celery_app.control.ping(timeout=1.0)
        active_workers = list(pong) if pong else []
        return {
            "broker_connected": True,
            "workers_available": len(active_workers),
            "active_workers": active_workers,
            "status": "healthy" if active_workers else "no_workers_online",
        }
    except Exception as exc:
        logger.warning("Celery worker ping failed: %s", exc)
        return {
            "broker_connected": True,
            "workers_available": 0,
            "active_workers": [],
            "status": f"ping_error: {exc}",
        }
