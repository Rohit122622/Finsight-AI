"""
FinSentry AI — Phase 8 GENUINE Backup & Recovery Tests

Unlike test_backup_recovery.py (which uses unittest.mock patches), this module performs
REAL operations against the infrastructure that is actually available in this environment:

  8A MongoDB  : REAL writes/reads to Atlas in an ISOLATED test collection (_phase8_recovery_test),
                real client close (failure), real reconnect (recovery), real data-survival check.
                NON-DESTRUCTIVE: only touches its own throwaway collection.
  8C Storage  : REAL file I/O against the local-disk storage backend that is actually in use
                (no R2 credentials configured -> R2StorageService falls back to .storage on disk).
                Real file delete (failure) + restore-from-backup (recovery) + real read verify.
  8B Redis    : REAL TCP probe of localhost:6379. Redis is genuinely unavailable and cannot be
                started here (no binary, Docker daemon down) -> recovery = NOT MEASURED.
  8E Worker   : REAL dispatch via job_service against REAL MongoDB with a genuinely-down broker.
                Verifies real broker-failure handling (job -> FAILED + BrokerUnavailableException).
                Worker restart/resume requires a live broker+worker -> that portion = NOT MEASURED.

DO NOT DESTROY PRODUCTION DATA. All tests use isolated keys/collections and clean up after themselves.
"""

import asyncio
import json
import shutil
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

TEST_COLLECTION = "_phase8_recovery_test"
results: List[Dict[str, Any]] = []


def _emit(test_id, name, failure_simulated, recovery_action, data_verified, status, details):
    entry = {
        "test_id": test_id,
        "test_name": name,
        "failure_simulated": failure_simulated,
        "recovery_action": recovery_action,
        "data_verified_afterward": data_verified,
        "status": status,  # PASS | FAIL | NOT MEASURED
        "details": details,
    }
    results.append(entry)
    print(f"\n  [{status}] {test_id}: {name}")
    print(f"    Failure simulated : {failure_simulated}")
    print(f"    Recovery action   : {recovery_action}")
    print(f"    Data verified     : {data_verified}")
    print(f"    Details           : {details}")


# ==============================================================================
# 8A + 8D: MongoDB / Database — GENUINE (real Atlas, isolated collection)
# ==============================================================================

async def _mongodb_genuine() -> None:
    from database.connection import mongodb

    marker = f"recovery-{uuid.uuid4()}"
    doc = {"_id": marker, "value": 424242, "created": datetime.now(timezone.utc).isoformat()}

    # --- Establish real connection to Atlas ---
    await mongodb.connect()
    db = mongodb.get_db()
    coll = db[TEST_COLLECTION]

    # --- REAL write + read (proves live connectivity & persistence) ---
    await coll.delete_many({"_id": marker})
    await coll.insert_one(doc)
    before = await coll.find_one({"_id": marker})
    wrote_ok = before is not None and before.get("value") == 424242

    if not wrote_ok:
        _emit("8A/8D", "MongoDB / Database Recovery (REAL Atlas)",
              failure_simulated="n/a", recovery_action="n/a", data_verified=False,
              status="FAIL", details="Could not perform initial real write/read to Atlas test collection.")
        return

    # --- SIMULATE FAILURE: close the real client mid-session (connection loss) ---
    old_db = mongodb._database  # capture handle bound to the client we are about to close
    await mongodb.disconnect()  # real close of the Motor client + pool

    failure_observed = False
    failure_detail = ""
    try:
        # Operating on the handle whose client was just closed must fail.
        await old_db[TEST_COLLECTION].find_one({"_id": marker})
    except Exception as exc:  # noqa: BLE001 - we WANT to observe the real failure
        failure_observed = True
        failure_detail = f"{type(exc).__name__}"

    # --- RECOVERY: get_db() triggers a real reconnection to Atlas ---
    new_db = mongodb.get_db()  # reconnection logic builds a fresh client
    recovered = await new_db[TEST_COLLECTION].find_one({"_id": marker})
    data_survived = recovered is not None and recovered.get("value") == 424242
    client_is_new = new_db is not old_db

    # --- Cleanup: remove the throwaway document + drop the isolated collection ---
    try:
        await new_db[TEST_COLLECTION].delete_many({"_id": marker})
        await new_db[TEST_COLLECTION].drop()
    except Exception:
        pass

    passed = wrote_ok and failure_observed and data_survived and client_is_new
    _emit(
        "8A/8D", "MongoDB / Database Recovery (REAL Atlas)",
        failure_simulated=f"Closed live Motor client mid-session; post-close op raised {failure_detail or 'no error'}",
        recovery_action="Called get_db() which built a NEW client and reconnected to Atlas",
        data_verified=f"Document with value=424242 re-read successfully after reconnect: {data_survived}",
        status="PASS" if passed else "FAIL",
        details=(f"real_write={wrote_ok}, failure_observed={failure_observed}, "
                 f"reconnected_new_client={client_is_new}, data_survived_outage={data_survived}. "
                 f"Isolated collection '{TEST_COLLECTION}' dropped after test (non-destructive)."),
    )

    await mongodb.disconnect()


def test_8a_mongodb():
    try:
        asyncio.run(_mongodb_genuine())
    except Exception as exc:  # noqa: BLE001
        _emit("8A/8D", "MongoDB / Database Recovery (REAL Atlas)",
              failure_simulated="n/a", recovery_action="n/a", data_verified=False,
              status="FAIL", details=f"Unexpected error: {type(exc).__name__}: {exc}")


# ==============================================================================
# 8C: Storage / R2 — GENUINE (real local-disk backend actually in use)
# ==============================================================================

def test_8c_storage():
    try:
        from services.r2_storage_service import R2StorageService

        key = f"users/_phase8_test/documents/recovery_{uuid.uuid4().hex}.bin"
        payload = b"PHASE8-REAL-STORAGE-RECOVERY-PAYLOAD-" + uuid.uuid4().bytes

        # Fresh instances (empty in-memory cache) force genuine disk reads.
        writer = R2StorageService()
        writer.upload_bytes(key, payload, "application/octet-stream")

        disk_path = writer._get_disk_path(key)
        on_disk_after_write = disk_path.exists()

        # Verify a DIFFERENT fresh instance reads the real file from disk (cross-instance persistence)
        reader = R2StorageService()
        read_back = reader.get_bytes(key)
        write_ok = on_disk_after_write and read_back == payload

        # --- Backup the real file (simulates a backup snapshot) ---
        backup_path = disk_path.with_suffix(disk_path.suffix + ".bak")
        shutil.copy2(disk_path, backup_path)

        # --- SIMULATE FAILURE: delete the real file from disk (data loss) ---
        disk_path.unlink()
        failure_observed = False
        failure_detail = ""
        probe = R2StorageService()  # empty cache -> must hit disk
        try:
            probe.get_bytes(key)
        except Exception as exc:  # noqa: BLE001 - expected genuine failure
            failure_observed = True
            failure_detail = type(exc).__name__

        # --- RECOVERY: restore the file from the backup snapshot ---
        shutil.copy2(backup_path, disk_path)
        restorer = R2StorageService()  # empty cache -> reads restored file from disk
        recovered = restorer.get_bytes(key)
        data_survived = recovered == payload

        # --- Cleanup ---
        try:
            disk_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
        except Exception:
            pass

        passed = write_ok and failure_observed and data_survived
        _emit(
            "8C", "R2 / Storage Recovery (REAL local-disk backend)",
            failure_simulated=f"Deleted the real file from disk; fresh-instance read raised {failure_detail or 'no error'}",
            recovery_action="Restored file from backup snapshot on disk",
            data_verified=f"Byte-for-byte payload re-read from disk after restore: {data_survived}",
            status="PASS" if passed else "FAIL",
            details=(f"real_disk_write={on_disk_after_write}, cross_instance_read={write_ok}, "
                     f"failure_observed={failure_observed}, data_survived={data_survived}. "
                     f"NOTE: R2 credentials are not configured, so the app genuinely uses the "
                     f"local-disk fallback (.storage) — that IS the storage backend under test."),
        )
    except Exception as exc:  # noqa: BLE001
        _emit("8C", "R2 / Storage Recovery (REAL local-disk backend)",
              failure_simulated="n/a", recovery_action="n/a", data_verified=False,
              status="FAIL", details=f"Unexpected error: {type(exc).__name__}: {exc}")


# ==============================================================================
# 8B: Redis — GENUINE probe; cannot restart here -> NOT MEASURED
# ==============================================================================

def test_8b_redis():
    from core.config import get_settings
    settings = get_settings()
    host, port = settings.REDIS_HOST, settings.REDIS_PORT

    reachable = False
    probe_detail = ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((host, port))
        reachable = True
    except Exception as exc:  # noqa: BLE001
        probe_detail = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()

    if reachable:
        # If Redis is actually up we could do a genuine flush/restart cycle, but it is not
        # running in this environment.
        _emit("8B", "Redis Failure & Recovery",
              failure_simulated="n/a", recovery_action="n/a", data_verified="n/a",
              status="NOT MEASURED",
              details=f"Redis unexpectedly reachable at {host}:{port}; genuine restart cycle still not "
                      f"performed to avoid disrupting a shared service.")
    else:
        _emit(
            "8B", "Redis Failure & Recovery",
            failure_simulated=f"Real TCP probe to {host}:{port} — connection refused ({probe_detail})",
            recovery_action="NONE — no redis-server binary, no Redis service, Docker daemon not running; "
                            "a real Redis instance cannot be started/restarted in this environment",
            data_verified="n/a",
            status="NOT MEASURED",
            details="Redis is genuinely unavailable. A real failure->restart->recovery cycle is not "
                    "possible here. Reported honestly as NOT MEASURED.",
        )


# ==============================================================================
# 8E: Worker / Celery — GENUINE broker-failure handling; restart -> NOT MEASURED
# ==============================================================================

def _dispatch_blocking(user_id: str, box: dict) -> None:
    """Run the real async dispatch in its own event loop (executed inside a daemon thread).

    create_and_dispatch_job -> apply_async is a SYNCHRONOUS blocking call; when the broker is
    down, Celery/kombu blocks inside it. Running it in a thread lets the caller bound it with a
    hard join timeout, so the test process never hangs.
    """
    from services.job_service import JobService
    from database.connection import mongodb
    from core.constants import AgentTaskType
    from core.exceptions import BrokerUnavailableException

    async def _run():
        await mongodb.connect()
        try:
            db = mongodb.get_db()
            svc = JobService(db=db)
            await svc.create_and_dispatch_job(
                user_id=user_id,
                agent_name="DummyAgent",
                task_type=AgentTaskType.DUMMY_TASK.value,
                payload={"phase8": True},
            )
            box["raised"] = False
            box["raised_type"] = "none"
        except BrokerUnavailableException:
            box["raised"] = True
            box["raised_type"] = "BrokerUnavailableException"
        except Exception as exc:  # noqa: BLE001
            box["raised"] = True
            box["raised_type"] = type(exc).__name__
        finally:
            box["done"] = True
            await mongodb.disconnect()

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        box["raised"] = True
        box["raised_type"] = type(exc).__name__
        box["done"] = True


def test_8e_worker():
    import threading
    import agents.dummy_agent  # noqa: F401  (self-registers "DummyAgent")
    from workers.celery_app import celery_app
    from core.constants import JobStatus

    # Try to make the down-broker publish fail fast rather than retry.
    celery_app.conf.task_publish_retry = False
    celery_app.conf.broker_connection_retry = False
    celery_app.conf.broker_connection_retry_on_startup = False
    celery_app.conf.broker_connection_max_retries = 1
    celery_app.conf.broker_transport_options = {
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        "max_retries": 0,
    }

    user_id = "_phase8_worker_test_user"
    box: dict = {"done": False, "raised": None, "raised_type": None}

    t = threading.Thread(target=_dispatch_blocking, args=(user_id, box), daemon=True)
    t.start()
    t.join(timeout=25)
    publish_blocked = t.is_alive()  # still running after 25s => publish did not fail fast

    # Independently verify the REAL DB state (separate short-lived sync client, no event-loop clash).
    job_created = False
    job_failed = False
    job_id_seen = None
    latest_status = None
    try:
        from database.connection import get_sync_db
        sdb = get_sync_db()
        doc = sdb.jobs.find_one({"user_id": user_id}, sort=[("created_at", -1)])
        if doc:
            job_created = True
            job_id_seen = doc.get("job_id")
            latest_status = doc.get("status")
            job_failed = latest_status == JobStatus.FAILED.value
        # cleanup throwaway records
        sdb.jobs.delete_many({"user_id": user_id})
    except Exception as exc:  # noqa: BLE001
        latest_status = f"db-check-error:{type(exc).__name__}"

    raised = box.get("raised")
    raised_type = box.get("raised_type")

    if raised and job_failed:
        status = "PARTIAL"
        failure_desc = f"Real dispatch with broker genuinely down raised {raised_type}"
        recovery_desc = ("App marked the job FAILED in real MongoDB + surfaced the broker error. "
                         "Worker restart/resume = NOT MEASURED (no live broker/worker here).")
        data_desc = f"Job persisted then transitioned to FAILED in real DB (job_id={job_id_seen}): True"
        details = ("GENUINE broker-failure handling verified against real MongoDB with a genuinely-down "
                   "broker. Restart/resume half is NOT MEASURED (requires real Redis + Celery worker).")
    elif publish_blocked:
        status = "PARTIAL"
        failure_desc = ("Real dispatch attempted against genuinely-down broker (redis://localhost:6379); "
                        "Celery publish BLOCKED >25s instead of failing fast")
        recovery_desc = ("Job row was created in real MongoDB (status=%s). Broker retry/backoff means it had "
                         "not yet been marked FAILED when bounded. Worker restart/resume = NOT MEASURED."
                         % latest_status)
        data_desc = f"Job record created in real DB (job_id={job_id_seen}, status={latest_status}): {job_created}"
        details = ("GENUINE finding: with the broker genuinely unreachable, the synchronous Celery publish "
                   "blocks (retry/backoff) rather than failing instantly. Real MongoDB job row was created. "
                   "Full worker recovery (restart + resume) is NOT MEASURED — no real broker/worker available.")
    else:
        status = "FAIL"
        failure_desc = f"raised={raised} ({raised_type}), publish_blocked={publish_blocked}"
        recovery_desc = "unexpected"
        data_desc = f"job_created={job_created}, latest_status={latest_status}"
        details = "Unexpected outcome for broker-down dispatch."

    _emit("8E", "Worker / Celery Recovery", failure_desc, recovery_desc, data_desc, status, details)


def main():
    print("=" * 74)
    print(" FinSentry AI — Phase 8 GENUINE Backup & Recovery Testing")
    print("=" * 74)

    test_8a_mongodb()
    test_8c_storage()
    test_8b_redis()
    test_8e_worker()

    print("\n" + "=" * 74)
    print(" PHASE 8 GENUINE RECOVERY SUMMARY")
    print("=" * 74)
    for r in results:
        print(f"  {r['test_id']:<7} {r['test_name']:<48} -> {r['status']}")
    print("=" * 74)
    print(json.dumps({"results": results}, indent=2, default=str))


if __name__ == "__main__":
    main()
