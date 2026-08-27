"""
Redis-backed upload rate limiting service for FinSentry AI (Phase 2D).

Enforces per-user upload frequency limits using Redis atomic counters.
"""

import logging
from typing import Optional

from core.config import get_settings
from core.exceptions import UploadRateLimitException
from database.redis_client import redis_manager

logger = logging.getLogger(__name__)


class UploadRateLimiter:
    """
    Rate limiter for document uploads per authenticated user.
    """

    _memory_counters: dict = {}

    @classmethod
    def check_rate_limit(cls, user_id: str) -> None:
        """
        Check if the user has exceeded their document upload limit.

        Raises:
            UploadRateLimitException: If limit is exceeded.
        """
        import time

        settings = get_settings()
        limit = settings.UPLOAD_RATE_LIMIT_REQUESTS
        window = settings.UPLOAD_RATE_LIMIT_WINDOW_SECONDS

        key = f"rate_limit:upload:{user_id}"

        try:
            client = redis_manager.get_client()
            current = client.incr(key)
            if current == 1:
                client.expire(key, window)

            if current > limit:
                ttl = client.ttl(key)
                logger.warning(
                    "Upload rate limit exceeded for user %s (%d/%d, reset in %ds)",
                    user_id,
                    current,
                    limit,
                    ttl,
                )
                raise UploadRateLimitException(
                    f"Upload rate limit exceeded ({limit} uploads per {window}s). Retry in {ttl}s."
                )

        except UploadRateLimitException:
            raise
        except Exception as exc:
                                                               
            logger.debug("Redis rate limiter unavailable (%s); using in-memory counter", exc)
            now = time.time()
            entry = cls._memory_counters.get(user_id)
            if not entry or now >= entry["expires_at"]:
                cls._memory_counters[user_id] = {"count": 1, "expires_at": now + window}
                current = 1
            else:
                entry["count"] += 1
                current = entry["count"]

            if current > limit:
                ttl = max(1, int(cls._memory_counters[user_id]["expires_at"] - now))
                logger.warning(
                    "In-memory upload rate limit exceeded for user %s (%d/%d, reset in %ds)",
                    user_id,
                    current,
                    limit,
                    ttl,
                )
                raise UploadRateLimitException(
                    f"Upload rate limit exceeded ({limit} uploads per {window}s). Retry in {ttl}s."
                )

    @classmethod
    def reset_for_user(cls, user_id: str) -> None:
        """Testing utility to clear rate limit for a user."""
        cls._memory_counters.pop(user_id, None)
        try:
            client = redis_manager.get_client()
            client.delete(f"rate_limit:upload:{user_id}")
        except Exception:
            pass


upload_rate_limiter = UploadRateLimiter()
