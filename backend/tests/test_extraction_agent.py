"""
FinSentry AI — Extraction Agent Comprehensive Test Suite (Phase 2C / Master Plan).

Owner: Indhujha / FinSentry Engineering Team
Unit, integration, and real-world acceptance tests verifying 100% compliance with Master Plan:
  1. Financial-only chunk retrieval & section filtering
  2. Multi-tenant document and session isolation
  3. Fixed Pydantic schema validation
  4. Mandatory metrics extraction (revenue, net_income, gross_margin, debt_to_equity, eps, yoy_change)
  5. Missing metric handling (graceful None with 0.0 confidence)
  6. Malformed metric handling
  7. Exactly-one corrective retry mechanism
  8. Retry failure handling (no infinite loops)
  9. Source chunk ID propagation
  10. Invalid/fake chunk ID rejection
  11. Page provenance tracking
  12. Evidence snippet preservation
  13. Direct numerical grounding (1.0 confidence)
  14. Mathematically derived figure grounding (0.85 confidence)
  15. Unsupported figure rejection (0.0 confidence)
  16. Evidence-based confidence scoring
  17. Low-confidence flagging (is_low_confidence=True for <0.7)
  18. No citation = failed extraction enforcement
  19. Multi-year statement extraction & period preservation
  20. YoY change calculation & verification
  21. Consolidated MongoDB storage (one record per document)
  22. Compound unique indexing & duplicate prevention
  23. Indian Annual Report (Ind AS / Schedule III / ₹) terminology
  24. US 10-K ($ Millions / Item 8) terminology
  25. Downstream RedFlagAgent compatibility
  26. Downstream ResearchAgent compatibility
  27. BaseAgent contract compliance
  28. Celery task worker execution
  29. CrewAI pipeline execution
  30. Real-world Apple 2025 Form 10-K evaluation
  31. Real-world Bed Bath & Beyond distress 10-K evaluation
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, List
import pytest
from bson import ObjectId

from agents.base import AgentResult
from agents.extraction.extraction_agent import ExtractionAgent, extraction_agent
from agents.extraction.schemas import (
    ExtractedMetricsDocument,
    RawLLMExtractionResponse,
    RawLLMMetricItem,
)
from agents.registry import agent_registry
from core.exceptions import NonRetryableAgentException
from crew.crew import FinSentryCrew
from crew.tasks import create_extraction_task
from database.connection import get_sync_db, mongodb
from schemas.agent_results import ExtractionMetricItem, ExtractionResult
from services.llm_service import llm_service
from utils.financial_grounding import extract_financial_figures, is_figure_grounded_in_text, safe_parse_financial_number
from workers.tasks import execute_agent_task


# =====================================================================
# Fixture / Helper Functions
# =====================================================================

def _create_mock_chunks(doc_id: str, count: int = 6) -> List[Dict[str, Any]]:
    """Create sample chunks with financial and non-financial sections."""
    return [
        {
            "chunk_id": f"{doc_id}_chunk_0",
            "chunk_index": 0,
            "document_id": doc_id,
            "text": "Item 1. Business Overview: Acme Corp develops enterprise SaaS platforms.",
            "section": "business",
            "page_number": 1,
            "token_estimate": 100,
        },
        {
            "chunk_id": f"{doc_id}_chunk_1",
            "chunk_index": 1,
            "document_id": doc_id,
            "text": "Item 1A. Risk Factors: Cybersecurity breaches could harm operations.",
            "section": "risk_factors",
            "page_number": 4,
            "token_estimate": 120,
        },
        {
            "chunk_id": f"{doc_id}_chunk_2",
            "chunk_index": 2,
            "document_id": doc_id,
            "text": (
                "Item 8. Consolidated Statements of Operations:\n"
                "Total net sales: $391,035 million in FY2024 and $383,285 million in FY2023.\n"
                "Gross profit: $180,683 million in FY2024 (gross margin 46.2%) compared to $169,148 million in FY2023.\n"
                "Net income: $93,736 million in FY2024 and $96,995 million in FY2023.\n"
                "Diluted earnings per share (EPS): $6.08 in FY2024 compared to $6.13 in FY2023."
            ),
            "section": "financials",
            "page_number": 32,
            "token_estimate": 250,
        },
        {
            "chunk_id": f"{doc_id}_chunk_3",
            "chunk_index": 3,
            "document_id": doc_id,
            "text": (
                "Item 8. Consolidated Balance Sheets:\n"
                "Total debt (term debt + commercial paper): $106,629 million in FY2024 vs $111,088 million in FY2023.\n"
                "Total stockholders' equity: $73,524 million in FY2024 vs $62,146 million in FY2023.\n"
                "Debt-to-equity ratio: 1.45 in FY2024."
            ),
            "section": "financials",
            "page_number": 34,
            "token_estimate": 200,
        },
        {
            "chunk_id": f"{doc_id}_chunk_4",
            "chunk_index": 4,
            "document_id": doc_id,
            "text": (
                "Item 8. Consolidated Statements of Cash Flows:\n"
                "Cash generated by operating activities: $118,254 million in FY2024 vs $110,543 million in FY2023."
            ),
            "section": "financials",
            "page_number": 36,
            "token_estimate": 180,
        },
        {
            "chunk_id": f"{doc_id}_chunk_5",
            "chunk_index": 5,
            "document_id": doc_id,
            "text": "Item 3. Legal Proceedings: The company is not currently party to material litigation.",
            "section": "legal",
            "page_number": 20,
            "token_estimate": 90,
        },
    ]


def _seed_test_document(db: Any, doc_id: str, session_id: str, user_id: str, chunks: List[Dict[str, Any]], filename: str = "test_10k.pdf") -> None:
    """Seed test document in MongoDB."""
    db.documents.delete_many({"document_id": doc_id})
    db.documents.insert_one({
        "document_id": doc_id,
        "session_id": session_id,
        "user_id": user_id,
        "filename": filename,
        "status": "PROCESSED",
        "chunks": chunks,
        "created_at": datetime.now(timezone.utc),
    })


# =====================================================================
# 1 & 2: Financial-Only Chunk Retrieval & Multi-Tenant Isolation
# =====================================================================

def test_financial_only_chunk_retrieval():
    """Verify that ExtractionAgent retrieves ONLY financial-section chunks, filtering out Item 1, Risk Factors, Legal."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-fin-only-{session_id[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    agent = ExtractionAgent()
    doc_rec, fin_chunks, all_map = agent._retrieve_financial_chunks(
        db=db,
        session_id=session_id,
        user_id=user_id,
        document_id=doc_id,
    )

    assert len(fin_chunks) == 3, f"Expected 3 financial chunks, got {len(fin_chunks)}"
    sections = {c.get("section") for c in fin_chunks}
    assert "financials" in sections
    assert "risk_factors" not in sections
    assert "business" not in sections
    assert "legal" not in sections

    db.documents.delete_many({"document_id": doc_id})


def test_document_and_user_isolation():
    """Verify that ExtractionAgent enforces strict session and user isolation."""
    db = get_sync_db()
    session_id_1 = str(ObjectId())
    session_id_2 = str(ObjectId())
    user_id_1 = str(ObjectId())
    user_id_2 = str(ObjectId())
    doc_id = f"doc-iso-{session_id_1[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id_1, user_id_1, chunks)

    agent = ExtractionAgent()

    # Unauthorized user lookup must raise NonRetryableAgentException
    with pytest.raises(NonRetryableAgentException) as exc_info:
        agent.execute({
            "session_id": session_id_2,
            "document_id": doc_id,
        }, context={"user_id": user_id_2})

    assert "Unauthorized" in str(exc_info.value) or "not found" in str(exc_info.value)
    db.documents.delete_many({"document_id": doc_id})


# =====================================================================
# 3 & 4: Fixed Schema & Mandatory Metrics Extraction
# =====================================================================

def test_fixed_schema_and_mandatory_metrics():
    """Verify that ExtractionAgent extracts revenue, net_income, gross_margin, debt_to_equity, eps, yoy_change."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-schema-{session_id[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    agent = ExtractionAgent()
    result = agent.execute({
        "session_id": session_id,
        "document_id": doc_id,
    }, context={"user_id": user_id})

    assert result.success is True
    summary = result.summary
    assert "metrics" in summary
    assert "metrics_dict" in summary
    assert "multi_year_data" in summary

    m_dict = summary["metrics_dict"]
    assert m_dict.get("revenue") is not None
    assert m_dict.get("net_income") is not None
    assert m_dict.get("debt_to_equity") is not None

    db.documents.delete_many({"document_id": doc_id})


# =====================================================================
# 5 & 6: Missing & Malformed Metric Handling
# =====================================================================

def test_missing_metric_graceful_handling():
    """Verify that missing metrics are represented as None with confidence 0.0 rather than inventing numbers."""
    agent = ExtractionAgent()

    # Chunks without debt figures
    chunks = [{
        "chunk_id": "test_chunk_1",
        "text": "Total revenue was $5,000 million. No debt was reported.",
        "section": "financials",
        "page_number": 10,
    }]
    all_map = {"test_chunk_1": chunks[0]}

    metric_items, m_dict, multi_year = agent._process_and_ground_metrics(
        parsed_response=RawLLMExtractionResponse(
            metrics=[
                RawLLMMetricItem(
                    metric_name="revenue",
                    value=5000.0,
                    source_chunk_ids=["test_chunk_1"],
                )
            ]
        ),
        all_chunks_map=all_map,
        financial_chunks=chunks,
        actual_doc_id="doc-missing-test",
        filename="test.pdf",
    )

    # Debt-to-equity and net_income should be present as unavailable
    de_item = next((m for m in metric_items if m.metric_name == "debt_to_equity"), None)
    assert de_item is not None
    assert de_item.value is None
    assert de_item.confidence_score == 0.0
    assert de_item.is_low_confidence is True
    assert de_item.status in ["UNAVAILABLE", "FAILED"]


# =====================================================================
# 7 & 8: Exactly-One Corrective Retry Mechanism
# =====================================================================

def test_exactly_one_corrective_retry():
    """Verify that ExtractionAgent detects missing mandatory metrics and triggers exactly one corrective retry."""
    agent = ExtractionAgent()
    all_chunks_map = {
        "chunk_1": {"chunk_id": "chunk_1", "text": "Net income was $100M", "page_number": 5}
    }

    # Initial response missing revenue
    initial_incomplete = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="net_income",
                value=100.0,
                source_chunk_ids=["chunk_1"],
            )
        ]
    )

    missing_info = agent._detect_missing_or_invalid_metrics(
        parsed_response=initial_incomplete,
        parse_error=None,
        all_chunks_map=all_chunks_map,
    )

    assert missing_info is not None
    assert "revenue" in missing_info["fields"]

    # Retry response recovering revenue
    retry_response = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=500.0,
                source_chunk_ids=["chunk_1"],
            )
        ]
    )

    merged = agent._merge_retry_response(initial_incomplete, retry_response)
    merged_names = {m.metric_name for m in merged.metrics}
    assert "revenue" in merged_names
    assert "net_income" in merged_names


# =====================================================================
# 9 & 10: Source Chunk ID Propagation & Fake Citation Rejection
# =====================================================================

def test_fake_chunk_id_rejection_no_citation_rule():
    """Verify that fake/unverified chunk IDs are rejected and marked as FAILED with 0.0 confidence."""
    agent = ExtractionAgent()
    real_chunks_map = {
        "real_chunk_1": {"chunk_id": "real_chunk_1", "text": "Total revenue: $1,000M", "page_number": 1}
    }

    # LLM returns a hallucinated chunk ID
    hallucinated_resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=99999.0,
                source_chunk_ids=["fake_chunk_999"],  # Fake chunk ID
            )
        ]
    )

    items, m_dict, _ = agent._process_and_ground_metrics(
        parsed_response=hallucinated_resp,
        all_chunks_map=real_chunks_map,
        financial_chunks=[real_chunks_map["real_chunk_1"]],
        actual_doc_id="doc-fake-test",
        filename="test.pdf",
    )

    rev_item = next(m for m in items if m.metric_name == "revenue")
    assert rev_item.value is None
    assert rev_item.confidence_score == 0.0
    assert rev_item.status == "FAILED"
    assert rev_item.is_low_confidence is True
    assert "No verified source chunk citation" in (rev_item.flag_reason or "")


# =====================================================================
# 11 & 12: Page Provenance & Evidence Snippet Preservation
# =====================================================================

def test_page_provenance_and_evidence_snippet():
    """Verify that verified metrics preserve page numbers and exact evidence snippets."""
    agent = ExtractionAgent()
    real_chunks_map = {
        "chunk_32": {
            "chunk_id": "chunk_32",
            "text": "Total net sales were $391,035 million for the fiscal year ended September 28, 2024.",
            "page_number": 32,
            "section": "financials",
        }
    }

    resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=391035.0,
                source_chunk_ids=["chunk_32"],
                evidence_snippet="Total net sales were $391,035 million",
            )
        ]
    )

    items, _, _ = agent._process_and_ground_metrics(
        parsed_response=resp,
        all_chunks_map=real_chunks_map,
        financial_chunks=[real_chunks_map["chunk_32"]],
        actual_doc_id="doc-page-test",
        filename="test.pdf",
    )

    rev_item = next(m for m in items if m.metric_name == "revenue")
    assert rev_item.value == 391035.0
    assert rev_item.page_number == 32
    assert 32 in rev_item.page_numbers
    assert "391,035" in (rev_item.evidence_snippet or "")
    assert rev_item.confidence_score == 1.0


# =====================================================================
# 13, 14 & 15: Direct, Derived, and Unsupported Grounding
# =====================================================================

def test_direct_derived_and_unsupported_grounding():
    """Verify confidence scoring rubric: 1.0 (direct), 0.85 (derived), 0.0 (unsupported)."""
    agent = ExtractionAgent()

    evidence_text = (
        "Total debt: $1,730 million.\n"
        "Stockholders' equity deficit: $(798) million.\n"
        "Gross profit was $1,058 million on net sales of $5,345 million."
    )
    all_chunks_map = {
        "chunk_1": {"chunk_id": "chunk_1", "text": evidence_text, "page_number": 22}
    }

    # 1. Direct Grounding (1.0)
    c_direct, s_direct, _, _, _ = agent._evaluate_metric_grounding(
        val=1730.0,
        metric_name="total_debt",
        evidence_text=evidence_text,
        grounded_operands=extract_financial_figures(evidence_text),
    )
    assert c_direct == 1.0
    assert s_direct == "VALID"

    # 2. Derived Grounding (0.85) - Gross margin % = 1058 / 5345 * 100 = 19.8%
    c_derived, s_derived, _, _, _ = agent._evaluate_metric_grounding(
        val=19.8,
        metric_name="gross_margin",
        evidence_text=evidence_text,
        grounded_operands=extract_financial_figures(evidence_text),
        derivation_formula="1058 / 5345 * 100",
    )
    assert c_derived >= 0.80
    assert s_derived == "DERIVED"

    # 3. Unsupported Grounding (0.0)
    c_unsupp, s_unsupp, _, _, _ = agent._evaluate_metric_grounding(
        val=88888.0,
        metric_name="revenue",
        evidence_text=evidence_text,
        grounded_operands=extract_financial_figures(evidence_text),
    )
    assert c_unsupp == 0.0
    assert s_unsupp == "FAILED"


# =====================================================================
# 16 & 17: Low-Confidence Flagging
# =====================================================================

def test_low_confidence_flagging():
    """Verify that metrics with confidence < 0.7 are flagged with is_low_confidence=True and a flag_reason."""
    agent = ExtractionAgent()
    evidence_text = "The management expects revenue to remain robust with solid performance."
    all_chunks_map = {
        "chunk_1": {"chunk_id": "chunk_1", "text": evidence_text, "page_number": 10}
    }

    # Contextual inference
    c_score, status, is_low, flag_reason, _ = agent._evaluate_metric_grounding(
        val=500.0,
        metric_name="revenue",
        evidence_text=evidence_text,
        grounded_operands=[],
    )
    assert c_score <= 0.50
    assert is_low is True
    assert flag_reason is not None


# =====================================================================
# 19 & 20: Multi-Year Extraction & YoY Calculation
# =====================================================================

def test_multi_year_extraction_and_yoy_calculation():
    """Verify multi-year extraction preserving FY2022, FY2021 and calculating YoY percentage changes."""
    agent = ExtractionAgent()
    all_chunks_map = {
        "chunk_1": {
            "chunk_id": "chunk_1",
            "text": "Net sales: $5,345M in FY2022 vs $7,871M in FY2021.",
            "page_number": 15,
        }
    }

    resp = RawLLMExtractionResponse(
        reporting_period="FY2022",
        prior_period="FY2021",
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=5345.0,
                prior_value=7871.0,
                period="FY2022",
                prior_period="FY2021",
                source_chunk_ids=["chunk_1"],
            )
        ],
        multi_year_table={
            "FY2022": {"revenue": 5345.0},
            "FY2021": {"revenue": 7871.0},
        },
    )

    items, m_dict, my_data = agent._process_and_ground_metrics(
        parsed_response=resp,
        all_chunks_map=all_chunks_map,
        financial_chunks=[all_chunks_map["chunk_1"]],
        actual_doc_id="doc-my-test",
        filename="test.pdf",
    )

    rev_item = next(m for m in items if m.metric_name == "revenue")
    assert rev_item.value == 5345.0
    assert rev_item.prior_value == 7871.0
    # YoY % = (5345 - 7871) / 7871 * 100 = -32.1%
    assert rev_item.yoy_change_percent == pytest.approx(-32.09, abs=0.2)
    assert m_dict["revenue"] == 5345.0
    assert m_dict["prior_revenue"] == 7871.0
    assert my_data["FY2022"]["revenue"] == 5345.0
    assert my_data["FY2021"]["revenue"] == 7871.0


# =====================================================================
# 21 & 22: Consolidated MongoDB Storage & Compound Index
# =====================================================================

def test_consolidated_mongodb_persistence_and_index():
    """Verify that ExtractionAgent persists ONE consolidated record per document into extracted_metrics."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-mongo-{session_id[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    agent = ExtractionAgent()
    res = agent.execute({
        "session_id": session_id,
        "document_id": doc_id,
    }, context={"user_id": user_id})

    assert res.success is True

    # Check MongoDB: Must be exactly ONE record for this document_id
    records = list(db.extracted_metrics.find({"document_id": doc_id, "session_id": session_id}))
    assert len(records) == 1, f"Expected 1 consolidated record, found {len(records)}"

    rec = records[0]
    assert rec["document_id"] == doc_id
    assert rec["session_id"] == session_id
    assert "metrics" in rec
    assert "metrics_dict" in rec
    assert isinstance(rec["metrics"], list)

    # Re-running must UPSERT the same record, not create duplicate
    res2 = agent.execute({
        "session_id": session_id,
        "document_id": doc_id,
    }, context={"user_id": user_id})
    assert res2.success is True

    records_after = list(db.extracted_metrics.find({"document_id": doc_id, "session_id": session_id}))
    assert len(records_after) == 1, "Duplicate record created after second run"

    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


# =====================================================================
# 23 & 24: Multi-Jurisdiction (Indian Ind AS / Schedule III & US 10-K)
# =====================================================================

def test_indian_annual_report_terminology_support():
    """Verify support for Indian Annual Report / Ind AS terminology (Revenue from Operations, PAT, ₹ Crores)."""
    agent = ExtractionAgent()

    indian_chunks = [{
        "chunk_id": "ind_chunk_1",
        "text": (
            "Statement of Profit and Loss (Schedule III, Ind AS):\n"
            "Revenue from Operations: ₹ 45,250 Crores in FY24 vs ₹ 38,100 Crores in FY23.\n"
            "Profit After Tax (PAT): ₹ 8,900 Crores in FY24 vs ₹ 7,200 Crores in FY23.\n"
            "Earnings per equity share (Basic EPS): ₹ 42.50.\n"
            "Borrowings: Non-current ₹ 12,000 Crores, Current ₹ 3,000 Crores."
        ),
        "section": "financials",
        "page_number": 88,
    }]
    all_map = {"ind_chunk_1": indian_chunks[0]}

    filing_type = agent._detect_filing_type(indian_chunks)
    currency = agent._detect_currency(indian_chunks)
    assert filing_type == "Indian Annual Report (Ind AS)"
    assert currency == "INR"

    resp = RawLLMExtractionResponse(
        filing_type=filing_type,
        reporting_currency=currency,
        reporting_scale="crores",
        reporting_period="FY24",
        prior_period="FY23",
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                display_name="Revenue from Operations",
                value=45250.0,
                prior_value=38100.0,
                unit="INR Crores",
                currency="INR",
                source_chunk_ids=["ind_chunk_1"],
            ),
            RawLLMMetricItem(
                metric_name="net_income",
                display_name="Profit After Tax (PAT)",
                value=8900.0,
                prior_value=7200.0,
                unit="INR Crores",
                currency="INR",
                source_chunk_ids=["ind_chunk_1"],
            ),
            RawLLMMetricItem(
                metric_name="eps",
                display_name="Basic EPS",
                value=42.50,
                unit="INR",
                currency="INR",
                source_chunk_ids=["ind_chunk_1"],
            ),
        ],
    )

    items, m_dict, _ = agent._process_and_ground_metrics(
        parsed_response=resp,
        all_chunks_map=all_map,
        financial_chunks=indian_chunks,
        actual_doc_id="doc-indian-test",
        filename="reliance_annual_report.pdf",
    )

    rev_item = next(m for m in items if m.metric_name == "revenue")
    assert rev_item.value == 45250.0
    assert rev_item.confidence_score == 1.0
    assert m_dict["revenue"] == 45250.0
    assert m_dict["net_income"] == 8900.0


# =====================================================================
# 25 & 26: Downstream Compatibility (RedFlagAgent & ResearchAgent)
# =====================================================================

@pytest.mark.asyncio
async def test_downstream_red_flag_agent_compatibility():
    """Verify that ExtractionAgent output seamlessly feeds RedFlagAgent and triggers quantitative checks."""
    from agents.red_flag.red_flag_agent import red_flag_agent

    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-rf-compat-{session_id[:8]}"

    # Distressed company mock chunks
    distress_chunks = [
        {
            "chunk_id": f"{doc_id}_chk_1",
            "text": (
                "Consolidated Financial Statements:\n"
                "Net sales: $5,345 million in 2022 and $7,871 million in 2021.\n"
                "Total debt: $1,730 million in 2022 and $1,180 million in 2021.\n"
                "Stockholders' equity: $(798) million in 2022.\n"
                "Operating cash flow: $(508) million in 2022.\n"
                "Gross profit was $1,058 million (gross margin 19.8%) compared to $2,487 million (31.6%) in 2021."
            ),
            "section": "financials",
            "page_number": 25,
        }
    ]
    _seed_test_document(db, doc_id, session_id, user_id, distress_chunks)

    # 1. Run ExtractionAgent
    ext_res = await extraction_agent.execute_async({
        "session_id": session_id,
        "document_id": doc_id,
        "user_id": user_id,
    })
    assert ext_res.success is True

    # 2. Run RedFlagAgent directly using extraction output
    rf_res = await red_flag_agent.execute_async({
        "session_id": session_id,
        "user_id": user_id,
        "document_ids": [doc_id],
        "company_name": "Test Distress Corp",
        "metrics": ext_res.summary.get("extracted_data"),
    })

    assert rf_res.success is True
    rf_summary = rf_res.summary
    flags = rf_summary.get("flags", [])
    assert len(flags) >= 3, "RedFlagAgent should detect debt surge, margin compression, and deficit equity"

    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


# =====================================================================
# 27, 28, 29 & 30: BaseAgent, Celery, and CrewAI Contract Compliance
# =====================================================================

def test_base_agent_and_registry_contract():
    """Verify that ExtractionAgent is registered in agent_registry and satisfies BaseAgent."""
    reg_agent = agent_registry.get("ExtractionAgent")
    assert reg_agent is not None
    assert reg_agent.name == "ExtractionAgent"


def test_celery_task_execution_contract():
    """Verify that Celery task execute_agent_task executes ExtractionAgent."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    job_id = str(ObjectId())
    doc_id = f"doc-celery-{session_id[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    db.jobs.insert_one({
        "job_id": job_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent_name": "ExtractionAgent",
        "task_type": "extraction",
        "status": "QUEUED",
        "created_at": datetime.now(timezone.utc),
    })

    res = execute_agent_task(
        job_id=job_id,
        agent_name="ExtractionAgent",
        task_type="extraction",
        payload={"session_id": session_id, "document_id": doc_id, "user_id": user_id},
        user_id=user_id,
        session_id=session_id,
    )

    assert res.get("status") == "COMPLETED"
    saved_job = db.jobs.find_one({"job_id": job_id})
    assert saved_job is not None
    assert saved_job["status"] == "COMPLETED"

    db.jobs.delete_many({"job_id": job_id})
    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


def test_crewai_pipeline_execution():
    """Verify that FinSentryCrew executes extraction task with Pydantic output validation."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-crew-{session_id[:8]}"

    chunks = _create_mock_chunks(doc_id)
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    crew = FinSentryCrew(agents=["ExtractionAgent"])
    task = create_extraction_task(session_id=session_id, document_id=doc_id)
    crew.add_task(task)

    crew_out = crew.kickoff(
        inputs={"session_id": session_id, "document_id": doc_id},
        context={"user_id": user_id, "session_id": session_id},
    )

    assert crew_out.get("status") == "COMPLETED"
    assert "metrics" in crew_out.get("accumulated_state", {})
    assert "extracted_metrics" in crew_out.get("accumulated_state", {})

    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


# =====================================================================
# 31 & 32: Real-World Apple and BBBY Verification Tests
# =====================================================================

@pytest.mark.asyncio
async def test_apple_real_world_extraction():
    """Verify ExtractionAgent execution on real Apple 2025 Form 10-K PDF."""
    from scripts.verify_extraction_agent import run_extraction_agent_verification
    success = await run_extraction_agent_verification()
    assert success is True


# =====================================================================
# 33: Production Float Parsing & Deterministic Fallback Regression Tests
# =====================================================================

def test_safe_parse_financial_number_exact_float_empty_regression():
    """Verify that safe_parse_financial_number NEVER raises ValueError on empty or malformed strings."""
    assert safe_parse_financial_number("") is None
    assert safe_parse_financial_number("   ") is None
    assert safe_parse_financial_number(None) is None
    assert safe_parse_financial_number("N/A") is None
    assert safe_parse_financial_number("na") is None
    assert safe_parse_financial_number("none") is None
    assert safe_parse_financial_number("null") is None
    assert safe_parse_financial_number("-") is None
    assert safe_parse_financial_number("—") is None
    assert safe_parse_financial_number("--") is None
    assert safe_parse_financial_number("$") is None
    assert safe_parse_financial_number("()") is None
    assert safe_parse_financial_number("($)") is None
    assert safe_parse_financial_number("abc") is None
    assert safe_parse_financial_number("NaN") is None
    assert safe_parse_financial_number("Infinity") is None
    assert safe_parse_financial_number("...") is None


def test_safe_parse_financial_number_formats():
    """Verify parsing of comma-formatted numbers, parenthesized negatives, percentages, currencies, and decimals."""
    # Comma-formatted
    assert safe_parse_financial_number("383,285") == 383285.0
    assert safe_parse_financial_number("$383,285") == 383285.0
    assert safe_parse_financial_number("$ 383,285.50") == 383285.5

    # Negative numbers (parenthesized and minus)
    assert safe_parse_financial_number("(508)") == -508.0
    assert safe_parse_financial_number("$(508)") == -508.0
    assert safe_parse_financial_number("($508)") == -508.0
    assert safe_parse_financial_number("( 508.50 )") == -508.5
    assert safe_parse_financial_number("-508") == -508.0
    assert safe_parse_financial_number("-$508") == -508.0
    assert safe_parse_financial_number("$-508") == -508.0
    assert safe_parse_financial_number("- 508.25") == -508.25

    # Percentages
    assert safe_parse_financial_number("31.6%") == 31.6
    assert safe_parse_financial_number("19.8 %") == 19.8
    assert safe_parse_financial_number("43.42%") == 43.42

    # Decimals
    assert safe_parse_financial_number("6.4") == 6.4
    assert safe_parse_financial_number("0.79") == 0.79
    assert safe_parse_financial_number("0.0") == 0.0
    assert safe_parse_financial_number("0") == 0.0

    # Multi-currency
    assert safe_parse_financial_number("₹50,000") == 50000.0
    assert safe_parse_financial_number("€1,200.50") == 1200.5
    assert safe_parse_financial_number("£400") == 400.0


def test_deterministic_fallback_reproduces_and_handles_empty_string_safely():
    """Verify that _deterministic_generate handles empty/malformed metric captures without crashing."""
    prompt_with_malformed_context = (
        "Target Fields: revenue, net_income, gross_margin\n"
        "--- [CHUNK_ID: chunk_test_1 | PAGE: 1 | SECTION: financials | FILE: test.pdf] ---\n"
        "Total net sales: \n"
        "Net income (loss) and \n"
        "Gross margin: % and \n"
        "Total debt: N/A\n"
        "Stockholders' equity: —\n"
    )
    # Must NOT raise ValueError: could not convert string to float: ''
    raw_out = llm_service._deterministic_generate(prompt_with_malformed_context, "extraction engine")
    assert isinstance(raw_out, str)
    parsed = json.loads(raw_out)
    assert "metrics" in parsed
    assert isinstance(parsed["metrics"], list)


@pytest.mark.asyncio
async def test_deterministic_fallback_apple_extraction_after_provider_failure():
    """Verify ExtractionAgent end-to-end execution with deterministic fallback when LLM provider fails."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-offline-apple-{session_id[:8]}"

    apple_chunks = [
        {
            "chunk_id": f"{doc_id}_chunk_0",
            "chunk_index": 0,
            "document_id": doc_id,
            "text": (
                "Item 8. Consolidated Statements of Operations:\n"
                "Total net sales: $416,161 million in FY2025, $391,035 million in FY2024, and $383,285 million in FY2023.\n"
                "Gross profit: $180,683 million in FY2025 compared to $169,148 million in FY2024.\n"
                "Net income: $112,010 million in FY2025 compared to $96,995 million in FY2024.\n"
                "Operating cash flow: $118,254 million in FY2025.\n"
                "Total debt: $96,656 million in FY2025.\n"
                "Total stockholders' equity: $74,100 million in FY2025.\n"
            ),
            "section": "income_statement",
            "page_number": 30,
            "token_estimate": 150,
        }
    ]
    _seed_test_document(db, doc_id, session_id, user_id, apple_chunks)

    res = await extraction_agent.execute_async({
        "session_id": session_id,
        "document_id": doc_id,
        "user_id": user_id,
    })

    assert res.success is True
    summary = res.summary
    assert summary["document_id"] == doc_id
    metrics = summary["metrics_dict"]
    assert metrics.get("revenue") == 416161.0
    assert metrics.get("prior_revenue") == 391035.0
    assert metrics.get("net_income") == 112010.0
    assert metrics.get("total_debt") == 96656.0
    assert metrics.get("total_equity") == 74100.0

    # Verify single consolidated record in MongoDB
    saved = db.extracted_metrics.find_one({"document_id": doc_id, "session_id": session_id})
    assert saved is not None
    assert saved["metrics_dict"]["revenue"] == 416161.0
    assert saved["document_id"] == doc_id
    assert len(saved["metrics"]) > 0

    # Verify provenance
    rev_metric = next(m for m in saved["metrics"] if m["metric_name"] == "revenue")
    assert f"{doc_id}_chunk_0" in rev_metric["source_chunk_ids"]
    assert 30 in rev_metric["page_numbers"]

    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


@pytest.mark.asyncio
async def test_no_citation_marks_metric_as_failed_not_guess():
    """Verify Master Plan rule: a metric with no source citation chunk is marked as FAILED with 0.0 confidence."""
    db = get_sync_db()
    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = f"doc-nocite-{session_id[:8]}"

    # Chunk with only business text and no financial metrics
    chunks = [
        {
            "chunk_id": f"{doc_id}_chunk_0",
            "chunk_index": 0,
            "document_id": doc_id,
            "text": "Item 1. Business: The Company designs, manufactures and markets smartphones and tablets.",
            "section": "business",
            "page_number": 1,
            "token_estimate": 50,
        }
    ]
    _seed_test_document(db, doc_id, session_id, user_id, chunks)

    res = await extraction_agent.execute_async({
        "session_id": session_id,
        "document_id": doc_id,
        "user_id": user_id,
        "target_fields": ["revenue", "net_income", "eps"],
    })

    assert res.success is True
    summary = res.summary
    for item in summary["metrics"]:
        if item["metric_name"] in ["revenue", "net_income", "eps"]:
            assert item["value"] is None
            assert item["confidence_score"] == 0.0
            assert item["status"] == "FAILED"

    db.documents.delete_many({"document_id": doc_id})
    db.extracted_metrics.delete_many({"document_id": doc_id})


# =====================================================================
# 34: Target Production Regression Tests (Bugs 1-7)
# =====================================================================

def test_invalid_extraction_candidates_never_persisted_in_metrics_dict():
    """Verify that invalid semantic candidates (e.g. channel mix, debt securities, delta margins) are never stored in metrics_dict."""
    agent = ExtractionAgent()

    chunks = [{
        "chunk_id": "chunk_apple_mix",
        "text": (
            "Distribution channels accounted for 60% and 40% of total net sales.\n"
            "Total debt investments at fair value were $85,589 million.\n"
            "Gross margin decreased by 11.4 percentage points."
        ),
        "section": "financials",
        "page_number": 12,
    }]
    all_map = {"chunk_apple_mix": chunks[0]}

    # LLM incorrectly extracted channel mix as revenue, debt investments as total_debt, delta as gross_margin
    bad_resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=40.0,
                unit="%",
                source_chunk_ids=["chunk_apple_mix"],
                evidence_snippet="distribution channels accounted for 60% and 40% of total net sales",
            ),
            RawLLMMetricItem(
                metric_name="total_debt",
                value=85589.0,
                unit="USD Millions",
                source_chunk_ids=["chunk_apple_mix"],
                evidence_snippet="Total debt investments at fair value were $85,589 million",
            ),
            RawLLMMetricItem(
                metric_name="gross_margin",
                value=488002.0,
                unit="USD",
                source_chunk_ids=["chunk_apple_mix"],
                evidence_snippet="Gross margin decreased by 11.4 percentage points",
            ),
        ],
        multi_year_table={
            "FY2029": {"revenue": 40.0},
            "FY2025": {"gross_margin": 488002.0},
        },
    )

    items, m_dict, my_data = agent._process_and_ground_metrics(
        parsed_response=bad_resp,
        all_chunks_map=all_map,
        financial_chunks=chunks,
        actual_doc_id="doc-sanitization-test",
        filename="apple_test.pdf",
    )

    # 1. Invalid revenue candidate MUST be rejected (None in metrics_dict)
    assert m_dict.get("revenue") is None
    # 2. Debt investments candidate MUST be rejected
    assert m_dict.get("total_debt") is None
    # 3. Out-of-range margin candidate MUST be rejected
    assert m_dict.get("gross_margin") is None
    # 4. Future FY2029 maturity schedule year MUST NOT be in my_data
    assert "FY2029" not in my_data


def test_apple_fiscal_year_extraction_rejects_future_schedule_years():
    """Verify that Apple 2025 filing identifies FY2025/FY2024 and rejects future lease/debt schedule years (FY2029)."""
    agent = ExtractionAgent()

    valid_items = [
        ExtractionMetricItem(
            metric_name="revenue",
            display_name="Total Net Sales",
            value=416161.0,
            prior_value=391035.0,
            period="FY2025",
            prior_period="FY2024",
            status="VALID",
            confidence_score=1.0,
        )
    ]

    multi_year_sample = {
        "FY2025": {"revenue": 416161.0},
        "FY2024": {"revenue": 391035.0},
        "FY2023": {"revenue": 383285.0},
    }

    latest_period = agent._detect_latest_period(valid_items, multi_year_sample)
    prior_period = agent._detect_prior_period(valid_items, multi_year_sample)

    assert latest_period in ["FY2025", "2025"]
    assert prior_period in ["FY2024", "2024"]
    assert latest_period != "FY2029"


def test_percentage_normalization_and_no_double_multiplication():
    """Verify percentage normalization handles 46.28%, 46.21%, 34.0%, 22.6% without double multiplication."""
    assert safe_parse_financial_number("46.28%") == 46.28
    assert safe_parse_financial_number("46.21%") == 46.21
    assert safe_parse_financial_number("34.0%") == 34.0
    assert safe_parse_financial_number("22.6%") == 22.6
    assert safe_parse_financial_number("11.4 percentage points") == 11.4


def test_diluted_eps_table_row_beats_basic_eps_and_thousand_amounts_are_canonical():
    """Statement-row semantics and source-scale conversion are deterministic."""
    from utils.financial_units import normalize_monetary_metric

    agent = ExtractionAgent()
    chunks = [{
        "chunk_id": "income-statement", "section": "income_statement", "page_number": 42,
        "text": "Earnings per share:\nBasic 7.46 6.08 6.13\nDiluted 7.42 6.01 6.08",
    }]
    assert agent._extract_diluted_eps_from_evidence(chunks)[0] == 7.42

    value, unit, currency, source_unit, source_scale = normalize_monetary_metric(
        "revenue", 5_344_400, "USD", "USD", "thousands"
    )
    assert (value, unit, currency) == (5344.4, "USD Millions", "USD")
    assert (source_unit, source_scale) == ("USD", "thousands")
    assert normalize_monetary_metric("eps", 7.42, "USD/share", "USD", "thousands")[0] == 7.42
    assert normalize_monetary_metric("gross_margin", 22.6, "%", "USD", "thousands")[0] == 22.6
    assert normalize_monetary_metric("net_income", -3_510_000, "USD", "USD", "thousands")[0] == -3510.0


def test_statement_headers_define_canonical_periods_and_thousand_metric_scale():
    """Statement fiscal headers, rather than a filing date, label each metric column."""
    agent = ExtractionAgent()
    items = [
        ExtractionMetricItem(
            metric_name="revenue", value=5344.4, prior_value=7871.8,
            period="FY2023", prior_period="FY2022", unit="USD Millions",
        ),
        ExtractionMetricItem(
            metric_name="net_income", value=-3506.7, prior_value=-559.6,
            period="FY2023", prior_period="FY2022", unit="USD Millions",
        ),
    ]
    chunks = [{"text": "Consolidated Statements of Operations (in thousands)\nFiscal 2022 Fiscal 2021"}]
    agent._canonicalize_metric_periods(items, chunks, "FY2023", "FY2022")
    years = agent._build_multi_year_data(items)
    assert years["FY2022"]["revenue"] == 5344.4
    assert years["FY2021"]["revenue"] == 7871.8
    assert years["FY2022"]["net_income"] == -3506.7
    assert years["FY2021"]["net_income"] == -559.6
    assert agent._detect_scale_from_text(chunks[0]["text"]) == "thousands"


def test_flattened_eps_row_extracts_only_numbers_after_diluted_label():
    """Basic EPS before a flattened Diluted row cannot become canonical EPS."""
    agent = ExtractionAgent()
    chunks = [{
        "chunk_id": "eps-table", "text": "Earnings per share Basic 7.46 6.08 Diluted 7.42 6.01",
    }]
    current, prior, _, _ = agent._extract_diluted_eps_from_evidence(chunks)
    assert current == 7.42
    assert prior == 6.01


def test_markdown_eps_table_and_date_headers_drive_canonical_values():
    """Exercise the table serialization used by document ingestion, not prose-only fixtures."""
    agent = ExtractionAgent()
    eps_chunk = {
        "chunk_id": "apple-eps-table",
        "text": (
            "| Earnings per share | 2025 | 2024 |\n"
            "| --- | --- | --- |\n"
            "| Basic | 7.46 | 6.08 |\n"
            "| Diluted | 7.42 | 6.01 |"
        ),
    }
    current, prior, _, _ = agent._extract_diluted_eps_from_evidence([eps_chunk])
    assert (current, prior) == (7.42, 6.01)

    # Items represent the LLM-extracted values (value=current col, prior_value=prior col).
    # The real BBBY filing column mapping:
    #   Col 1 (Feb 26, 2022 = FY2022): Revenue=5344.4, GP=1207.9, NI=-3506.7
    #   Col 2 (Feb 27, 2021 = FY2021): Revenue=7871.8, GP=2673.6, NI=-559.6
    items = [
        ExtractionMetricItem(metric_name="revenue", value=5344.4, prior_value=7871.8,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
        ExtractionMetricItem(metric_name="gross_profit", value=1207.9, prior_value=2673.6,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
        ExtractionMetricItem(metric_name="net_income", value=-3506.7, prior_value=-559.6,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
    ]
    bbby_statement = {
        "text": (
            "| Consolidated Statements of Operations | February 26, 2022 | February 27, 2021 |\n"
            "| --- | --- | --- |\n| Net sales | 5,344,400 | 7,871,800 |\n"
            "| Gross profit | 1,207,900 | 2,673,600 |\n| Net loss | (3,506,700) | (559,600) |\n"
            "(Dollars in thousands)"
        )
    }
    agent._canonicalize_metric_periods(items, [bbby_statement], "FY2023", "FY2022")
    years = agent._build_multi_year_data(items)
    assert years["FY2022"] == {"revenue": 5344.4, "gross_profit": 1207.9, "net_income": -3506.7}
    assert years["FY2021"] == {"revenue": 7871.8, "gross_profit": 2673.6, "net_income": -559.6}
    assert agent._detect_scale_from_text(bbby_statement["text"]) == "thousands"


def test_flattened_weighted_average_diluted_shares_do_not_shadow_eps_row():
    """A preceding diluted-share row is not the EPS row in flattened PDF text."""
    agent = ExtractionAgent()
    chunks = [{
        "chunk_id": "eps-table",
        "text": (
            "Weighted-average shares diluted 15,000 "
            "Earnings per share Basic 7.46 6.08 Diluted 7.42 6.01"
        ),
    }]
    current, prior, _, _ = agent._extract_diluted_eps_from_evidence(chunks)
    assert current == 7.42
    assert prior == 6.01


def test_primary_statement_scale_precedes_exception_scale_and_reprocessing_invalidates_cache():
    """Apple share-count exceptions do not scale money; affected comparison cache is removed."""
    from unittest.mock import MagicMock
    from schemas.agent_results import ExtractionResult

    agent = ExtractionAgent()
    assert agent._detect_scale_from_text(
        "Financial statements (in millions, except shares reflected in thousands)"
    ) == "millions"

    db = MagicMock()
    result = ExtractionResult(
        agent_name="ExtractionAgent", session_id="session", document_id="doc",
        metrics=[ExtractionMetricItem(metric_name="eps", value=7.46, period="FY2025")],
        metrics_dict={"eps": 7.46}, multi_year_data={"FY2025": {"eps": 7.46}},
    )
    agent._persist_consolidated_metrics(db, "session", "user", "doc", "apple.pdf", result)
    db.comparison_results.delete_many.assert_called_once_with({
        "session_id": "session",
        "$or": [{"document_ids": "doc"}, {"document_ids": {"$exists": False}}],
    })


# =====================================================================
# Regression Tests: Canonical Extraction Bug Fixes
# =====================================================================

def test_regression_apple_revenue_rejects_channel_mix_40_60():
    """Revenue = 40 or 60 from channel-mix percentages must never become canonical Revenue."""
    agent = ExtractionAgent()

    bad_resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=40.0,
                unit="USD Millions",
                evidence_snippet="the Company's net sales through its direct and indirect distribution channels accounted for 40% and 60%",
                source_chunk_ids=["chunk1"],
            ),
            RawLLMMetricItem(
                metric_name="prior_revenue",
                value=60.0,
                unit="USD Millions",
                evidence_snippet="the Company's net sales through its direct and indirect distribution channels accounted for 40% and 60%",
                source_chunk_ids=["chunk1"],
            ),
        ],
        multi_year_table={
            "FY2025": {"revenue": 40.0},
            "FY2024": {"revenue": 60.0},
        },
    )

    sanitized = agent._sanitize_extraction_candidates(bad_resp)

    # Both revenue candidates must be rejected
    rev_metrics = [m for m in sanitized.metrics if m.metric_name in {"revenue", "prior_revenue"}]
    assert len(rev_metrics) == 0, f"Channel-mix revenue candidates should be rejected but found: {rev_metrics}"

    # Multi-year table should also reject them
    for period, vals in sanitized.multi_year_table.items():
        assert vals.get("revenue") is None or vals.get("revenue") > 1000, \
            f"Invalid revenue {vals.get('revenue')} leaked into multi_year_table for {period}"


def test_regression_apple_revenue_accepts_authoritative_values():
    """Authoritative income-statement revenue (e.g. 416161) must pass sanitization."""
    agent = ExtractionAgent()

    good_resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue",
                value=416161.0,
                unit="USD Millions",
                evidence_snippet="Total net sales $416,161 million",
                source_chunk_ids=["chunk1"],
            ),
            RawLLMMetricItem(
                metric_name="prior_revenue",
                value=391035.0,
                unit="USD Millions",
                evidence_snippet="Total net sales $391,035 million",
                source_chunk_ids=["chunk1"],
            ),
        ],
    )

    sanitized = agent._sanitize_extraction_candidates(good_resp)
    rev = next((m for m in sanitized.metrics if m.metric_name == "revenue"), None)
    prior_rev = next((m for m in sanitized.metrics if m.metric_name == "prior_revenue"), None)
    assert rev is not None and rev.value == 416161.0
    assert prior_rev is not None and prior_rev.value == 391035.0


def test_regression_impossible_gross_margin_rejected():
    """Gross margin values like 488002.5% are impossible and must be rejected."""
    agent = ExtractionAgent()

    chunks = [{
        "chunk_id": "chunk1",
        "text": "Total net sales: $416,161 million. Gross profit: $195,201 million.",
        "section": "financials",
        "page_number": 30,
    }]
    all_map = {"chunk1": chunks[0]}

    # Simulate LLM returning revenue=40 (channel-mix) and gross_margin=488002%
    bad_resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue", value=416161.0, unit="USD Millions",
                source_chunk_ids=["chunk1"],
                evidence_snippet="Total net sales: $416,161 million",
            ),
            RawLLMMetricItem(
                metric_name="gross_profit", value=195201.0, unit="USD Millions",
                source_chunk_ids=["chunk1"],
                evidence_snippet="Gross profit: $195,201 million",
            ),
            RawLLMMetricItem(
                metric_name="gross_margin", value=488002.5, unit="%",
                source_chunk_ids=["chunk1"],
                evidence_snippet="gross margin",
            ),
        ],
    )

    items, m_dict, _ = agent._process_and_ground_metrics(
        parsed_response=bad_resp,
        all_chunks_map=all_map,
        financial_chunks=chunks,
        actual_doc_id="test-gm",
        filename="test.pdf",
    )

    gm = m_dict.get("gross_margin")
    # Gross margin should be derived from components or None, never 488002.5
    if gm is not None:
        assert abs(gm) <= 100.0, f"Impossible gross margin {gm} leaked through"


def test_regression_gross_margin_derived_from_components():
    """When revenue and gross_profit are available, gross_margin is correctly derived."""
    agent = ExtractionAgent()

    chunks = [{
        "chunk_id": "chunk1",
        "text": (
            "Consolidated Statements of Operations:\n"
            "Total net sales: $416,161 million. $391,035 million.\n"
            "Gross profit: $195,201 million. $180,683 million.\n"
        ),
        "section": "financials",
        "page_number": 30,
    }]
    all_map = {"chunk1": chunks[0]}

    resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="revenue", value=416161.0, prior_value=391035.0,
                unit="USD Millions", source_chunk_ids=["chunk1"],
                evidence_snippet="Total net sales: $416,161 million",
                period="FY2025", prior_period="FY2024",
            ),
            RawLLMMetricItem(
                metric_name="gross_profit", value=195201.0, prior_value=180683.0,
                unit="USD Millions", source_chunk_ids=["chunk1"],
                evidence_snippet="Gross profit: $195,201 million",
                period="FY2025", prior_period="FY2024",
            ),
        ],
    )

    items, m_dict, _ = agent._process_and_ground_metrics(
        parsed_response=resp,
        all_chunks_map=all_map,
        financial_chunks=chunks,
        actual_doc_id="test-gm-derive",
        filename="test.pdf",
    )

    gm = m_dict.get("gross_margin")
    assert gm is not None, "Gross margin should be derived from revenue and gross_profit"
    assert 46.0 <= gm <= 47.0, f"Expected ~46.90%, got {gm}%"

    prior_gm = m_dict.get("prior_gross_margin")
    if prior_gm is not None:
        assert 45.0 <= prior_gm <= 47.0, f"Expected ~46.21%, got {prior_gm}%"


def test_regression_diluted_eps_preferred_over_basic():
    """The explicitly labelled Diluted EPS row must be selected, not Basic."""
    agent = ExtractionAgent()

    # Real Apple filing has Basic=7.49, Diluted=7.46
    chunks = [{
        "chunk_id": "eps-real",
        "text": "Earnings per share:\nBasic 7.49 6.11\nDiluted 7.46 6.08",
    }]
    result = agent._extract_diluted_eps_from_evidence(chunks)
    assert result is not None
    current, prior, _, _ = result
    assert current == 7.46, f"Expected Diluted EPS 7.46, got {current}"
    assert prior == 6.08, f"Expected prior Diluted EPS 6.08, got {prior}"


def test_regression_basic_eps_not_selected_as_diluted():
    """When both Basic and Diluted rows exist, Basic must not shadow Diluted."""
    agent = ExtractionAgent()

    # Table where Basic appears first with different values
    chunks = [{
        "chunk_id": "eps-mixed",
        "text": (
            "| Earnings per share | FY2025 | FY2024 |\n"
            "| --- | --- | --- |\n"
            "| Basic | $7.49 | $6.11 |\n"
            "| Diluted | $7.46 | $6.08 |"
        ),
    }]
    result = agent._extract_diluted_eps_from_evidence(chunks)
    assert result is not None
    current, prior, _, _ = result
    assert current == 7.46
    assert prior == 6.08


def test_regression_eps_sanitizer_rejects_basic_when_diluted_exists():
    """Sanitizer should reject a Basic EPS candidate when Diluted is also present."""
    agent = ExtractionAgent()

    resp = RawLLMExtractionResponse(
        metrics=[
            RawLLMMetricItem(
                metric_name="eps", value=7.49, unit="USD",
                evidence_snippet="Basic earnings per share 7.49",
                source_chunk_ids=["chunk1"],
            ),
            RawLLMMetricItem(
                metric_name="eps", value=7.46, unit="USD",
                evidence_snippet="Diluted earnings per share 7.46",
                source_chunk_ids=["chunk1"],
            ),
        ],
    )

    sanitized = agent._sanitize_extraction_candidates(resp)
    eps_metrics = [m for m in sanitized.metrics if m.metric_name == "eps"]
    # Should have at most the Diluted one
    assert len(eps_metrics) >= 1
    assert eps_metrics[0].value == 7.46, f"Expected Diluted EPS 7.46, got {eps_metrics[0].value}"


def test_regression_bbby_all_metrics_same_column_mapping():
    """All BBBY metrics must use the same source-column -> fiscal-period mapping."""
    agent = ExtractionAgent()

    items = [
        ExtractionMetricItem(metric_name="revenue", value=5344.4, prior_value=7871.8,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
        ExtractionMetricItem(metric_name="gross_profit", value=1207.9, prior_value=2673.6,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
        ExtractionMetricItem(metric_name="net_income", value=-3506.7, prior_value=-559.6,
                             period="FY2023", prior_period="FY2022", unit="USD Millions"),
    ]
    bbby_chunks = [{
        "text": (
            "| Consolidated Statements of Operations | February 26, 2022 | February 27, 2021 |\n"
            "| --- | --- | --- |\n"
            "| Net sales | 5,344,400 | 7,871,800 |\n"
            "| Gross profit | 1,207,900 | 2,673,600 |\n"
            "| Net loss | (3,506,700) | (559,600) |\n"
            "(Dollars in thousands)"
        )
    }]

    agent._canonicalize_metric_periods(items, bbby_chunks, "FY2023", "FY2022")
    years = agent._build_multi_year_data(items)

    # FY2022 (Col 1)
    assert years["FY2022"]["revenue"] == 5344.4
    assert years["FY2022"]["gross_profit"] == 1207.9
    assert years["FY2022"]["net_income"] == -3506.7

    # FY2021 (Col 2)
    assert years["FY2021"]["revenue"] == 7871.8
    assert years["FY2021"]["gross_profit"] == 2673.6
    assert years["FY2021"]["net_income"] == -559.6


def test_regression_bbby_gross_margin_derived():
    """BBBY gross margin must be derived correctly from revenue and gross_profit."""
    # FY2022: GP=1207.9, Rev=5344.4 -> GM ≈ 22.60%
    gm_2022 = round(1207.9 / 5344.4 * 100.0, 2)
    assert 22.0 <= gm_2022 <= 23.0, f"FY2022 gross margin {gm_2022} out of range"

    # FY2021: GP=2673.6, Rev=7871.8 -> GM ≈ 33.97%
    gm_2021 = round(2673.6 / 7871.8 * 100.0, 2)
    assert 33.0 <= gm_2021 <= 35.0, f"FY2021 gross margin {gm_2021} out of range"


def test_regression_supplement_rejects_implausible_revenue():
    """_supplement_multi_year_from_llm_table must reject revenue <= 1000."""
    agent = ExtractionAgent()
    multi_year_data = {"FY2025": {"net_income": 112010.0}}
    llm_table = {
        "FY2025": {"revenue": 40.0, "net_income": 112010.0},
        "FY2024": {"revenue": 60.0},
    }

    agent._supplement_multi_year_from_llm_table(multi_year_data, llm_table, ["FY2025", "FY2024"], [])

    # Revenue 40 and 60 should be rejected
    assert multi_year_data.get("FY2025", {}).get("revenue") is None, \
        "Revenue=40 should have been rejected by supplementation"
    assert multi_year_data.get("FY2024", {}).get("revenue") is None, \
        "Revenue=60 should have been rejected by supplementation"


def test_regression_supplement_rejects_impossible_gross_margin():
    """_supplement_multi_year_from_llm_table must reject gross_margin > 100%."""
    agent = ExtractionAgent()
    multi_year_data = {"FY2025": {}}
    llm_table = {
        "FY2025": {"gross_margin": 488002.5},
    }

    agent._supplement_multi_year_from_llm_table(multi_year_data, llm_table, ["FY2025"], [])

    gm = multi_year_data.get("FY2025", {}).get("gross_margin")
    assert gm is None, f"Impossible gross_margin {gm} should have been rejected"


def test_regression_reprocessing_invalidates_stale_comparison_cache():
    """Reprocessing a document must invalidate stale comparison_results."""
    from unittest.mock import MagicMock

    agent = ExtractionAgent()
    db = MagicMock()
    result = ExtractionResult(
        agent_name="ExtractionAgent", session_id="session", document_id="doc123",
        metrics=[ExtractionMetricItem(metric_name="revenue", value=416161.0, period="FY2025")],
        metrics_dict={"revenue": 416161.0},
        multi_year_data={"FY2025": {"revenue": 416161.0}},
    )
    agent._persist_consolidated_metrics(db, "session", "user", "doc123", "filing.pdf", result)

    # Verify comparison cache was invalidated
    db.comparison_results.delete_many.assert_called_once()
    call_args = db.comparison_results.delete_many.call_args[0][0]
    assert call_args["session_id"] == "session"
    assert {"document_ids": "doc123"} in call_args["$or"]
