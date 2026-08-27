"""
Live Analysis and Multi-Agent Orchestration Service for FinSentry AI (Phase 2G - Live Processing).

Coordinates live, end-to-end multi-agent financial investigations across session documents,
tracking progress transitions (0% -> 100%) and persisting structured investment research reports.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database

from agents.registry import agent_registry
from core.constants import AgentTaskType, JobStatus
from core.exceptions import (
    DocumentNotFoundException,
    NonRetryableAgentException,
    UnauthorizedDocumentAccessException,
)
from database.connection import get_sync_db, mongodb
from models.job import JobModel
from models.report import AnalysisReportModel, ReportSectionModel

logger = logging.getLogger(__name__)


class LiveAnalysisService:
    """
    Coordinates live multi-agent financial research workflows and analysis report persistence.
    """

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db

    def _get_db(self) -> AsyncIOMotorDatabase:
        if self._db is not None:
            return self._db
        return mongodb.get_db()

                                                                                 

    def run_live_analysis_sync(
        self,
        session_id: str,
        user_id: str,
        query: Optional[str] = None,
        focus_areas: Optional[List[str]] = None,
        report_title: Optional[str] = None,
        baseline_entity: Optional[str] = None,
        comparison_entity: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> AnalysisReportModel:
        """
        Execute synchronous multi-agent financial analysis pipeline with live step updates.
        """
        title = report_title or "Comprehensive Financial Analysis Report"
        baseline = baseline_entity or "Current Reporting Period"
        comparison = comparison_entity or "Prior Reporting Period"
        focus = focus_areas or ["accounting", "solvency", "governance", "guidance"]

        from services.job_service import job_service

        context = {"user_id": user_id, "session_id": session_id, "job_id": job_id}
        start_time = time.time()

        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=5,
                current_step="INITIALIZING",
                event_message="Initializing live multi-agent research pipeline.",
            )

                                                                               
        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=25,
                current_step="EXTRACTION",
                event_message="ExtractionAgent analyzing document chunks for KPIs and balance sheet figures.",
            )

        extraction_agent = agent_registry.get("ExtractionAgent")
        ext_res = extraction_agent.execute(
            payload={
                "session_id": session_id,
                "target_fields": ["revenue", "ebitda", "operating_income", "debt", "cash_flow", "margins"],
            },
            context=context,
        )
        extracted_data = (ext_res.summary or {}).get("extracted_data", {})
        extracted_metrics: List[Dict[str, Any]] = []
        if isinstance(extracted_data, dict):
            for k, v in extracted_data.items():
                extracted_metrics.append({"metric_name": str(k), "value": v})

                                                                               
        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=50,
                current_step="RED_FLAG_ANALYSIS",
                event_message="RedFlagAgent running forensic scans for accounting and solvency risks.",
            )

        red_flag_agent = agent_registry.get("RedFlagAgent")
        rf_res = red_flag_agent.execute(
            payload={
                "session_id": session_id,
                "risk_focus": f"{', '.join(focus)}. Query focus: {query or 'General due diligence'}",
            },
            context=context,
        )
        rf_summary = rf_res.summary or {}
        red_flags_list = rf_summary.get("flags", [])
        risk_score = float(rf_summary.get("risk_score", 15.0))

                                                                               
        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=75,
                current_step="COMPARISON",
                event_message="ComparisonAgent evaluating historical variances and performance trends.",
            )

        comp_agent = agent_registry.get("ComparisonAgent")
        comp_res = comp_agent.execute(
            payload={
                "session_id": session_id,
                "baseline_entity": baseline,
                "comparison_entity": comparison,
            },
            context=context,
        )
        comp_summary = comp_res.summary or {}
        key_takeaways = comp_summary.get("key_takeaways", [])

                                                                               
        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=90,
                current_step="REPORT_SYNTHESIS",
                event_message="ReportAgent synthesizing findings into institutional audit report.",
            )

        report_agent = agent_registry.get("ReportAgent")
        rep_res = report_agent.execute(
            payload={
                "session_id": session_id,
                "report_title": title,
            },
            context=context,
        )
        rep_summary = rep_res.summary or {}
        exec_summary = rep_summary.get("executive_summary", f"Financial due diligence analysis for session {session_id}.")
        raw_sections = rep_summary.get("sections", [])
        recommendations = rep_summary.get("recommendations", ["Continue regular monitoring of filing disclosures."])

                                         
        sections: List[ReportSectionModel] = []
        for s in raw_sections:
            if isinstance(s, dict):
                sections.append(
                    ReportSectionModel(
                        title=s.get("title", "Section"),
                        content=s.get("content", ""),
                        key_findings=s.get("key_findings", []),
                    )
                )

        if not sections:
            sections = [
                ReportSectionModel(
                    title="Executive Synthesis & Performance",
                    content=exec_summary,
                    key_findings=key_takeaways or ["Positive baseline operational metrics."],
                ),
                ReportSectionModel(
                    title="Risk & Anomaly Assessment",
                    content=f"Detected {len(red_flags_list)} risk items. Overall composite risk score: {risk_score}/100.",
                    key_findings=[f"{f.get('title')}: {f.get('severity')}" for f in red_flags_list if isinstance(f, dict)],
                ),
            ]

                                                                               
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        report = AnalysisReportModel(
            report_id=report_id,
            session_id=session_id,
            user_id=user_id,
            report_title=title,
            executive_summary=exec_summary,
            risk_score=risk_score,
            sections=sections,
            extracted_metrics=extracted_metrics,
            red_flags=red_flags_list,
            recommendations=recommendations,
            status="COMPLETED",
            created_at=now,
            updated_at=now,
        )

        db: Database = get_sync_db()
        db.analysis_reports.insert_one(report.to_dict())

        if job_id:
            job_service.update_job_progress_sync(
                job_id=job_id,
                progress_percent=100,
                current_step="COMPLETED",
                event_message=f"Live research completed in {time.time() - start_time:.2f}s. Report generated: {report_id}",
            )

        logger.info(
            "Live analysis completed for session %s: report %s (risk score: %.1f)",
            session_id,
            report_id,
            risk_score,
        )
        return report

    async def run_live_analysis_async(
        self,
        session_id: str,
        user_id: str,
        query: Optional[str] = None,
        focus_areas: Optional[List[str]] = None,
        report_title: Optional[str] = None,
        baseline_entity: Optional[str] = None,
        comparison_entity: Optional[str] = None,
    ) -> JobModel:
        """
        Enqueue live multi-agent analysis to background Celery job queue.
        """
        payload = {
            "session_id": session_id,
            "query": query,
            "focus_areas": focus_areas or [],
            "report_title": report_title or "Comprehensive Financial Analysis Report",
            "baseline_entity": baseline_entity,
            "comparison_entity": comparison_entity,
        }

        from services.job_service import job_service

        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="ReportAgent",
            task_type=AgentTaskType.REPORT_GENERATION.value,
            payload=payload,
            session_id=session_id,
        )
        return job

                                                                                

    async def get_report(
        self, report_id: str, user_id: str, session_id: str
    ) -> AnalysisReportModel:
        """
        Fetch a report enforcing session and user ownership.
        """
        db = self._get_db()
        doc = await db.analysis_reports.find_one(
            {"report_id": report_id, "user_id": user_id, "session_id": session_id}
        )
        if not doc:
                                                                               
            exists_any = await db.analysis_reports.find_one({"report_id": report_id})
            if exists_any:
                raise UnauthorizedDocumentAccessException()
            raise DocumentNotFoundException(f"Report '{report_id}' not found.")

        return AnalysisReportModel.from_mongo(doc)

    async def list_reports(
        self, user_id: str, session_id: str, skip: int = 0, limit: int = 20
    ) -> Tuple[List[AnalysisReportModel], int]:
        """
        List analysis reports for a session with pagination.
        """
        db = self._get_db()
        query = {"user_id": user_id, "session_id": session_id}
        total = await db.analysis_reports.count_documents(query)

        cursor = (
            db.analysis_reports.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [AnalysisReportModel.from_mongo(d) for d in docs], total

    async def delete_report(
        self, report_id: str, user_id: str, session_id: str
    ) -> bool:
        """
        Delete an analysis report.
        """
        await self.get_report(report_id, user_id, session_id)
        db = self._get_db()
        await db.analysis_reports.delete_one(
            {"report_id": report_id, "user_id": user_id, "session_id": session_id}
        )
        logger.info("Deleted analysis report %s from session %s", report_id, session_id)
        return True

    async def get_session_red_flags(
        self, user_id: str, session_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve structured RedFlagResult and lifecycle status for a session.
        Status: NOT_RUN | RUNNING | COMPLETED_WITH_FLAGS | COMPLETED_NO_FLAGS | FAILED
        """
        db = self._get_db()

                                                                     
        running_job = await db.jobs.find_one({
            "session_id": session_id,
            "user_id": user_id,
            "status": {"$in": ["QUEUED", "RUNNING", "PROCESSING"]},
            "task_type": {"$in": ["DOCUMENT_ANALYSIS", "RED_FLAG_ANALYSIS", "REPORT_GENERATION"]},
        })
        if running_job:
            return {
                "session_id": session_id,
                "status": "RUNNING",
                "total_flags": 0,
                "high_severity_count": 0,
                "risk_score": 0.0,
                "overall_assessment": "Forensic risk assessment is currently in progress...",
                "flags": [],
            }

                                                                      
        rf_doc = await db.red_flags.find_one({"session_id": session_id})
        if rf_doc:
            flags = rf_doc.get("flags", [])
            total_flags = len(flags)
            high_count = sum(
                1 for f in flags if str(f.get("severity", "")).upper() in ["HIGH", "CRITICAL"]
            )
            risk_score = rf_doc.get("risk_score", 0.0)
            overall_assessment = rf_doc.get("overall_assessment", "")
            status_str = "COMPLETED_WITH_FLAGS" if total_flags > 0 else "COMPLETED_NO_FLAGS"
            return {
                "session_id": session_id,
                "status": status_str,
                "total_flags": total_flags,
                "high_severity_count": high_count,
                "risk_score": risk_score,
                "overall_assessment": overall_assessment,
                "flags": flags,
            }

                                                 
        reports, _ = await self.list_reports(user_id=user_id, session_id=session_id, limit=5)
        if reports:
            report_flags: List[Dict[str, Any]] = []
            for r in reports:
                report_flags.extend(r.red_flags)
            total_flags = len(report_flags)
            status_str = "COMPLETED_WITH_FLAGS" if total_flags > 0 else "COMPLETED_NO_FLAGS"
            return {
                "session_id": session_id,
                "status": status_str,
                "total_flags": total_flags,
                "high_severity_count": sum(
                    1 for f in report_flags if str(f.get("severity", "")).upper() in ["HIGH", "CRITICAL"]
                ),
                "risk_score": reports[0].risk_score if reports else 0.0,
                "overall_assessment": reports[0].executive_summary if reports else "",
                "flags": report_flags,
            }

                                                
        failed_job = await db.jobs.find_one({
            "session_id": session_id,
            "user_id": user_id,
            "status": "FAILED",
            "task_type": {"$in": ["DOCUMENT_ANALYSIS", "RED_FLAG_ANALYSIS", "REPORT_GENERATION"]},
        })
        failed_doc = await db.documents.find_one(
            {"session_id": session_id, "user_id": user_id, "status": "FAILED"}
        )
        if failed_job or failed_doc:
            err_msg = (failed_job.get("error") if failed_job else None) or "Document processing or forensic analysis failed."
            return {
                "session_id": session_id,
                "status": "FAILED",
                "total_flags": 0,
                "high_severity_count": 0,
                "risk_score": 0.0,
                "overall_assessment": str(err_msg),
                "flags": [],
            }

                                   
        return {
            "session_id": session_id,
            "status": "NOT_RUN",
            "total_flags": 0,
            "high_severity_count": 0,
            "risk_score": 0.0,
            "overall_assessment": "Risk assessment not yet run.",
            "flags": [],
        }


live_analysis_service = LiveAnalysisService()
