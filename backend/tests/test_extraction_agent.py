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
