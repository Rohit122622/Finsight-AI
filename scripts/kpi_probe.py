#!/usr/bin/env python
"""
FinSentry AI — Availability / health probe (Phase 7 KPI, PART I).

A lightweight, repeatable probe intended to be run on a schedule (cron / uptime
monitor) to BUILD a real uptime dataset over time. It does NOT itself claim any
uptime percentage — uptime must be derived from accumulated observations.

Usage:
    python scripts/kpi_probe.py                 # probe once, print JSON
    python scripts/kpi_probe.py --log           # also append a line to kpi_probe_history.jsonl
    PROBE_BASE_URL=https://api.example.com python scripts/kpi_probe.py

Components probed:
    * FastAPI health endpoint (liveness)
    * API availability (OpenAPI schema)
    * Redis (broker/cache) — if reachable
    * Celery worker — reported as MANUAL unless CELERY_INSPECT=1 (requires app import)

Environment:
    PROBE_BASE_URL     default http://127.0.0.1:8001
    PROBE_HEALTH_PATH  default /api/v1/health
    REDIS_URL          e.g. redis://localhost:6379/0  (else REDIS_HOST/REDIS_PORT)
    REDIS_HOST         default localhost
    REDIS_PORT         default 6379
    CELERY_INSPECT     set to 1 to attempt a celery worker ping (heavier)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.getenv("PROBE_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
HEALTH_PATH = os.getenv("PROBE_HEALTH_PATH", "/api/v1/health")
TIMEOUT = float(os.getenv("PROBE_TIMEOUT", "10"))


def _http(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "finsentry-kpi-probe"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (trusted, own service)
            status = resp.getcode()
            resp.read(2048)
        return {"ok": 200 <= status < 400, "status_code": status, "response_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status_code": None, "response_ms": round((time.perf_counter() - start) * 1000, 1), "error": type(exc).__name__}


def _redis() -> dict:
    start = time.perf_counter()
    try:
        import redis  # type: ignore

        url = os.getenv("REDIS_URL")
        if url:
            client = redis.Redis.from_url(url, socket_connect_timeout=TIMEOUT, socket_timeout=TIMEOUT)
        else:
            client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                socket_connect_timeout=TIMEOUT,
                socket_timeout=TIMEOUT,
            )
        pong = client.ping()
        return {"ok": bool(pong), "response_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "response_ms": round((time.perf_counter() - start) * 1000, 1), "error": type(exc).__name__}


def _celery() -> dict:
    if os.getenv("CELERY_INSPECT") != "1":
        return {"ok": None, "note": "skipped — set CELERY_INSPECT=1 to attempt worker ping (requires app import)"}
    start = time.perf_counter()
    try:
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from workers.celery_app import celery_app  # type: ignore

        replies = celery_app.control.inspect(timeout=TIMEOUT).ping() or {}
        return {"ok": len(replies) > 0, "workers": list(replies.keys()), "response_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "response_ms": round((time.perf_counter() - start) * 1000, 1), "error": type(exc).__name__}


def probe() -> dict:
    health = _http(HEALTH_PATH)
    api = _http("/openapi.json")
    redis_status = _redis()
    celery_status = _celery()

    components = {
        "health": health,
        "api": api,
        "redis": redis_status,
        "celery_worker": celery_status,
    }
    # Overall success = required components (health) up. Redis/celery are advisory here.
    overall_ok = bool(health.get("ok"))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "success": overall_ok,
        "components": components,
    }


def main() -> int:
    result = probe()
    print(json.dumps(result, indent=2))

    if "--log" in sys.argv:
        log_path = Path(__file__).resolve().parent.parent / "kpi_probe_history.jsonl"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(result) + "\n")
        print(f"\nAppended observation to {log_path}")

    # Exit non-zero if the required liveness probe failed (useful for cron alerting).
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
