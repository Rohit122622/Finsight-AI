"""
FinSentry AI — Phase 5H Locust Performance Test Module

This module provides a safe, controlled performance test harness for local/test environments.
DO NOT run against production.

Usage:
  python -m tests.test_locust_performance

Or with locust CLI:
  pip install locust
  locust -f tests/test_locust_performance.py --headless -u 5 -r 1 -t 30s --host http://127.0.0.1:8001
"""

import os
import sys
import time
import random
import json
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Try to import locust, fall back to simulation if not available
try:
    from locust import HttpUser, task, between, events
    LOCUST_AVAILABLE = True
except ImportError:
    LOCUST_AVAILABLE = False
    print("[INFO] Locust not installed. Running in simulation mode.")

import httpx


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics from a test run."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    response_times_ms: List[float] = field(default_factory=list)
    users: int = 0
    spawn_rate: float = 0.0
    duration_seconds: float = 0.0
    rps: float = 0.0
    
    @property
    def p50(self) -> float:
        if not self.response_times_ms:
            return 0.0
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.50)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def p95(self) -> float:
        if not self.response_times_ms:
            return 0.0
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def p99(self) -> float:
        if not self.response_times_ms:
            return 0.0
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "users": self.users,
            "spawn_rate": self.spawn_rate,
            "duration_seconds": self.duration_seconds,
            "rps": round(self.rps, 2),
            "p50_ms": round(self.p50, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
            "avg_response_ms": round(statistics.mean(self.response_times_ms), 2) if self.response_times_ms else 0.0,
        }


class FinSentryPerformanceTester:
    """
    Lightweight performance tester for FinSentry API endpoints.
    Runs controlled load tests without requiring the full Locust framework.
    """
    
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        users: int = 5,
        spawn_rate: float = 1.0,
        duration_seconds: float = 30.0,
    ):
        self.base_url = base_url
        self.users = users
        self.spawn_rate = spawn_rate
        self.duration_seconds = duration_seconds
        self.metrics = PerformanceMetrics(users=users, spawn_rate=spawn_rate, duration_seconds=duration_seconds)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
    
    def _record_request(self, success: bool, response_time_ms: float):
        with self._lock:
            self.metrics.total_requests += 1
            if success:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
            self.metrics.response_times_ms.append(response_time_ms)
    
    def _make_request(self, client: httpx.Client, endpoint: str, method: str = "GET", **kwargs) -> bool:
        """Make a single request and record metrics."""
        start = time.perf_counter()
        try:
            if method.upper() == "GET":
                response = client.get(endpoint, **kwargs)
            elif method.upper() == "POST":
                response = client.post(endpoint, **kwargs)
            else:
                response = client.request(method, endpoint, **kwargs)
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            success = response.status_code < 400
            self._record_request(success, elapsed_ms)
            return success
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._record_request(False, elapsed_ms)
            return False
    
    def _simulate_user(self, user_id: int):
        """Simulate a single user making requests."""
        with httpx.Client(base_url=self.base_url, timeout=30.0) as client:
            end_time = time.time() + self.duration_seconds
            
            while time.time() < end_time and not self._stop_event.is_set():
                # Health check (correct endpoint)
                self._make_request(client, "/api/v1/health")
                
                # API docs check
                self._make_request(client, "/docs")
                
                # OpenAPI schema
                self._make_request(client, "/openapi.json")
                
                # Small delay between requests
                time.sleep(random.uniform(0.1, 0.5))
    
    def run(self) -> PerformanceMetrics:
        """Run the performance test."""
        print(f"\n[PERFORMANCE TEST] Starting load test")
        print(f"  Base URL: {self.base_url}")
        print(f"  Users: {self.users}")
        print(f"  Spawn Rate: {self.spawn_rate}/s")
        print(f"  Duration: {self.duration_seconds}s")
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.users) as executor:
            # Spawn users gradually
            futures = []
            for i in range(self.users):
                futures.append(executor.submit(self._simulate_user, i))
                time.sleep(1.0 / self.spawn_rate)
            
            # Wait for all users to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"  [ERROR] User thread failed: {e}")
        
        actual_duration = time.time() - start_time
        self.metrics.duration_seconds = actual_duration
        self.metrics.rps = self.metrics.total_requests / actual_duration if actual_duration > 0 else 0
        
        return self.metrics


def run_safe_performance_test() -> Dict[str, Any]:
    """
    Run a safe, controlled performance test against local/test environment.
    Returns metrics dictionary suitable for Phase 5H reporting.
    """
    # Check if backend is reachable
    base_url = os.getenv("PERF_TEST_URL", "http://127.0.0.1:8001")
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{base_url}/api/v1/health")
            if response.status_code >= 500:
                return {
                    "status": "SKIPPED",
                    "reason": f"Backend not healthy (status {response.status_code})",
                    "metrics": None,
                }
    except Exception as e:
        return {
            "status": "SKIPPED",
            "reason": f"Backend not reachable: {e}",
            "metrics": None,
        }
    
    # Run controlled performance test
    tester = FinSentryPerformanceTester(
        base_url=base_url,
        users=5,
        spawn_rate=1.0,
        duration_seconds=30.0,
    )
    
    metrics = tester.run()
    
    print(f"\n[PERFORMANCE RESULTS]")
    print(f"  Total Requests: {metrics.total_requests}")
    print(f"  Successful: {metrics.successful_requests}")
    print(f"  Failed: {metrics.failed_requests}")
    print(f"  RPS: {metrics.rps:.2f}")
    print(f"  p50: {metrics.p50:.2f} ms")
    print(f"  p95: {metrics.p95:.2f} ms")
    print(f"  p99: {metrics.p99:.2f} ms")
    
    return {
        "status": "COMPLETED",
        "metrics": metrics.to_dict(),
    }


# Locust User class (if locust is available)
if LOCUST_AVAILABLE:
    class FinSentryUser(HttpUser):
        """Locust user class for FinSentry API load testing."""
        wait_time = between(0.5, 2.0)
        
        @task(10)
        def health_check(self):
            self.client.get("/api/v1/health")
        
        @task(5)
        def api_docs(self):
            self.client.get("/docs")
        
        @task(3)
        def openapi_schema(self):
            self.client.get("/openapi.json")


if __name__ == "__main__":
    result = run_safe_performance_test()
    print(f"\n[FINAL RESULT]")
    print(json.dumps(result, indent=2))
