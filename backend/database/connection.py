import logging
import threading
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database

from core.config import get_settings

logger = logging.getLogger(__name__)


class MongoDB:
    """
    Manages a single Motor client and its database handle.

    Usage:
        db = MongoDB()
        await db.connect()      # call from FastAPI lifespan/startup
        database = db.get_db()  # obtain the database handle
        await db.disconnect()   # call from FastAPI lifespan/shutdown
    """

    def __init__(self) -> None:
        self._client: Optional[AsyncIOMotorClient] = None
        self._database: Optional[AsyncIOMotorDatabase] = None
        self._loop = None
        self._lock = threading.Lock()

    async def connect(self) -> None:
        """
        Open a connection pool to MongoDB Atlas.

        Motor uses connection pooling by default; maxPoolSize controls
        the upper bound of concurrent connections.
        """
        settings = get_settings()
        import asyncio
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        try:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass

            self._client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                maxPoolSize=50,
                minPoolSize=1,
                maxIdleTimeMS=45_000,
                connectTimeoutMS=15_000,
                serverSelectionTimeoutMS=10_000,
                socketTimeoutMS=30_000,
                retryWrites=True,
                retryReads=True,
            )
            self._database = self._client[settings.DATABASE_NAME]

            await self._client.admin.command("ping")
            logger.info(
                "Connected to MongoDB Atlas — database: %s",
                settings.DATABASE_NAME,
            )
        except Exception:
            logger.exception("Failed to connect to MongoDB Atlas")
            raise

    async def disconnect(self) -> None:
        """Close the Motor client and release all pooled connections."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None
            self._loop = None
            logger.info("Disconnected from MongoDB Atlas")

    def get_db(self) -> AsyncIOMotorDatabase:
        """
        Return the active database handle, binding safely to the current running event loop.
        """
        settings = get_settings()
        import asyncio

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None
            or self._database is None
            or (current_loop is not None and self._loop != current_loop)
            or (self._loop is not None and self._loop.is_closed())
        ):
            with self._lock:
                if (
                    self._client is None
                    or self._database is None
                    or (current_loop is not None and self._loop != current_loop)
                    or (self._loop is not None and self._loop.is_closed())
                ):
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                    self._loop = current_loop
                    self._client = AsyncIOMotorClient(
                        settings.MONGODB_URI,
                        maxPoolSize=50,
                        minPoolSize=1,
                        maxIdleTimeMS=45_000,
                        connectTimeoutMS=15_000,
                        serverSelectionTimeoutMS=10_000,
                        socketTimeoutMS=30_000,
                        retryWrites=True,
                        retryReads=True,
                    )
                    self._database = self._client[settings.DATABASE_NAME]

        return self._database


mongodb = MongoDB()


async def get_database() -> AsyncIOMotorDatabase:
    """
    Dependency-injection helper for FastAPI routes.

    Example:
        @router.get("/items")
        async def list_items(db = Depends(get_database)):
            ...
    """
    return mongodb.get_db()


class SyncMongoDB:
    """
    Synchronous PyMongo client manager for background Celery worker tasks.

    Prevents asyncio event loop collisions inside Celery worker processes.
    """

    def __init__(self) -> None:
        self._client: Optional[MongoClient] = None
        self._database: Optional[Database] = None
        self._lock = threading.Lock()

    def get_db(self) -> Database:
        """Return the active synchronous pymongo Database instance."""
        if self._database is None:
            with self._lock:
                if self._database is None:
                    settings = get_settings()
                    self._client = MongoClient(
                        settings.MONGODB_URI,
                        maxPoolSize=20,
                        minPoolSize=1,
                        maxIdleTimeMS=45_000,
                        connectTimeoutMS=15_000,
                        serverSelectionTimeoutMS=10_000,
                        socketTimeoutMS=30_000,
                        retryWrites=True,
                        retryReads=True,
                    )
                    self._database = self._client[settings.DATABASE_NAME]
        return self._database

    def close(self) -> None:
        """Close the synchronous client."""
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
                self._database = None


sync_mongodb = SyncMongoDB()


def get_sync_db() -> Database:
    """Helper to obtain the synchronous database handle for Celery tasks."""
    return sync_mongodb.get_db()

