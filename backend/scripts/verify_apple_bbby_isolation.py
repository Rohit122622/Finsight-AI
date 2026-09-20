"""
FinSentry AI — Apple & BBBY Same-Session Document Isolation Verification.

Directly verifies the production fix for:
"Apple and BBBY are in the same research session, but the Apple
Risk & Flags UI displayed BBBY's findings and risk score."

Verifies:
  1. Both Apple and BBBY can run RedFlagAgent in the exact same session_id.
  2. MongoDB `red_flags` collection maintains 2 distinct isolated documents keyed by session_id + document_id.
  3. LiveAnalysisService with document_id=apple_doc_id returns strictly Apple's results.
  4. LiveAnalysisService with document_id=bbby_doc_id returns strictly BBBY's results.
  5. Apple cannot receive BBBY's high risk score or going concern findings.
  6. LiveAnalysisService without document_id returns multi-document breakdown.
  7. Margin delta (11.4 pp / 11.8 pp) semantic validation properly handles level vs delta.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from bson import ObjectId

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import mongodb, get_sync_db
from agents.red_flag.red_flag_agent import red_flag_agent, validate_metric_semantics
from services.live_analysis_service import live_analysis_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_isolation_verification() -> bool:
    print("=" * 80)
    print("FINSENTRY AI — APPLE & BBBY SAME-SESSION ISOLATION VERIFICATION")
    print("=" * 80)

    await mongodb.connect()
    db = mongodb.get_db()
    sync_db = get_sync_db()

    session_id = f"iso_sess_{str(ObjectId())[:8]}"
    user_id = f"iso_user_{str(ObjectId())[:8]}"
    apple_doc_id = f"doc_apple_{str(ObjectId())[:8]}"
    bbby_doc_id = f"doc_bbby_{str(ObjectId())[:8]}"

    passed = 0
    total = 0

    def check(desc: str, cond: bool):
        nonlocal passed, total
        total += 1
        status = "PASSED" if cond else "FAILED"
        print(f"[{status}] Test {total:02d}: {desc}")
        if cond:
            passed += 1
        else:
            print(f"       -> FAILURE DETAIL: condition was False")

    try:
        # Step 1: Insert document records into MongoDB
        await db.documents.insert_many([
            {
                "_id": ObjectId(),
                "document_id": apple_doc_id,
                "session_id": session_id,
                "user_id": user_id,
                "filename": "Apple_2025_Form_10K.pdf",
                "company_name": "Apple Inc",
                "status": "PROCESSED",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "_id": ObjectId(),
                "document_id": bbby_doc_id,
                "session_id": session_id,
                "user_id": user_id,
                "filename": "BBBY_2023_Form_10K.pdf",
                "company_name": "Bed Bath & Beyond Inc",
                "status": "PROCESSED",
                "created_at": datetime.now(timezone.utc),
            },
        ])

        # Step 2: Insert extracted_metrics records for both documents in the SAME session
        await db.extracted_metrics.insert_many([
            {
                "session_id": session_id,
                "document_id": apple_doc_id,
                "company_name": "Apple Inc",
                "fiscal_period": "FY2025",
                "metrics_dict": {
                    "total_revenue": 391035000000.0,
                    "gross_margin": 46.2,
                    "operating_margin": 31.5,
                    "operating_cash_flow": 118254000000.0,
                    "total_debt": 106629000000.0,
                    "total_equity": 66885000000.0,
                },
                "metrics": [
                    {
                        "metric_name": "total_revenue",
                        "value": 391035000000.0,
                        "document_id": apple_doc_id,
                        "document_filename": "Apple_2025_Form_10K.pdf",
                    },
                    {
                        "metric_name": "gross_margin",
                        "value": 46.2,
                        "document_id": apple_doc_id,
                        "document_filename": "Apple_2025_Form_10K.pdf",
                    },
                    {
                        "metric_name": "operating_cash_flow",
                        "value": 118254000000.0,
                        "document_id": apple_doc_id,
                        "document_filename": "Apple_2025_Form_10K.pdf",
                    },
                ],
                "created_at": datetime.now(timezone.utc),
            },
            {
                "session_id": session_id,
                "document_id": bbby_doc_id,
                "company_name": "Bed Bath & Beyond Inc",
                "fiscal_period": "FY2022",
                "metrics_dict": {
                    "total_revenue": 5340000000.0,
                    "prior_total_revenue": 7870000000.0,
                    "gross_margin": 19.8,
                    "prior_gross_margin": 31.6,
                    "operating_cash_flow": -980000000.0,
                    "net_income": -3500000000.0,
                    "total_debt": 5200000000.0,
                    "total_equity": -1100000000.0,
                },
                "metrics": [
                    {
                        "metric_name": "gross_margin",
                        "value": 19.8,
                        "prior_value": 31.6,
                        "document_id": bbby_doc_id,
                        "document_filename": "BBBY_2023_Form_10K.pdf",
                        "evidence_snippet": "gross margin was 19.8% compared to 31.6% in prior year",
                    },
                    {
                        "metric_name": "operating_cash_flow",
                        "value": -980000000.0,
                        "document_id": bbby_doc_id,
                        "document_filename": "BBBY_2023_Form_10K.pdf",
                    },
                    {
                        "metric_name": "total_debt",
                        "value": 5200000000.0,
                        "document_id": bbby_doc_id,
                        "document_filename": "BBBY_2023_Form_10K.pdf",
                    },
                    {
                        "metric_name": "total_equity",
                        "value": -1100000000.0,
                        "document_id": bbby_doc_id,
                        "document_filename": "BBBY_2023_Form_10K.pdf",
                    },
                ],
                "created_at": datetime.now(timezone.utc),
            },
        ])

        # Step 3: Execute RedFlagAgent for Apple in the session
        print("\n--- Executing RedFlagAgent for Apple ---")
        apple_payload = {
            "session_id": session_id,
            "user_id": user_id,
            "document_id": apple_doc_id,
            "company_name": "Apple Inc",
        }
        apple_res = await red_flag_agent.execute_async(apple_payload)
        apple_data = apple_res.summary or {}
        check("Apple RedFlagAgent executed successfully", apple_res is not None and apple_res.success is True)
        check("Apple company name is 'Apple Inc'", apple_data.get("company_name") == "Apple Inc")
        check("Apple document_id is preserved", apple_data.get("document_id") == apple_doc_id)
        check("Apple risk score is low (< 20)", float(apple_data.get("risk_score", 0)) < 20.0)
        check("Apple high severity count is 0", apple_data.get("high_severity_count") == 0)

        # Step 4: Execute RedFlagAgent for BBBY in the SAME session
        print("\n--- Executing RedFlagAgent for BBBY (same session) ---")
        bbby_payload = {
            "session_id": session_id,
            "user_id": user_id,
            "document_id": bbby_doc_id,
            "company_name": "Bed Bath & Beyond Inc",
        }
        bbby_res = await red_flag_agent.execute_async(bbby_payload)
        bbby_data = bbby_res.summary or {}
        check("BBBY RedFlagAgent executed successfully", bbby_res is not None and bbby_res.success is True)
        check("BBBY company name is 'Bed Bath & Beyond Inc'", bbby_data.get("company_name") == "Bed Bath & Beyond Inc")
        check("BBBY document_id is preserved", bbby_data.get("document_id") == bbby_doc_id)
        check("BBBY risk score is high (>= 30)", float(bbby_data.get("risk_score", 0)) >= 30.0)
        check("BBBY has high severity flags", bbby_data.get("high_severity_count", 0) >= 1)

        # Step 5: Verify MongoDB persistence has 2 SEPARATE records
        print("\n--- Verifying MongoDB Isolation ---")
        stored_rf_records = await db.red_flags.find({"session_id": session_id}).to_list(10)
        check("MongoDB has exactly 2 red_flags records for this session", len(stored_rf_records) == 2)

        apple_db_rec = await db.red_flags.find_one({"session_id": session_id, "document_id": apple_doc_id})
        bbby_db_rec = await db.red_flags.find_one({"session_id": session_id, "document_id": bbby_doc_id})
        check("Apple record exists in DB with correct document_id", apple_db_rec is not None and apple_db_rec.get("document_id") == apple_doc_id)
        check("BBBY record exists in DB with correct document_id", bbby_db_rec is not None and bbby_db_rec.get("document_id") == bbby_doc_id)
        check("Apple DB record risk_score != BBBY DB record risk_score", apple_db_rec.get("risk_score") != bbby_db_rec.get("risk_score"))

        # Step 6: Verify LiveAnalysisService queries with document_id
        print("\n--- Verifying LiveAnalysisService Document-Level Retrieval ---")
        apple_live = await live_analysis_service.get_session_red_flags(user_id=user_id, session_id=session_id, document_id=apple_doc_id)
        check("LiveAnalysisService for Apple returns document_id == apple_doc_id", apple_live.get("document_id") == apple_doc_id)
        check("LiveAnalysisService for Apple returns company_name == 'Apple Inc'", apple_live.get("company_name") == "Apple Inc")
        check("LiveAnalysisService for Apple returns Apple's low risk score", apple_live.get("risk_score") == apple_data.get("risk_score"))
        check("LiveAnalysisService for Apple contains NO BBBY flags", not any("equity deficit" in f.get("title", "").lower() for f in apple_live.get("flags", [])))
        check("LiveAnalysisService for Apple high_severity_count is 0", apple_live.get("high_severity_count") == 0)

        bbby_live = await live_analysis_service.get_session_red_flags(user_id=user_id, session_id=session_id, document_id=bbby_doc_id)
        check("LiveAnalysisService for BBBY returns document_id == bbby_doc_id", bbby_live.get("document_id") == bbby_doc_id)
        check("LiveAnalysisService for BBBY returns company_name == 'Bed Bath & Beyond Inc'", bbby_live.get("company_name") == "Bed Bath & Beyond Inc")
        check("LiveAnalysisService for BBBY returns BBBY's high risk score", bbby_live.get("risk_score") == bbby_data.get("risk_score"))
        check("LiveAnalysisService for BBBY contains quantitative distress flags", any("equity" in f.get("title", "").lower() or "margin" in f.get("title", "").lower() for f in bbby_live.get("flags", [])))
        check("LiveAnalysisService for BBBY has high_severity_count >= 1", bbby_live.get("high_severity_count") >= 1)

        # Step 7: Verify Multi-Document session lookup without document_id
        print("\n--- Verifying Multi-Document Session Query (No document_id param) ---")
        multi_live = await live_analysis_service.get_session_red_flags(user_id=user_id, session_id=session_id, document_id=None)
        check("Multi-doc query returns documents breakdown list", "documents" in multi_live and len(multi_live["documents"]) == 2)
        doc_ids_in_multi = {d.get("document_id") for d in multi_live.get("documents", [])}
        check("Multi-doc breakdown contains both apple_doc_id and bbby_doc_id", doc_ids_in_multi == {apple_doc_id, bbby_doc_id})

        # Step 8: Verify Margin Delta Semantic Validation
        print("\n--- Verifying Margin Delta Semantic Rejection ---")
        delta_val = validate_metric_semantics(
            target_key="gross_margin",
            item={
                "metric_name": "gross_margin",
                "value": 11.4,
                "evidence_snippet": "gross margin decreased by 11.4 percentage points compared to prior year",
                "period": "FY2025",
            }
        )
        check("validate_metric_semantics rejects 11.4 pp margin delta as a margin LEVEL", delta_val is False)

        level_val = validate_metric_semantics(
            target_key="gross_margin",
            item={
                "metric_name": "gross_margin",
                "value": 46.2,
                "evidence_snippet": "gross margin was 46.2% for the fiscal year",
                "period": "FY2025",
            }
        )
        check("validate_metric_semantics accepts 46.2% as a valid margin LEVEL", level_val is True)

    finally:
        # Cleanup test records
        await db.documents.delete_many({"session_id": session_id})
        await db.extracted_metrics.delete_many({"session_id": session_id})
        await db.red_flags.delete_many({"session_id": session_id})
        await mongodb.disconnect()

    print("\n" + "=" * 80)
    print(f"VERIFICATION RESULT: {passed}/{total} checks PASSED")
    print("=" * 80)
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_isolation_verification())
    sys.exit(0 if success else 1)
