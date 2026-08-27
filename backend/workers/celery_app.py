"""
Celery application instance and configuration for FinSentry AI.
"""

import logging
from celery import Celery

from core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "finsentry_worker",
    broker=settings.get_celery_broker_url(),
    backend=settings.get_celery_result_backend(),
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
                                      
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,                                              
)

                                                     
try:
    import agents.dummy_agent              
    import agents.document.document_agent              
    import agents.extraction.extraction_agent              
    import agents.red_flag.red_flag_agent              
    import agents.comparison.comparison_agent              
    import agents.research.research_agent              
    import agents.report.report_agent              
    import agents.analysis.live_analysis_agent              
    logger.info("Successfully registered all agent modules in Celery worker.")
except Exception as exc:
    logger.error("Failed to register agent modules in worker: %s", exc)

