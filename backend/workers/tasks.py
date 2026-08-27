"""
Celery asynchronous task definitions for FinSentry AI.

All agent tasks execute here in the worker process, updating MongoDB with
persistent job status transitions and emitting structured sanitized logs.
"""

import concurrent.futures
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


from celery import Task
from celery.utils.log import get_task_logger

import crew                                                                
from agents.base import AgentResult
from agents.registry import agent_registry
from core.config import get_settings
from core.constants import AgentTaskType, JobStatus
from core.exceptions import (
    AgentNotFoundException,
    AgentTimeoutException,
    NonRetryableAgentException,
    RetryableAgentException,
)
from core.logging import log_agent_event
from database.connection import get_sync_db
from workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="workers.tasks.orchestrate_crew_pipeline", bind=True)
def orchestrate_crew_pipeline(
    self: Task,
    job_id: str,
    session_id: str,
    document_id: str,
    user_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Celery task orchestrating the full multi-agent CrewAI pipeline:
    DocumentAgent -> ExtractionAgent -> RedFlagAgent (proactive) -> MongoDB.
    """
    full_payload = dict(payload or {})
    full_payload.update({
        "session_id": session_id,
        "document_id": document_id,
        "user_id": user_id,
    })
    return execute_agent_task(
        job_id=job_id,
        agent_name="CrewOrchestrator",
        task_type=AgentTaskType.DOCUMENT_ANALYSIS.value,
        payload=full_payload,
        user_id=user_id,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


@celery_app.task(name="workers.tasks.health_task", bind=True)

def health_task(self: Task, x: int, y: int) -> int:
    """
    Trivial arithmetic task to verify Celery broker/worker round-trip.
    """
    logger.info("Health task executed: %s + %s", x, y)
    return x + y


def _update_job_in_db(job_id: str, update_fields: Dict[str, Any]) -> None:
    """
    Persist job status transition to MongoDB using the synchronous client.
    """
    try:
        db = get_sync_db()
        db.jobs.update_one({"job_id": job_id}, {"$set": update_fields})
    except Exception as exc:
        logger.error("Failed to update job %s in MongoDB: %s", job_id, exc)


@celery_app.task(
    name="workers.tasks.execute_agent_task",
    bind=True,
    max_retries=None,                                      
)
def execute_agent_task(
    self: Task,
    job_id: str,
    agent_name: str,
    task_type: str = AgentTaskType.DUMMY_TASK.value,
    payload: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generic agent task executor.

    Orchestrates agent lookup, central timeout, exponential backoff retries,
    MongoDB state updates, and structured sanitized logging.
    """
    settings = get_settings()
    payload = payload or {}
    effective_timeout = timeout_seconds or settings.AGENT_DEFAULT_TIMEOUT_SECONDS
    effective_max_retries = (
        max_retries if max_retries is not None else settings.AGENT_MAX_RETRIES
    )
    base_backoff = settings.AGENT_RETRY_BACKOFF_SECONDS
    current_retry = getattr(getattr(self, "request", None), "retries", 0) or 0

    start_time = time.time()
    now_utc = datetime.now(timezone.utc)
    document_id = payload.get("document_id")
    model_name = payload.get("model") or settings.DEFAULT_LLM_PROVIDER

                                                                
    _update_job_in_db(
        job_id,
        {
            "status": JobStatus.PROCESSING.value,
            "started_at": now_utc,
            "retry_count": current_retry,
        },
    )

    log_agent_event(
        logger,
        logging.INFO,
        f"Starting agent task '{task_type}' with agent '{agent_name}' (retry {current_retry}/{effective_max_retries})",
        job_id=job_id,
        agent_name=agent_name,
        task_type=task_type,
        document_id=document_id,
        user_id=user_id,
        session_id=session_id,
        started_at=now_utc.isoformat(),
        status=JobStatus.PROCESSING.value,
        model=model_name,
        retry_count=current_retry,
        worker_id=getattr(getattr(self, "request", None), "hostname", "worker"),
    )

    try:
                                       
        agent = agent_registry.get(agent_name)

                                                           
        context = {
            "job_id": job_id,
            "user_id": user_id,
            "session_id": session_id,
            "document_id": document_id,
            "retry_count": current_retry,
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(agent.execute, payload, context)
            try:
                result: AgentResult = future.result(timeout=float(effective_timeout))
            except concurrent.futures.TimeoutError:
                raise AgentTimeoutException(
                    f"Agent '{agent_name}' timed out after exceeding execution limit of {effective_timeout}s."
                )

                                                               
        latency_ms = (time.time() - start_time) * 1000
        completed_at = datetime.now(timezone.utc)

        _update_job_in_db(
            job_id,
            {
                "status": JobStatus.COMPLETED.value,
                "completed_at": completed_at,
                "result_summary": result.summary,
                "result_ref": result.result_ref,
                "error": None,
            },
        )

        log_agent_event(
            logger,
            logging.INFO,
            f"Agent task '{task_type}' completed successfully in {latency_ms:.2f}ms",
            job_id=job_id,
            agent_name=agent_name,
            task_type=task_type,
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            started_at=now_utc.isoformat(),
            completed_at=completed_at.isoformat(),
            status=JobStatus.COMPLETED.value,
            latency=latency_ms / 1000.0,
            latency_ms=latency_ms,
            model=model_name,
            retry_count=current_retry,
            worker_id=self.request.hostname,
        )

        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "success": True,
            "summary": result.summary,
            "result_ref": result.result_ref,
        }

    except RetryableAgentException as exc:
        latency_ms = (time.time() - start_time) * 1000
        logger.warning("Retryable agent error in job %s: %s", job_id, exc)

        if current_retry < effective_max_retries:
            next_retry = current_retry + 1
            countdown = base_backoff * (2**current_retry)

            _update_job_in_db(
                job_id,
                {
                    "retry_count": next_retry,
                    "error": f"Retrying ({next_retry}/{effective_max_retries}): {str(exc)}",
                },
            )

            log_agent_event(
                logger,
                logging.WARNING,
                f"Transient failure; scheduling retry {next_retry}/{effective_max_retries} in {countdown:.1f}s",
                job_id=job_id,
                agent_name=agent_name,
                task_type=task_type,
                document_id=document_id,
                user_id=user_id,
                session_id=session_id,
                started_at=now_utc.isoformat(),
                status=JobStatus.PROCESSING.value,
                latency=latency_ms / 1000.0,
                latency_ms=latency_ms,
                model=model_name,
                retry_count=next_retry,
                error=str(exc),
                worker_id=self.request.hostname,
            )

            raise self.retry(countdown=countdown, exc=exc, max_retries=effective_max_retries)

                                                  
        completed_at = datetime.now(timezone.utc)
        error_msg = f"Max retries ({effective_max_retries}) exceeded: {str(exc)}"

        _update_job_in_db(
            job_id,
            {
                "status": JobStatus.FAILED.value,
                "completed_at": completed_at,
                "error": error_msg,
            },
        )

        log_agent_event(
            logger,
            logging.ERROR,
            f"Agent task permanently failed after {effective_max_retries} retries: {error_msg}",
            job_id=job_id,
            agent_name=agent_name,
            task_type=task_type,
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            started_at=now_utc.isoformat(),
            completed_at=completed_at.isoformat(),
            status=JobStatus.FAILED.value,
            latency=latency_ms / 1000.0,
            latency_ms=latency_ms,
            model=model_name,
            retry_count=current_retry,
            error=error_msg,
            worker_id=self.request.hostname,
        )

        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "success": False,
            "error": error_msg,
        }

    except (NonRetryableAgentException, AgentNotFoundException, AgentTimeoutException, Exception) as exc:
        latency_ms = (time.time() - start_time) * 1000
        completed_at = datetime.now(timezone.utc)
        error_msg = str(exc)

        _update_job_in_db(
            job_id,
            {
                "status": JobStatus.FAILED.value,
                "completed_at": completed_at,
                "error": error_msg,
            },
        )

        log_agent_event(
            logger,
            logging.ERROR,
            f"Agent task failed non-retryably: {error_msg}",
            job_id=job_id,
            agent_name=agent_name,
            task_type=task_type,
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            started_at=now_utc.isoformat(),
            completed_at=completed_at.isoformat(),
            status=JobStatus.FAILED.value,
            latency=latency_ms / 1000.0,
            latency_ms=latency_ms,
            model=model_name,
            retry_count=current_retry,
            error=error_msg,
            worker_id=self.request.hostname,
        )

        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "success": False,
            "error": error_msg,
        }
