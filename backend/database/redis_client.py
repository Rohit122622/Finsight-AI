"""
Redis client manager and connectivity checks for FinSentry AI.
"""

import logging
from typing import Optional

import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from core.config import get_settings

logger = logging.getLogger(__name__)


class RedisManager:
    """
    Manages Redis connection pooling and health diagnostics.
    """

    def __init__(self) -> None:
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None

    def get_client(self) -> redis.Redis:
        """Return the active Redis client with connection pooling."""
        if self._client is None:
            settings = get_settings()
            redis_url = settings.get_redis_url()
            self._pool = redis.ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                socket_timeout=1.0,
                socket_connect_timeout=0.2,
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client

    def ping(self) -> bool:
        """
        Check if Redis is reachable.

        Returns True if Redis responds with PONG, False otherwise without raising.
        """
        try:
            client = self.get_client()
            return bool(client.ping())
        except (ConnectionError, TimeoutError, RedisError, Exception) as exc:
            logger.warning("Redis ping check failed: %s", exc)
            return False

    def get_health_status(self) -> dict:
        """
        Return structured broker diagnostics.
        """
        settings = get_settings()
        is_alive = self.ping()
        return {
            "broker": "redis",
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "db": settings.REDIS_DB,
            "connected": is_alive,
            "status": "healthy" if is_alive else "unreachable",
        }

    def close(self) -> None:
        """Close connections in the pool."""
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._pool is not None:
            self._pool.disconnect()
            self._pool = None


redis_manager = RedisManager()


def get_redis_client() -> redis.Redis:
    """Dependency helper to get active Redis client."""
    return redis_manager.get_client()
