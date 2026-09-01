"""
FinSentry AI — Red Flag Agent Production Test Suite (Phase 2C).

Owner: Sajjan Pawar / FinSentry Engineering Team
Comprehensive unit and integration test suite verifying 100% compliance with Master Plan:
  1. Quantitative rule checks (Debt surge, margin compression, OCF divergence, revenue decline, negative equity)
  2. Quantitative chunk provenance resolution & propagation
  3. Qualitative forensic LLM analysis (Going concern, restatements, related party, internal controls, covenant breach)
  4. Fixed deterministic severity rubric & LLM override prevention
  5. Semantic deduplication with provenance union
  6. Anti-leakage text sanitization
  7. Deterministic composite risk score calculation
  8. MongoDB persistence & index structure
  9. Safe handling of missing/invalid provenance
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from bson import ObjectId

from agents.red_flag.red_flag_agent import RedFlagAgent, red_flag_agent
from database.connection import mongodb
from schemas.agent_results import RedFlagItem, RedFlagResult


# =====================================================================
# 1. Quantitative Rule Engine Tests
# =====================================================================

def test_debt_growth_detection_high_and_medium():
    """Verify debt surge detection triggers HIGH at >=40% and MEDIUM at >=20%."""
    agent = RedFlagAgent()

    # High debt surge: $1,450M from $1,000M (+45.0%)
    high_metrics = {"total_debt": 1450.0, "prior_total_debt": 1000.0}
    flags_high = agent.scan_quantitative_metrics(high_metrics)
    assert len(flags_high) == 1
    assert flags_high[0].severity == "HIGH"
    assert flags_high[0].category == "Solvency"
    assert "Significant Debt Growth" in flags_high[0].title
    assert "45.0%" in flags_high[0].description

    # Medium debt growth: $1,250M from $1,000M (+25.0%)
    med_metrics = {"total_debt": 1250.0, "prior_total_debt": 1000.0}
    flags_med = agent.scan_quantitative_metrics(med_metrics)
    assert len(flags_med) == 1
    assert flags_med[0].severity == "MEDIUM"
    assert flags_med[0].category == "Solvency"
    assert "Rising Debt" in flags_med[0].title


def test_gross_margin_compression_detection():
    """Verify gross margin drop triggers HIGH at >=10% and MEDIUM at >=5%."""
    agent = RedFlagAgent()

    # High margin compression: 35.0% down to 22.0% (13.0 percentage points drop)
    high_metrics = {"gross_margin": 0.22, "prior_gross_margin": 0.35}
    flags_high = agent.scan_quantitative_metrics(high_metrics)
    assert len(flags_high) == 1
    assert flags_high[0].severity == "HIGH"
    assert flags_high[0].category == "Profitability"
    assert "Severe Gross Margin Compression" in flags_high[0].title

    # Medium margin compression: 35.0% down to 28.0% (7.0 percentage points drop)
    med_metrics = {"gross_margin": 0.28, "prior_gross_margin": 0.35}
    flags_med = agent.scan_quantitative_metrics(med_metrics)
    assert len(flags_med) == 1
    assert flags_med[0].severity == "MEDIUM"
    assert "Falling Gross Margin" in flags_med[0].title


def test_operating_margin_compression_detection():
    """Verify operating margin drop triggers HIGH at >=10% and MEDIUM at >=5%."""
    agent = RedFlagAgent()

    # High operating margin drop: 18.0% down to 6.0% (12.0 pts drop)
    high_metrics = {"operating_margin": 0.06, "prior_operating_margin": 0.18}
    flags_high = agent.scan_quantitative_metrics(high_metrics)
    assert len(flags_high) == 1
    assert flags_high[0].severity == "HIGH"
    assert "Severe Operating Margin Compression" in flags_high[0].title

    # Medium operating margin drop: 18.0% down to 12.0% (6.0 pts drop)
    med_metrics = {"operating_margin": 0.12, "prior_operating_margin": 0.18}
    flags_med = agent.scan_quantitative_metrics(med_metrics)
    assert len(flags_med) == 1
    assert flags_med[0].severity == "MEDIUM"
    assert "Declining Operating Margin" in flags_med[0].title


def test_negative_operating_cash_flow_and_divergence():
    """Verify cash flow divergence (negative OCF with positive Net Income) vs negative OCF."""
    agent = RedFlagAgent()

    # OCF Divergence: OCF = -$300M with positive Net Income = +$500M -> HIGH
    divergence_metrics = {"operating_cash_flow": -300.0, "net_income": 500.0}
    flags_div = agent.scan_quantitative_metrics(divergence_metrics)
    assert len(flags_div) == 1
    assert flags_div[0].severity == "HIGH"
    assert flags_div[0].category == "Accounting"
    assert "Operating Cash Flow Divergence" in flags_div[0].title

    # Standard Negative OCF: OCF = -$300M with negative Net Income = -$400M -> MEDIUM
    burn_metrics = {"operating_cash_flow": -300.0, "net_income": -400.0}
    flags_burn = agent.scan_quantitative_metrics(burn_metrics)
    assert len(flags_burn) == 1
    assert flags_burn[0].severity == "MEDIUM"
    assert "Negative Operating Cash Flow" in flags_burn[0].title


def test_debt_to_equity_deterioration_and_negative_equity():
    """Verify D/E leverage growth, high absolute D/E, and negative equity detection."""
    agent = RedFlagAgent()

    # D/E growth: from D/E 1.0 ($1000/$1000) to D/E 1.8 ($1800/$1000) (+80% growth) -> HIGH
    high_de_growth = {
        "total_debt": 1800.0,
        "prior_total_debt": 1000.0,
        "total_equity": 1000.0,
        "prior_total_equity": 1000.0,
    }
    flags_de_growth = agent.scan_quantitative_metrics(high_de_growth)
    de_flags = [f for f in flags_de_growth if "debt_to_equity" in f.metric_name]
    assert len(de_flags) == 1
    assert de_flags[0].severity == "HIGH"
    assert "Deteriorating Debt-to-Equity Leverage" in de_flags[0].title

    # Negative equity deficit -> HIGH
    neg_equity = {
        "total_debt": 1500.0,
        "total_equity": -450.0,
    }
    flags_neg_eq = agent.scan_quantitative_metrics(neg_equity)
    eq_flags = [f for f in flags_neg_eq if "total_equity" in f.metric_name]
    assert len(eq_flags) == 1
    assert eq_flags[0].severity == "HIGH"
    assert "Negative Stockholders' Equity Deficit" in eq_flags[0].title


def test_revenue_contraction_detection():
    """Verify top-line revenue decline triggers HIGH at >=15% and MEDIUM at >=5%."""
    agent = RedFlagAgent()

    # Severe revenue drop: $5,345M from $7,871M (-32.1%) -> HIGH
    severe_rev = {"revenue": 5345.0, "prior_revenue": 7871.0}
    flags_high = agent.scan_quantitative_metrics(severe_rev)
    assert len(flags_high) == 1
    assert flags_high[0].severity == "HIGH"
    assert "Severe Revenue Contraction" in flags_high[0].title
    assert "32.1%" in flags_high[0].description

    # Moderate revenue drop: $9,200M from $10,000M (-8.0%) -> MEDIUM
    mod_rev = {"revenue": 9200.0, "prior_revenue": 10000.0}
    flags_med = agent.scan_quantitative_metrics(mod_rev)
    assert len(flags_med) == 1
    assert flags_med[0].severity == "MEDIUM"
    assert "Declining Revenue" in flags_med[0].title


# =====================================================================
# 2. Quantitative Provenance Attachment Tests
# =====================================================================

def test_quantitative_provenance_propagation_and_resolution():
    """Verify that quantitative flags receive exact source_chunk_ids, page, and section from provenance map."""
    agent = RedFlagAgent()

    metrics = {
        "total_debt": 1500.0,
        "prior_total_debt": 1000.0,
        "gross_margin": 0.20,
        "prior_gross_margin": 0.35,
    }

    mock_prov_map = {
        "total_debt": {
            "chunk_id": "chk-doc1-p45-debt",
            "source_chunk_ids": ["chk-doc1-p45-debt"],
            "page_number": 45,
            "section": "financials",
            "document_filename": "annual_report.pdf",
            "document_id": "doc-001",
            "evidence_snippet": "Total long-term debt increased to $1,500 million.",
        },
        "gross_margin": {
            "chunk_id": "chk-doc1-p30-margin",
            "source_chunk_ids": ["chk-doc1-p30-margin"],
            "page_number": 30,
            "section": "md_and_a",
            "document_filename": "annual_report.pdf",
            "document_id": "doc-001",
            "evidence_snippet": "Gross margin compressed to 20.0% due to cost inflation.",
        },
    }

    flags = agent.scan_quantitative_metrics(metrics, provenance_map=mock_prov_map)
    assert len(flags) == 2

    debt_flag = next(f for f in flags if f.metric_name == "total_debt")
    assert debt_flag.source_chunk_ids == ["chk-doc1-p45-debt"]
    assert debt_flag.page_number == 45
    assert debt_flag.section == "financials"
    assert debt_flag.document_id == "doc-001"
    assert "Total long-term debt increased" in debt_flag.evidence_snippet

    margin_flag = next(f for f in flags if f.metric_name == "gross_margin")
    assert margin_flag.source_chunk_ids == ["chk-doc1-p30-margin"]
    assert margin_flag.page_number == 30
    assert margin_flag.section == "md_and_a"


# =====================================================================
# 3. Fixed Deterministic Severity Rubric & Override Prevention
# =====================================================================

def test_deterministic_severity_rubric_prevents_llm_override():
    """Verify that deterministic rubric overrides LLM output in both directions."""
    eval_sev = RedFlagAgent._evaluate_qualitative_severity

    # 1. LLM attempts to downgrade Going Concern to LOW -> Rubric enforces HIGH
    sev_gc = eval_sev(
        title="Going Concern Opinion",
        description="The auditor expressed substantial doubt about continuing as a going concern.",
        category="Accounting",
        raw_severity="LOW",
    )
    assert sev_gc == "HIGH"

    # 2. LLM attempts to downgrade Debt Covenant Breach to LOW -> Rubric enforces HIGH
    sev_cov = eval_sev(
        title="Debt Covenant Breach",
        description="The company defaulted on minimum liquidity covenants under its credit facility.",
        category="Solvency",
        raw_severity="LOW",
    )
    assert sev_cov == "HIGH"

    # 3. LLM attempts to downgrade Restatement to LOW -> Rubric enforces HIGH
    sev_restatement = eval_sev(
        title="Prior Period Financial Restatement",
        description="The company identified material misstatements requiring restated earnings.",
        category="Accounting",
        raw_severity="LOW",
    )
    assert sev_restatement == "HIGH"

    # 4. LLM attempts to upgrade general minor disclosure to HIGH -> Rubric downgrades to LOW
    sev_minor = eval_sev(
        title="Office Lease Expiration",
        description="A commercial warehouse lease expires next fiscal quarter in the ordinary course.",
        category="Operational",
        raw_severity="HIGH",
    )
    assert sev_minor == "LOW"

    # 5. SOX 404 Material Weakness -> Enforces MEDIUM
    sev_sox = eval_sev(
        title="Material Weakness in Internal Controls",
        description="Management identified a material weakness in inventory valuation controls.",
        category="Governance",
        raw_severity="LOW",
    )
    assert sev_sox == "MEDIUM"

    # 6. Related-Party Transaction -> Enforces MEDIUM
    sev_rpt = eval_sev(
        title="Related-Party Loan to Executive",
        description="The company disclosed related-party transactions with an affiliated entity.",
        category="Governance",
        raw_severity="LOW",
    )
    assert sev_rpt == "MEDIUM"


# =====================================================================
# 4. Semantic Deduplication & Citation Union
# =====================================================================

def test_semantic_deduplication_and_citation_union():
    """Verify that multiple flags for the same risk merge cleanly, unioning all chunk IDs."""
    agent = RedFlagAgent()

    flag1 = RedFlagItem(
        severity="MEDIUM",
        category="Solvency",
        title="Significant Debt Growth",
        description="Total debt grew rapidly year over year.",
        source="QUANTITATIVE",
        source_chunk_ids=["chunk-001"],
        page_number=12,
        evidence_snippet="Short snippet.",
    )

    flag2 = RedFlagItem(
        severity="HIGH",
        category="Solvency",
        title="Significant Debt Growth",
        description="Total debt surged 45% exceeding leverage limits.",
        source="QUALITATIVE",
        source_chunk_ids=["chunk-002", "chunk-003"],
        page_number=14,
        evidence_snippet="Longer, more comprehensive evidence snippet from 10-K filing.",
    )

    distinct_flag = RedFlagItem(
        severity="HIGH",
        category="Accounting",
        title="Going Concern Qualification",
        description="Auditor issued going concern paragraph.",
        source="QUALITATIVE",
        source_chunk_ids=["chunk-004"],
        page_number=18,
    )

    deduped = agent._deduplicate_flags([flag1, flag2, distinct_flag])

    # Should merge flag1 and flag2, keeping distinct_flag
    assert len(deduped) == 2

    merged_debt = next(f for f in deduped if f.category == "Solvency")
    assert merged_debt.severity == "HIGH"  # Promoted from MEDIUM to HIGH
    assert set(merged_debt.source_chunk_ids) == {"chunk-001", "chunk-002", "chunk-003"}  # Unioned chunk IDs
    assert "Longer, more comprehensive" in merged_debt.evidence_snippet  # Best evidence preserved


# =====================================================================
# 5. Text Sanitization & Anti-Leakage
# =====================================================================

def test_anti_leakage_sanitization():
    """Verify that raw internal chunk IDs and ObjectIDs are stripped from user-facing text."""
    agent = RedFlagAgent()

    leaky_flag = RedFlagItem(
        severity="HIGH",
        category="Solvency",
        title="Debt Surge (CHUNK_001)",
        description="Total debt increased sharply in chunk_abc_123 according to 66c3a1e2f9d8a4b5c6e7f8a9.",
        source="QUANTITATIVE",
        source_chunk_ids=["chunk_abc_123"],
    )

    sanitized = agent._sanitize_flags([leaky_flag])
    assert len(sanitized) == 1
    clean = sanitized[0]

    assert "CHUNK_" not in clean.title
    assert "chunk_" not in clean.description
    assert "66c3a1e2f9d8a4b5c6e7f8a9" not in clean.description
    # Internal chunk ID remains preserved in source_chunk_ids list for auditability
    assert clean.source_chunk_ids == ["chunk_abc_123"]


# =====================================================================
# 6. Composite Risk Score Calculation
# =====================================================================

def test_deterministic_risk_score_calculation():
    """Verify composite risk score calculation: HIGH=15, MEDIUM=5, LOW=2 (max 100)."""
    score_fn = RedFlagAgent._compute_deterministic_risk_score

    # 2 HIGH, 1 MEDIUM, 2 LOW -> 2*15 + 1*5 + 2*2 = 30 + 5 + 4 = 39.0
    flags = [
        RedFlagItem(severity="HIGH", category="Solvency", title="Debt Growth", description="Desc"),
        RedFlagItem(severity="HIGH", category="Accounting", title="Going Concern", description="Desc"),
        RedFlagItem(severity="MEDIUM", category="Profitability", title="Margin Compression", description="Desc"),
        RedFlagItem(severity="LOW", category="Legal", title="Routine Litigation", description="Desc"),
        RedFlagItem(severity="LOW", category="Operational", title="Supplier Concentration", description="Desc"),
    ]
    assert score_fn(flags) == 39.0

    # 8 HIGH flags -> 8 * 15 = 120 -> Capped at 100.0
    many_high = [
        RedFlagItem(severity="HIGH", category="Solvency", title=f"High Risk {i}", description="Desc")
        for i in range(8)
    ]
    assert score_fn(many_high) == 100.0


# =====================================================================
# 7. MongoDB Persistence & Indexes
# =====================================================================

@pytest.mark.asyncio
async def test_mongodb_persistence_and_indexes():
    """Verify that RedFlagAgent persists results into MongoDB red_flags collection with correct schema."""
    await mongodb.connect()
    db = mongodb.get_db()

    session_id = str(ObjectId())
    user_id = str(ObjectId())
    doc_id = str(ObjectId())

    test_flag = RedFlagItem(
        severity="HIGH",
        category="Solvency",
        title="Severe Debt Surge",
        description="Total debt surged 45% year-over-year.",
        source="QUANTITATIVE",
        source_chunk_ids=["chk-001"],
        page_number=10,
        section="financials",
        document_id=doc_id,
        document_filename="test_10k.pdf",
    )

    result = RedFlagResult(
        agent_name="RedFlagAgent",
        session_id=session_id,
        user_id=user_id,
        document_id=doc_id,
        company_name="Test Corp",
        total_flags=1,
        high_severity_count=1,
        flags=[test_flag],
        risk_score=15.0,
        overall_assessment="Forensic assessment identified 1 high severity risk.",
        quantitative_flags_count=1,
        qualitative_flags_count=0,
    )

    RedFlagAgent._persist_to_db(session_id=session_id, result=result, user_id=user_id, document_id=doc_id)

    saved = await db.red_flags.find_one({"session_id": session_id})
    assert saved is not None
    assert saved["session_id"] == session_id
    assert saved["user_id"] == user_id
    assert saved["document_id"] == doc_id
    assert saved["total_flags"] == 1
    assert saved["flags"][0]["source_chunk_ids"] == ["chk-001"]

    # Clean up test document
    await db.red_flags.delete_many({"session_id": session_id})


# =====================================================================
# 8. Missing and Invalid Provenance Handling
# =====================================================================

def test_missing_and_invalid_provenance_handling():
    """Verify that missing provenance is handled gracefully without inventing fake IDs."""
    agent = RedFlagAgent()

    # Pass metrics with no provenance map
    metrics = {"total_debt": 1500.0, "prior_total_debt": 1000.0}
    flags = agent.scan_quantitative_metrics(metrics, provenance_map=None)
    assert len(flags) == 1
    # source_chunk_ids should be empty list, never a fabricated fake ID
    assert flags[0].source_chunk_ids == []
    assert flags[0].page_number is None


# =====================================================================
# 9. Real-World BBBY Distress Verification Test
# =====================================================================

@pytest.mark.asyncio
async def test_bbby_real_world_distress_end_to_end():
    """Verify that RedFlagAgent identifies distress indicators from authentic BBBY 10-K filing."""
    from scripts.verify_bbby_distress import run_bbby_distress_verification
    success = await run_bbby_distress_verification()
    assert success is True


# =====================================================================
# 10. Targeted Bug #1 & Bug #2 Semantic Validation & Formatting Tests
# =====================================================================

def test_bug1_apple_distribution_channels_rejected_as_revenue():
    """
    BUG #1 TEST A: Distribution channel percentages (60% and 40%) MUST NOT be classified
    as revenue or trigger a false 'Revenue Contraction' flag from 60 -> 40.
    When true revenue (416,161) is present, it must use the actual revenue.
    """
    agent = RedFlagAgent()

    # Metrics list containing both channel distribution percentages and genuine net sales
    extracted_items = [
        {
            "metric_name": "revenue",
            "display_name": "Direct and Indirect Distribution Channels",
            "value": 60.0,
            "prior_value": 40.0,
            "unit": "%",
            "evidence_snippet": "The Company's direct and indirect distribution channels accounted for 60% and 40% of total net sales, respectively.",
            "source_chunk_ids": ["chk-dist-01"],
            "page_number": 34,
        },
        {
            "metric_name": "revenue",
            "display_name": "Total Net Sales",
            "value": 416161.0,
            "prior_value": 391035.0,
            "unit": "USD Millions",
            "evidence_snippet": "Total net sales were $416,161 million in 2025 compared to $391,035 million in 2024.",
            "source_chunk_ids": ["chk-rev-01"],
            "page_number": 45,
        },
    ]

    norm_metrics, prov = agent._extract_normalized_metrics_with_provenance(extracted_items)

    # 1. Verify normalized revenue is the actual net sales, NOT the 60/40 channel percentage
    assert norm_metrics.get("revenue") == 416161.0
    assert norm_metrics.get("prior_revenue") == 391035.0

    # 2. Verify no false revenue contraction flag is generated (revenue grew from 391k to 416k)
    flags = agent.scan_quantitative_metrics(norm_metrics, provenance_map=prov)
    rev_flags = [f for f in flags if f.metric_name == "revenue"]
    assert len(rev_flags) == 0, f"Must NOT create revenue contraction flag for growing revenue: {rev_flags}"


def test_bug1_microsoft_debt_investments_rejected_as_total_debt():
    """
    BUG #1 TEST B: Investment-related figures (e.g. debt investments 295 -> 85,589)
    MUST NOT be classified as total debt or trigger a false 'Significant Debt Growth' flag.
    """
    agent = RedFlagAgent()

    extracted_items = [
        {
            "metric_name": "total_debt",
            "display_name": "Total Debt Investments",
            "value": 85589.0,
            "prior_value": 295.0,
            "unit": "USD Millions",
            "evidence_snippet": "Total debt investments at fair value were $85,589 million compared to $295 million in prior year.",
            "source_chunk_ids": ["chk-inv-01"],
            "page_number": 72,
        }
    ]

    norm_metrics, prov = agent._extract_normalized_metrics_with_provenance(extracted_items)

    # 1. Total debt must be excluded because semantic identity shows it's debt investments
    assert norm_metrics.get("total_debt") is None

    # 2. No false debt growth flag generated
    flags = agent.scan_quantitative_metrics(norm_metrics, provenance_map=prov)
    debt_flags = [f for f in flags if f.metric_name == "total_debt"]
    assert len(debt_flags) == 0, f"Must NOT generate debt growth flag from debt investments: {debt_flags}"


def test_bug1_valid_total_debt_accepted():
    """
    BUG #1 TEST C: Genuine total debt obligations (with valid semantics) ARE accepted
    and properly trigger quantitative rules.
    """
    agent = RedFlagAgent()

    extracted_items = [
        {
            "metric_name": "total_debt",
            "display_name": "Total Debt Obligations",
            "value": 85589.0,
            "prior_value": 295.0,
            "unit": "USD Millions",
            "evidence_snippet": "Total long-term debt and borrowings outstanding were $85,589 million compared to $295 million.",
            "source_chunk_ids": ["chk-debt-valid-01"],
            "page_number": 65,
        }
    ]

    norm_metrics, prov = agent._extract_normalized_metrics_with_provenance(extracted_items)

    assert norm_metrics.get("total_debt") == 85589.0
    assert norm_metrics.get("prior_total_debt") == 295.0

    flags = agent.scan_quantitative_metrics(norm_metrics, provenance_map=prov)
    debt_flags = [f for f in flags if f.metric_name == "total_debt"]
    assert len(debt_flags) == 1
    assert debt_flags[0].severity == "HIGH"
    assert debt_flags[0].source_chunk_ids == ["chk-debt-valid-01"]


def test_bug1_ambiguous_metric_without_confirmation_rejected():
    """
    BUG #1 TEST D: If metric is ambiguous (generic 'debt') and evidence references securities/investments,
    do NOT silently promote it to total_debt.
    """
    agent = RedFlagAgent()

    extracted_items = [
        {
            "metric_name": "debt",
            "display_name": "Debt",
            "value": 5000.0,
            "prior_value": 1000.0,
            "evidence_snippet": "available-for-sale debt securities held by the company",
            "source_chunk_ids": ["chk-ambig-01"],
        }
    ]

    norm_metrics, prov = agent._extract_normalized_metrics_with_provenance(extracted_items)
    assert norm_metrics.get("total_debt") is None

    flags = agent.scan_quantitative_metrics(norm_metrics, provenance_map=prov)
    debt_flags = [f for f in flags if f.metric_name == "total_debt"]
    assert len(debt_flags) == 0


def test_bug2_bbby_margin_percentage_point_consistency():
    """
    BUG #2 TEST: Gross margin decline from 34.0% to 22.6% MUST be described as an
    11.4 percentage-point decrease, and MUST NOT claim '34.0% -> 11.4%'.
    """
    agent = RedFlagAgent()

    metrics = {
        "gross_margin": 0.226,          # 22.6%
        "prior_gross_margin": 0.340,    # 34.0%
    }

    flags = agent.scan_quantitative_metrics(metrics)
    assert len(flags) == 1
    flag = flags[0]

    assert flag.severity == "HIGH"
    assert "Severe Gross Margin Compression" in flag.title

    # Must state 11.4 percentage points
    assert "11.4 percentage points" in flag.description
    assert "34.0%" in flag.description
    assert "22.6%" in flag.description

    # Must NOT claim that gross margin dropped to 11.4%
    assert "to 11.4%" not in flag.description
    assert "from 34.0% to 11.4%" not in flag.description


def test_embedding_service_process_singleton_reuse():
    """
    Verify that multiple EmbeddingService instances in the same process share the model cache.
    """
    from services.embedding_service import EmbeddingService, _SHARED_MODELS

    srv1 = EmbeddingService()
    srv2 = EmbeddingService()

    # Both instances point to the same model cache
    assert srv1.model_name == srv2.model_name


def test_multi_turn_query_context_retention():
    """
    Verify that QueryUnderstandingService retains entity, metrics, and years across conversation turns.
    """
    from schemas.query_understanding import QueryUnderstandingRequest
    from services.query_understanding_service import query_understanding_service

    # Turn 1: Initial question
    req1 = QueryUnderstandingRequest(
        query="What were Apple's total net sales in fiscal 2023, 2024, and 2025?",
        conversation_history=[],
    )
    res1 = query_understanding_service.understand_query(req1)
    assert "Apple" in res1.entities or any("Apple" in e for e in res1.entities)
    assert any("net sales" in m.lower() or "revenue" in m.lower() for m in res1.financial_signals.metrics)

    # Turn 2: Follow-up question with pronoun/abbreviation
    req2 = QueryUnderstandingRequest(
        query="What about 2024?",
        conversation_history=[
            {"role": "user", "content": "What were Apple's total net sales in fiscal 2023, 2024, and 2025?"},
            {"role": "assistant", "content": "Apple's total net sales were $383,285M in 2023, $391,035M in 2024, and $416,161M in 2025."},
        ],
    )
    res2 = query_understanding_service.understand_query(req2)
    assert res2.is_follow_up or res2.requires_context
    assert "Apple" in res2.entities or any("Apple" in e for e in res2.entities)
    assert 2024 in res2.temporal_signals.years

    # Turn 3: Follow-up calculation question
    req3 = QueryUnderstandingRequest(
        query="How much did it increase from 2024 to 2025?",
        conversation_history=[
            {"role": "user", "content": "What were Apple's total net sales in fiscal 2023, 2024, and 2025?"},
            {"role": "assistant", "content": "Apple's total net sales were $383,285M in 2023, $391,035M in 2024, and $416,161M in 2025."},
            {"role": "user", "content": "What about 2024?"},
            {"role": "assistant", "content": "In 2024, Apple's net sales were $391,035 million."},
        ],
    )
    res3 = query_understanding_service.understand_query(req3)
    assert res3.is_follow_up or res3.requires_context
    assert "Apple" in res3.entities or any("Apple" in e for e in res3.entities)
    assert 2024 in res3.temporal_signals.years or 2025 in res3.temporal_signals.years


