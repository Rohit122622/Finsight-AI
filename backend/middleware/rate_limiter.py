"""
In-memory sliding window rate limiter.

Provides per-key (typically per-IP) rate limiting using an in-memory
store.  Designed for Phase 1 development use — single-process only.

Phase 2 migration note:
    This module should be replaced with a Redis-backed implementation
    in Phase 2 to support distributed rate limiting across multiple
    application instances.  The public API (check_rate_limit,
    record_attempt, reset) should remain the same so callers don't
    need to change.
"""

import logging
import time
import threading
from typing import Dict, List

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Sliding window rate limiter backed by an in-memory dict.

    Tracks timestamps of failed attempts per key.  A key is blocked
    once it accumulates ``max_attempts`` within ``window_seconds``.

    Thread-safe via a simple lock.

    Parameters:
        max_attempts:   Maximum failed attempts before blocking.
        window_seconds: Sliding window duration in seconds.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _cleanup(self, key: str) -> None:
        """Remove timestamps outside the current window for *key*."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        if key in self._attempts:
            self._attempts[key] = [
                ts for ts in self._attempts[key] if ts > cutoff
            ]
            if not self._attempts[key]:
                del self._attempts[key]

    def check_rate_limit(self, key: str) -> bool:
        """
        Return ``True`` if the key is allowed to proceed.

        Return ``False`` if the key has exceeded the attempt limit
        within the current window.
        """
        with self._lock:
            self._cleanup(key)
            attempts = self._attempts.get(key, [])
            if len(attempts) >= self.max_attempts:
                return False
            return True

    def record_attempt(self, key: str) -> None:
        """Record a failed attempt for *key*."""
        with self._lock:
            self._cleanup(key)
            if key not in self._attempts:
                self._attempts[key] = []
            self._attempts[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        """Clear all recorded attempts for *key* (e.g. on successful login)."""
        with self._lock:
            self._attempts.pop(key, None)


                                                                       
 
                                             
                                                                    

login_rate_limiter = InMemoryRateLimiter(max_attempts=5, window_seconds=300)
