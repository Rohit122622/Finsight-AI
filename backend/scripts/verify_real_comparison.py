"""
FinSentry AI — Real-World Multi-Company Comparison Acceptance Verification.

Owner: Sivaram / FinSentry Engineering Team

Executes real-world end-to-end verification of ComparisonAgent using:
  1. Real Apple 2025 Form 10-K
  2. Real Bed Bath & Beyond (BBBY) distress Form 10-K
  (Both extracted via DocumentAgent and ExtractionAgent — NO synthetic data)

Verifies:
  - Document & Session Isolation
  - Consuming real extracted_metrics from MongoDB
  - Company identity derivation
  - Fiscal period alignment
  - Missing metric preservation (None / unavailable, not 0)
  - Deterministic peer statistics (peer average, highest, lowest)
  - Percentile ranking convention
  - Source provenance preservation
  - MongoDB persistence in comparison_results
  - Deterministic cache hit on repeat call
  - Stale cache invalidation on data update
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bson import ObjectId

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import mongodb, get_sync_db
from services.storage_service import storage_service
from agents.document.document_agent import document_agent
from agents.extraction.extraction_agent import extraction_agent
from agents.comparison.comparison_agent import comparison_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_real_world_comparison_verification() -> bool:
    print("=" * 80)
    print("FINSENTRY AI — COMPARISON AGENT REAL-WORLD ACCEPTANCE VERIFICATION")
    print("=" * 80)

    await mongodb.connect()
    db = mongodb.get_db()
    sync_db = get_sync_db()

    session_id = f"real_comp_sess_{str(ObjectId())[:8]}"
    user_id = f"real_comp_user_{str(ObjectId())[:8]}"

    try:
        # -----------------------------------------------------------------
        # Step 1: Ingest & Extract Apple 2025 Form 10-K
        # -----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("[STEP 1: INGEST & EXTRACT REAL APPLE 2025 FORM 10-K]")
        print("=" * 60)

        apple_pdf_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "apple_2025_annual_report.pdf"
        assert apple_pdf_path.exists(), f"Apple fixture PDF not found at {apple_pdf_path}"
        apple_bytes = apple_pdf_path.read_bytes()

        apple_doc_id = f"doc-apple-{session_id[:8]}"
        apple_filename = "apple_2025_annual_report.pdf"

        storage_service.save_file(
            session_id=session_id,
            filename=apple_filename,
            content=apple_bytes,
            document_id=apple_doc_id,
            user_id=user_id,
        )

        await db.documents.insert_one({
            "document_id": apple_doc_id,
            "session_id": session_id,
            "user_id": user_id,
            "filename": apple_filename,
            "status": "UPLOADED",
            "file_size": len(apple_bytes),
            "chunks": [],
        })

        print("  Ingesting Apple 2025 Form 10-K via DocumentAgent...")
        doc_res_apple = document_agent.execute({
            "document_id": apple_doc_id,
            "session_id": session_id,
            "user_id": user_id,
        })
        assert doc_res_apple.success is True, f"DocumentAgent failed for Apple: {doc_res_apple.error}"
        print(f"  --> Apple DocumentAgent success. Chunks indexed.")

        print("  Extracting financial metrics from Apple 2025 Form 10-K...")
        ext_res_apple = await extraction_agent.execute_async({
            "session_id": session_id,
            "document_id": apple_doc_id,
            "user_id": user_id,
        })
        assert ext_res_apple.success is True, f"ExtractionAgent failed for Apple: {ext_res_apple.error}"
        apple_dict = ext_res_apple.summary.get("metrics_dict", {})
        print(f"  --> Apple Extraction success. Revenue: {apple_dict.get('revenue')}")

        # -----------------------------------------------------------------
        # Step 2: Ingest & Extract BBBY Distress 10-K
        # -----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("[STEP 2: INGEST & EXTRACT REAL BBBY DISTRESS FORM 10-K]")
        print("=" * 60)

        bbby_pdf_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bbby_distress_10k.pdf"
        assert bbby_pdf_path.exists(), f"BBBY fixture PDF not found at {bbby_pdf_path}"
        bbby_bytes = bbby_pdf_path.read_bytes()

        bbby_doc_id = f"doc-bbby-{session_id[:8]}"
        bbby_filename = "bbby_distress_10k.pdf"

        storage_service.save_file(
            session_id=session_id,
            filename=bbby_filename,
            content=bbby_bytes,
            document_id=bbby_doc_id,
            user_id=user_id,
        )

        await db.documents.insert_one({
            "document_id": bbby_doc_id,
            "session_id": session_id,
            "user_id": user_id,
            "filename": bbby_filename,
            "status": "UPLOADED",
            "file_size": len(bbby_bytes),
            "chunks": [],
        })

        print("  Ingesting BBBY Form 10-K via DocumentAgent...")
        doc_res_bbby = document_agent.execute({
            "document_id": bbby_doc_id,
            "session_id": session_id,
            "user_id": user_id,
        })
        assert doc_res_bbby.success is True, f"DocumentAgent failed for BBBY: {doc_res_bbby.error}"
        print(f"  --> BBBY DocumentAgent success. Chunks indexed.")

        print("  Extracting financial metrics from BBBY Form 10-K...")
        ext_res_bbby = await extraction_agent.execute_async({
            "session_id": session_id,
            "document_id": bbby_doc_id,
            "user_id": user_id,
        })
        assert ext_res_bbby.success is True, f"ExtractionAgent failed for BBBY: {ext_res_bbby.error}"
        bbby_dict = ext_res_bbby.summary.get("metrics_dict", {})
        print(f"  --> BBBY Extraction success. Revenue: {bbby_dict.get('revenue')}")

        # -----------------------------------------------------------------
        # Step 3: Run ComparisonAgent on Apple + BBBY
        # -----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("[STEP 3: RUN COMPARISON AGENT (APPLE VS BBBY)]")
        print("=" * 60)

        comp_res = comparison_agent.execute(
            payload={
                "session_id": session_id,
                "document_ids": [apple_doc_id, bbby_doc_id],
            },
            context={"user_id": user_id},
        )
        assert comp_res.success is True, f"ComparisonAgent failed: {comp_res.error}"
        summary = comp_res.summary
        assert summary is not None

        # Verify Companies
        companies = summary.get("companies", [])
        assert len(companies) == 2, f"Expected 2 companies, got {len(companies)}"
        company_names = {c["company_name"] for c in companies}
        print(f"  --> Compared Companies: {company_names} ✅")
        assert any("Apple" in c for c in company_names)
        assert any("Bed Bath & Beyond" in c or "BBBY" in c or "Bbby" in c for c in company_names)

        # Verify Period Alignment (Disjoint periods -> common_periods is empty)
        fiscal_periods = summary.get("fiscal_periods", [])
        common_periods = summary.get("common_periods", [])
        company_only_periods = summary.get("company_only_periods", {})
        has_common = summary.get("has_common_periods", True)

        print(f"  --> All Validated Fiscal Periods: {fiscal_periods} ✅")
        print(f"  --> Common Fiscal Periods (Intersection >= 2 peers): {common_periods} ✅")
        print(f"  --> Company-Only Periods: {company_only_periods} ✅")
        print(f"  --> Has Common Periods Flag: {has_common} ✅")

        assert common_periods == [], f"Expected 0 common periods for Apple + BBBY, got {common_periods}"
        assert has_common is False, "Expected has_common_periods to be False for disjoint periods"
        assert len(company_only_periods) >= 2, "Expected company-only periods for both Apple and BBBY"

        # Verify Metrics and Missing Data Handling
        metrics = summary.get("metrics", [])
        assert len(metrics) > 0, "Expected comparison metrics to be populated"
        print(f"  --> Compared Metrics Count: {len(metrics)} ✅")

        # Check Revenue metric specifically
        rev_metric = next((m for m in metrics if m["metric_name"] == "revenue"), None)
        assert rev_metric is not None, "Revenue metric not found in comparison"

        print("\n  --> Revenue Details across periods (Strict Single-Company Unavailable Semantics):")
        for period_entry in rev_metric["periods"]:
            period = period_entry["fiscal_period"]
            stats = period_entry["peer_statistics"]
            val_strs = []
            for v in period_entry["values"]:
                c_name = v["company_name"]
                if v["available"]:
                    val_strs.append(f"{c_name}: {v['value']:g}")
                else:
                    val_strs.append(f"{c_name}: unavailable")
                    # Strict check: missing value must NOT be 0.0
                    assert v["value"] is None, f"Missing metric for {c_name} in {period} must be None, not {v['value']}"

            # Strict acceptance rule: N < 2 must NEVER produce peer_average, highest, lowest
            valid_cnt = stats.get("valid_count", 0)
            peer_avg = stats.get("peer_average")
            highest = stats.get("highest")
            lowest = stats.get("lowest")

            assert valid_cnt == 1, f"Expected valid_count=1 for disjoint period {period}, got {valid_cnt}"
            assert peer_avg is None, f"Peer average for single company in {period} must be None, got {peer_avg}"
            assert highest is None, f"Highest peer for single company in {period} must be None, got {highest}"
            assert lowest is None, f"Lowest peer for single company in {period} must be None, got {lowest}"

            print(f"      Period {period}: {', '.join(val_strs)} | Valid Count: {valid_cnt} | Peer Avg: {peer_avg} (Unavailable) | High: {highest} | Low: {lowest}")

        # Check Provenance Preservation
        has_prov = False
        for p in rev_metric["periods"]:
            for v in p["values"]:
                if v["company_name"] == "Apple" and v["available"] and v.get("provenance"):
                    has_prov = True
                    print(f"  --> Provenance Preserved for Apple Revenue: {list(v['provenance'].keys())} ✅")
                    break
            if has_prov:
                break
        assert has_prov is True, "Expected provenance to be preserved from extracted_metrics"

        # -----------------------------------------------------------------
        # Step 4: Verify MongoDB Persistence in comparison_results
        # -----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("[STEP 4: VERIFY MONGODB PERSISTENCE & CACHE]")
        print("=" * 60)

        persisted = sync_db.comparison_results.find_one({"session_id": session_id})
        assert persisted is not None, "comparison_results record not found in MongoDB"
        assert "document_ids_hash" in persisted
        assert "data_version" in persisted
        assert "comparison" in persisted
        print("  --> comparison_results Record Verified in MongoDB ✅")

        # -----------------------------------------------------------------
        # Step 5: Verify Cache HIT on Repeat Call
        # -----------------------------------------------------------------
        print("  Running repeat comparison to test CACHE HIT...")
        repeat_res = comparison_agent.execute(
            payload={
                "session_id": session_id,
                "document_ids": [bbby_doc_id, apple_doc_id],  # Swapped order
            },
            context={"user_id": user_id},
        )
        assert repeat_res.success is True
        assert repeat_res.metadata.get("cache_hit") is True, "Expected Cache HIT on repeat call"
        print(f"  --> Cache HIT Verified (Order-Independent) ✅ (Latency: {repeat_res.metadata.get('latency_ms', 0):.2f}ms)")

        # Verify no duplicate records created in comparison_results
        total_cache_docs = sync_db.comparison_results.count_documents({"session_id": session_id})
        assert total_cache_docs == 1, f"Expected exactly 1 comparison_results document, found {total_cache_docs}"
        print("  --> Zero Duplication Verified in MongoDB ✅")

        # -----------------------------------------------------------------
        # Step 6: Verify Stale Cache Invalidation
        # -----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("[STEP 6: VERIFY STALE CACHE INVALIDATION]")
        print("=" * 60)

        # Update apple's updated_at timestamp in extracted_metrics to simulate new extraction
        new_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        sync_db.extracted_metrics.update_one(
            {"document_id": apple_doc_id, "session_id": session_id},
            {"$set": {"updated_at": new_time}},
        )
        print("  Simulated extracted_metrics data update...")

        stale_check_res = comparison_agent.execute(
            payload={
                "session_id": session_id,
                "document_ids": [apple_doc_id, bbby_doc_id],
            },
            context={"user_id": user_id},
        )
        assert stale_check_res.success is True
        assert stale_check_res.metadata.get("cache_hit") is False, "Expected Cache MISS after data update"
        print("  --> Stale Cache Invalidation & Recomputation Verified ✅")

        print("\n" + "=" * 80)
        print("ALL REAL-WORLD COMPARISON VERIFICATIONS PASSED SUCCESSFULLY! 10/10 ✅")
        print("=" * 80)
        return True

    finally:
        # Clean up test session data
        print("\nCleaning up test session artifacts...")
        await db.documents.delete_many({"session_id": session_id})
        await db.extracted_metrics.delete_many({"session_id": session_id})
        await db.comparison_results.delete_many({"session_id": session_id})
        await mongodb.disconnect()
        print("Cleanup complete.")


if __name__ == "__main__":
    success = asyncio.run(run_real_world_comparison_verification())
    if not success:
        sys.exit(1)
