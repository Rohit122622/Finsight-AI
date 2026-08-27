"""
Isolated OCR Service and Adapters for FinSentry AI.

Provides modular OCR extraction interface with Unstructured support,
mock hooks for unit/integration testing, and graceful error handling.
"""

import io
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BaseOCRAdapter(ABC):
    """Abstract interface for OCR extraction backends."""

    @abstractmethod
    def ocr_document(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        """
        Execute OCR on binary content.

        Returns:
            Tuple of (full_text, page_count, page_segments)
            where page_segments is a list of dicts with {"page": int, "text": str}.
        """
        pass


class UnstructuredOCRAdapter(BaseOCRAdapter):
    """Adapter for Unstructured-based OCR extraction."""

    def ocr_document(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        try:
            from unstructured.partition.pdf import partition_pdf                

            elements = partition_pdf(
                file=io.BytesIO(content),
                strategy="ocr_only",
                infer_table_structure=True,
            )

            page_map: Dict[int, List[str]] = {}
            for el in elements:
                page_num = getattr(el.metadata, "page_number", 1) or 1
                page_map.setdefault(page_num, []).append(str(el))

            segments = []
            full_parts = []
            for p_num in sorted(page_map.keys()):
                p_text = "\n".join(page_map[p_num]).strip()
                if p_text:
                    segments.append({"page": p_num, "text": p_text})
                    full_parts.append(f"--- [Page {p_num}] ---\n{p_text}")

            full_text = "\n\n".join(full_parts)
            page_count = len(page_map) or 1
            return full_text, page_count, segments

        except ImportError:
            logger.warning("Unstructured OCR library not available in environment.")
            raise RuntimeError("Unstructured OCR library is not installed.")
        except Exception as exc:
            logger.error("Unstructured OCR execution failed: %s", exc)
            raise RuntimeError(f"OCR execution failed: {exc}")


class FallbackOCRAdapter(BaseOCRAdapter):
    """
    Testing and fallback OCR adapter.
    Allows registering mock OCR responses for tests or simulating scanned text extraction.
    """

    def __init__(self) -> None:
        self._mock_responses: Dict[str, Tuple[str, int, List[Dict[str, Any]]]] = {}
        self._default_mock_text: Optional[str] = None

    def set_mock_response(
        self, filename: str, full_text: str, page_count: int, segments: List[Dict[str, Any]]
    ) -> None:
        """Testing hook to register deterministic OCR output for specific test files."""
        self._mock_responses[filename] = (full_text, page_count, segments)

    def set_default_mock_text(self, text: Optional[str]) -> None:
        self._default_mock_text = text

    def clear_mocks(self) -> None:
        self._mock_responses.clear()
        self._default_mock_text = None

    def ocr_document(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        if filename in self._mock_responses:
            return self._mock_responses[filename]

        if self._default_mock_text is not None:
            return (
                self._default_mock_text,
                1,
                [{"page": 1, "text": self._default_mock_text}],
            )

                                                                        
        raise RuntimeError(
            f"OCR engine is not configured to process scanned document '{filename}'."
        )


class EasyOCRAdapter(BaseOCRAdapter):
    """
    Production OCR adapter using EasyOCR with pypdfium2 rasterization.
    Executes deep learning OCR on scanned image-only PDFs with GPU/CPU support.
    """

    def __init__(self, use_gpu: Optional[bool] = None) -> None:
        self._use_gpu = use_gpu
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            try:
                import easyocr
                import torch
                gpu_avail = torch.cuda.is_available() if self._use_gpu is None else self._use_gpu
                self._reader = easyocr.Reader(["en"], gpu=gpu_avail, verbose=False)
            except Exception as exc:
                logger.error("Failed to initialize EasyOCR reader: %s", exc)
                raise RuntimeError(f"EasyOCR initialization failed: {exc}")
        return self._reader

    def ocr_document(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        try:
            import numpy as np
            import pypdfium2 as pdfium

            reader = self._get_reader()
            pdf = pdfium.PdfDocument(content)
            page_count = len(pdf)
            segments: List[Dict[str, Any]] = []
            full_parts: List[str] = []

            for page_idx in range(page_count):
                page_num = page_idx + 1
                page = pdf[page_idx]
                pil_image = page.render(scale=2.0).to_pil()
                img_np = np.array(pil_image)
                lines = reader.readtext(img_np, detail=0)
                page_text = "\n".join(lines).strip()
                if page_text:
                    segments.append({"page": page_num, "text": page_text})
                    full_parts.append(f"--- [Page {page_num}] ---\n{page_text}")

            full_text = "\n\n".join(full_parts)
            return full_text, page_count, segments
        except Exception as exc:
            logger.error("EasyOCR document extraction failed: %s", exc)
            raise RuntimeError(f"EasyOCR extraction failed: {exc}")


class OCRService:
    """
    Central OCR service delegating to the configured OCR adapter.
    """

    def __init__(self) -> None:
        try:
            import easyocr                             
            self._adapter: BaseOCRAdapter = EasyOCRAdapter()
        except ImportError:
            self._adapter: BaseOCRAdapter = FallbackOCRAdapter()

    def set_adapter(self, adapter: BaseOCRAdapter) -> None:
        self._adapter = adapter

    def get_adapter(self) -> BaseOCRAdapter:
        return self._adapter

    def ocr_document(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        """
        Execute OCR via the configured adapter.
        """
        return self._adapter.ocr_document(content=content, filename=filename)


ocr_service = OCRService()

