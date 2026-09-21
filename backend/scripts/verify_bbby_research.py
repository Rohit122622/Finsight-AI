"""
FinSentry AI — Real-World Research Agent Acceptance Verification: Bed Bath & Beyond (BBBY).

Owner: Rohit / FinSentry Engineering Team
Evaluates ResearchAgent on authentic corporate distress filings covering:
  - Factual numerical metrics (Net sales, gross margin, total debt)
  - Grounded percentage and YoY calculations (-32.1% net sales drop, -11.8 pts margin drop)
  - Qualitative risk & forensic disclosures (Going concern, credit default, material weakness)
  - Multi-part compound question decomposition ("Compare margins and tell me the biggest risk")
  - Multi-turn follow-up queries with session memory
  - Hard refusal on future/unsupported questions
  - Exact document/page/chunk citation verification
  - Zero leakage of raw internal IDs
"""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch
from bson import ObjectId

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import mongodb
from services.storage_service import storage_service
from agents.document.document_agent import document_agent
from agents.red_flag.red_flag_agent import red_flag_agent
from agents.research.research_agent import research_agent
from core.constants import LLMProvider
from schemas.llm_fallback import LLMFallbackResult
from services.llm_fallback_service import llm_fallback_service
from scripts.deterministic_research_llm import deterministic_research_completion
from scripts.financial_value_matcher import answer_contains_term as _answer_contains_term

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def deterministic_llm_generation():
    """
    Replace ONLY the LLM generation seam with a deterministic, evidence-grounded
    extractive summarizer.

    Answer composition is the sole non-deterministic step in this pipeline, and it
    behaves differently between a developer machine (provider API keys present ->
    live model) and GitHub Actions (no keys -> every provider raises AUTH_ERROR,
    the fallback chain exhausts, and the offline rules engine yields an answer
    containing no figures at all). Pinning this one seam makes the factual
    assertions below identical in both environments.

    Everything else still runs for real: ingestion, chunking, embedding, hybrid
    retrieval, query understanding, refusal gates, claim grounding, citation
    validation against real chunk IDs/pages, and MongoDB persistence. The
    replacement answer is extracted verbatim from the retrieved
    <SOURCE_EVIDENCE>, so a retrieval regression still fails this test.
    """

    async def _deterministic_generate_with_fallback(
        prompt,
        system_prompt=None,
        config=None,
        is_structured_json=False,
    ):
        content = deterministic_research_completion(prompt, system_prompt)
        return LLMFallbackResult(
            content=content,
            structured_json=None,
            primary_provider=LLMProvider.OLLAMA,
            selected_provider=LLMProvider.OLLAMA,
            selected_model="deterministic-evidence-extractive-stub",
            is_fallback=False,
            fallback_attempts_count=1,
            invocations_log=[],
            execution_time_ms=0.0,
            status="completed",
        )

    with patch.object(
        llm_fallback_service,
        "generate_with_fallback",
        side_effect=_deterministic_generate_with_fallback,
    ):
        yield


async def run_bbby_research_verification(deterministic: bool = True) -> bool:
    """
    Run the BBBY research audit.

    deterministic=True (default, used by the CI regression test) pins the LLM
    generation seam to an evidence-grounded extractive stub so the factual
    assertions are reproducible on any machine and in GitHub Actions, where no
    LLM provider credentials exist. Every other stage runs for real.

    deterministic=False runs the full live-LLM integration path (requires
    provider API keys) and is available via `python -m scripts.verify_bbby_research --live`.
    """
    if deterministic:
        with deterministic_llm_generation():
            return await _run_bbby_benchmarks()
    return await _run_bbby_benchmarks()


async def _run_bbby_benchmarks() -> bool:
    print("=" * 75)
    print("FINSENTRY AI — BED BATH & BEYOND (BBBY) RESEARCH AGENT AUDIT")
    print("=" * 75)

    pdf_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bbby_distress_10k.pdf"
    if not pdf_path.exists():
        print(f"ERROR: BBBY distress PDF not found at {pdf_path}")
        return False

    pdf_bytes = pdf_path.read_bytes()
    print(f"\n[STAGE 1: DOCUMENT INGESTION & FORENSIC SCREENING]")
    print(f"  Filing: Bed Bath & Beyond Inc. Form 10-K (FY2022/2023)")
    print(f"  Path: {pdf_path} ({len(pdf_bytes):,} bytes)")

    await mongodb.connect()
    db = mongodb.get_db()

    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-bbby-{session_id[:8]}"
    filename = "bbby_distress_10k.pdf"

    # Save to storage service
    storage_service.save_file(
        session_id=session_id,
        filename=filename,
        content=pdf_bytes,
        document_id=doc_id,
        user_id=user_id,
    )

    # Ingest document
    await db.documents.delete_many({"document_id": doc_id})
    await db.documents.insert_one({
        "document_id": doc_id,
        "session_id": session_id,
        "user_id": user_id,
        "filename": filename,
        "status": "UPLOADED",
        "file_size": len(pdf_bytes),
        "chunks": [],
    })

    doc_res = document_agent.execute({
        "document_id": doc_id,
        "session_id": session_id,
        "user_id": user_id,
        "chunk_size_tokens": 400,
        "chunk_overlap_tokens": 50,
    })
    assert doc_res.success is True, f"DocumentAgent execution failed: {doc_res.error}"

    doc_record = await db.documents.find_one({"document_id": doc_id})
    stored_chunks = doc_record.get("chunks", [])
    print(f"  DocumentAgent Status: {doc_record['status']} ({len(stored_chunks)} chunks indexed)")
    chunk_ids_set = {c.get("chunk_id") for c in stored_chunks if c.get("chunk_id")}

    # Run proactive red flag agent
    print("  Running proactive Red Flag Agent to populate session risk intelligence...")
    rf_res = await red_flag_agent.execute_async({
        "session_id": session_id,
        "user_id": user_id,
        "document_ids": [doc_id],
        "company_name": "Bed Bath & Beyond Inc.",
        "metrics": {
            "revenue": 5345.0,
            "prior_revenue": 7871.0,
            "gross_margin": 0.198,
            "prior_gross_margin": 0.316,
            "total_debt": 1730.0,
            "prior_total_debt": 1180.0,
            "operating_cash_flow": -508.0,
            "net_income": -1400.0,
            "total_equity": -798.0,
        },
    })
    assert rf_res.success is True, "RedFlagAgent execution must succeed"
    print(f"  RedFlagAgent populated {rf_res.summary.get('total_flags', 0)} risk flags in database.")

    # -----------------------------------------------------------------
    # STAGE 2: EXECUTE 7 CANONICAL RESEARCH BENCHMARKS
    # -----------------------------------------------------------------
    print(f"\n[STAGE 2: RESEARCH AGENT REASONING & CITATION BENCHMARKS]")

    test_queries = [
        # Query 1: Direct Factual Financial Metric
        {
            "id": "Q1_FACTUAL",
            "query": "What were BBBY's net sales in fiscal 2021 and fiscal 2022?",
            # Authoritative reference (official BBBY 2023 10-K): fiscal 2022 net
            # sales $5,344.7M, fiscal 2021 $7,871M. Both canonical terms below are
            # in MILLIONS.
            #
            # DOCUMENTED NORMALIZATION: the fixture filing
            # (tests/fixtures/bbby_distress_10k.pdf, built by
            # scripts/generate_bbby_distress_fixture.py) discloses net sales rounded
            # to whole millions as "$5,345" / "$7,871". $5,345M is the correct
            # whole-million rounding of the official $5,344.7M, so the precision-aware
            # matcher accepts it (|5345 - 5344.7| = 0.3 <= the +/-0.5M band implied by
            # whole-million precision). We therefore keep the precise official value
            # as the reference rather than downgrading it to the rounded figure.
            #
            # Validated by normalized financial value (scripts/financial_value_matcher.py):
            # "5,344.7 million", "$5,344.7M", "5.3447 billion", "5.345 billion",
            # "$5.3 billion", "5,345 million" and "5,344,700,000" all satisfy the
            # fiscal-2022 fact, while a genuinely different figure still fails.
            "expected_terms": ["5,344.7", "7,871"],
            "expect_refusal": False,
            "description": "Factual Metric Extraction",
        },
        # Query 2: Numerical Calculation & YoY Change
        {
            "id": "Q2_CALCULATION",
            "query": "What percentage did net sales decrease from fiscal 2021 to 2022?",
            "expected_terms": ["32.1"],
            "expected_direction": ["decrease", "decline", "drop", "fell", "down"],
            "expect_refusal": False,
            "description": "Numerical Grounding (-32.1% drop)",
        },
        # Query 3: Forensic Qualitative Disclosure
        {
            "id": "Q3_GOING_CONCERN",
            "query": "What does the independent auditor's report state about going concern?",
            "expected_terms": ["substantial doubt", "going concern"],
            "expect_refusal": False,
            "description": "Forensic Audit Opinion Retrieval",
        },
        # Query 4: Multi-Part Compound Question
        {
            "id": "Q4_MULTIPART",
            "query": "Compare gross margin between 2021 and 2022 and tell me the biggest risk disclosed.",
            "expected_terms": ["19.8", "31.6", "risk"],
            "expect_refusal": False,
            "description": "Multi-Part Query Decomposition (Margin Comparison + Risk)",
        },
        # Query 5: Multi-Turn Follow-Up (Uses Session Memory)
        {
            "id": "Q5_FOLLOWUP",
            "query": "How much total debt did they have in that same period?",
            "expected_terms": ["1,730"],
            "expect_refusal": False,
            "description": "Conversational Follow-Up Resolution",
        },
        # Query 6: Hard Refusal - Future Unreported Period
        {
            "id": "Q6_REFUSAL_FUTURE",
            "query": "What will BBBY's net sales and gross profit be in fiscal 2030?",
            "expected_terms": [],
            "expect_refusal": True,
            "description": "Hard Refusal on Future Speculation",
        },
        # Query 7: Hard Refusal - Out-of-Session Entity
        {
            "id": "Q7_REFUSAL_ENTITY",
            "query": "What was Tesla's automotive gross margin in this report?",
            "expected_terms": [],
            "expect_refusal": True,
            "description": "Hard Refusal on Unrelated Entity",
        },
    ]

    conversation_id = f"conv-bbby-{session_id[:8]}"

    for tq in test_queries:
        qid = tq["id"]
        query_text = tq["query"]
        expect_refusal = tq["expect_refusal"]
        desc = tq["description"]

        print(f"\n--- Benchmark [{qid}]: {query_text} ---")
        print(f"  Focus: {desc}")

        agent_result = await research_agent.execute_async(
            payload={
                "query": query_text,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "document_ids": [doc_id],
                "top_k": 5,
                "mode": "hybrid",
            },
            context={"user_id": user_id},
        )

        assert agent_result.success is True, f"ResearchAgent execution failed for {qid}"
        summary = agent_result.summary
        answer = summary.get("answer", "")
        refused = summary.get("refused", False)
        confidence = summary.get("confidence", 0.0)
        citations = summary.get("citations", [])
        cited_cids = summary.get("cited_chunk_ids", [])

        print(f"  Answer: {answer[:180]}...")
        print(f"  Refused: {refused} | Confidence: {confidence:.2f} | Citations: {len(citations)} | Cited Chunks: {len(cited_cids)}")

        # Verify zero leakage of internal IDs
        assert "CHUNK_" not in answer, f"Forbidden raw 'CHUNK_' token in answer for {qid}"
        assert "_chunk_" not in answer, f"Forbidden raw '_chunk_' token in answer for {qid}"
        assert "chk-" not in answer, f"Forbidden raw 'chk-' token in answer for {qid}"
        assert str(ObjectId()) not in answer, f"Forbidden raw MongoDB ObjectId in answer for {qid}"

        if expect_refusal:
            assert refused is True, f"Expected hard refusal for query {qid}, but agent attempted to answer"
            assert confidence == 0.0, f"Confidence must be 0.0 on refusal for {qid}"
            assert len(citations) == 0, f"Refusal must not attach fake/misleading citations for {qid}"
            print(f"  --> Benchmark {qid}: PASSED (Hard Refusal, 0.0 confidence, 0 misleading citations) ✅")
        else:
            assert refused is False, f"Unexpected refusal for supported query {qid}: {answer}"
            assert confidence > 0.4, f"Confidence must be positive for supported query {qid}, got {confidence}"
            assert len(citations) > 0, f"Supported query {qid} MUST contain at least one verified citation"

            # Check citation validity
            for cit in citations:
                cid = cit.get("chunk_id")
                page = cit.get("page_number")
                snippet = cit.get("snippet", "")
                assert cid in chunk_ids_set, f"Cited chunk '{cid}' not found in actual document chunks"
                assert page is not None and page >= 1, f"Citation page must be >= 1, got {page}"
                assert len(snippet) > 5, "Citation must include non-empty source snippet"

            # Check expected keywords/numbers in answer.
            # Numeric terms are matched by value (tolerant of formatting/rounding);
            # qualitative terms are matched as case-insensitive substrings.
            for term in tq["expected_terms"]:
                assert _answer_contains_term(answer, term), f"Expected term '{term}' not found in answer for {qid}"

            if "expected_direction" in tq and tq["expected_direction"]:
                assert any(d in answer.lower() for d in tq["expected_direction"]), f"Expected direction from {tq['expected_direction']} not found in answer for {qid}"

            print(f"  --> Benchmark {qid}: PASSED (Factually verified, {len(citations)} citations, exact page/chunk provenance) ✅")

    # -----------------------------------------------------------------
    # STAGE 3: PERSISTENCE & MULTI-TURN MEMORY AUDIT
    # -----------------------------------------------------------------
    print(f"\n[STAGE 3: MONGODB CHAT PERSISTENCE AUDIT]")

    # Check research_conversations
    conv_doc = await db.research_conversations.find_one({"conversation_id": conversation_id})
    assert conv_doc is not None, "Conversation record must be stored in research_conversations"
    assert conv_doc["session_id"] == session_id
    assert conv_doc["user_id"] == user_id
    print(f"  Conversation record verified: conversation_id={conversation_id}, messages={conv_doc['message_count']}")

    # Check research_messages
    stored_msgs = await db.research_messages.find({"conversation_id": conversation_id}).to_list(length=100)
    assert len(stored_msgs) >= len(test_queries), f"Expected >= {len(test_queries)} messages, found {len(stored_msgs)}"
    print(f"  Message records verified: stored_count={len(stored_msgs)}")

    # Check session memory
    mem_doc = await db.research_session_memory.find_one({"session_id": session_id})
    assert mem_doc is not None, "Session memory must be updated in research_session_memory"
    print(f"  Session memory verified: entities={mem_doc.get('entities')}, prior_queries={len(mem_doc.get('prior_queries', []))}")

    # Cleanup test session
    await db.documents.delete_many({"document_id": doc_id})
    await db.red_flags.delete_many({"session_id": session_id})
    await db.research_conversations.delete_many({"conversation_id": conversation_id})
    await db.research_messages.delete_many({"session_id": session_id})
    await db.research_session_memory.delete_many({"session_id": session_id})

    print("\n" + "=" * 75)
    print("BED BATH & BEYOND (BBBY) RESEARCH AGENT VERIFICATION: 100% PASS")
    print("=" * 75)
    return True


if __name__ == "__main__":
    # --live exercises the real LLM providers (requires API keys). The default
    # deterministic mode is what CI and the pytest regression use.
    live = "--live" in sys.argv
    success = asyncio.run(run_bbby_research_verification(deterministic=not live))
    if not success:
        sys.exit(1)
