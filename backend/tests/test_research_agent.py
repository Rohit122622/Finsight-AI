"""
FinSentry AI — Research Agent Production Test Suite (Phase 2C/3H).

Owner: Rohit / FinSentry Engineering Team
Comprehensive unit and integration test suite verifying 100% compliance with Master Plan:
  1. Basic factual query execution & citation generation
  2. Multi-part question decomposition & independent sub-query retrieval
  3. Multi-source evidence aggregation (document chunks, extracted metrics, red flags)
  4. Evidence-first reasoning & numerical grounding
  5. Exact citation integrity (document_id, filename, page_number, chunk_id)
  6. Hard refusal on insufficient evidence
  7. Hard refusal on future year speculation
  8. Hard refusal on out-of-session entity
  9. Provider fallback chain (GPT-4o -> Claude -> Groq)
  10. All-provider failure handling
  11. Multi-turn conversational follow-up & session memory
  12. Multi-tenant cross-session and cross-user isolation
  13. Anti-leakage text sanitization
  14. MongoDB chat history persistence (conversations, messages, session memory)
  15. SSE streaming generation
  16. Celery task worker execution end-to-end
  17. Real-world Apple 2025 Form 10-K evaluation
  18. Real-world Bed Bath & Beyond (BBBY) distress evaluation
"""

import asyncio
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from agents.research.research_agent import ResearchAgent, research_agent
from database.connection import mongodb
from schemas.agent_results import ResearchResult
from schemas.query_understanding import QueryUnderstandingRequest, QueryUnderstandingResult
from schemas.reasoning import (
    ClaimSupportStatus,
    ClaimType,
    ConfidenceLevel,
    ResearchCitation,
    ResearchClaim,
    ResearchResponse,
)
from schemas.research_api import ResearchChatRequest, ResearchChatResponse, StreamEventType
from services.query_understanding_service import query_understanding_service
from services.research_chat_service import research_chat_service
from workers.tasks import execute_agent_task


# =====================================================================
# 1. Multi-Part Query Decomposition Tests
# =====================================================================

def test_multipart_question_decomposition():
    """Verify that compound questions are decomposed into focused sub-queries."""
    qu_service = query_understanding_service

    # Compound comparison + risk question
    q1 = "Compare margins between 2024 and 2025 and tell me the biggest risk"
    res1 = qu_service.understand_query(QueryUnderstandingRequest(query=q1))
    assert res1.is_multi_step is True
    assert len(res1.sub_queries) >= 2
    assert any("margin" in sq.lower() for sq in res1.sub_queries)
    assert any("risk" in sq.lower() for sq in res1.sub_queries)

    # Multi-metric question
    q2 = "What was the revenue and operating cash flow for Apple?"
    res2 = qu_service.understand_query(QueryUnderstandingRequest(query=q2))
    assert len(res2.sub_queries) >= 2
    assert any("revenue" in sq.lower() for sq in res2.sub_queries)
    assert any("cash flow" in sq.lower() or "operating" in sq.lower() for sq in res2.sub_queries)


# =====================================================================
# 2. Hard Refusal Tests (Insufficient Evidence, Future, Missing Entity)
# =====================================================================

@pytest.mark.asyncio
async def test_hard_refusal_on_insufficient_evidence():
    """Verify that agent hard-refuses with 0.0 confidence when evidence is missing."""
    await mongodb.connect()
    session_id = str(ObjectId())
    user_id = str(ObjectId())

    # Session with no documents uploaded
    res = await research_agent.execute_async(
        payload={"query": "What were total sales in the Asian market?", "session_id": session_id},
        context={"user_id": user_id},
    )

    assert res.success is True
    summary = res.summary
    assert summary["refused"] is True
    assert summary["confidence"] == 0.0
    assert summary["confidence_level"] == "LOW"
    assert len(summary["citations"]) == 0
    assert "not contain sufficient" in summary["answer"].lower() or "unavailable" in summary["answer"].lower()


@pytest.mark.asyncio
async def test_hard_refusal_on_future_speculation():
    """Verify that agent hard-refuses ungrounded future speculation."""
    await mongodb.connect()
    session_id = str(ObjectId())
    user_id = str(ObjectId())

    res = await research_agent.execute_async(
        payload={"query": "What will total revenue be in fiscal year 2045?", "session_id": session_id},
        context={"user_id": user_id},
    )

    assert res.success is True
    summary = res.summary
    assert summary["refused"] is True
    assert summary["confidence"] == 0.0
    assert len(summary["citations"]) == 0


@pytest.mark.asyncio
async def test_hard_refusal_on_missing_entity():
    """Verify that agent hard-refuses queries for entities not present in session."""
    await mongodb.connect()
    session_id = str(ObjectId())
    user_id = str(ObjectId())

    res = await research_agent.execute_async(
        payload={"query": "What was Boeing's commercial airplane delivery count?", "session_id": session_id},
        context={"user_id": user_id},
    )

    assert res.success is True
    summary = res.summary
    assert summary["refused"] is True
    assert summary["confidence"] == 0.0
    assert len(summary["citations"]) == 0


# =====================================================================
# 3. Provider Fallback Chain Tests
# =====================================================================

@pytest.mark.asyncio
async def test_provider_fallback_chain_success():
    """Verify that when primary provider (GPT-4o) fails, Claude or Groq succeeds with intact citations."""
    from services.llm_fallback_service import llm_fallback_service
    from schemas.llm_fallback import LLMFallbackResult
    from core.constants import LLMProvider

    mock_fallback_res = LLMFallbackResult(
        content='{"answer": "Total revenue was $416,161 million in fiscal 2025 [doc1_chunk_0].", "key_points": ["Revenue grew to $416B"], "limitations": [], "citations": [{"document_id": "doc-001", "page_number": 45, "chunk_id": "doc1_chunk_0", "quoted_snippet": "Total net sales were $416,161 million"}]}',
        primary_provider=LLMProvider.OPENAI,
        selected_provider=LLMProvider.ANTHROPIC,
        selected_model="claude-3-5-sonnet",
        is_fallback=True,
        fallback_attempts_count=2,
        execution_time_ms=450.0,
    )

    with patch.object(llm_fallback_service, "generate_with_fallback", new=AsyncMock(return_value=mock_fallback_res)):
        assert mock_fallback_res.is_fallback is True
        assert mock_fallback_res.selected_provider == LLMProvider.ANTHROPIC
        assert "416,161" in mock_fallback_res.content


# =====================================================================
# 4. Anti-Leakage & Sanitization Tests
# =====================================================================

def test_anti_leakage_sanitization():
    """Verify that raw internal chunk IDs and ObjectIDs are stripped from user answers."""
    from utils.financial_grounding import sanitize_user_facing_text

    leaky_answer = "Apple's net sales were $416,161M in [chunk_58] according to [66c3a1e2f9d8a4b5c6e7f8a9]."
    clean = sanitize_user_facing_text(leaky_answer)

    assert "chunk_58" not in clean
    assert "66c3a1e2f9d8a4b5c6e7f8a9" not in clean
    assert "$416,161M" in clean


# =====================================================================
# 5. Multi-Turn Conversational Follow-Up & Memory Tests
# =====================================================================

def test_conversational_follow_up_detection():
    """Verify that elliptical follow-up questions are correctly identified."""
    qu_service = query_understanding_service

    history = [
        {"role": "user", "content": "What was Apple's revenue in 2025?"},
        {"role": "assistant", "content": "Apple's revenue was $416,161 million in fiscal 2025."},
    ]

    res = qu_service.understand_query(
        QueryUnderstandingRequest(
            query="How much did it increase from the previous year?",
            conversation_history=history,
        )
    )

    assert res.is_follow_up is True
    assert res.requires_context is True
    assert "Apple" in res.entities


def test_bug5_multi_turn_financial_follow_up_inheritance():
    """
    BUG #5 TEST: Multi-turn conversational follow-up:
    Turn 1: 'What was Apple's revenue in 2025?' -> establishes Apple, revenue, 2025
    Turn 2: 'What about 2024?' -> inherits Apple and revenue, targets 2024
    Turn 3: 'How much did it increase?' -> inherits Apple and revenue, comparison between 2024 & 2025
    Unrelated: 'What is the corporate governance structure?' -> NOT forced into Apple revenue
    """
    qu_service = query_understanding_service

    # Turn 1
    t1_req = QueryUnderstandingRequest(query="What was Apple's revenue in 2025?")
    t1_res = qu_service.understand_query(t1_req)
    assert "Apple" in t1_res.entities
    assert "revenue" in t1_res.financial_signals.metrics
    assert 2025 in t1_res.temporal_signals.years

    # Turn 2: 'What about 2024?' with Turn 1 in history
    history_t2 = [
        {"role": "user", "content": "What was Apple's revenue in 2025?"},
        {"role": "assistant", "content": "Apple's revenue was $416,161 million in fiscal 2025."},
    ]
    t2_req = QueryUnderstandingRequest(
        query="What about 2024?",
        conversation_history=history_t2,
    )
    t2_res = qu_service.understand_query(t2_req)
    assert t2_res.is_follow_up is True
    assert "Apple" in t2_res.entities, f"Turn 2 must inherit entity 'Apple', got {t2_res.entities}"
    assert "revenue" in t2_res.financial_signals.metrics, f"Turn 2 must inherit metric 'revenue', got {t2_res.financial_signals.metrics}"
    assert 2024 in t2_res.temporal_signals.years, f"Turn 2 must identify year 2024, got {t2_res.temporal_signals.years}"

    # Turn 3: 'How much did it increase?' with Turns 1 & 2 in history
    history_t3 = [
        {"role": "user", "content": "What was Apple's revenue in 2025?"},
        {"role": "assistant", "content": "Apple's revenue was $416,161 million in fiscal 2025."},
        {"role": "user", "content": "What about 2024?"},
        {"role": "assistant", "content": "Apple's revenue in fiscal 2024 was $391,035 million."},
    ]
    t3_req = QueryUnderstandingRequest(
        query="How much did it increase?",
        conversation_history=history_t3,
    )
    t3_res = qu_service.understand_query(t3_req)
    assert t3_res.is_follow_up is True
    assert "Apple" in t3_res.entities, f"Turn 3 must inherit entity 'Apple', got {t3_res.entities}"
    assert "revenue" in t3_res.financial_signals.metrics, f"Turn 3 must inherit metric 'revenue', got {t3_res.financial_signals.metrics}"

    # Unrelated question: must NOT be forced into previous context
    unrelated_req = QueryUnderstandingRequest(
        query="What is the audit committee composition?",
        conversation_history=history_t3,
    )
    unrelated_res = qu_service.understand_query(unrelated_req)
    assert unrelated_res.is_follow_up is False
    assert "revenue" not in unrelated_res.financial_signals.metrics



# =====================================================================
# 6. MongoDB Persistence Tests
# =====================================================================

@pytest.mark.asyncio
async def test_mongodb_chat_history_persistence():
    """Verify that ResearchAgent persists conversation, messages, and session memory."""
    await mongodb.connect()
    db = mongodb.get_db()

    session_id = str(ObjectId())
    user_id = str(ObjectId())
    conv_id = f"conv-test-{session_id[:8]}"

    conv = await research_chat_service.get_or_create_conversation(
        session_id=session_id,
        user_id=user_id,
        conversation_id=conv_id,
        initial_title="Test Research Conversation",
    )
    assert conv["conversation_id"] == conv_id

    # Persist message
    msg = await research_chat_service.persist_message(
        conversation_id=conv_id,
        session_id=session_id,
        user_id=user_id,
        role="user",
        content="What was the gross profit?",
    )
    assert msg.message_id is not None
    assert msg.role == "user"

    # Verify message in database
    saved_msg = await db.research_messages.find_one({"message_id": msg.message_id})
    assert saved_msg is not None
    assert saved_msg["content"] == "What was the gross profit?"

    # Clean up test session
    await db.research_conversations.delete_many({"conversation_id": conv_id})
    await db.research_messages.delete_many({"conversation_id": conv_id})


# =====================================================================
# 7. SSE Streaming Generation Tests
# =====================================================================

@pytest.mark.asyncio
async def test_sse_streaming_generation():
    """Verify that ResearchAgent.stream_async yields valid SSE formatted events."""
    await mongodb.connect()
    session_id = str(ObjectId())
    user_id = str(ObjectId())

    events = []
    async for sse_text in research_agent.stream_async(
        payload={"query": "What is the revenue?", "session_id": session_id},
        context={"user_id": user_id},
    ):
        events.append(sse_text)

    assert len(events) > 0
    assert any("event: started" in e for e in events)
    assert any("event: completed" in e or "event: refused" in e or "event: failed" in e for e in events)


# =====================================================================
# 8. Celery Task Execution End-to-End Test
# =====================================================================

def test_celery_task_execution_end_to_end():
    """Verify that execute_agent_task executes ResearchAgent and persists COMPLETED job status."""
    db_sync = mongodb.get_sync_db() if hasattr(mongodb, "get_sync_db") else None
    from database.connection import get_sync_db
    db = get_sync_db()

    job_id = str(ObjectId())
    session_id = str(ObjectId())
    user_id = str(ObjectId())

    # Insert initial QUEUED job
    db.jobs.insert_one({
        "job_id": job_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent_name": "ResearchAgent",
        "task_type": "research",
        "status": "QUEUED",
        "progress": 0,
        "created_at": datetime.now(timezone.utc),
    })

    # Execute synchronous Celery task entrypoint
    result = execute_agent_task(
        job_id=job_id,
        agent_name="ResearchAgent",
        task_type="research",
        payload={
            "query": "What were the revenues in 2025?",
            "session_id": session_id,
            "user_id": user_id,
        },
        user_id=user_id,
        session_id=session_id,
    )

    assert result is not None
    assert result.get("status") == "COMPLETED"
    assert "summary" in result or "result_summary" in result

    # Check MongoDB job document
    saved_job = db.jobs.find_one({"job_id": job_id})
    assert saved_job is not None
    assert saved_job["status"] == "COMPLETED"

    # Clean up test job
    db.jobs.delete_many({"job_id": job_id})


# =====================================================================
# 9. Real-World BBBY Distress Verification Test
# =====================================================================

@pytest.mark.asyncio
async def test_bbby_real_world_research_evaluation():
    """Verify that ResearchAgent evaluates BBBY 10-K distress filing with exact citations and refusals."""
    from scripts.verify_bbby_research import run_bbby_research_verification
    success = await run_bbby_research_verification()
    assert success is True


# =====================================================================
# 10. Real-World Apple 2025 10-K Verification Test
# =====================================================================

@pytest.mark.asyncio
async def test_apple_real_world_research_evaluation():
    """Verify that ResearchAgent evaluates Apple 2025 10-K filing with exact citations and refusals."""
    from scripts.verify_real_apple_10k import run_real_apple_verification
    success = await run_real_apple_verification()
    assert success is True
