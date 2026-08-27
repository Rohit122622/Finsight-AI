"""
FinSentry AI — Deployment Health Checks (Phase 2H).

Provides deep readiness and liveness probes that verify all
infrastructure dependencies: MongoDB, Redis, Celery workers.

Endpoints:
    GET /api/v1/health           → Lightweight liveness probe (exists in main.py)
    GET /api/v1/health/ready     → Deep readiness probe (all dependencies)
    GET /api/v1/health/info      → Build/version metadata
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from core.config import get_settings
from database.connection import mongodb
from database.redis_client import redis_manager

logger = logging.getLogger(__name__)

router = APIRouter()


_BOOT_TIME = datetime.now(timezone.utc)


@router.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    """
    Deep readiness probe — verifies MongoDB, Redis, and reports component status.

    Returns HTTP 200 with status="ready" when all dependencies are healthy.
    Returns HTTP 200 with status="degraded" when some dependencies are unavailable.
    The caller (load balancer, orchestrator) can decide whether to route traffic.
    """
    checks: dict = {}
    overall_healthy = True


    try:
        db = mongodb.get_db()
        start = time.monotonic()
        await db.command("ping")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        checks["mongodb"] = {
            "status": "healthy",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        overall_healthy = False
        checks["mongodb"] = {
            "status": "unhealthy",
            "error": str(exc),
        }


    try:
        start = time.monotonic()
        redis_alive = redis_manager.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        checks["redis"] = {
            "status": "healthy" if redis_alive else "unhealthy",
            "latency_ms": latency_ms,
        }
        if not redis_alive:
            overall_healthy = False
    except Exception as exc:
        overall_healthy = False
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(exc),
        }


    try:
        from workers.celery_app import celery_app as _celery
        inspector = _celery.control.inspect(timeout=3.0)
        ping_resp = inspector.ping()
        worker_count = len(ping_resp) if ping_resp else 0
        checks["celery_workers"] = {
            "status": "healthy" if worker_count > 0 else "no_workers",
            "active_workers": worker_count,
        }
        if worker_count == 0:

            checks["celery_workers"]["status"] = "degraded"
    except Exception as exc:
        checks["celery_workers"] = {
            "status": "degraded",
            "error": str(exc),
        }


    uptime_seconds = round((datetime.now(timezone.utc) - _BOOT_TIME).total_seconds(), 1)

    return {
        "status": "ready" if overall_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }


@router.get("/health/info", tags=["health"])
async def build_info() -> dict:
    """
    Return build and version metadata for deployment tracking.
    """
    settings = get_settings()
    import os

    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": os.environ.get("APP_ENV", "development"),
        "python_version": _get_python_version(),
        "boot_time": _BOOT_TIME.isoformat(),
        "uptime_seconds": round(
            (datetime.now(timezone.utc) - _BOOT_TIME).total_seconds(), 1
        ),
    }


def _get_python_version() -> str:
    """Return the running Python version string."""
    import sys
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
