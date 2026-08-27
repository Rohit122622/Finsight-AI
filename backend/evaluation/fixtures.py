"""
FinSentry AI — Phase 3K Ground-Truth Evaluation Fixtures.

Provides verified, source-traceable financial documents for evaluation:
  1. doc-acme-10k-2024: Acme Corporation FY2024 Form 10-K (Annual Report)
  2. doc-acme-10q-q3-2024: Acme Corporation Q3 2024 Form 10-Q (Quarterly Report)
  3. doc-globaltech-10k-2024: GlobalTech Inc FY2024 Form 10-K (Peer Benchmark)

Every ground-truth answer in the evaluation dataset maps to specific text chunks,
page numbers, and sections defined in this fixture set.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.document import DocumentChunk
from services.embedding_service import embedding_service


                                                                       

EVALUATION_DOCUMENT_FIXTURES: List[Dict[str, Any]] = [
                                                                        
                                                   
                                                                        
    {
        "document_id": "doc-acme-10k-2024",
        "filename": "Acme_Corp_FY2024_10K.pdf",
        "file_type": "application/pdf",
        "title": "Acme Corporation Annual Report 2024 (Form 10-K)",
        "total_pages": 48,
        "chunks": [
                                                              
            {
                "chunk_id": "chunk-acme-10k-p12-income",
                "page_number": 12,
                "section": "Item 8. Consolidated Statements of Operations",
                "text": (
                    "ACME CORPORATION CONSOLIDATED STATEMENTS OF OPERATIONS\n"
                    "For the Fiscal Year Ended December 31, 2024 (in millions, except per share data):\n"
                    "Total Revenue was $14,800 million ($14.8 billion) for FY2024, compared to $12,500 million ($12.5 billion) in FY2023, representing year-over-year revenue growth of $2,300 million or 18.4%.\n"
                    "Cost of goods sold was $6,780 million, resulting in Gross Profit of $8,020 million and a Gross Margin of 54.2%.\n"
                    "Research & Development expense was $2,100 million.\n"
                    "Operating Income was $2,950 million.\n"
                    "Net Income for the year ended December 31, 2024 was $1,950 million ($1.95 billion), compared to $1,550 million in FY2023.\n"
                    "Diluted earnings per share was $3.90."
                ),
            },
                                       
            {
                "chunk_id": "chunk-acme-10k-p14-ebitda",
                "page_number": 14,
                "section": "Item 7. Non-GAAP Financial Measures - EBITDA and Adjusted EBITDA",
                "text": (
                    "NON-GAAP FINANCIAL MEASURES RECONCILIATION\n"
                    "For the year ended December 31, 2024, Earnings Before Interest, Taxes, Depreciation, and Amortization (EBITDA) reached $3,600 million ($3.6 billion), an increase from $2,950 million in FY2023.\n"
                    "EBITDA margin for FY2024 was 24.3%, expanding 70 basis points from 23.6% in the prior fiscal year.\n"
                    "Depreciation and amortization expense included in operating expenses was $650 million for the year."
                ),
            },
                                                
            {
                "chunk_id": "chunk-acme-10k-p18-debt",
                "page_number": 18,
                "section": "Item 8. Note 7 — Financing Arrangements and Long-Term Debt",
                "text": (
                    "NOTE 7 — FINANCING ARRANGEMENTS AND LONG-TERM DEBT\n"
                    "As of December 31, 2024, the Company's total outstanding long-term debt was $1,200 million ($1.2 billion), consisting entirely of 4.75% Senior Unsecured Notes.\n"
                    "The 4.75% Senior Notes mature in June 2029 with semi-annual interest payments due June 15 and December 15.\n"
                    "The Company held $800 million in cash and cash equivalents, resulting in Net Debt of $400 million ($1,200 million debt less $800 million cash).\n"
                    "With FY2024 EBITDA of $3,600 million, the Net Debt to Adjusted EBITDA leverage ratio stood at 0.11x at fiscal year-end."
                ),
            },
                                              
            {
                "chunk_id": "chunk-acme-10k-p22-cashflow",
                "page_number": 22,
                "section": "Item 8. Consolidated Statements of Cash Flows",
                "text": (
                    "ACME CORPORATION CONSOLIDATED STATEMENTS OF CASH FLOWS\n"
                    "For the Fiscal Year Ended December 31, 2024 (in millions):\n"
                    "Net cash provided by operating activities (Operating Cash Flow) was $2,800 million ($2.8 billion) for FY2024.\n"
                    "Capital expenditures (CapEx) for property, plant, and equipment were $650 million in FY2024, compared to $500 million in FY2023 (an increase of $150 million or 30.0%).\n"
                    "Free Cash Flow (calculated as Operating Cash Flow of $2,800 million minus Capital Expenditures of $650 million) was $2,150 million ($2.15 billion)."
                ),
            },
                                                               
            {
                "chunk_id": "chunk-acme-10k-p26-segments",
                "page_number": 26,
                "section": "Item 1. Segment Financial Performance - Cloud Infrastructure",
                "text": (
                    "BUSINESS SEGMENT REPORTING\n"
                    "The Cloud Infrastructure segment generated $6,200 million ($6.2 billion) in revenue in FY2024, representing 41.9% of Acme Corporation's total consolidated revenue.\n"
                    "Cloud Infrastructure revenue grew 28.5% year-over-year from $4,825 million in FY2023, driven by customer adoption of enterprise multi-cloud management solutions."
                ),
            },
                                                              
            {
                "chunk_id": "chunk-acme-10k-p29-mda-rd",
                "page_number": 29,
                "section": "Item 7. Management's Discussion and Analysis - Research and Development",
                "text": (
                    "RESEARCH AND DEVELOPMENT EXPENSES\n"
                    "Research and development (R&D) expense increased by $380 million to $2,100 million in FY2024 from $1,720 million in FY2023.\n"
                    "The increase was driven by expanded investments in autonomous AI model architectures, accelerated compute infrastructure procurement, and targeted hiring of specialized machine learning engineers."
                ),
            },
                                             
            {
                "chunk_id": "chunk-acme-10k-p35-risks",
                "page_number": 35,
                "section": "Item 1A. Risk Factors — Cybersecurity and Artificial Intelligence Regulation",
                "text": (
                    "ITEM 1A. RISK FACTORS\n"
                    "Cybersecurity Threats: We face sophisticated cybersecurity threats, ransomware attempts, and unauthorized access risks to our distributed cloud infrastructure.\n"
                    "Artificial Intelligence Regulatory Uncertainty: Emerging global regulatory frameworks governing artificial intelligence models, safety audits, and automated algorithmic decision-making could impose compliance burdens, mandate operational redesigns, or restrict international commercial deployment of our AI features."
                ),
            },
                                                        
            {
                "chunk_id": "chunk-acme-10k-p39-fx-risk",
                "page_number": 39,
                "section": "Item 7A. Quantitative and Qualitative Disclosures About Market Risk - Foreign Exchange",
                "text": (
                    "FOREIGN CURRENCY EXCHANGE RISK\n"
                    "We conduct business internationally and are exposed to foreign currency fluctuations, primarily the Euro, British Pound, and Japanese Yen.\n"
                    "Under our foreign exchange risk management policy, the Company enters into forward currency contracts to hedge up to 75% of forecasted foreign currency commercial transactions for rolling twelve-month horizons to minimize net volatility."
                ),
            },
                                                 
            {
                "chunk_id": "chunk-acme-10k-p42-tax",
                "page_number": 42,
                "section": "Item 8. Note 12 — Income Taxes",
                "text": (
                    "NOTE 12 — INCOME TAXES\n"
                    "The effective income tax rate for the fiscal year ended December 31, 2024 was 21.4%, compared to 20.8% in FY2023.\n"
                    "The provision for income taxes was $530 million on pre-tax consolidated income of $2,480 million."
                ),
            },
                                                           
            {
                "chunk_id": "chunk-acme-10k-p47-audit",
                "page_number": 47,
                "section": "Item 8. Report of Independent Registered Public Accounting Firm",
                "text": (
                    "REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM\n"
                    "To the Shareholders and Board of Directors of Acme Corporation:\n"
                    "We have audited the accompanying consolidated balance sheets of Acme Corporation as of December 31, 2024 and 2023, and the related consolidated statements of operations, comprehensive income, and cash flows.\n"
                    "In our opinion, the consolidated financial statements present fairly, in all material respects, the financial position of Acme Corporation in conformity with U.S. GAAP.\n"
                    "We also have audited the Company's internal control over financial reporting as of December 31, 2024, and issued an unqualified audit opinion.\n"
                    "/s/ PricewaterhouseCoopers LLP\n"
                    "San Jose, California\n"
                    "February 18, 2025"
                ),
            },
        ],
    },
                                                                        
                                                    
                                                                        
    {
        "document_id": "doc-acme-10q-q3-2024",
        "filename": "Acme_Corp_Q3_2024_10Q.pdf",
        "file_type": "application/pdf",
        "title": "Acme Corporation Quarterly Report Q3 2024 (Form 10-Q)",
        "total_pages": 32,
        "chunks": [
                                                            
            {
                "chunk_id": "chunk-acme-10q-p08-margins",
                "page_number": 8,
                "section": "Item 2. Management's Discussion and Analysis — Quarterly Operating Trends",
                "text": (
                    "QUARTERLY FINANCIAL SUMMARY AND OPERATING MARGINS\n"
                    "In the third quarter of fiscal 2024 (Q3 2024), revenue reached $3,850 million ($3.85 billion).\n"
                    "Operating margins across fiscal 2024 trended as follows: Q1 2024 was 26.1%, Q2 2024 was 25.0%, Q3 2024 was 23.2%, and Q4 2024 subsequently rebounded to 24.5%.\n"
                    "The third quarter operating margin of 23.2% represented the low point of the fiscal year."
                ),
            },
                                                               
            {
                "chunk_id": "chunk-acme-10q-p11-mda-margin-decline",
                "page_number": 11,
                "section": "Item 2. MD&A — Analysis of Operating Margin Compression",
                "text": (
                    "EXPLANATION OF Q3 OPERATING MARGIN CONTRACTION\n"
                    "The contraction of operating margin to 23.2% in Q3 2024 was primarily caused by severe raw material inflationary pressures in key semiconductor sub-components, combined with unexpected supply chain freight disruptions and surcharges in the Pacific shipping corridor that elevated expedited shipping costs by $85 million during the quarter."
                ),
            },
        ],
    },
                                                                        
                                                                  
                                                                        
    {
        "document_id": "doc-globaltech-10k-2024",
        "filename": "GlobalTech_Inc_FY2024_10K.pdf",
        "file_type": "application/pdf",
        "title": "GlobalTech Inc Annual Report 2024 (Form 10-K)",
        "total_pages": 44,
        "chunks": [
                                                      
            {
                "chunk_id": "chunk-globaltech-10k-p06-financials",
                "page_number": 6,
                "section": "Item 8. Consolidated Financial Highlights",
                "text": (
                    "GLOBALTECH INC. SELECTED FINANCIAL DATA\n"
                    "For the Fiscal Year Ended December 31, 2024 (in millions):\n"
                    "Total Revenue was $8,500 million ($8.5 billion).\n"
                    "EBITDA was $2,100 million ($2.1 billion).\n"
                    "Net Income was $1,100 million ($1.1 billion).\n"
                    "Operating cash flow was $1,750 million."
                ),
            },
                                                                       
            {
                "chunk_id": "chunk-globaltech-10k-p15-debt-zero",
                "page_number": 15,
                "section": "Item 8. Note 5 — Liquidity, Capital Structure, and Debt",
                "text": (
                    "NOTE 5 — CAPITAL STRUCTURE, SOLVENCY, AND ZERO DEBT\n"
                    "As of December 31, 2024, GlobalTech Inc. had $0 long-term debt and $0 short-term borrowings.\n"
                    "The Company maintains zero outstanding debt obligations and held $950 million in unrestricted cash and short-term marketable securities.\n"
                    "Consequently, GlobalTech holds a net debt position of $0 million (net cash of $950 million), maintaining an entirely unencumbered balance sheet."
                ),
            },
        ],
    },
]


def get_all_fixture_chunks(session_id: str, user_id: str) -> List[DocumentChunk]:
    """
    Generate typed DocumentChunk objects with precalculated embeddings for all evaluation documents.
    """
    all_chunks: List[DocumentChunk] = []
    for doc in EVALUATION_DOCUMENT_FIXTURES:
        doc_id = doc["document_id"]
        for ch in doc["chunks"]:
            chunk_obj = DocumentChunk(
                chunk_id=ch["chunk_id"],
                document_id=doc_id,
                session_id=session_id,
                user_id=user_id,
                page_number=ch["page_number"],
                section=ch["section"],
                text=ch["text"],
                embedding=embedding_service.generate_embedding(ch["text"]),
            )
            all_chunks.append(chunk_obj)
    return all_chunks


async def seed_evaluation_documents(
    db: Any,
    session_id: str = "eval-session-001",
    user_id: str = "eval-user-001",
) -> List[Dict[str, Any]]:
    """
    Seed evaluation documents and pre-indexed chunks into MongoDB.
    """
    if db is None:
        return []

    now = datetime.now(timezone.utc)
    seeded_docs: List[Dict[str, Any]] = []

    for doc_fixture in EVALUATION_DOCUMENT_FIXTURES:
        doc_id = doc_fixture["document_id"]
        chunks_data = []
        for ch in doc_fixture["chunks"]:
            chunk_embedding = embedding_service.generate_embedding(ch["text"])
            chunks_data.append(
                {
                    "chunk_id": ch["chunk_id"],
                    "document_id": doc_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "page_number": ch["page_number"],
                    "section": ch["section"],
                    "text": ch["text"],
                    "embedding": chunk_embedding,
                    "created_at": now,
                }
            )

        doc_record = {
            "document_id": doc_id,
            "session_id": session_id,
            "user_id": user_id,
            "filename": doc_fixture["filename"],
            "file_type": doc_fixture["file_type"],
            "title": doc_fixture["title"],
            "total_pages": doc_fixture["total_pages"],
            "status": "PROCESSED",
            "chunks": chunks_data,
            "created_at": now,
            "updated_at": now,
        }

        await db.documents.update_one(
            {"document_id": doc_id, "session_id": session_id, "user_id": user_id},
            {"$set": doc_record},
            upsert=True,
        )
        seeded_docs.append(doc_record)

    return seeded_docs
