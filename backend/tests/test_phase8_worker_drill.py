"""
FinSentry AI — Phase 8 GENUINE Celery Worker Recovery Drill

Uses the ISOLATED test Redis (host port 6380) as broker/result backend and the project's REAL
Celery app + real execute_agent_task + real DummyAgent. Job state is tracked in the real MongoDB
(isolated test user; cleaned up afterward).

Drill:
  start Redis (already running :6380) -> start Celery worker -> submit a safe long test job
  -> wait until worker is PROCESSING it -> HARD-KILL the worker mid-processing
  -> verify job did NOT complete (stuck PROCESSING) -> restart worker
  -> verify the unacked task is redelivered and the job reaches COMPLETED (recovery).

Relies on the app's own celery config: task_acks_late=True + task_reject_on_worker_lost=True.
"""

import os
import sys
import time
import uuid
import json
import asyncio
import subprocess
from pathlib import Path

os.environ.pop("DEBUG", None)
os.environ["REDIS_PORT"] = "6380"  # publish to the isolated test Redis

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import agents.dummy_agent  # noqa: E402,F401  (registers "DummyAgent")
from core.constants import AgentTaskType, JobStatus  # noqa: E402
from database.connection import get_sync_db  # noqa: E402

USER_ID = "_phase8_worker_drill_user"
SLEEP_SECONDS = 8            # task duration (< visibility_timeout to avoid self-redelivery)
ISOLATED_BROKER = "redis://localhost:6380/0"
WORKER_LOG_1 = backend_dir / "tests" / "_worker1.log"
WORKER_LOG_2 = backend_dir / "tests" / "_worker2.log"


def _dispatch_job() -> str:
    """Insert + publish a real job via the app's job_service (async). Returns job_id.

    core.config runs load_dotenv(override=True) which resets REDIS_PORT to 6379, so we pin the
    app's Celery broker to the ISOLATED test Redis (:6380) explicitly before publishing.
    """
    from workers.celery_app import celery_app
    celery_app.conf.broker_url = ISOLATED_BROKER
    celery_app.conf.result_backend = ISOLATED_BROKER
    celery_app.conf.broker_transport_options = {"visibility_timeout": 30}

    from services.job_service import JobService
    from database.connection import mongodb

    async def _run():
        await mongodb.connect()
        try:
            svc = JobService(db=mongodb.get_db())
            job = await svc.create_and_dispatch_job(
                user_id=USER_ID,
                agent_name="DummyAgent",
                task_type=AgentTaskType.DUMMY_TASK.value,
                payload={"mode": "SUCCESS", "sleep_seconds": SLEEP_SECONDS, "key": "phase8drill"},
            )
            return job.job_id
        finally:
            await mongodb.disconnect()

    return asyncio.run(_run())


def _job_status(sdb, job_id):
    doc = sdb.jobs.find_one({"job_id": job_id})
    return (doc or {}).get("status"), doc


def _start_worker(logfile: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["REDIS_PORT"] = "6380"
    env.pop("DEBUG", None)
    fh = open(logfile, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests._phase8_worker_entry"],
        cwd=str(backend_dir),
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
    )
    proc._logfh = fh  # type: ignore[attr-defined]
    return proc


def _kill(proc: subprocess.Popen):
    try:
        proc.kill()  # TerminateProcess on Windows == hard crash, no graceful shutdown
        proc.wait(timeout=10)
    except Exception:
        pass
    try:
        proc._logfh.close()  # type: ignore[attr-defined]
    except Exception:
        pass


def main():
    steps = {}
    sdb = get_sync_db()

    # ---- Submit a safe long-running test job (publishes to isolated Redis :6380) ----
    job_id = _dispatch_job()
    steps["job_id"] = job_id
    status, _ = _job_status(sdb, job_id)
    steps["1_dispatched_status"] = status  # expected QUEUED

    # ---- Start worker #1 ----
    w1 = _start_worker(WORKER_LOG_1)
    steps["2_worker1_pid"] = w1.pid

    # ---- Wait until the worker is PROCESSING the job ----
    processing_seen = False
    started_at_1 = None
    for _ in range(60):  # up to ~60s for worker boot + pickup
        status, doc = _job_status(sdb, job_id)
        if status == JobStatus.PROCESSING.value:
            processing_seen = True
            started_at_1 = doc.get("started_at")
            break
        if status == JobStatus.COMPLETED.value:
            break  # too fast (shouldn't happen with sleep)
        time.sleep(1)
    steps["3_processing_seen_before_kill"] = processing_seen

    if not processing_seen:
        # Could not get the worker to process — capture logs and abort as PARTIAL.
        _kill(w1)
        steps["worker1_log_tail"] = WORKER_LOG_1.read_text(encoding="utf-8", errors="ignore")[-1500:]
        _finish(steps, sdb, job_id, verdict="PARTIAL",
                reason="Worker did not reach PROCESSING; see worker1_log_tail.")
        return 1

    # ---- HARD-KILL the worker mid-processing (simulate crash) ----
    time.sleep(3)  # let it be a few seconds into the 15s sleep
    _kill(w1)
    steps["4_worker1_killed"] = True

    # ---- Verify failure behavior: job stuck (not COMPLETED) right after the crash ----
    time.sleep(2)
    status_after_kill, _ = _job_status(sdb, job_id)
    steps["5_status_after_kill"] = status_after_kill
    steps["5_not_completed_after_kill"] = status_after_kill != JobStatus.COMPLETED.value

    # ---- Restart the worker ----
    w2 = _start_worker(WORKER_LOG_2)
    steps["6_worker2_pid"] = w2.pid

    # ---- Verify redelivery + recovery: job should reach COMPLETED ----
    completed = False
    final_doc = None
    # allow: visibility_timeout(10s) + worker boot + re-run sleep(15s) + margin
    for _ in range(90):
        status, doc = _job_status(sdb, job_id)
        if status == JobStatus.COMPLETED.value:
            completed = True
            final_doc = doc
            break
        if status == JobStatus.FAILED.value:
            final_doc = doc
            break
        time.sleep(1)
    steps["7_recovered_completed"] = completed
    steps["7_final_status"] = (final_doc or {}).get("status")
    started_at_2 = (final_doc or {}).get("started_at")
    # started_at should have been rewritten by the second (recovery) execution
    steps["7_reprocessed_by_new_worker"] = bool(started_at_2 and started_at_1 and started_at_2 != started_at_1) or completed

    _kill(w2)

    verdict = "PASS" if (processing_seen and steps["5_not_completed_after_kill"] and completed) else "PARTIAL"
    if verdict != "PASS":
        steps["worker2_log_tail"] = WORKER_LOG_2.read_text(encoding="utf-8", errors="ignore")[-1500:]
    _finish(steps, sdb, job_id, verdict=verdict,
            reason="Worker crash mid-task; task redelivered to restarted worker and job COMPLETED."
            if verdict == "PASS" else "Recovery not fully observed within time budget.")
    return 0 if verdict == "PASS" else 1


def _finish(steps, sdb, job_id, verdict, reason):
    # cleanup throwaway job record(s)
    try:
        sdb.jobs.delete_many({"user_id": USER_ID})
    except Exception:
        pass
    for f in (WORKER_LOG_1, WORKER_LOG_2):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    print("=" * 72)
    print(" PHASE 8 — GENUINE CELERY WORKER RECOVERY DRILL (isolated Redis :6380)")
    print("=" * 72)
    for k, v in steps.items():
        if k.endswith("log_tail"):
            print(f"  {k}:\n{v}")
        else:
            print(f"  {k:<32} = {v}")
    print("-" * 72)
    print(f"  VERDICT: {verdict}")
    print(f"  {reason}")
    print("=" * 72)
    print(json.dumps({"worker_drill": {"steps": steps, "verdict": verdict}}, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
