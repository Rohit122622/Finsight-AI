"""
JobService for asynchronous agent job creation, Celery dispatch, and status tracking.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from agents.registry import agent_registry
from core.config import get_settings
from core.constants import AgentTaskType, JobStatus
from core.exceptions import (
    AgentNotFoundException,
    BrokerUnavailableException,
    JobNotFoundException,
    UnauthorizedJobAccessException,
)
from database.connection import mongodb
from models.job import JobModel
from workers.celery_app import celery_app
from workers.tasks import execute_agent_task

logger = logging.getLogger(__name__)


class JobService:
    """
    Manages the lifecycle of asynchronous agent jobs from the FastAPI perspective.
    """

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db

    def _get_db(self) -> AsyncIOMotorDatabase:
        if self._db is not None:
            return self._db
        return mongodb.get_db()

    async def create_and_dispatch_job(
        self,
        user_id: str,
        agent_name: str,
        task_type: str = AgentTaskType.DUMMY_TASK.value,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> JobModel:
        """
        Create a job record in MongoDB and dispatch it to the Celery queue.

        If idempotency_key is provided and an active/completed job exists for this user,
        returns the existing job to prevent duplicate execution pipelines.

        If the Celery/Redis broker is unreachable, transitions the job to FAILED
        and raises BrokerUnavailableException. NEVER executes the task synchronously.
        """
        settings = get_settings()
                                              
        agent_registry.get(agent_name)

        db = self._get_db()

                                                                                          
        if idempotency_key:
            existing = await db.jobs.find_one({
                "user_id": user_id,
                "metadata.idempotency_key": idempotency_key,
                "status": {"$in": [JobStatus.QUEUED.value, JobStatus.PROCESSING.value, JobStatus.COMPLETED.value]},
            })
            if existing:
                logger.info(
                    "Idempotency hit for user %s, key %s: returning existing job %s",
                    user_id,
                    idempotency_key,
                    existing.get("job_id"),
                )
                return JobModel.from_mongo(existing)

        job_id = str(uuid.uuid4())
        effective_timeout = timeout_seconds or settings.AGENT_DEFAULT_TIMEOUT_SECONDS
        effective_max_retries = (
            max_retries if max_retries is not None else settings.AGENT_MAX_RETRIES
        )

        job_meta: Dict[str, Any] = {"submitted_payload_keys": list((payload or {}).keys())}
        if idempotency_key:
            job_meta["idempotency_key"] = idempotency_key

        job = JobModel(
            job_id=job_id,
            user_id=user_id,
            session_id=session_id,
            agent_name=agent_name,
            task_type=task_type,
            status=JobStatus.QUEUED.value,
            created_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=effective_max_retries,
            timeout_seconds=effective_timeout,
            metadata=job_meta,
        )

        await db.jobs.insert_one(job.to_dict())

                                      
        try:
            execute_agent_task.apply_async(
                kwargs={
                    "job_id": job_id,
                    "agent_name": agent_name,
                    "task_type": task_type,
                    "payload": payload or {},
                    "user_id": user_id,
                    "session_id": session_id,
                    "timeout_seconds": effective_timeout,
                    "max_retries": effective_max_retries,
                },
                task_id=job_id,
                retry=False,
            )
            logger.info("Dispatched job %s for agent '%s' to Celery", job_id, agent_name)
        except Exception as exc:
                                                                                       
            error_msg = f"Failed to dispatch to message broker: {exc}"
            logger.error(error_msg)
            await db.jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": JobStatus.FAILED.value,
                        "completed_at": datetime.now(timezone.utc),
                        "error": error_msg,
                    }
                },
            )
            raise BrokerUnavailableException(error_msg)

        return job

    async def get_job_by_id(self, job_id: str, user_id: str) -> JobModel:
        """
        Fetch a job by ID and verify user ownership.
        """
        db = self._get_db()
        doc = await db.jobs.find_one({"job_id": job_id})
        if not doc:
            raise JobNotFoundException(job_id)

        job = JobModel.from_mongo(doc)
        if job.user_id != user_id:
            logger.warning("User %s attempted unauthorized access to job %s", user_id, job_id)
            raise UnauthorizedJobAccessException()

        return job

    async def list_user_jobs(
        self, user_id: str, skip: int = 0, limit: int = 20
    ) -> List[JobModel]:
        """
        List jobs for a user with pagination.
        """
        db = self._get_db()
        cursor = (
            db.jobs.find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [JobModel.from_mongo(d) for d in docs]

    async def cancel_job(self, job_id: str, user_id: str) -> JobModel:
        """
        Cancel a queued or processing job.
        """
        job = await self.get_job_by_id(job_id, user_id)
        if job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
            return job

                          
        try:
            celery_app.control.revoke(job_id, terminate=True)
        except Exception as exc:
            logger.warning("Could not revoke Celery task %s: %s", job_id, exc)

        db = self._get_db()
        completed_at = datetime.now(timezone.utc)
        await db.jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": JobStatus.CANCELLED.value,
                    "completed_at": completed_at,
                    "error": "Job cancelled by user",
                }
            },
        )
        job.status = JobStatus.CANCELLED.value
        job.completed_at = completed_at
        job.error = "Job cancelled by user"
        return job

    async def update_job_progress(
        self,
        job_id: str,
        progress_percent: int,
        current_step: Optional[str] = None,
        event_message: Optional[str] = None,
    ) -> None:
        """Update job progress percentage and event log asynchronously."""
        db = self._get_db()
        update_fields: Dict[str, Any] = {
            "progress_percent": max(0, min(100, progress_percent)),
            "status": JobStatus.PROCESSING.value,
        }
        if current_step:
            update_fields["current_step"] = current_step

        update_op: Dict[str, Any] = {"$set": update_fields}
        if event_message:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step": current_step or "PROCESSING",
                "message": event_message,
            }
            update_op["$push"] = {"events": event}

        await db.jobs.update_one({"job_id": job_id}, update_op)

                                                                              
        try:
            job_doc = await db.jobs.find_one({"job_id": job_id}, {"session_id": 1})
            if job_doc and job_doc.get("session_id"):
                session_id = job_doc["session_id"]
                from services.event_bus import event_bus
                from services.websocket_manager import ws_manager
                event_bus.publish_job_progress(
                    session_id=session_id,
                    job_id=job_id,
                    progress_percent=progress_percent,
                    current_step=current_step or "PROCESSING",
                    status=JobStatus.PROCESSING.value,
                )
                await ws_manager.broadcast_to_session(
                    session_id=session_id,
                    message={
                        "type": "job_progress",
                        "session_id": session_id,
                        "payload": {
                            "job_id": job_id,
                            "progress_percent": max(0, min(100, progress_percent)),
                            "current_step": current_step or "PROCESSING",
                            "status": JobStatus.PROCESSING.value,
                            "message": event_message,
                        },
                    },
                )
        except Exception:
            pass

    @staticmethod
    def update_job_progress_sync(
        job_id: str,
        progress_percent: int,
        current_step: Optional[str] = None,
        event_message: Optional[str] = None,
    ) -> None:
        """Synchronous helper for Celery workers to record live progress without event loop collisions."""
        from database.connection import get_sync_db
        try:
            db = get_sync_db()
            update_fields: Dict[str, Any] = {
                "progress_percent": max(0, min(100, progress_percent)),
                "status": JobStatus.PROCESSING.value,
            }
            if current_step:
                update_fields["current_step"] = current_step

            update_op: Dict[str, Any] = {"$set": update_fields}
            if event_message:
                event = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "step": current_step or "PROCESSING",
                    "message": event_message,
                }
                update_op["$push"] = {"events": event}

            db.jobs.update_one({"job_id": job_id}, update_op)

                                                                                      
            try:
                job_doc = db.jobs.find_one({"job_id": job_id}, {"session_id": 1})
                if job_doc and job_doc.get("session_id"):
                    from services.event_bus import event_bus
                    event_bus.publish_job_progress(
                        session_id=job_doc["session_id"],
                        job_id=job_id,
                        progress_percent=progress_percent,
                        current_step=current_step or "PROCESSING",
                        status=JobStatus.PROCESSING.value,
                    )
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Failed to record sync progress for job %s: %s", job_id, exc)


job_service = JobService()
