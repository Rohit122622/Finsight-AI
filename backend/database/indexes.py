"""
Database index definitions.

Called once during application startup to ensure that critical indexes
exist. Motor's create_index() is idempotent — it is safe to invoke on
every boot without duplicating indexes.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all application-level indexes.

    Indexes:
        users.email              – unique, for login/registration lookups
        research_sessions.user_id   – for per-user session listing
        research_sessions.created_at – descending, for chronological queries
    """
    try:
        await db.users.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="idx_users_email_unique",
        )
        logger.info("Ensured index: idx_users_email_unique on users.email")

        await db.research_sessions.create_index(
            [("user_id", ASCENDING)],
            name="idx_research_sessions_user_id",
        )
        logger.info(
            "Ensured index: idx_research_sessions_user_id on "
            "research_sessions.user_id"
        )

        await db.research_sessions.create_index(
            [("created_at", DESCENDING)],
            name="idx_research_sessions_created_at",
        )
        logger.info(
            "Ensured index: idx_research_sessions_created_at on "
            "research_sessions.created_at"
        )

                                                                       
        await db.refresh_tokens.create_index(
            [("jti", ASCENDING)],
            unique=True,
            name="idx_refresh_tokens_jti_unique",
        )
        logger.info("Ensured index: idx_refresh_tokens_jti_unique on refresh_tokens.jti")

        await db.refresh_tokens.create_index(
            [("user_id", ASCENDING)],
            name="idx_refresh_tokens_user_id",
        )
        logger.info(
            "Ensured index: idx_refresh_tokens_user_id on "
            "refresh_tokens.user_id"
        )

                                                                        
        await db.jobs.create_index(
            [("job_id", ASCENDING)],
            unique=True,
            name="idx_jobs_job_id_unique",
        )
        logger.info("Ensured index: idx_jobs_job_id_unique on jobs.job_id")

        await db.jobs.create_index(
            [("user_id", ASCENDING)],
            name="idx_jobs_user_id",
        )
        logger.info("Ensured index: idx_jobs_user_id on jobs.user_id")

        await db.jobs.create_index(
            [("session_id", ASCENDING)],
            name="idx_jobs_session_id",
        )
        logger.info("Ensured index: idx_jobs_session_id on jobs.session_id")

        await db.jobs.create_index(
            [("status", ASCENDING)],
            name="idx_jobs_status",
        )
        logger.info("Ensured index: idx_jobs_status on jobs.status")

        await db.jobs.create_index(
            [("created_at", DESCENDING)],
            name="idx_jobs_created_at",
        )
        logger.info("Ensured index: idx_jobs_created_at on jobs.created_at")

                                                                        
        await db.documents.create_index(
            [("document_id", ASCENDING)],
            unique=True,
            name="idx_documents_document_id_unique",
        )
        logger.info("Ensured index: idx_documents_document_id_unique on documents.document_id")

        await db.documents.create_index(
            [("session_id", ASCENDING)],
            name="idx_documents_session_id",
        )
        logger.info("Ensured index: idx_documents_session_id on documents.session_id")

        await db.documents.create_index(
            [("user_id", ASCENDING)],
            name="idx_documents_user_id",
        )
        logger.info("Ensured index: idx_documents_user_id on documents.user_id")

        await db.documents.create_index(
            [("status", ASCENDING)],
            name="idx_documents_status",
        )
        logger.info("Ensured index: idx_documents_status on documents.status")

        await db.documents.create_index(
            [("session_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_documents_session_created",
        )
        logger.info("Ensured index: idx_documents_session_created on documents(session_id, created_at)")

                                                                       
        await db.documents.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("metadata.sha256", ASCENDING)],
            name="idx_documents_user_session_sha256",
        )
        logger.info("Ensured index: idx_documents_user_session_sha256 on documents(user_id, session_id, metadata.sha256)")

                                                                               
        await db.analysis_reports.create_index(
            [("report_id", ASCENDING)],
            unique=True,
            name="idx_analysis_reports_report_id_unique",
        )
        logger.info("Ensured index: idx_analysis_reports_report_id_unique on analysis_reports.report_id")

        await db.analysis_reports.create_index(
            [("session_id", ASCENDING)],
            name="idx_analysis_reports_session_id",
        )
        logger.info("Ensured index: idx_analysis_reports_session_id on analysis_reports.session_id")

        await db.analysis_reports.create_index(
            [("user_id", ASCENDING)],
            name="idx_analysis_reports_user_id",
        )
        logger.info("Ensured index: idx_analysis_reports_user_id on analysis_reports.user_id")

        await db.analysis_reports.create_index(
            [("session_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_analysis_reports_session_created",
        )
        logger.info("Ensured index: idx_analysis_reports_session_created on analysis_reports(session_id, created_at)")

                                                                                       
        await db.chat_messages.create_index(
            [("message_id", ASCENDING)],
            unique=True,
            name="idx_chat_messages_message_id_unique",
        )
        logger.info("Ensured index: idx_chat_messages_message_id_unique on chat_messages.message_id")

        await db.chat_messages.create_index(
            [("session_id", ASCENDING)],
            name="idx_chat_messages_session_id",
        )
        logger.info("Ensured index: idx_chat_messages_session_id on chat_messages.session_id")

        await db.chat_messages.create_index(
            [("user_id", ASCENDING)],
            name="idx_chat_messages_user_id",
        )
        logger.info("Ensured index: idx_chat_messages_user_id on chat_messages.user_id")

        await db.chat_messages.create_index(
            [("session_id", ASCENDING), ("created_at", ASCENDING)],
            name="idx_chat_messages_session_created",
        )
        logger.info("Ensured index: idx_chat_messages_session_created on chat_messages(session_id, created_at)")

                                                                        
        await db.research_conversations.create_index(
            [("conversation_id", ASCENDING)],
            unique=True,
            name="idx_research_conversations_id_unique",
        )
        await db.research_conversations.create_index(
            [("session_id", ASCENDING), ("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_research_conversations_lookup",
        )
        logger.info("Ensured indexes on research_conversations")

        await db.research_messages.create_index(
            [("message_id", ASCENDING)],
            unique=True,
            name="idx_research_messages_id_unique",
        )
        await db.research_messages.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            name="idx_research_messages_conv_created",
        )
        await db.research_messages.create_index(
            [("session_id", ASCENDING), ("user_id", ASCENDING), ("created_at", ASCENDING)],
            name="idx_research_messages_session_created",
        )
        logger.info("Ensured indexes on research_messages")

        await db.research_session_memory.create_index(
            [("session_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
            name="idx_research_session_memory_unique",
        )
        logger.info("Ensured index: idx_research_session_memory_unique on research_session_memory")

                                                                        
        await db.research_traces.create_index(
            [("trace_id", ASCENDING)],
            unique=True,
            name="idx_research_traces_id_unique",
        )
        await db.research_traces.create_index(
            [("session_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_research_traces_session_created",
        )
        await db.research_traces.create_index(
            [("conversation_id", ASCENDING)],
            name="idx_research_traces_conversation_id",
        )
        await db.research_traces.create_index(
            [("user_id", ASCENDING)],
            name="idx_research_traces_user_id",
        )
        logger.info("Ensured indexes on research_traces")

    except Exception:
        logger.exception("Failed to create database indexes")
        raise
