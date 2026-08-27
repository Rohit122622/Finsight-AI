"""
FinSentry AI — Phase 3K Evaluation Dataset.

Defines a deterministic, source-backed evaluation dataset of 25 financial research questions.
Each case maps directly to verified ground-truth data in `backend/evaluation/fixtures.py`.

Dataset Version: 1.0.0
"""

import json
import logging
from typing import List, Optional

from schemas.evaluation import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationDataset,
    EvaluationDifficulty,
    MultiTurnMessage,
)

logger = logging.getLogger(__name__)

CURRENT_DATASET_VERSION = "1.0.0"

EVALUATION_CASES: List[EvaluationCase] = [
                                                                       
    EvaluationCase(
        case_id="case-01",
        question="What was Acme Corporation's total revenue for the fiscal year ended December 31, 2024?",
        expected_answer="Acme Corporation's total revenue for FY2024 was $14,800 million ($14.8 billion), representing an 18.4% increase compared to $12,500 million in FY2023.",
        acceptable_answer_variants=[
            "Total revenue was $14.8 billion in FY2024, up 18.4% from $12.5 billion in FY2023.",
            "Acme Corp reported $14,800 million in total revenue for 2024.",
            "Revenue for fiscal year 2024 was $14.8B.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=12,
        expected_section="Item 8. Consolidated Statements of Operations",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 12, Item 8. Consolidated Statements of Operations]",
        expected_claims=[
            "Total revenue in FY2024 was $14,800 million ($14.8 billion)",
            "Revenue grew 18.4% year-over-year from $12,500 million in FY2023",
        ],
        expected_metrics=["revenue", "growth"],
        category=EvaluationCategory.FACTUAL,
        difficulty=EvaluationDifficulty.EASY,
        notes="Core top-line revenue verification from 10-K operations statement",
    ),
    EvaluationCase(
        case_id="case-02",
        question="What was the revenue and percentage contribution of the Cloud Infrastructure segment in FY2024?",
        expected_answer="The Cloud Infrastructure segment generated $6,200 million ($6.2 billion) in revenue in FY2024, accounting for 41.9% of Acme Corporation's total consolidated revenue and growing 28.5% year-over-year.",
        acceptable_answer_variants=[
            "Cloud Infrastructure revenue was $6.2 billion (41.9% of total revenue), growing 28.5% YoY.",
            "Cloud Infrastructure generated $6,200M, representing 41.9% of total revenue.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=26,
        expected_section="Item 1. Segment Financial Performance - Cloud Infrastructure",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 26, Item 1. Segment Financial Performance - Cloud Infrastructure]",
        expected_claims=[
            "Cloud Infrastructure revenue was $6,200 million ($6.2 billion) in FY2024",
            "Cloud Infrastructure contributed 41.9% of total revenue",
            "Segment revenue grew 28.5% from $4,825 million in FY2023",
        ],
        expected_metrics=["segment revenue", "percentage contribution"],
        category=EvaluationCategory.FACTUAL,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Segment reporting fact extraction",
    ),

                                                                       
    EvaluationCase(
        case_id="case-03",
        question="What was Acme Corporation's EBITDA and EBITDA margin in FY2024?",
        expected_answer="In FY2024, Acme Corporation's EBITDA reached $3,600 million ($3.6 billion), resulting in an EBITDA margin of 24.3% (an expansion of 70 basis points from 23.6% in FY2023).",
        acceptable_answer_variants=[
            "EBITDA was $3.6 billion with an EBITDA margin of 24.3% in FY2024.",
            "EBITDA was $3,600 million and EBITDA margin was 24.3%.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=14,
        expected_section="Item 7. Non-GAAP Financial Measures - EBITDA and Adjusted EBITDA",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 14, Item 7. Non-GAAP Financial Measures - EBITDA and Adjusted EBITDA]",
        expected_claims=[
            "FY2024 EBITDA was $3,600 million ($3.6 billion)",
            "FY2024 EBITDA margin was 24.3%",
        ],
        expected_metrics=["EBITDA", "EBITDA margin"],
        category=EvaluationCategory.FINANCIAL_METRIC,
        difficulty=EvaluationDifficulty.EASY,
        notes="Non-GAAP metric extraction",
    ),
    EvaluationCase(
        case_id="case-04",
        question="What was Acme Corporation's consolidated net income and diluted earnings per share for FY2024?",
        expected_answer="Acme Corporation reported consolidated net income of $1,950 million ($1.95 billion) and diluted earnings per share of $3.90 for FY2024, up from $1,550 million in FY2023.",
        acceptable_answer_variants=[
            "Net income was $1.95 billion ($1,950 million) and diluted EPS was $3.90 for 2024.",
            "FY2024 net income was $1,950M with EPS of $3.90.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=12,
        expected_section="Item 8. Consolidated Statements of Operations",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 12, Item 8. Consolidated Statements of Operations]",
        expected_claims=[
            "Net income was $1,950 million ($1.95 billion) in FY2024",
            "Diluted earnings per share was $3.90 in FY2024",
        ],
        expected_metrics=["net income", "EPS"],
        category=EvaluationCategory.FINANCIAL_METRIC,
        difficulty=EvaluationDifficulty.EASY,
        notes="Bottom-line income verification",
    ),
    EvaluationCase(
        case_id="case-05",
        question="What was Acme Corporation's gross profit and gross margin for FY2024?",
        expected_answer="Acme Corporation achieved gross profit of $8,020 million on cost of goods sold of $6,780 million in FY2024, delivering a gross margin of 54.2%.",
        acceptable_answer_variants=[
            "Gross profit was $8,020 million and gross margin was 54.2% for FY2024.",
            "Gross margin was 54.2% with gross profit of $8.02 billion.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=12,
        expected_section="Item 8. Consolidated Statements of Operations",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 12, Item 8. Consolidated Statements of Operations]",
        expected_claims=[
            "Gross profit was $8,020 million in FY2024",
            "Gross margin was 54.2% in FY2024",
        ],
        expected_metrics=["gross profit", "gross margin"],
        category=EvaluationCategory.FINANCIAL_METRIC,
        difficulty=EvaluationDifficulty.EASY,
        notes="Gross margin percentage verification",
    ),
    EvaluationCase(
        case_id="case-06",
        question="What was Acme Corporation's operating cash flow for FY2024?",
        expected_answer="Net cash provided by operating activities (Operating Cash Flow) was $2,800 million ($2.8 billion) for the fiscal year ended December 31, 2024.",
        acceptable_answer_variants=[
            "Operating cash flow was $2,800 million ($2.8B) in FY2024.",
            "Net cash from operating activities was $2.8 billion in 2024.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=22,
        expected_section="Item 8. Consolidated Statements of Cash Flows",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 22, Item 8. Consolidated Statements of Cash Flows]",
        expected_claims=[
            "Operating cash flow was $2,800 million ($2.8 billion) in FY2024",
        ],
        expected_metrics=["operating cash flow"],
        category=EvaluationCategory.FINANCIAL_METRIC,
        difficulty=EvaluationDifficulty.EASY,
        notes="Cash flow statement extraction",
    ),

                                                                       
    EvaluationCase(
        case_id="case-07",
        question="How did Acme Corporation's FY2024 revenue compare to FY2023?",
        expected_answer="Acme Corporation's revenue grew by $2,300 million or 18.4% year-over-year, increasing from $12,500 million ($12.5 billion) in FY2023 to $14,800 million ($14.8 billion) in FY2024.",
        acceptable_answer_variants=[
            "Revenue increased 18.4% ($2.3 billion), from $12.5B in 2023 to $14.8B in 2024.",
            "FY2024 revenue rose 18.4% YoY from $12,500 million in FY2023 to $14,800 million.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=12,
        expected_section="Item 8. Consolidated Statements of Operations",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 12, Item 8. Consolidated Statements of Operations]",
        expected_claims=[
            "FY2023 revenue was $12,500 million ($12.5 billion)",
            "FY2024 revenue was $14,800 million ($14.8 billion)",
            "Revenue increased by $2,300 million or 18.4%",
        ],
        expected_metrics=["revenue comparison", "YoY growth"],
        category=EvaluationCategory.COMPARISON,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Period comparison with percentage delta calculation",
    ),
    EvaluationCase(
        case_id="case-08",
        question="Compare Acme Corporation's FY2024 revenue and EBITDA to peer GlobalTech Inc.",
        expected_answer="In FY2024, Acme Corporation generated $14,800 million ($14.8 billion) in revenue and $3,600 million in EBITDA, compared to GlobalTech Inc.'s revenue of $8,500 million ($8.5 billion) and EBITDA of $2,100 million ($2.1 billion). Acme exceeded GlobalTech by $6.3 billion in revenue and $1.5 billion in EBITDA.",
        acceptable_answer_variants=[
            "Acme had $14.8B revenue and $3.6B EBITDA, while GlobalTech had $8.5B revenue and $2.1B EBITDA in FY2024.",
            "Acme's revenue ($14.8B) and EBITDA ($3.6B) both exceeded GlobalTech ($8.5B revenue, $2.1B EBITDA).",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=12,
        expected_section="Item 8. Consolidated Statements of Operations",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 12, Item 8. Consolidated Statements of Operations]",
        expected_claims=[
            "Acme Corporation FY2024 revenue was $14,800 million and EBITDA was $3,600 million",
            "GlobalTech Inc FY2024 revenue was $8,500 million and EBITDA was $2,100 million",
        ],
        expected_metrics=["peer comparison", "revenue", "EBITDA"],
        category=EvaluationCategory.COMPARISON,
        difficulty=EvaluationDifficulty.HARD,
        notes="Cross-document peer company comparison",
    ),

                                                                       
    EvaluationCase(
        case_id="case-09",
        question="What was the operating margin trend across the four quarters of fiscal 2024?",
        expected_answer="Acme Corporation's operating margin trended as follows across 2024: Q1 was 26.1%, Q2 was 25.0%, Q3 contracted to a low of 23.2%, and Q4 rebounded to 24.5%.",
        acceptable_answer_variants=[
            "Operating margin trend: Q1 26.1%, Q2 25.0%, Q3 23.2%, Q4 24.5%.",
            "Margins declined from Q1 (26.1%) to Q3 (23.2%) before recovering to 24.5% in Q4.",
        ],
        expected_document_id="doc-acme-10q-q3-2024",
        expected_document_name="Acme_Corp_Q3_2024_10Q.pdf",
        expected_page=8,
        expected_section="Item 2. Management's Discussion and Analysis — Quarterly Operating Trends",
        expected_citation="[Acme_Corp_Q3_2024_10Q.pdf, Page 8, Item 2. Management's Discussion and Analysis — Quarterly Operating Trends]",
        expected_claims=[
            "Q1 2024 operating margin was 26.1%",
            "Q2 2024 operating margin was 25.0%",
            "Q3 2024 operating margin was 23.2%",
            "Q4 2024 operating margin was 24.5%",
        ],
        expected_metrics=["quarterly margin trend"],
        category=EvaluationCategory.TREND,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Sequential quarterly trajectory analysis",
    ),
    EvaluationCase(
        case_id="case-10",
        question="How did capital expenditures trend from FY2023 to FY2024?",
        expected_answer="Capital expenditures (CapEx) increased by $150 million or 30.0%, rising from $500 million in FY2023 to $650 million in FY2024.",
        acceptable_answer_variants=[
            "CapEx rose from $500 million in 2023 to $650 million in 2024 (a 30% increase).",
            "Capital expenditures grew 30.0% YoY, from $500M in FY2023 to $650M in FY2024.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=22,
        expected_section="Item 8. Consolidated Statements of Cash Flows",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 22, Item 8. Consolidated Statements of Cash Flows]",
        expected_claims=[
            "FY2023 CapEx was $500 million",
            "FY2024 CapEx was $650 million",
            "CapEx increased by $150 million (30.0%)",
        ],
        expected_metrics=["CapEx trend", "percentage increase"],
        category=EvaluationCategory.TREND,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Annual capital expenditure trajectory",
    ),

                                                                       
    EvaluationCase(
        case_id="case-11",
        question="Why did Acme Corporation's operating margin contract in Q3 2024?",
        expected_answer="The contraction of operating margin to 23.2% in Q3 2024 was primarily caused by severe raw material inflationary pressures in key semiconductor components and unexpected supply chain freight disruptions in the Pacific shipping corridor that elevated shipping costs by $85 million.",
        acceptable_answer_variants=[
            "Operating margin declined in Q3 2024 due to semiconductor raw material inflation and supply chain shipping freight disruptions that added $85 million in costs.",
            "Q3 margin compression was caused by semiconductor cost inflation and Pacific freight disruptions ($85M extra cost).",
        ],
        expected_document_id="doc-acme-10q-q3-2024",
        expected_document_name="Acme_Corp_Q3_2024_10Q.pdf",
        expected_page=11,
        expected_section="Item 2. MD&A — Analysis of Operating Margin Compression",
        expected_citation="[Acme_Corp_Q3_2024_10Q.pdf, Page 11, Item 2. MD&A — Analysis of Operating Margin Compression]",
        expected_claims=[
            "Margin contraction was caused by raw material semiconductor inflation",
            "Supply chain freight disruptions in the Pacific corridor elevated costs by $85 million",
        ],
        expected_metrics=["margin drivers", "freight surcharge"],
        category=EvaluationCategory.CAUSAL,
        difficulty=EvaluationDifficulty.HARD,
        notes="Causal attribution requiring explicit documentary evidence",
    ),
    EvaluationCase(
        case_id="case-12",
        question="What drove the increase in Research & Development (R&D) expense in FY2024?",
        expected_answer="R&D expense increased by $380 million to $2,100 million in FY2024 driven by expanded investments in autonomous AI model architectures, accelerated compute infrastructure procurement, and targeted hiring of specialized machine learning engineers.",
        acceptable_answer_variants=[
            "R&D expense grew to $2,100M driven by AI model architecture investments, compute procurement, and machine learning engineer hiring.",
            "The increase was caused by autonomous AI investments, compute infrastructure, and hiring ML engineers.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=29,
        expected_section="Item 7. Management's Discussion and Analysis - Research and Development",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 29, Item 7. Management's Discussion and Analysis - Research and Development]",
        expected_claims=[
            "R&D expense rose to $2,100 million ($380 million increase)",
            "Increase was driven by autonomous AI model architectures, compute procurement, and hiring ML engineers",
        ],
        expected_metrics=["R&D drivers"],
        category=EvaluationCategory.CAUSAL,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Management explanation of operational expense growth",
    ),

                                                                       
    EvaluationCase(
        case_id="case-13",
        question="What cybersecurity and AI regulatory risks were highlighted in Acme Corporation's Item 1A Risk Factors?",
        expected_answer="Item 1A highlighted risks from sophisticated cybersecurity threats and ransomware targeting distributed cloud infrastructure, as well as emerging global AI regulatory frameworks that could impose compliance audits, mandate operational redesigns, or restrict international commercial deployment.",
        acceptable_answer_variants=[
            "Acme highlighted cybersecurity threats/ransomware to cloud infrastructure and AI regulatory compliance uncertainty/audits in Item 1A.",
            "Key risks included ransomware/cybersecurity attacks and international AI regulation compliance burdens.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=35,
        expected_section="Item 1A. Risk Factors — Cybersecurity and Artificial Intelligence Regulation",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 35, Item 1A. Risk Factors — Cybersecurity and Artificial Intelligence Regulation]",
        expected_claims=[
            "Company faces cybersecurity threats and ransomware targeting cloud infrastructure",
            "Emerging AI regulatory frameworks could mandate audits or restrict commercial deployment",
        ],
        expected_metrics=["risk disclosures"],
        category=EvaluationCategory.RISK,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Item 1A risk disclosure verification",
    ),
    EvaluationCase(
        case_id="case-14",
        question="What is Acme Corporation's foreign currency risk exposure and hedging policy?",
        expected_answer="Acme Corporation is exposed to foreign currency fluctuations primarily in the Euro, British Pound, and Japanese Yen, and enters into forward contracts to hedge up to 75% of forecasted commercial transactions over rolling 12-month periods.",
        acceptable_answer_variants=[
            "Acme is exposed to the Euro, Pound, and Yen, and hedges up to 75% of forecasted transactions over 12 months using forward contracts.",
            "Foreign exchange policy hedges up to 75% of rolling 12-month transactions for EUR, GBP, and JPY.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=39,
        expected_section="Item 7A. Quantitative and Qualitative Disclosures About Market Risk - Foreign Exchange",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 39, Item 7A. Quantitative and Qualitative Disclosures About Market Risk - Foreign Exchange]",
        expected_claims=[
            "Currency exposure primarily relates to Euro, British Pound, and Japanese Yen",
            "Hedging policy uses forward contracts for up to 75% of forecasted transactions over 12 months",
        ],
        expected_metrics=["hedging percentage", "currency exposure"],
        category=EvaluationCategory.RISK,
        difficulty=EvaluationDifficulty.MEDIUM,
        notes="Market risk and derivative hedging governance",
    ),

                                                                       
    EvaluationCase(
        case_id="case-15",
        question="Who is Acme Corporation's independent auditor and what opinion did they issue on internal controls in FY2024?",
        expected_answer="PricewaterhouseCoopers LLP served as the independent registered public accounting firm and issued an unqualified audit opinion on both the consolidated financial statements and the Company's internal control over financial reporting as of December 31, 2024.",
        acceptable_answer_variants=[
            "PricewaterhouseCoopers LLP issued an unqualified opinion on the financial statements and internal controls as of Dec 31, 2024.",
            "The auditor is PricewaterhouseCoopers LLP (PwC) who gave an unqualified audit opinion.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=47,
        expected_section="Item 8. Report of Independent Registered Public Accounting Firm",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 47, Item 8. Report of Independent Registered Public Accounting Firm]",
        expected_claims=[
            "PricewaterhouseCoopers LLP is the independent registered public accounting firm",
            "Auditor issued an unqualified audit opinion on financial statements and internal controls",
        ],
        expected_metrics=["auditor name", "audit opinion"],
        category=EvaluationCategory.DOCUMENT_LOOKUP,
        difficulty=EvaluationDifficulty.EASY,
        notes="Audit report specific fact lookup",
    ),
    EvaluationCase(
        case_id="case-16",
        question="What was Acme Corporation's effective income tax rate in FY2024?",
        expected_answer="Acme Corporation's effective income tax rate was 21.4% for FY2024 (tax provision of $530 million on pre-tax income of $2,480 million), compared to 20.8% in FY2023.",
        acceptable_answer_variants=[
            "Effective tax rate was 21.4% for FY2024.",
            "The effective tax rate in 2024 was 21.4%, with a $530M tax provision.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=42,
        expected_section="Item 8. Note 12 — Income Taxes",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 42, Item 8. Note 12 — Income Taxes]",
        expected_claims=[
            "Effective tax rate was 21.4% in FY2024",
            "Provision for income taxes was $530 million on pre-tax income of $2,480 million",
        ],
        expected_metrics=["effective tax rate"],
        category=EvaluationCategory.DOCUMENT_LOOKUP,
        difficulty=EvaluationDifficulty.EASY,
        notes="Tax note lookup",
    ),

                                                                       
    EvaluationCase(
        case_id="case-17",
        question="Calculate Acme Corporation's Free Cash Flow for FY2024 using Operating Cash Flow and Capital Expenditures.",
        expected_answer="Acme Corporation's Free Cash Flow was $2,150 million ($2.15 billion), calculated as Operating Cash Flow of $2,800 million minus Capital Expenditures of $650 million.",
        acceptable_answer_variants=[
            "Free Cash Flow was $2.15 billion ($2,800M operating cash flow minus $650M CapEx).",
            "FCF = $2,800M - $650M = $2,150 million ($2.15B).",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=22,
        expected_section="Item 8. Consolidated Statements of Cash Flows",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 22, Item 8. Consolidated Statements of Cash Flows]",
        expected_claims=[
            "Operating cash flow was $2,800 million",
            "Capital expenditures were $650 million",
            "Free Cash Flow was $2,150 million ($2.15 billion)",
        ],
        expected_metrics=["Free Cash Flow", "Operating Cash Flow", "CapEx"],
        category=EvaluationCategory.MULTI_STEP,
        difficulty=EvaluationDifficulty.HARD,
        notes="Multi-step subtraction arithmetic grounded in financial statements",
    ),
    EvaluationCase(
        case_id="case-18",
        question="Calculate Acme Corporation's Net Debt to EBITDA leverage ratio as of December 31, 2024.",
        expected_answer="Acme Corporation's Net Debt to EBITDA leverage ratio was 0.11x, calculated as Net Debt of $400 million ($1,200 million total debt minus $800 million cash) divided by EBITDA of $3,600 million.",
        acceptable_answer_variants=[
            "Net Debt to EBITDA leverage ratio was 0.11x ($400M net debt divided by $3,600M EBITDA).",
            "Leverage ratio was 0.11x ($1.2B debt - $0.8B cash = $0.4B net debt / $3.6B EBITDA).",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=18,
        expected_section="Item 8. Note 7 — Financing Arrangements and Long-Term Debt",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 18, Item 8. Note 7 — Financing Arrangements and Long-Term Debt]",
        expected_claims=[
            "Total debt was $1,200 million and cash was $800 million, giving net debt of $400 million",
            "EBITDA was $3,600 million",
            "Net debt to EBITDA leverage ratio was 0.11x",
        ],
        expected_metrics=["leverage ratio", "net debt", "EBITDA"],
        category=EvaluationCategory.MULTI_STEP,
        difficulty=EvaluationDifficulty.HARD,
        notes="Multi-step solvency and leverage metric derivation",
    ),

                                                                       
    EvaluationCase(
        case_id="case-19",
        question="What was Acme Corporation's total debt outstanding at the end of FY2024?",
        expected_answer="As of December 31, 2024, Acme Corporation's total outstanding long-term debt was $1,200 million ($1.2 billion), consisting entirely of 4.75% Senior Unsecured Notes.",
        acceptable_answer_variants=[
            "Total debt was $1.2 billion ($1,200 million) in 4.75% Senior Unsecured Notes.",
            "Outstanding debt was $1,200M in 4.75% senior notes.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=18,
        expected_section="Item 8. Note 7 — Financing Arrangements and Long-Term Debt",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 18, Item 8. Note 7 — Financing Arrangements and Long-Term Debt]",
        expected_claims=[
            "Total long-term debt was $1,200 million ($1.2 billion)",
            "Debt consists of 4.75% Senior Unsecured Notes",
        ],
        expected_metrics=["total debt"],
        category=EvaluationCategory.FOLLOW_UP,
        difficulty=EvaluationDifficulty.EASY,
        notes="Turn 1 of debt follow-up thread",
    ),
    EvaluationCase(
        case_id="case-20",
        question="When do those notes mature and what is the coupon rate?",
        expected_answer="The 4.75% Senior Unsecured Notes mature in June 2029 and carry an annual coupon interest rate of 4.75% with semi-annual payments on June 15 and December 15.",
        acceptable_answer_variants=[
            "The notes mature in June 2029 with a 4.75% coupon rate.",
            "Maturity is June 2029 at 4.75% interest.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=18,
        expected_section="Item 8. Note 7 — Financing Arrangements and Long-Term Debt",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 18, Item 8. Note 7 — Financing Arrangements and Long-Term Debt]",
        expected_claims=[
            "Notes mature in June 2029",
            "Coupon interest rate is 4.75%",
        ],
        expected_metrics=["debt maturity", "coupon rate"],
        category=EvaluationCategory.FOLLOW_UP,
        difficulty=EvaluationDifficulty.MEDIUM,
        multi_turn_history=[
            MultiTurnMessage(
                role="user",
                content="What was Acme Corporation's total debt outstanding at the end of FY2024?",
            ),
            MultiTurnMessage(
                role="assistant",
                content="As of December 31, 2024, Acme Corporation's total outstanding long-term debt was $1,200 million ($1.2 billion), consisting entirely of 4.75% Senior Unsecured Notes.",
            ),
        ],
        notes="Turn 2 of debt follow-up thread testing pronoun/elliptical resolution",
    ),
    EvaluationCase(
        case_id="case-21",
        question="What was Acme's capital expenditure in 2024?",
        expected_answer="Acme Corporation's capital expenditures (CapEx) were $650 million in FY2024.",
        acceptable_answer_variants=[
            "CapEx was $650 million in 2024.",
            "Capital expenditures for property, plant, and equipment were $650M.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=22,
        expected_section="Item 8. Consolidated Statements of Cash Flows",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 22, Item 8. Consolidated Statements of Cash Flows]",
        expected_claims=["Capital expenditures were $650 million in FY2024"],
        expected_metrics=["CapEx"],
        category=EvaluationCategory.FOLLOW_UP,
        difficulty=EvaluationDifficulty.EASY,
        notes="Turn 1 of CapEx thread",
    ),
    EvaluationCase(
        case_id="case-22",
        question="How does that figure compare with the prior year?",
        expected_answer="Capital expenditures increased by $150 million or 30.0%, rising from $500 million in FY2023 to $650 million in FY2024.",
        acceptable_answer_variants=[
            "CapEx increased by 30% ($150 million) compared to $500 million in 2023.",
            "In 2023 CapEx was $500M, so 2024 CapEx represents a 30.0% ($150M) increase.",
        ],
        expected_document_id="doc-acme-10k-2024",
        expected_document_name="Acme_Corp_FY2024_10K.pdf",
        expected_page=22,
        expected_section="Item 8. Consolidated Statements of Cash Flows",
        expected_citation="[Acme_Corp_FY2024_10K.pdf, Page 22, Item 8. Consolidated Statements of Cash Flows]",
        expected_claims=[
            "Prior year (FY2023) CapEx was $500 million",
            "CapEx increased by $150 million (30.0%)",
        ],
        expected_metrics=["CapEx comparison", "percentage growth"],
        category=EvaluationCategory.FOLLOW_UP,
        difficulty=EvaluationDifficulty.MEDIUM,
        multi_turn_history=[
            MultiTurnMessage(role="user", content="What was Acme's capital expenditure in 2024?"),
            MultiTurnMessage(
                role="assistant",
                content="Acme Corporation's capital expenditures (CapEx) were $650 million in FY2024.",
            ),
        ],
        notes="Turn 2 of CapEx thread testing relative prior-year comparative resolution",
    ),

                                                                                      
    EvaluationCase(
        case_id="case-23",
        question="What is GlobalTech Inc.'s total debt and net debt position?",
        expected_answer="GlobalTech Inc. had $0 long-term debt and $0 short-term borrowings as of December 31, 2024, holding $950 million in cash and short-term marketable securities for a verified net debt position of $0 million (net cash of $950 million).",
        acceptable_answer_variants=[
            "GlobalTech has $0 debt and zero net debt, holding $950M in cash and marketable securities.",
            "Total debt is $0 and net debt is $0 million for GlobalTech.",
        ],
        expected_document_id="doc-globaltech-10k-2024",
        expected_document_name="GlobalTech_Inc_FY2024_10K.pdf",
        expected_page=15,
        expected_section="Item 8. Note 5 — Liquidity, Capital Structure, and Debt",
        expected_citation="[GlobalTech_Inc_FY2024_10K.pdf, Page 15, Item 8. Note 5 — Liquidity, Capital Structure, and Debt]",
        expected_claims=[
            "GlobalTech had $0 long-term debt and $0 short-term debt",
            "Net debt is $0 million with $950 million cash",
        ],
        expected_metrics=["debt", "net debt"],
        expected_refusal=False,
        verified_negative=True,
        category=EvaluationCategory.INSUFFICIENT_EVIDENCE,
        difficulty=EvaluationDifficulty.HARD,
        notes="CRITICAL TEST: Verified negative finding ($0 debt). Must NOT refuse, must return verified $0 finding.",
    ),
    EvaluationCase(
        case_id="case-24",
        question="What were Acme Corporation's total sales in South America in fiscal year 2020?",
        expected_answer="The provided documents do not contain sufficient information to answer this question.",
        acceptable_answer_variants=[
            "The provided documents do not contain information regarding Acme Corporation's South America sales for 2020.",
            "I do not have sufficient evidence in the uploaded documents to provide South America sales for FY2020.",
        ],
        expected_document_id=None,
        expected_page=None,
        expected_claims=[],
        expected_refusal=True,
        expected_refusal_reason="The provided documents cover FY2024 and Q3 2024 operations and do not contain South America geographic segment sales for fiscal year 2020.",
        category=EvaluationCategory.INSUFFICIENT_EVIDENCE,
        difficulty=EvaluationDifficulty.EASY,
        notes="Insufficient evidence test: Absent historical geographic data must trigger deterministic safe refusal.",
    ),
    EvaluationCase(
        case_id="case-25",
        question="What is the CEO's projected stock selling schedule and personal financial forecast for 2030?",
        expected_answer="The provided documents do not contain sufficient information to answer this question.",
        acceptable_answer_variants=[
            "The provided documents do not contain information regarding the CEO's personal stock selling schedule or 2030 forecasts.",
            "Insufficient information: Personal executive stock trading schedules and 2030 projections are not contained in the provided documents.",
        ],
        expected_document_id=None,
        expected_page=None,
        expected_claims=[],
        expected_refusal=True,
        expected_refusal_reason="Executive personal stock sales schedules and 2030 speculative forecasts are not present in the corporate 10-K or 10-Q filings.",
        category=EvaluationCategory.INSUFFICIENT_EVIDENCE,
        difficulty=EvaluationDifficulty.EASY,
        notes="Insufficient evidence test: Speculative executive query must refuse without hallucination.",
    ),
]


def get_evaluation_dataset() -> EvaluationDataset:
    """
    Get the standard FinSentry Phase 3K production evaluation dataset.
    """
    return EvaluationDataset(
        dataset_version=CURRENT_DATASET_VERSION,
        description="FinSentry AI Financial RAG Production Evaluation Benchmark",
        cases=EVALUATION_CASES,
    )


def filter_by_category(
    dataset: EvaluationDataset, category: EvaluationCategory
) -> List[EvaluationCase]:
    """Filter dataset cases by question category."""
    return [c for c in dataset.cases if c.category == category]


def filter_by_case_id(
    dataset: EvaluationDataset, case_id: str
) -> Optional[EvaluationCase]:
    """Lookup single evaluation case by case ID."""
    for c in dataset.cases:
        if c.case_id.lower() == case_id.lower():
            return c
    return None
