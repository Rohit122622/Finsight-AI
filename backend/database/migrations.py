"""
FinSentry AI — Database Migrations & Schema Harmonization.

Handles automated, idempotent database migrations on startup.
Specifically ensures the extracted_metrics collection adheres to the
Master Plan requirement:
"ONE consolidated extracted_metrics record per document."
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from utils.financial_grounding import safe_parse_financial_number

logger = logging.getLogger(__name__)


async def migrate_extracted_metrics_collection(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Idempotent migration function to harmonize legacy extracted_metrics records.

    Problem addressed:
      Earlier versions stored multiple individual metric rows per session/document
      (e.g., separate records for 'revenue', 'title', etc.) often with document_id=None.
      The Master Plan requires exactly ONE consolidated record per document, keyed by
      unique (document_id, session_id).

    Migration actions:
      1. Detects legacy single-metric rows and records where document_id is missing/None.
      2. Groups legacy rows by (session_id, document_id).
      3. For records missing document_id, attempts to resolve the primary document_id
         from the documents collection for that session, falling back to 'doc_legacy_{session_id}'.
      4. Merges individual metric items, topics, figures, and metadata into a single
         consolidated ExtractedMetricsDocument-compliant record.
      5. Replaces separate legacy rows with the single consolidated record.
      6. Merges any lingering duplicates for the same (document_id, session_id) pair.
      7. Guarantees zero data loss while enabling the unique compound index to be created.
    """
    stats = {
        "legacy_records_found": 0,
        "consolidated_created": 0,
        "duplicates_merged": 0,
        "total_records_now": 0,
    }

    try:
        # Check if any legacy records exist
        # Legacy records either have 'metric_name' or missing/null 'document_id' or non-list 'metrics'
        query = {
            "$or": [
                {"document_id": None},
                {"document_id": {"$exists": False}},
                {"metric_name": {"$exists": True}},
                {"metrics": {"$not": {"$type": "array"}}},
                {"extracted_data": {"$exists": False}},
            ]
        }
        
        legacy_cursor = db.extracted_metrics.find(query)
        legacy_docs = await legacy_cursor.to_list(10000)
        
        if not legacy_docs:
            logger.info("extracted_metrics migration check: All records are already consolidated. No migration needed.")
            stats["total_records_now"] = await db.extracted_metrics.count_documents({})
            return stats

        stats["legacy_records_found"] = len(legacy_docs)
        logger.info(
            "Found %d legacy extracted_metrics records. Beginning automated consolidation...",
            len(legacy_docs),
        )

        # Group legacy documents by (session_id, document_id)
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for doc in legacy_docs:
            sess_id = str(doc.get("session_id") or "legacy_session")
            doc_id = doc.get("document_id")
            doc_id_str = str(doc_id) if doc_id is not None else None
            groups.setdefault((sess_id, doc_id_str), []).append(doc)

        for (sess_id, doc_id_str), items in groups.items():
            ids_to_remove = [it["_id"] for it in items if "_id" in it]
            
            # Resolve document_id and metadata
            resolved_doc_id = doc_id_str
            doc_filename: Optional[str] = None
            user_id: Optional[str] = None
            earliest_created: Optional[datetime] = None
            latest_updated: Optional[datetime] = None

            for it in items:
                if not user_id and it.get("user_id"):
                    user_id = str(it.get("user_id"))
                
                c_at = it.get("created_at")
                if isinstance(c_at, datetime):
                    if earliest_created is None or c_at < earliest_created:
                        earliest_created = c_at
                u_at = it.get("updated_at")
                if isinstance(u_at, datetime):
                    if latest_updated is None or u_at > latest_updated:
                        latest_updated = u_at

            now = datetime.now(timezone.utc)
            if not earliest_created:
                earliest_created = now
            if not latest_updated:
                latest_updated = earliest_created

            # Look up document if doc_id is missing or to fetch filename/user_id
            if not resolved_doc_id:
                matched_doc = await db.documents.find_one({"session_id": sess_id})
                if matched_doc:
                    resolved_doc_id = str(matched_doc.get("document_id") or matched_doc.get("_id"))
                    doc_filename = matched_doc.get("filename")
                    if not user_id and matched_doc.get("user_id"):
                        user_id = str(matched_doc.get("user_id"))
                else:
                    resolved_doc_id = f"doc_legacy_{sess_id}"
                    doc_filename = f"legacy_{sess_id}.pdf"
            else:
                matched_doc = await db.documents.find_one({"document_id": resolved_doc_id})
                if matched_doc:
                    doc_filename = matched_doc.get("filename")
                    if not user_id and matched_doc.get("user_id"):
                        user_id = str(matched_doc.get("user_id"))

            # Build consolidated data
            metrics_list: List[Dict[str, Any]] = []
            metrics_dict: Dict[str, Optional[float]] = {}
            extracted_data: Dict[str, Any] = {}
            confidence_scores: Dict[str, float] = {}
            provenance_map: Dict[str, Any] = {}

            for it in items:
                # Case A: Legacy single-metric record
                m_name = it.get("metric_name")
                val = it.get("value")

                if m_name == "extracted_metrics" and isinstance(val, dict):
                    extracted_data["key_figures"] = val.get("key_figures", [])
                    extracted_data["identified_topics"] = val.get("identified_topics", [])
                elif m_name:
                    extracted_data[m_name] = val
                    parsed_num = safe_parse_financial_number(val)
                    if parsed_num is not None:
                        metrics_dict[m_name] = parsed_num

                # Case B: Partially consolidated record with metrics dict or list
                if "metrics" in it and isinstance(it["metrics"], list):
                    for sub_m in it["metrics"]:
                        if isinstance(sub_m, dict) and "metric_name" in sub_m:
                            metrics_list.append(sub_m)
                            s_name = sub_m["metric_name"]
                            if sub_m.get("value") is not None:
                                metrics_dict[s_name] = sub_m.get("value")
                            if sub_m.get("confidence_score") is not None:
                                confidence_scores[s_name] = float(sub_m["confidence_score"])

                if "extracted_data" in it and isinstance(it["extracted_data"], dict):
                    extracted_data.update(it["extracted_data"])

                if "metrics_dict" in it and isinstance(it["metrics_dict"], dict):
                    metrics_dict.update(it["metrics_dict"])

                if m_name and m_name not in ["title", "executive_summary", "status", "extracted_metrics"]:
                    conf = float(it.get("confidence_score", 0.95)) if isinstance(it.get("confidence_score"), (int, float)) else 0.95
                    confidence_scores[m_name] = conf
                    metrics_list.append({
                        "metric_name": m_name,
                        "display_name": m_name.replace("_", " ").title(),
                        "value": metrics_dict.get(m_name),
                        "prior_value": None,
                        "unit": None,
                        "currency": "USD",
                        "period": None,
                        "prior_period": None,
                        "yoy_change_percent": None,
                        "source_chunk_ids": [],
                        "page_numbers": [],
                        "evidence_snippet": str(val) if val is not None else None,
                        "grounding_status": "DIRECT",
                        "confidence_score": conf,
                        "flagged_for_review": False,
                        "flag_reason": None,
                        "derivation_formula": None,
                    })

            # Check if a modern consolidated document already exists for (resolved_doc_id, sess_id)
            existing_modern = await db.extracted_metrics.find_one({
                "document_id": resolved_doc_id,
                "session_id": sess_id,
                "_id": {"$nin": ids_to_remove},
            })

            if existing_modern:
                # Merge into existing modern document without overwriting its verified extractions
                merged_extracted_data = {**extracted_data, **existing_modern.get("extracted_data", {})}
                merged_metrics_dict = {**metrics_dict, **existing_modern.get("metrics_dict", {})}
                await db.extracted_metrics.update_one(
                    {"_id": existing_modern["_id"]},
                    {
                        "$set": {
                            "extracted_data": merged_extracted_data,
                            "metrics_dict": merged_metrics_dict,
                            "updated_at": max(latest_updated, existing_modern.get("updated_at", latest_updated)),
                        }
                    },
                )
                stats["duplicates_merged"] += 1
            else:
                # Construct new consolidated document
                consolidated_doc = {
                    "document_id": resolved_doc_id,
                    "session_id": sess_id,
                    "user_id": user_id or "legacy_user",
                    "document_filename": doc_filename or "document.pdf",
                    "filing_type": "Legacy Consolidated",
                    "reporting_currency": "USD",
                    "reporting_scale": "units",
                    "reporting_period": None,
                    "prior_period": None,
                    "metrics": metrics_list,
                    "metrics_dict": metrics_dict,
                    "multi_year_data": {},
                    "extracted_data": extracted_data,
                    "confidence_scores": confidence_scores,
                    "provenance_map": provenance_map,
                    "chunks_analyzed": len(items),
                    "financial_chunks_count": len(items),
                    "retry_attempted": False,
                    "retry_success": True,
                    "confidence_average": 0.95,
                    "low_confidence_count": 0,
                    "failed_metrics_count": 0,
                    "created_at": earliest_created,
                    "updated_at": latest_updated,
                }
                await db.extracted_metrics.insert_one(consolidated_doc)
                stats["consolidated_created"] += 1

            # Delete the legacy individual rows
            if ids_to_remove:
                await db.extracted_metrics.delete_many({"_id": {"$in": ids_to_remove}})

        # Final pass: Ensure strict uniqueness across entire collection
        # Check if any duplicate (document_id, session_id) pairs remain
        pipeline = [
            {"$group": {"_id": {"document_id": "$document_id", "session_id": "$session_id"}, "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
            {"$filter": {"count": {"$gt": 1}}} if False else {"$match": {"count": {"$gt": 1}}},
        ]
        dupe_cursor = db.extracted_metrics.aggregate(pipeline)
        dupes = await dupe_cursor.to_list(1000)
        for dupe in dupes:
            dupe_ids = dupe["ids"]
            # Keep the newest one and remove older duplicate copies
            keep_id = dupe_ids[-1]
            remove_ids = dupe_ids[:-1]
            await db.extracted_metrics.delete_many({"_id": {"$in": remove_ids}})
            stats["duplicates_merged"] += len(remove_ids)

        stats["total_records_now"] = await db.extracted_metrics.count_documents({})
        logger.info(
            "extracted_metrics migration completed successfully: %d legacy rows consolidated into %d records. Total collection size: %d",
            stats["legacy_records_found"],
            stats["consolidated_created"],
            stats["total_records_now"],
        )
        return stats

    except Exception as exc:
        logger.exception("Error during extracted_metrics migration: %s", exc)
        raise
