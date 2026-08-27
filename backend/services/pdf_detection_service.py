"""
PDF Inspection and Detection Service for FinSentry AI.

Determines document validity, encryption, page counts, text quality/density,
and makes deterministic decisions on whether OCR is strictly necessary.
"""

import io
import logging
from typing import Optional, Tuple
import pypdf

from agents.document.schemas import PDFDetectionResult

logger = logging.getLogger(__name__)

                                                                       
TEXT_DENSITY_THRESHOLD_CHARS = 40


class PDFDetectionService:
    """
    Service for inspecting PDF documents, validating integrity, and detecting text layers.
    """

    def inspect_pdf(self, content: bytes) -> PDFDetectionResult:
        """
        Inspect PDF bytes and determine text density and OCR requirements.
        """
        if not content or len(content) < 4:
            return PDFDetectionResult(
                is_valid_pdf=False,
                is_text_based=False,
                text_density=0.0,
                page_count=0,
                requires_ocr=False,
                has_encryption=False,
                has_images=False,
                error_message="Empty or invalid file content.",
            )

                              
        if not content.startswith(b"%PDF-"):
            return PDFDetectionResult(
                is_valid_pdf=False,
                is_text_based=False,
                text_density=0.0,
                page_count=0,
                requires_ocr=False,
                has_encryption=False,
                has_images=False,
                error_message="File does not have a valid PDF header (%PDF-).",
            )

        try:
            stream = io.BytesIO(content)
            reader = pypdf.PdfReader(stream)

                                 
            if reader.is_encrypted:
                try:
                                                       
                    decrypt_res = reader.decrypt("")
                    if decrypt_res == 0:
                        return PDFDetectionResult(
                            is_valid_pdf=False,
                            is_text_based=False,
                            text_density=0.0,
                            page_count=0,
                            requires_ocr=False,
                            has_encryption=True,
                            has_images=False,
                            error_message="PDF is password protected or encrypted.",
                        )
                except Exception:
                    return PDFDetectionResult(
                        is_valid_pdf=False,
                        is_text_based=False,
                        text_density=0.0,
                        page_count=0,
                        requires_ocr=False,
                        has_encryption=True,
                        has_images=False,
                        error_message="PDF is encrypted and cannot be decrypted.",
                    )

            page_count = len(reader.pages)
            if page_count == 0:
                return PDFDetectionResult(
                    is_valid_pdf=True,
                    is_text_based=False,
                    text_density=0.0,
                    page_count=0,
                    requires_ocr=False,
                    has_encryption=False,
                    has_images=False,
                    error_message="PDF contains zero pages.",
                )

            total_chars = 0
            has_images = False
            pages_with_text = 0

                                                                              
            max_sample_pages = min(page_count, 30)
            for idx in range(max_sample_pages):
                page = reader.pages[idx]
                text = page.extract_text() or ""
                clean_text = text.strip()
                chars_in_page = len(clean_text)
                total_chars += chars_in_page
                if chars_in_page > 15:
                    pages_with_text += 1

                                               
                if hasattr(page, "images") and len(page.images) > 0:
                    has_images = True

            avg_density = total_chars / max(max_sample_pages, 1)

                           
                                                                                        
            is_text_based = avg_density >= TEXT_DENSITY_THRESHOLD_CHARS or (pages_with_text >= max_sample_pages * 0.5)
            requires_ocr = not is_text_based

            logger.info(
                "PDF inspection: pages=%d, avg_density=%.1f chars/page, text_based=%s, requires_ocr=%s",
                page_count,
                avg_density,
                is_text_based,
                requires_ocr,
            )

            return PDFDetectionResult(
                is_valid_pdf=True,
                is_text_based=is_text_based,
                text_density=avg_density,
                page_count=page_count,
                requires_ocr=requires_ocr,
                has_encryption=False,
                has_images=has_images,
                error_message=None,
            )

        except Exception as exc:
            logger.error("PDF inspection failed with exception: %s", exc)
            return PDFDetectionResult(
                is_valid_pdf=False,
                is_text_based=False,
                text_density=0.0,
                page_count=0,
                requires_ocr=False,
                has_encryption=False,
                has_images=False,
                error_message=f"Malformed or corrupted PDF document: {exc}",
            )


pdf_detection_service = PDFDetectionService()
