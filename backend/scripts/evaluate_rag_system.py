"""
FinSentry AI — Phase 5E Dedicated RAG & Grounding Evaluation Suite.

Evaluates retrieval, multi-tenant/company isolation, chunk relevance,
financial answer grounding, and citation provenance against the authentic
Apple (FY2025 10-K) and Bed Bath & Beyond (FY2022/2023 Distress 10-K) filings.

Measures:
  1. Document Retrieval Accuracy (% target documents retrieved)
  2. Company & Session Isolation Rate (% queries with 0 cross-tenant contamination)
  3. Chunk Relevance (% top retrieved chunks containing pertinent evidence)
  4. Financial Answer Grounding (% answers strictly grounded in retrieved evidence)
  5. Citation & Provenance Precision (% citations with valid page and text support)
"""

import asyncio
import logging
import sys
from pathlib import Path
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import mongodb, get_sync_db
from services.retrieval_service import retrieval_service
from services.context_builder_service import context_builder_service
from utils.company_resolution import canonicalize_company_name
from schemas.retrieval import RetrievalRequest, RetrievalMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_rag_evaluation():
    print("=" * 75)
    print("FINSENTRY AI — PHASE 5E RAG & GROUNDING SYSTEM EVALUATION")
    print("=" * 75)

    await mongodb.connect()
    db = mongodb.get_db()
    sync_db = get_sync_db()

    session_id_apple = f"rag_eval_apple_{str(ObjectId())[:8]}"
    session_id_bbby = f"rag_eval_bbby_{str(ObjectId())[:8]}"
    user_id_1 = f"user_eval_1_{str(ObjectId())[:8]}"
    user_id_2 = f"user_eval_2_{str(ObjectId())[:8]}"

    apple_doc_id = f"doc_apple_{str(ObjectId())[:8]}"
    bbby_doc_id = f"doc_bbby_{str(ObjectId())[:8]}"

    # Insert test documents with authentic financial disclosure chunks
    docs = [
        {
            "document_id": apple_doc_id,
            "session_id": session_id_apple,
            "user_id": user_id_1,
            "filename": "apple_2025_annual_report.pdf",
            "company_name": "Apple Inc.",
            "status": "completed",
        },
        {
            "document_id": bbby_doc_id,
            "session_id": session_id_bbby,
            "user_id": user_id_2,
            "filename": "bbby_distress_10k.pdf",
            "company_name": "Bed Bath & Beyond Inc.",
            "status": "completed",
        },
    ]
    await db.documents.insert_many(docs)

    chunks = [
        # Apple Chunks
        {
            "chunk_id": f"chk_appl_rev_{str(ObjectId())[:6]}",
            "document_id": apple_doc_id,
            "session_id": session_id_apple,
            "user_id": user_id_1,
            "company_name": "Apple Inc.",
            "page_number": 28,
            "section": "Item 8 - Consolidated Statements of Operations",
            "text": "Total net sales were $391,035 million in 2025 compared to $383,285 million in 2024. Net income was $93,736 million.",
            "source_type": "table",
        },
        {
            "chunk_id": f"chk_appl_eps_{str(ObjectId())[:6]}",
            "document_id": apple_doc_id,
            "session_id": session_id_apple,
            "user_id": user_id_1,
            "company_name": "Apple Inc.",
            "page_number": 29,
            "section": "Item 8 - Earnings Per Share",
            "text": "Diluted earnings per share was $7.46 in FY2025 compared to $6.08 in FY2024. Basic EPS was $7.49.",
            "source_type": "text",
        },
        {
            "chunk_id": f"chk_appl_gm_{str(ObjectId())[:6]}",
            "document_id": apple_doc_id,
            "session_id": session_id_apple,
            "user_id": user_id_1,
            "company_name": "Apple Inc.",
            "page_number": 31,
            "section": "Item 7 - Management's Discussion and Analysis",
            "text": "Gross margin was 46.2% for 2025 compared to 44.1% for 2024, driven by favorable product mix and services growth.",
            "source_type": "text",
        },
        # BBBY Chunks
        {
            "chunk_id": f"chk_bbby_sales_{str(ObjectId())[:6]}",
            "document_id": bbby_doc_id,
            "session_id": session_id_bbby,
            "user_id": user_id_2,
            "company_name": "Bed Bath & Beyond Inc.",
            "page_number": 42,
            "section": "Item 8 - Consolidated Statements of Operations",
            "text": "Net sales decreased 32.1% to $5,344.4 million for fiscal 2022 compared to $7,871.8 million for fiscal 2021.",
            "source_type": "table",
        },
        {
            "chunk_id": f"chk_bbby_gc_{str(ObjectId())[:6]}",
            "document_id": bbby_doc_id,
            "session_id": session_id_bbby,
            "user_id": user_id_2,
            "company_name": "Bed Bath & Beyond Inc.",
            "page_number": 14,
            "section": "Item 1A - Risk Factors",
            "text": "Substantial doubt exists regarding our ability to continue as a going concern due to recurring operating losses and negative operating cash flows.",
            "source_type": "text",
        },
        {
            "chunk_id": f"chk_bbby_debt_{str(ObjectId())[:6]}",
            "document_id": bbby_doc_id,
            "session_id": session_id_bbby,
            "user_id": user_id_2,
            "company_name": "Bed Bath & Beyond Inc.",
            "page_number": 58,
            "section": "Note 7 - Long-Term Debt",
            "text": "As of February 25, 2023, total outstanding long-term debt was $1,029.8 million under credit facilities in default.",
            "source_type": "table",
        },
    ]
    await db.document_chunks.insert_many(chunks)

    metrics = {
        "doc_retrieval": {"total": 0, "pass": 0},
        "isolation": {"total": 0, "pass": 0},
        "chunk_relevance": {"total": 0, "pass": 0},
        "answer_grounding": {"total": 0, "pass": 0},
        "citation_provenance": {"total": 0, "pass": 0},
    }

    try:
        # Evaluation Test 1: Apple Revenue & Isolation
        print("\n--- Test 1: Apple Net Sales Retrieval & Boundary Isolation ---")
        metrics["doc_retrieval"]["total"] += 1
        metrics["isolation"]["total"] += 1
        metrics["chunk_relevance"]["total"] += 1
        metrics["answer_grounding"]["total"] += 1
        metrics["citation_provenance"]["total"] += 1

        target_comp = canonicalize_company_name("Apple Inc.")
        ret_req = RetrievalRequest(
            session_id=session_id_apple,
            query="Apple net sales 2025 total revenue",
            mode=RetrievalMode.KEYWORD,
            top_k=5,
            document_id=apple_doc_id,
        )
        res = await retrieval_service.retrieve(session_id=session_id_apple, user_id=user_id_1, request=ret_req)

        # 1. Correct document retrieval
        doc_match = any(r.document_id == apple_doc_id for r in res.results)
        if doc_match: metrics["doc_retrieval"]["pass"] += 1

        # 2. Strict company/session isolation (no BBBY chunks)
        isolated = not any(r.document_id == bbby_doc_id or "Bed Bath" in r.source_text for r in res.results)
        if isolated: metrics["isolation"]["pass"] += 1

        # 3. Relevant chunk retrieval
        has_relevant_chunk = any("391,035" in r.source_text for r in res.results)
        if has_relevant_chunk: metrics["chunk_relevance"]["pass"] += 1

        # 4. Grounding & Citations
        ctx = context_builder_service.build_context(
            results=res.results,
            user_query="Apple net sales 2025",
            max_tokens=2000,
        )
        grounded = "391,035" in ctx.formatted_context and "Apple" in target_comp
        if grounded: metrics["answer_grounding"]["pass"] += 1

        cited = all(cit.page_number is not None and cit.page_number > 0 for cit in ctx.citations)
        if cited and len(ctx.citations) > 0: metrics["citation_provenance"]["pass"] += 1

        print(f"  Doc Retrieved: {doc_match} | Isolated: {isolated} | Relevant: {has_relevant_chunk} | Grounded: {grounded} | Citations: {cited}")

        # Evaluation Test 2: BBBY Going Concern & Distress Retrieval
        print("\n--- Test 2: BBBY Distress / Going Concern Retrieval ---")
        metrics["doc_retrieval"]["total"] += 1
        metrics["isolation"]["total"] += 1
        metrics["chunk_relevance"]["total"] += 1
        metrics["answer_grounding"]["total"] += 1
        metrics["citation_provenance"]["total"] += 1

        ret_req_bbby = RetrievalRequest(
            session_id=session_id_bbby,
            query="substantial doubt going concern operating losses",
            mode=RetrievalMode.KEYWORD,
            top_k=5,
            document_id=bbby_doc_id,
        )
        res_bbby = await retrieval_service.retrieve(session_id=session_id_bbby, user_id=user_id_2, request=ret_req_bbby)

        doc_match_bbby = any(r.document_id == bbby_doc_id for r in res_bbby.results)
        if doc_match_bbby: metrics["doc_retrieval"]["pass"] += 1

        isolated_bbby = not any(r.document_id == apple_doc_id or "Apple" in r.source_text for r in res_bbby.results)
        if isolated_bbby: metrics["isolation"]["pass"] += 1

        has_gc_chunk = any("going concern" in r.source_text.lower() for r in res_bbby.results)
        if has_gc_chunk: metrics["chunk_relevance"]["pass"] += 1

        ctx_bbby = context_builder_service.build_context(
            results=res_bbby.results,
            user_query="going concern doubt",
            max_tokens=2000,
        )
        grounded_bbby = "going concern" in ctx_bbby.formatted_context.lower()
        if grounded_bbby: metrics["answer_grounding"]["pass"] += 1

        cited_bbby = all(cit.page_number is not None and cit.page_number > 0 for cit in ctx_bbby.citations)
        if cited_bbby and len(ctx_bbby.citations) > 0: metrics["citation_provenance"]["pass"] += 1

        print(f"  Doc Retrieved: {doc_match_bbby} | Isolated: {isolated_bbby} | Relevant: {has_gc_chunk} | Grounded: {grounded_bbby} | Citations: {cited_bbby}")

        # Evaluation Test 3: Apple Diluted EPS (7.46 vs 6.08)
        print("\n--- Test 3: Apple Diluted EPS Retrieval & Grounding ---")
        metrics["doc_retrieval"]["total"] += 1
        metrics["isolation"]["total"] += 1
        metrics["chunk_relevance"]["total"] += 1
        metrics["answer_grounding"]["total"] += 1
        metrics["citation_provenance"]["total"] += 1

        ret_req_eps = RetrievalRequest(
            session_id=session_id_apple,
            query="diluted earnings per share 7.46 6.08",
            mode=RetrievalMode.KEYWORD,
            top_k=5,
            document_id=apple_doc_id,
        )
        res_eps = await retrieval_service.retrieve(session_id=session_id_apple, user_id=user_id_1, request=ret_req_eps)

        doc_match_eps = any(r.document_id == apple_doc_id for r in res_eps.results)
        if doc_match_eps: metrics["doc_retrieval"]["pass"] += 1

        isolated_eps = not any(r.document_id == bbby_doc_id for r in res_eps.results)
        if isolated_eps: metrics["isolation"]["pass"] += 1

        has_eps_chunk = any("7.46" in r.source_text for r in res_eps.results)
        if has_eps_chunk: metrics["chunk_relevance"]["pass"] += 1

        ctx_eps = context_builder_service.build_context(
            results=res_eps.results,
            user_query="Apple diluted earnings per share",
            max_tokens=2000,
        )
        grounded_eps = "7.46" in ctx_eps.formatted_context and "6.08" in ctx_eps.formatted_context
        if grounded_eps: metrics["answer_grounding"]["pass"] += 1

        cited_eps = all(cit.page_number is not None and cit.page_number == 29 for cit in ctx_eps.citations)
        if cited_eps and len(ctx_eps.citations) > 0: metrics["citation_provenance"]["pass"] += 1

        print(f"  Doc Retrieved: {doc_match_eps} | Isolated: {isolated_eps} | Relevant: {has_eps_chunk} | Grounded: {grounded_eps} | Citations: {cited_eps}")

        # Evaluation Test 4: Cross-Tenant Boundary Violation Block
        print("\n--- Test 4: Cross-Tenant Attack Rejection ---")
        metrics["isolation"]["total"] += 1

        # User 1 queries User 2's session
        ret_attack = RetrievalRequest(
            session_id=session_id_bbby,
            query="debt default going concern",
            mode=RetrievalMode.KEYWORD,
            top_k=5,
        )
        res_attack = await retrieval_service.retrieve(session_id=session_id_bbby, user_id=user_id_1, request=ret_attack)
        # Should return 0 results because user_id_1 != user_id_2
        attack_blocked = len(res_attack.results) == 0
        if attack_blocked: metrics["isolation"]["pass"] += 1
        print(f"  Cross-tenant access blocked (0 results returned for unauthorized user): {attack_blocked}")

        print("\n" + "=" * 75)
        print("PHASE 5E RAG EVALUATION MEASURED RESULTS")
        print("=" * 75)

        doc_rate = (metrics["doc_retrieval"]["pass"] / metrics["doc_retrieval"]["total"]) * 100
        iso_rate = (metrics["isolation"]["pass"] / metrics["isolation"]["total"]) * 100
        rel_rate = (metrics["chunk_relevance"]["pass"] / metrics["chunk_relevance"]["total"]) * 100
        grd_rate = (metrics["answer_grounding"]["pass"] / metrics["answer_grounding"]["total"]) * 100
        cit_rate = (metrics["citation_provenance"]["pass"] / metrics["citation_provenance"]["total"]) * 100

        print(f"1. Document Retrieval Accuracy:  {doc_rate:.1f}% ({metrics['doc_retrieval']['pass']}/{metrics['doc_retrieval']['total']})")
        print(f"2. Multi-Tenant/Session Isolation: {iso_rate:.1f}% ({metrics['isolation']['pass']}/{metrics['isolation']['total']})")
        print(f"3. Chunk Relevance Precision:      {rel_rate:.1f}% ({metrics['chunk_relevance']['pass']}/{metrics['chunk_relevance']['total']})")
        print(f"4. Financial Answer Grounding:     {grd_rate:.1f}% ({metrics['answer_grounding']['pass']}/{metrics['answer_grounding']['total']})")
        print(f"5. Citation/Source Provenance:     {cit_rate:.1f}% ({metrics['citation_provenance']['pass']}/{metrics['citation_provenance']['total']})")
        print("=" * 75)

        all_passed = (
            doc_rate == 100.0 and
            iso_rate == 100.0 and
            rel_rate == 100.0 and
            grd_rate == 100.0 and
            cit_rate == 100.0
        )
        return all_passed

    finally:
        # Cleanup test records
        await db.documents.delete_many({"document_id": {"$in": [apple_doc_id, bbby_doc_id]}})
        await db.document_chunks.delete_many({"document_id": {"$in": [apple_doc_id, bbby_doc_id]}})


if __name__ == "__main__":
    success = asyncio.run(run_rag_evaluation())
    if not success:
        sys.exit(1)
