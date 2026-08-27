"""
FinSentry AI — FastAPI application entry-point.

Configures the ASGI application, CORS policy, database lifecycle
hooks, and the top-level health endpoint.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agents import router as agents_router
from api.analysis import router as analysis_router
from api.auth import router as auth_router
from api.documents import router as documents_router
from api.evaluation import router as evaluation_router
from api.google_auth import router as google_auth_router
from api.health import router as health_router
from api.jobs import router as jobs_router
from api.research import router as research_router
from api.research_chat import router as research_chat_router
from api.secure_upload import router as upload_router
from api.sessions import router as sessions_router
from api.websockets import router as websockets_router
from core.config import get_settings
from database.connection import mongodb
from database.indexes import create_indexes
import agents.dummy_agent                                                
import agents.document.document_agent                                                   
import agents.extraction.extraction_agent                                                     
import agents.red_flag.red_flag_agent                                                  
import agents.comparison.comparison_agent                                                     
import agents.research.research_agent                                                   
import agents.report.report_agent                                                 
import agents.analysis.live_analysis_agent                                                       

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    Startup:
        1. Connect to MongoDB Atlas.
        2. Ensure required indexes exist.

    Shutdown:
        1. Gracefully disconnect from MongoDB Atlas.
    """
    logger.info("Starting FinSentry AI…")
    await mongodb.connect()

    db = mongodb.get_db()
    await create_indexes(db)
    logger.info("Startup complete")

    yield

    logger.info("Shutting down FinSentry AI…")
    await mongodb.disconnect()
    logger.info("Shutdown complete")


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", tags=["health"])
async def health_check() -> dict:
    """Lightweight liveness probe."""
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(google_auth_router, prefix="/api/v1/auth/google", tags=["auth"])
app.include_router(sessions_router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(
    documents_router,
    prefix="/api/v1/sessions/{session_id}/documents",
    tags=["documents"],
)
app.include_router(upload_router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(
    research_router,
    prefix="/api/v1/sessions/{session_id}",
    tags=["research"],
)
app.include_router(
    research_chat_router,
    prefix="/api/v1/research",
    tags=["research-chat"],
)
app.include_router(
    analysis_router,
    prefix="/api/v1/sessions/{session_id}",
    tags=["analysis"],
)
app.include_router(jobs_router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(agents_router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(evaluation_router, prefix="/api/v1/evaluation", tags=["evaluation"])
app.include_router(websockets_router, prefix="/api/v1", tags=["websockets", "chat"])