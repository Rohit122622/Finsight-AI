"""
Phase 8 worker-drill entry (TEST HARNESS ONLY — not application code).

Boots the project's REAL Celery app (workers.celery_app) but:
  * points the broker/result backend at the ISOLATED test Redis (host port 6380) via REDIS_PORT,
  * lowers the Redis visibility_timeout so a message left unacked by a killed worker is
    redelivered to the restarted worker within seconds (default is 3600s),
  * runs a single-task solo pool so a hard kill cleanly simulates a worker crash.

The application's task code, agents, acks_late / reject_on_worker_lost settings are all unchanged.
"""

import os
import sys
from pathlib import Path

os.environ.pop("DEBUG", None)
os.environ["REDIS_PORT"] = "6380"  # isolated test Redis

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from workers.celery_app import celery_app  # noqa: E402  (self-registers agents + tasks)

# NOTE: core.config runs load_dotenv(override=True), which clobbers REDIS_PORT back to the
# .env value (6379). So we cannot rely on the env var — pin the broker/backend explicitly to
# the ISOLATED test Redis on 6380.
_ISOLATED = "redis://localhost:6380/0"
celery_app.conf.broker_url = _ISOLATED
celery_app.conf.result_backend = _ISOLATED
# visibility_timeout MUST exceed the longest task so a healthy worker never redelivers its own
# in-flight message. After a crash, the unacked message is restored ~visibility_timeout later.
celery_app.conf.broker_transport_options = {"visibility_timeout": 30}
celery_app.conf.result_backend_transport_options = {"visibility_timeout": 30}

if __name__ == "__main__":
    celery_app.worker_main(
        [
            "worker",
            "--pool=solo",
            "-c", "1",
            "--loglevel=info",
            "-n", "phase8drill@%h",
            "--without-gossip",
            "--without-mingle",
        ]
    )
