"""
FinSentry AI — Report Generation Agent (Production Implementation).

Owner: Vanshika / FinSentry Engineering Team

The final compilation and presentation layer of the FinSentry AI multi-agent pipeline.
Assembles persisted outputs from:
  1. Document Agent
  2. Extraction Agent
  3. Red Flag Agent
  4. Comparison Agent
  5. Research Agent
into one deterministic, institutional analyst-style PDF report stored in Cloudflare R2
and recorded in MongoDB.

CRITICAL ARCHITECTURAL RULES:
  1. ZERO LLM calls during report generation.
  2. Strictly deterministic data compilation and PDF rendering.
  3. Missing != zero (missing data is strictly 'N/A', never '$0').
  4. Single-company session gracefully generates without broken comparison charts.
  5. R2 upload failure blocks successful database persistence (no false success).
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from agents.report.chart_generator import ChartGenerator
from agents.report.pdf_builder import PDFBuilder
from agents.report.report_compiler import ReportCompiler
from agents.report.schemas import ReportDocument
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException, RetryableAgentException, StorageServiceException
from database.connection import get_sync_db
from models.report import AnalysisReportModel, ReportSectionModel
from services.r2_storage_service import r2_storage_service
from utils.pdf_security import (
    encrypt_pdf_bytes,
    encrypt_password_at_rest,
    generate_pdf_password,
)

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """
    Production Report Agent: Compiles multi-agent research outputs into an institutional PDF report.
    """

    def __init__(self, name: str = "ReportAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.REPORT_GENERATION)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute deterministic report compilation and PDF generation.

        Payload:
            session_id: str (required)
            user_id: Optional[str] (resolved from context if omitted)
            report_title: Optional[str]
            report_version: Optional[str] (default 'v1.0')
            document_ids: Optional[List[str]]
        """
        start_time = time.time()
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        title = payload.get("report_title", "Financial Research & Institutional Audit Report")
        version = payload.get("report_version", "v1.0")

        if not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required security boundaries: 'session_id' and 'user_id' must be provided."
            )

        logger.info(
            "ReportAgent starting deterministic compilation for session=%s, user=%s, version=%s",
            session_id,
            user_id,
            version,
        )

        try:
            # 1. Check idempotency & existing report reuse
            db = get_sync_db()
            report_id = ReportCompiler.generate_deterministic_report_id(session_id, user_id, version)
            existing_report = db.reports.find_one({"session_id": session_id, "report_id": report_id, "user_id": user_id})
            if existing_report and existing_report.get("status") == "COMPLETED" and existing_report.get("object_key"):
                def _normalize_dt(val):
                    if val is None:
                        return None
                    if isinstance(val, datetime):
                        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
                    if isinstance(val, (int, float)):
                        return datetime.fromtimestamp(val, tz=timezone.utc)
                    if isinstance(val, str):
                        try:
                            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
                        except Exception:
                            return None
                    return None

                report_created_at = _normalize_dt(existing_report.get("created_at"))
                latest_source_ts = None
                for col_name in ["extracted_metrics", "red_flags", "comparison_results"]:
                    col = getattr(db, col_name)
                    latest_doc = col.find_one({"session_id": session_id}, sort=[("updated_at", -1)])
                    if latest_doc and isinstance(latest_doc, dict):
                        doc_ts = _normalize_dt(latest_doc.get("updated_at") or latest_doc.get("created_at"))
                        if doc_ts:
                            if latest_source_ts is None or doc_ts > latest_source_ts:
                                latest_source_ts = doc_ts

                object_key = existing_report.get("object_key")
                # Only reuse if the existing artifact is a LOCKED (encrypted) PDF. Pre-feature
                # plaintext reports must be regenerated so the delivered/downloaded PDF is encrypted.
                if (
                    existing_report.get("pdf_locked")
                    and (latest_source_ts is None or (report_created_at and report_created_at >= latest_source_ts))
                    and r2_storage_service.object_exists(object_key)
                ):
                    logger.info("ReportAgent reusing existing completed report: %s", report_id)
                    summary_output = {
                        "report_id": report_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "report_title": existing_report.get("metadata", {}).get("report_title", title),
                        "report_version": version,
                        "companies": existing_report.get("metadata", {}).get("companies", []),
                        "status": "COMPLETED",
                        "object_key": object_key,
                        "download_url": existing_report.get("download_url") or f"/api/v1/sessions/{session_id}/reports/{report_id}/download",
                        "pdf_size_bytes": existing_report.get("pdf_size_bytes", 0),
                        "pdf_sha256": existing_report.get("pdf_sha256", ""),
                        "risk_score": existing_report.get("red_flags", {}).get("composite_risk_score", 0.0),
                        "total_red_flags": existing_report.get("red_flags", {}).get("total_flags", 0),
                        "comparison_included": existing_report.get("comparison", {}).get("is_available", False),
                        "pdf_locked": bool(existing_report.get("pdf_locked", False)),
                        "email_status": existing_report.get("email_status", "queued"),
                        "password_available": bool(existing_report.get("pdf_password_enc")),
                        "is_reused": True,
                    }
                    return AgentResult(
                        success=True,
                        task_type=self.default_task_type.value,
                        agent_name=self.name,
                        summary=summary_output,
                        result_ref=report_id,
                        metadata=summary_output,
                    )

            # 2. Gather all authoritative persisted agent outputs from MongoDB
            # Session-scoped documents
            documents = list(db.documents.find({"session_id": session_id, "user_id": user_id}))

            # Extraction Agent outputs
            extracted_metrics_list = list(db.extracted_metrics.find({"session_id": session_id, "user_id": user_id}))

            # Red Flag Agent outputs
            red_flags_list = list(db.red_flags.find({"session_id": session_id, "user_id": user_id}))

            # Comparison Agent outputs (session-scoped)
            comparison_results_list = list(
                db.comparison_results.find({"session_id": session_id}).sort("updated_at", -1).limit(1)
            )

            # If multi-company session but comparison hasn't been run yet, execute ComparisonAgent automatically
            if not comparison_results_list and len(extracted_metrics_list) >= 2:
                try:
                    from agents.comparison.comparison_agent import ComparisonAgent
                    comp_agent = ComparisonAgent()
                    comp_input = {
                        "session_id": session_id,
                        "user_id": user_id,
                        "document_ids": [doc.get("document_id") for doc in extracted_metrics_list if doc.get("document_id")],
                    }
                    comp_res = comp_agent.execute(comp_input)
                    if comp_res.success:
                        comparison_results_list = list(
                            db.comparison_results.find({"session_id": session_id}).sort("updated_at", -1).limit(1)
                        )
                except Exception as comp_exc:
                    logger.warning("Auto-invoking ComparisonAgent during report generation failed: %s", comp_exc)

            # Research Agent Q&A findings (session & user scoped)
            research_messages = list(
                db.research_messages.find({"session_id": session_id, "user_id": user_id}).sort("created_at", 1)
            )

            # Research session memory (if present)
            research_memory = db.research_session_memory.find_one({"session_id": session_id, "user_id": user_id})

            data_assembly_ms = (time.time() - start_time) * 1000

            # 2. Compile ReportDocument using pure-Python deterministic compiler (ZERO LLM CALLS)
            compile_start = time.time()
            report_doc: ReportDocument = ReportCompiler.compile(
                session_id=session_id,
                user_id=user_id,
                report_title=title,
                report_version=version,
                documents=documents,
                extracted_metrics_list=extracted_metrics_list,
                red_flags_list=red_flags_list,
                comparison_results_list=comparison_results_list,
                research_messages_list=research_messages,
                research_memory=research_memory,
            )

            # 3. Generate static comparison chart if multi-company comparison is present
            chart_start = time.time()
            chart_png_bytes: Optional[bytes] = None
            if report_doc.comparison.is_available:
                chart_png_bytes = ChartGenerator.generate_comparison_bar_chart(report_doc.comparison)
            chart_gen_ms = (time.time() - chart_start) * 1000

            # 4. Render PDF using ReportLab Platypus
            pdf_start = time.time()
            unlocked_pdf_bytes = PDFBuilder.build_pdf(report_doc, chart_png_bytes=chart_png_bytes)

            # 4b. Encrypt the PDF in-memory (AES-256). The unlocked bytes are never
            # persisted or exposed — only the encrypted artifact leaves this scope.
            pdf_password = generate_pdf_password()
            pdf_password_enc = encrypt_password_at_rest(pdf_password)
            pdf_bytes = encrypt_pdf_bytes(unlocked_pdf_bytes, pdf_password)
            del unlocked_pdf_bytes  # drop the unlocked copy promptly
            pdf_render_ms = (time.time() - pdf_start) * 1000

            # Size/hash reflect the ENCRYPTED artifact (what is stored/downloaded/emailed).
            pdf_size = len(pdf_bytes)
            pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            report_doc.pdf_size_bytes = pdf_size
            report_doc.pdf_sha256 = pdf_sha256

            # 5. Upload PDF to Cloudflare R2 via R2StorageService
            upload_start = time.time()
            object_key = report_doc.object_key
            try:
                r2_storage_service.upload_bytes(
                    key=object_key,
                    data=pdf_bytes,
                    content_type="application/pdf",
                )
            except StorageServiceException as upload_exc:
                logger.error("R2 storage upload failed for report %s: %s", report_doc.metadata.report_id, upload_exc)
                # CRITICAL: If R2 fails, do NOT mark report completed or create successful record
                raise RetryableAgentException(f"Failed to upload report PDF to Cloudflare R2: {upload_exc}")

            r2_upload_ms = (time.time() - upload_start) * 1000

            # Generate short-lived presigned URL for secure access
            try:
                download_url = r2_storage_service.generate_presigned_url(object_key, expires_in_seconds=3600)
                report_doc.download_url = download_url
            except Exception as presign_exc:
                logger.warning("Failed to generate presigned URL: %s", presign_exc)
                report_doc.download_url = f"/api/v1/sessions/{session_id}/reports/{report_doc.metadata.report_id}/download"

            # 6. Persist to MongoDB authoritative 'reports' collection
            report_dict = report_doc.to_mongo()
            report_dict["pdf_locked"] = True
            report_dict["pdf_password_enc"] = pdf_password_enc  # Fernet token, never plaintext
            report_dict["email_status"] = "queued"
            db.reports.replace_one(
                {"session_id": session_id, "report_id": report_doc.metadata.report_id},
                report_dict,
                upsert=True,
            )

            # 7. Compatibility Projection: Mirror to 'analysis_reports' for existing frontend viewer
            now = datetime.now(timezone.utc)
            section_models = [
                ReportSectionModel(
                    title="Key Financial Performance",
                    content=f"Evaluated {len(report_doc.key_financials.metrics)} metrics across {len(report_doc.key_financials.companies)} entities.",
                    key_findings=[
                        f"{m.display_name}: " + ", ".join([f"{v.company_name} {v.formatted_value}" for v in m.values if v.available])
                        for m in report_doc.key_financials.metrics[:5]
                    ],
                ),
                ReportSectionModel(
                    title="Forensic Red Flags & Anomalies",
                    content=f"Detected {report_doc.red_flags.total_flags} anomalies. Composite Risk Score: {report_doc.red_flags.composite_risk_score:.1f}/100.",
                    key_findings=[f"{f.title}: {f.severity}" for f in report_doc.red_flags.findings[:5]],
                ),
            ]
            if report_doc.comparison.is_available:
                section_models.append(
                    ReportSectionModel(
                        title="Peer Comparison & Benchmark",
                        content=f"Benchmarked {', '.join(report_doc.comparison.compared_companies)} across {len(report_doc.comparison.metrics)} metrics.",
                        key_findings=[f"{m.display_name} peer average: {m.peer_average}" for m in report_doc.comparison.metrics[:4]],
                    )
                )

            compat_report = AnalysisReportModel(
                report_id=report_doc.metadata.report_id,
                session_id=session_id,
                user_id=user_id,
                report_title=title,
                executive_summary=report_doc.executive_summary.narrative,
                risk_score=report_doc.red_flags.composite_risk_score,
                sections=section_models,
                extracted_metrics=[
                    {"metric": m.metric_key, "display": m.display_name}
                    for m in report_doc.key_financials.metrics
                ],
                red_flags=[
                    f.model_dump() for f in report_doc.red_flags.findings
                ],
                recommendations=[
                    "Conduct regular quarterly filing verifications.",
                    "Monitor working capital and operating cash flow margins.",
                ],
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            )
            compat_dict = compat_report.to_dict()
            compat_dict["download_url"] = report_doc.download_url
            compat_dict["object_key"] = object_key
            compat_dict["pdf_size_bytes"] = pdf_size
            compat_dict["pdf_locked"] = True
            compat_dict["pdf_password_enc"] = pdf_password_enc
            compat_dict["email_status"] = "queued"
            db.analysis_reports.replace_one(
                {"session_id": session_id, "report_id": report_doc.metadata.report_id},
                compat_dict,
                upsert=True,
            )

            # 7b. Queue the automatic email of the SAME encrypted artifact to the
            # authenticated user's registered address. Non-blocking; email failure
            # never invalidates the successfully generated + persisted report.
            email_status = "queued"
            try:
                from workers.email_tasks import send_locked_pdf_email

                send_locked_pdf_email.apply_async(
                    kwargs={
                        "kind": "report",
                        "user_id": user_id,
                        "session_id": session_id,
                        "ref_id": report_doc.metadata.report_id,
                        "object_key": object_key,
                    }
                )
            except Exception as email_exc:  # noqa: BLE001 - never block report success
                logger.warning("Could not queue report email (type=%s)", type(email_exc).__name__)
                email_status = "failed"
                try:
                    db.reports.update_one(
                        {"session_id": session_id, "report_id": report_doc.metadata.report_id},
                        {"$set": {"email_status": email_status}},
                    )
                    db.analysis_reports.update_one(
                        {"session_id": session_id, "report_id": report_doc.metadata.report_id},
                        {"$set": {"email_status": email_status}},
                    )
                except Exception:
                    pass

            total_latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "ReportAgent generated PDF %s for session %s in %.1fms (PDF size: %d bytes, SHA256: %s)",
                report_doc.metadata.report_id,
                session_id,
                total_latency_ms,
                pdf_size,
                pdf_sha256[:12],
            )

            summary_output = {
                "report_id": report_doc.metadata.report_id,
                "session_id": session_id,
                "user_id": user_id,
                "report_title": title,
                "report_version": version,
                "companies": report_doc.metadata.companies,
                "status": "COMPLETED",
                "object_key": object_key,
                "download_url": report_doc.download_url,
                "pdf_size_bytes": pdf_size,
                "pdf_sha256": pdf_sha256,
                "pdf_locked": True,
                "email_status": email_status,
                "password_available": True,
                "risk_score": report_doc.red_flags.composite_risk_score,
                "total_red_flags": report_doc.red_flags.total_flags,
                "comparison_included": report_doc.comparison.is_available,
                "latency_metrics": {
                    "data_assembly_ms": round(data_assembly_ms, 2),
                    "chart_gen_ms": round(chart_gen_ms, 2),
                    "pdf_render_ms": round(pdf_render_ms, 2),
                    "r2_upload_ms": round(r2_upload_ms, 2),
                    "total_ms": round(total_latency_ms, 2),
                },
            }

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=summary_output,
                result_ref=report_doc.metadata.report_id,
                metadata=summary_output,
            )

        except (NonRetryableAgentException, RetryableAgentException):
            raise
        except Exception as exc:
            logger.error("Unexpected error in ReportAgent: %s", exc, exc_info=True)
            raise RetryableAgentException(f"ReportAgent unexpected compilation failure: {exc}")


report_agent = ReportAgent()
agent_registry.register(report_agent, overwrite=True)
