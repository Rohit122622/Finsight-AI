"""
Prompts for ExtractionAgent (Phase 2C / Master Plan).

Provides multi-format financial extraction prompts (US 10-K, Indian Annual Reports / Ind AS / Schedule III),
exact provenance chunk citation instructions, and targeted corrective retry prompts.
"""

from typing import Any, Dict, List, Optional


EXTRACTION_SYSTEM_PROMPT = """You are an expert institutional financial analyst and forensic accounting extraction engine.
Your task is to extract exact quantitative financial metrics, accounting figures, ratios, and multi-year comparative data from the provided financial filing chunks into a strictly validated JSON structure.

CRITICAL EXTRACTION RULES:
1. OUTPUT FORMAT: Output ONLY a valid JSON object matching the requested schema. Do NOT include markdown code fences, commentary, or conversational text.
2. NO HALLUCINATION & STRICT SEMANTIC IDENTITY: Extract ONLY figures directly stated or mathematically verifiable in the provided text/tables.
   - If a metric is not found in the provided chunks, set its `value` to null and `source_chunk_ids` to empty [].
   - NEVER invent, guess, or estimate financial figures.
   - NEVER fabricate or invent chunk IDs.
3. EXACT CITATIONS & PROVENANCE:
   - For every extracted metric, you MUST include the exact `source_chunk_ids` from the chunk headers (e.g. ["doc_123_chunk_4"]).
   - Include the page number(s) in `page_numbers` and quote the verbatim table row or text sentence in `evidence_snippet`.
4. MULTI-YEAR & COMPARATIVE PERIODS:
   - Financial statements typically report multiple fiscal years (e.g., FY2024 vs FY2023, or FY2022 vs FY2021).
   - Set `value` to the latest/current fiscal period (and set `period`, e.g. "FY2024").
   - Set `prior_value` to the preceding comparative fiscal period (and set `prior_period`, e.g. "FY2023").
   - Populate `multi_year_table` mapping each fiscal year to its metrics.
   - If YoY change is reported or calculable, include `yoy_change_percent`.
5. STRICT ANTI-MISCLASSIFICATION RULES:
   - REVENUE: Must ONLY be consolidated total net sales / total revenue / revenue from operations. NEVER extract distribution channel percentages (e.g. 40%, 60%), channel mix, segment percentages, customer concentration, or regional share as revenue.
   - TOTAL DEBT: Must ONLY be actual borrowings, debt obligations, long-term and short-term debt (liabilities). NEVER extract "debt investments", "investment in debt securities", "marketable securities", or other asset investments as total_debt.
   - GROSS MARGIN / OPERATING MARGIN: Extract the ACTUAL current margin percentage level (e.g. 22.6%), NEVER extract the percentage-point change/delta (e.g. 11.4 percentage points) as the margin value.
6. TERMINOLOGY & MULTI-JURISDICTION SUPPORT:
   - US 10-K: "Total Net Sales", "Revenue", "Gross Profit", "Operating Income", "Net Income (Loss)", "Diluted EPS", "Total Debt", "Stockholders' Equity".
   - Indian Annual Reports (Ind AS / Schedule III): "Revenue from Operations", "Total Income", "Profit After Tax (PAT)", "Profit for the year", "Basic/Diluted EPS (₹)", "Borrowings (Current + Non-Current)", "Total Equity / Other Equity", "Statement of Profit and Loss".
   - Consolidated vs Standalone: Prefer Consolidated figures when available; if only Standalone is present, extract Standalone figures and note filing_type.
7. MANDATORY TARGET METRICS:
   - revenue (Total revenue / Net sales / Revenue from operations — NOT channel percentages)
   - net_income (Net income / Net loss / PAT)
   - gross_margin (Gross margin % level — NOT margin delta/change)
   - debt_to_equity (Total debt / Total equity ratio)
   - eps (Diluted earnings per share / Basic earnings per share)
   - operating_cash_flow (Net cash provided by / used in operating activities)
   - total_debt (Total borrowings / short-term + long-term debt — NOT debt investments)
   - total_equity (Total stockholders' / shareholders' equity / net worth)
   - operating_margin (Operating income / Revenue ratio)"""


def build_extraction_prompt(
    chunks: List[Dict[str, Any]],
    target_fields: Optional[List[str]] = None,
    filename: str = "financial_document.pdf",
) -> str:
    """
    Build structured extraction prompt with explicit chunk citation tags and metadata.
    """
    fields_to_extract = target_fields or [
        "revenue",
        "net_income",
        "gross_margin",
        "debt_to_equity",
        "eps",
        "operating_cash_flow",
        "total_debt",
        "total_equity",
        "operating_margin",
        "yoy_revenue_change",
    ]

    context_blocks: List[str] = []
    for ch in chunks:
        cid = ch.get("chunk_id", "unknown_chunk")
        pnum = ch.get("page_number", 1)
        sec = ch.get("section", "financials")
        text = ch.get("text", "").strip()
        context_blocks.append(
            f"--- [CHUNK_ID: {cid} | PAGE: {pnum} | SECTION: {sec} | FILE: {filename}] ---\n{text}"
        )

    full_context = "\n\n".join(context_blocks)
    if not full_context:
        full_context = "[No financial document chunks available.]"

    return f"""Target Document: {filename}
Target Fields: {', '.join(fields_to_extract)}

Financial Document Context:
{full_context}

Instructions:
Extract the financial metrics listed above from the provided context.
Return ONLY a valid JSON object with the following schema:
{{
  "filing_type": "US 10-K | Indian Annual Report (Ind AS) | Financial Statement",
  "reporting_currency": "USD | INR | EUR | etc.",
  "reporting_scale": "millions | thousands | crores | lakhs | units",
  "reporting_period": "FY2024",
  "prior_period": "FY2023",
  "metrics": [
    {{
      "metric_name": "revenue",
      "display_name": "Total Net Sales",
      "value": 391035.0,
      "prior_value": 383285.0,
      "unit": "USD Millions",
      "currency": "USD",
      "period": "FY2024",
      "prior_period": "FY2023",
      "yoy_change_percent": 2.02,
      "source_chunk_ids": ["doc_1_chunk_4"],
      "page_numbers": [32],
      "evidence_snippet": "Total net sales: $391,035 million in 2024 compared to $383,285 million in 2023",
      "derivation_formula": null
    }},
    {{
      "metric_name": "debt_to_equity",
      "display_name": "Debt to Equity Ratio",
      "value": 1.45,
      "prior_value": 1.20,
      "unit": "Ratio",
      "currency": null,
      "period": "FY2024",
      "prior_period": "FY2023",
      "yoy_change_percent": 20.8,
      "source_chunk_ids": ["doc_1_chunk_8", "doc_1_chunk_12"],
      "page_numbers": [34, 38],
      "evidence_snippet": "Total debt: $106,629M, Total shareholders equity: $73,524M",
      "derivation_formula": "total_debt (106629) / total_equity (73524)"
    }}
  ],
  "multi_year_table": {{
    "FY2024": {{
      "revenue": 391035.0,
      "net_income": 93736.0,
      "gross_margin": 46.2,
      "total_debt": 106629.0,
      "total_equity": 73524.0,
      "eps": 6.08
    }},
    "FY2023": {{
      "revenue": 383285.0,
      "net_income": 96995.0,
      "gross_margin": 44.1,
      "total_debt": 111088.0,
      "total_equity": 62146.0,
      "eps": 6.13
    }}
  }}
}}"""


def build_corrective_retry_prompt(
    chunks: List[Dict[str, Any]],
    missing_or_malformed_fields: List[str],
    error_reason: str,
    filename: str = "financial_document.pdf",
) -> str:
    """
    Build strict corrective retry prompt targeting specifically the missing or malformed fields.
    """
    context_blocks: List[str] = []
    for ch in chunks:
        cid = ch.get("chunk_id", "unknown_chunk")
        pnum = ch.get("page_number", 1)
        sec = ch.get("section", "financials")
        text = ch.get("text", "").strip()
        context_blocks.append(
            f"--- [CHUNK_ID: {cid} | PAGE: {pnum} | SECTION: {sec} | FILE: {filename}] ---\n{text}"
        )

    full_context = "\n\n".join(context_blocks)

    return f"""CORRECTIVE RETRY INSTRUCTION:
Your initial extraction had issues: {error_reason}
Target fields requiring immediate correction / extraction: {', '.join(missing_or_malformed_fields)}

Document Context:
{full_context}

STRICT AUDIT RULES FOR THIS RETRY:
1. Focus specifically on accurately extracting or recalculating: {', '.join(missing_or_malformed_fields)}.
2. You MUST cite the EXACT chunk IDs from the context headers (e.g. "source_chunk_ids": ["{chunks[0].get('chunk_id', 'chunk_0')}"]).
3. If a metric is truly absent from all provided chunks, explicitly return `value: null`, `source_chunk_ids: []`, rather than guessing or fabricating numbers.
4. Ensure all numeric values are clean float numbers (e.g. 5345.0, not "$5,345 million").
5. Return ONLY a valid JSON object matching the standard extraction schema."""
