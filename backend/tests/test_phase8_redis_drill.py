"""
FinSentry AI — Phase 8 GENUINE Redis Recovery Drill

Runs against an ISOLATED test Redis container (finsentry-redis-test on host port 6380),
NOT the shared finsentry-redis (6379) and NOT any production instance.

Drill:
  Redis running -> verify connection -> cache + queue op -> stop Redis (docker stop)
  -> verify failure behavior -> restart Redis (docker start) -> verify reconnection
  -> verify application/data state after recovery.

Only isolated test keys are used and they are deleted at the end.
"""

import json
import subprocess
import sys
import time

import redis

PORT = 6380
CONTAINER = "finsentry-redis-test"
CACHE_KEY = "phase8:cache:key"
QUEUE_KEY = "phase8:queue"
POST_KEY = "phase8:post"


def dcmd(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def main():
    steps = {}

    # ---- 1. Redis running -> verify connection ----
    r = redis.Redis(host="localhost", port=PORT, socket_connect_timeout=5, socket_timeout=5)
    steps["1_ping_initial"] = bool(r.ping())

    # ---- 2. Perform cache + queue operations ----
    r.set(CACHE_KEY, "hello-recovery")
    r.delete(QUEUE_KEY)
    r.rpush(QUEUE_KEY, "job1", "job2", "job3")
    steps["2_cache_set_ok"] = r.get(CACHE_KEY) == b"hello-recovery"
    steps["2_queue_len"] = r.llen(QUEUE_KEY)
    # Force an RDB snapshot so a container restart can restore state
    try:
        r.save()
        steps["2_rdb_saved"] = True
    except Exception as exc:  # noqa: BLE001
        steps["2_rdb_saved"] = f"err:{type(exc).__name__}"

    # ---- 3. Stop Redis (genuine container stop) ----
    stop = dcmd("stop", CONTAINER)
    steps["3_docker_stop_rc"] = stop.returncode
    steps["3_docker_stop_out"] = (stop.stdout or stop.stderr).strip()
    time.sleep(2)

    # ---- 4. Verify failure behavior ----
    failure_observed = False
    failure_error = ""
    try:
        rf = redis.Redis(host="localhost", port=PORT, socket_connect_timeout=3, socket_timeout=3)
        rf.ping()
    except Exception as exc:  # noqa: BLE001 - expected genuine failure
        failure_observed = True
        failure_error = type(exc).__name__
    steps["4_failure_observed"] = failure_observed
    steps["4_failure_error"] = failure_error

    # ---- 5. Restart Redis (genuine container start) -> verify reconnection ----
    start = dcmd("start", CONTAINER)
    steps["5_docker_start_rc"] = start.returncode
    reconnected = False
    for _ in range(30):
        try:
            rr = redis.Redis(host="localhost", port=PORT, socket_connect_timeout=2, socket_timeout=2)
            if rr.ping():
                reconnected = True
                break
        except Exception:
            time.sleep(1)
    steps["5_reconnected"] = reconnected

    # ---- 6. Verify application/data state after recovery ----
    val = None
    qlen = None
    post_write_ok = False
    if reconnected:
        r4 = redis.Redis(host="localhost", port=PORT, socket_connect_timeout=5, socket_timeout=5)
        try:
            val = r4.get(CACHE_KEY)
            qlen = r4.llen(QUEUE_KEY)
            # Verify Redis is fully operational for NEW work after recovery
            r4.set(POST_KEY, "ok")
            post_write_ok = r4.get(POST_KEY) == b"ok"
        except Exception as exc:  # noqa: BLE001
            steps["6_post_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                r4.delete(CACHE_KEY, QUEUE_KEY, POST_KEY)
            except Exception:
                pass

    steps["6_cache_after_restart"] = val.decode() if val else None
    steps["6_queue_len_after_restart"] = qlen
    steps["6_new_write_after_restart_ok"] = post_write_ok

    # ---- Verdict ----
    passed = (
        steps.get("1_ping_initial")
        and steps.get("2_cache_set_ok")
        and steps.get("2_queue_len") == 3
        and steps.get("4_failure_observed")
        and steps.get("5_reconnected")
        and steps.get("6_new_write_after_restart_ok")
    )
    data_persisted = steps.get("6_cache_after_restart") == "hello-recovery" and steps.get("6_queue_len_after_restart") == 3

    print("=" * 72)
    print(" PHASE 8 — GENUINE REDIS RECOVERY DRILL (isolated container :6380)")
    print("=" * 72)
    for k, v in steps.items():
        print(f"  {k:<32} = {v}")
    print("-" * 72)
    print(f"  VERDICT: {'PASS' if passed else 'FAIL'}")
    print(f"  Data persisted across restart (RDB): {data_persisted}")
    print("=" * 72)
    print(json.dumps({"redis_drill": {"steps": steps, "passed": bool(passed), "data_persisted": bool(data_persisted)}}, indent=2, default=str))

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
