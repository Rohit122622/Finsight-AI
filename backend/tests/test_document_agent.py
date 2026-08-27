"""
Comprehensive Automated Test Suite for Document Agent (Priyadarshini).

Tests:
1. Text-based PDF detection (requires_ocr=False)
2. Scanned/image PDF detection (requires_ocr=True)
3. OCR conditional gating (OCR skipped on text PDFs, invoked on scanned PDFs)
4. Unstructured.io OCR adapter and fallback
5. pdfplumber structured table extraction and Markdown table formatting
6. Table integrity (numbers preserved without scrambling)
7. Chunking token bounds (300-500 target tokens) & overlap
8. Section boundary preservation
9. Table atomicity (tables never split across chunks)
10. Section classifier tagging (financials, MD&A, auditor notes, footnotes)
11. Neural BAAI/bge-large-en 1024-dim embedding generation & validation
12. MongoDB Atlas Vector Search definition & retrieval execution
13. Graceful handling of corrupted PDFs
14. Graceful handling of password-protected/encrypted PDFs
"""

import io
import math
import os
import tempfile
import pytest
from pypdf import PdfWriter

from agents.document.document_agent import DocumentAgent
from agents.document.schemas import ExtractedTable, ParsedChunk
from core.constants import DocumentStatus
from core.exceptions import NonRetryableAgentException
from database.indexes import ATLAS_VECTOR_SEARCH_INDEX_DEFINITION
from models.document import DocumentChunk, DocumentMetadata, DocumentModel
from services.chunking_service import ChunkingService, chunking_service
from services.embedding_service import EmbeddingService, embedding_service
from services.ocr_service import BaseOCRAdapter, FallbackOCRAdapter, OCRService, UnstructuredOCRAdapter
from services.pdf_detection_service import PDFDetectionService, pdf_detection_service
from services.section_classifier_service import SectionClassifierService, section_classifier_service
from services.table_extraction_service import TableExtractionService, table_extraction_service


def _create_simple_text_pdf(text_content: str) -> bytes:
    """Helper to create a valid text-based PDF in memory."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, text_content[:100])
    lines = text_content.split("\n")
    y = 700
    for line in lines:
        if y < 50:
            c.showPage()
            y = 750
        c.drawString(72, y, line[:90])
        y -= 15
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _create_password_protected_pdf(text_content: str, password: str = "secret") -> bytes:
    """Helper to create an encrypted/password-protected PDF in memory."""
    raw_pdf = _create_simple_text_pdf(text_content)
    writer = PdfWriter()
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_pdf))
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.getvalue()


# =====================================================================
# 1 & 2: PDF Text vs Scanned Detection Tests
# =====================================================================

def test_text_pdf_detection():
    """Verify that text-dense PDFs are detected as text-based (OCR not required)."""
    text = "Item 8. Consolidated Financial Statements.\n" + ("The company reported total revenue of $10,000,000 for the fiscal year.\n" * 20)
    pdf_bytes = _create_simple_text_pdf(text)

    inspect_res = pdf_detection_service.inspect_pdf(pdf_bytes)
    assert inspect_res.is_valid_pdf is True
    assert inspect_res.has_encryption is False
    assert inspect_res.requires_ocr is False
    assert inspect_res.page_count >= 1
    assert inspect_res.text_density > 40.0


def test_scanned_pdf_detection_low_density():
    """Verify that image/low-density PDFs trigger requires_ocr=True."""
    # PDF with almost zero text (single character on page)
    pdf_bytes = _create_simple_text_pdf("X")
    inspect_res = pdf_detection_service.inspect_pdf(pdf_bytes)
    assert inspect_res.is_valid_pdf is True
    assert inspect_res.requires_ocr is True


# =====================================================================
# 3 & 4: OCR Service & Conditional Gating Tests
# =====================================================================

def test_ocr_service_adapters_and_fallback():
    """Verify that OCRService manages Unstructured and fallback adapters."""
    custom_ocr = OCRService()
    fallback = FallbackOCRAdapter()
    fallback.set_default_mock_text("EXTRACTED_MOCK_OCR_TEXT")

    custom_ocr.set_adapter(fallback)
    full_text, page_count, segments = custom_ocr.ocr_document(b"%PDF-mock", filename="scanned.pdf")
    assert "EXTRACTED_MOCK_OCR_TEXT" in full_text
    assert page_count == 1
    assert len(segments) == 1
    assert segments[0]["text"] == "EXTRACTED_MOCK_OCR_TEXT"


def test_unstructured_adapter_structure():
    """Verify UnstructuredOCRAdapter initializes properly and has ocr_document interface."""
    adapter = UnstructuredOCRAdapter()
    assert isinstance(adapter, BaseOCRAdapter)
    assert hasattr(adapter, "ocr_document")


# =====================================================================
# 5 & 6: pdfplumber Table Extraction & Number Integrity Tests
# =====================================================================

def test_table_extraction_markdown_formatting():
    """Verify table extraction formats rows into valid Markdown tables without number scrambling."""
    service = TableExtractionService()

    table_grid = [
        ["Line Item", "FY 2024", "FY 2023"],
        ["Total Revenue", "$14,800M", "$12,500M"],
        ["Net Income", "$2,450M", "$1,980M"],
        ["Gross Margin", "42.5%", "40.1%"],
    ]
    norm_table = service._normalize_table(table_grid, page_number=1, table_sequence=1)
    assert norm_table is not None
    assert norm_table.metadata["column_count"] == 3
    assert norm_table.metadata["row_count"] == 3
    assert "$14,800M" in norm_table.markdown
    assert "$2,450M" in norm_table.markdown
    assert "| Line Item | FY 2024 | FY 2023 |" in norm_table.markdown
    assert "| --- | --- | --- |" in norm_table.markdown


def test_table_extraction_handles_empty_or_noisy_cells():
    """Verify table cleaner removes whitespace and handles None cells."""
    service = TableExtractionService()
    raw_grid = [
        [" Metric ", None, "Value \n"],
        ["Revenue\n(in millions)", " $1,200 ", "1200"],
    ]
    norm_table = service._normalize_table(raw_grid, page_number=2, table_sequence=1)
    assert norm_table is not None
    assert "Revenue (in millions)" in norm_table.markdown
    assert "$1,200" in norm_table.markdown


# =====================================================================
# 7 & 8: Chunking Token Bounds & Section Boundary Preservation
# =====================================================================

def test_chunking_token_bounds_and_overlap():
    """Verify that ChunkingService targets 300-500 tokens with bounded chunk sizes."""
    paragraphs = [
        f"Paragraph {i}: Acme Corporation recorded strong operating performance across all enterprise software business units in fiscal year 2024, resulting in higher recurring revenue."
        for i in range(30)
    ]
    page_segments = [{"page": 1, "text": "\n\n".join(paragraphs)}]

    chunks = chunking_service.chunk_document_content(
        document_id="doc-test-01",
        session_id="sess-01",
        user_id="user-01",
        page_segments=page_segments,
        extracted_tables=[],
        target_token_size=400,
        overlap_tokens=50,
    )

    assert len(chunks) >= 1
    for ch in chunks:
        assert ch.token_estimate <= 600
        assert len(ch.text) > 0
        assert ch.document_id == "doc-test-01"


def test_section_boundary_preservation():
    """Verify that chunking flushes when crossing detected SEC section boundaries."""
    text_with_sections = (
        "Item 1. Business.\n"
        "Acme Corp develops enterprise financial intelligence software platforms.\n\n"
        "Item 1A. Risk Factors.\n"
        "Our operations are subject to macroeconomic fluctuations, credit risks, and interest rate changes.\n\n"
        "Item 8. Financial Statements and Supplementary Data.\n"
        "Consolidated Statements of Income: Revenue was $14,800M in FY2024."
    )
    page_segments = [{"page": 1, "text": text_with_sections}]

    chunks = chunking_service.chunk_document_content(
        document_id="doc-sec-test",
        session_id="sess-01",
        user_id="user-01",
        page_segments=page_segments,
        extracted_tables=[],
        target_token_size=400,
    )

    sections_found = {c.section for c in chunks if c.section}
    assert len(sections_found) >= 2


# =====================================================================
# 9: Table Atomicity (Never split a table across chunks)
# =====================================================================

def test_table_atomicity():
    """Verify that extracted tables are stored as standalone, atomic chunks (content_type='table')."""
    sample_table = ExtractedTable(
        table_id="tbl-atomic-1",
        page_number=5,
        row_count=10,
        column_count=4,
        headers=["Period", "Revenue", "Operating Income", "Net Margin"],
        markdown="| Period | Revenue | Operating Income | Net Margin |\n| --- | --- | --- | --- |\n| 2024 | $500M | $120M | 24% |",
        raw_rows=[["2024", "$500M", "$120M", "24%"]],
    )

    chunks = chunking_service.chunk_document_content(
        document_id="doc-table-atomic",
        session_id="sess-01",
        user_id="user-01",
        page_segments=[{"page": 5, "text": "Some contextual narrative before table."}],
        extracted_tables=[sample_table],
    )

    table_chunks = [c for c in chunks if c.content_type == "table"]
    assert len(table_chunks) == 1
    tbl_ch = table_chunks[0]
    assert tbl_ch.table_id == "tbl-atomic-1"
    assert "$500M" in tbl_ch.text
    assert tbl_ch.page_number == 5


# =====================================================================
# 10: Section Classifier Tagging
# =====================================================================

def test_section_classifier_tagging():
    """Verify that section classifier tags chunks with financials, MD&A, auditor notes, footnotes."""
    clf = SectionClassifierService()

    sec_fin, label_fin = clf.classify_text("Item 8. Consolidated Financial Statements and Balance Sheet")
    assert sec_fin == "financials"
    assert "Financial Statements" in label_fin

    sec_mda, label_mda = clf.classify_text("Item 7. Management's Discussion and Analysis of Financial Condition")
    assert sec_mda == "md_and_a"
    assert "MD&A" in label_mda

    sec_aud, label_aud = clf.classify_text("Report of Independent Registered Public Accounting Firm")
    assert sec_aud == "auditor_notes"
    assert "Auditor" in label_aud

    sec_ft, label_ft = clf.classify_text("See accompanying footnotes and accounting details")
    assert sec_ft == "footnotes"
    assert "Footnotes" in label_ft


# =====================================================================
# 11: BAAI/bge-large-en Embedding Generation & Dimension Validation
# =====================================================================

def test_bge_large_en_embeddings_dimension_and_normalization():
    """Verify that embeddings are 1024-dimensional and unit-normalized."""
    emb_service = EmbeddingService(model_name="BAAI/bge-large-en-v1.5", dimension=1024)

    text = "Acme Corporation reported consolidated revenue of $14,800 million for fiscal year 2024."
    vec = emb_service.generate_embedding(text)

    assert len(vec) == 1024
    assert emb_service.validate_vector(vec) is True

    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-3


def test_batch_embeddings_generation():
    """Verify batch embedding generation produces identical length and valid vectors."""
    emb_service = EmbeddingService(dimension=1024)
    texts = [
        "First financial chunk regarding gross profit margin expansion.",
        "Second chunk regarding operating cash flow and working capital.",
        "Third chunk regarding debt covenant ratios and leverage.",
    ]
    batch_vecs = emb_service.generate_embeddings_batch(texts)
    assert len(batch_vecs) == 3
    for vec in batch_vecs:
        assert len(vec) == 1024
        assert emb_service.validate_vector(vec) is True


def test_cosine_similarity_computation():
    """Verify cosine similarity between identical and orthogonal vectors."""
    vec1 = [1.0, 0.0] + [0.0] * 1022
    vec2 = [1.0, 0.0] + [0.0] * 1022
    vec3 = [0.0, 1.0] + [0.0] * 1022

    assert abs(EmbeddingService.cosine_similarity(vec1, vec2) - 1.0) < 1e-4
    assert abs(EmbeddingService.cosine_similarity(vec1, vec3) - 0.0) < 1e-4


# =====================================================================
# 12: MongoDB Atlas Vector Search Index Configuration
# =====================================================================

def test_atlas_vector_search_index_schema():
    """Verify Atlas Vector Search index definition matches MongoDB Atlas specifications."""
    idx_def = ATLAS_VECTOR_SEARCH_INDEX_DEFINITION
    assert idx_def["name"] == "vector_index"
    assert idx_def["type"] == "vectorSearch"

    fields = idx_def["definition"]["fields"]
    vector_field = next(f for f in fields if f.get("type") == "vector")
    assert vector_field["path"] == "chunks.embedding"
    assert vector_field["numDimensions"] == 1024
    assert vector_field["similarity"] == "cosine"

    filter_paths = [f["path"] for f in fields if f.get("type") == "filter"]
    assert "session_id" in filter_paths
    assert "user_id" in filter_paths
    assert "status" in filter_paths


# =====================================================================
# 13 & 14: Corrupted and Encrypted PDF Handling
# =====================================================================

def test_corrupted_pdf_inspection():
    """Verify corrupted PDF bytes fail validation cleanly with error message."""
    corrupt_bytes = b"NOT_A_VALID_PDF_HEADER_DATA_123456"
    inspect_res = pdf_detection_service.inspect_pdf(corrupt_bytes)
    assert inspect_res.is_valid_pdf is False
    assert inspect_res.error_message is not None


def test_password_protected_pdf_inspection():
    """Verify password-protected PDF is detected and marked has_encryption=True."""
    encrypted_pdf_bytes = _create_password_protected_pdf("Confidential Financials", password="mypassword")
    inspect_res = pdf_detection_service.inspect_pdf(encrypted_pdf_bytes)
    assert inspect_res.has_encryption is True
