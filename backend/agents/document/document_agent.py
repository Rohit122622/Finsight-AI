import hashlib
import io
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.base import AgentResult, BaseAgent
from agents.document.schemas import (
    DocumentAgentPayload,
    DocumentAgentResultSummary,
    ExtractedTable,
    ParsedChunk,
)
from agents.registry import agent_registry
from core.constants import AgentTaskType, DocumentStatus
from core.exceptions import (
    DocumentNotFoundException,
    InvalidDocumentException,
    NonRetryableAgentException,
    RetryableAgentException,
)
from database.connection import get_sync_db
from models.document import DocumentChunk, DocumentMetadata
from services.chunking_service import chunking_service
from services.embedding_service import embedding_service
from services.ocr_service import ocr_service
from services.pdf_detection_service import pdf_detection_service
from services.r2_storage_service import r2_storage_service
from services.storage_service import storage_service
from services.table_extraction_service import table_extraction_service

logger = logging.getLogger(__name__)


class DocumentAgent(BaseAgent):
    """
    Canonical Document Ingestion and Processing Agent for FinSentry AI.
    """

    def __init__(self, name: str = "DocumentAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.DOCUMENT_ANALYSIS)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute full document ingestion, parsing, chunking, and indexing pipeline.

        Payload:
            document_id: str (required)
            session_id: str (required)
            user_id: str (optional, defaults to context)
            chunk_size_tokens: int (optional, default 400)
            chunk_overlap_tokens: int (optional, default 50)
            force_ocr: bool (optional, default False)

        Context:
            user_id: str (required if not in payload)
            job_id: str (optional)
        """
        start_time = time.time()
        document_id = payload.get("document_id")
        session_id = payload.get("session_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        job_id = (context or {}).get("job_id") or payload.get("job_id")

        chunk_size_tokens = payload.get("chunk_size_tokens") or payload.get("chunk_size") or 400
        chunk_overlap_tokens = payload.get("chunk_overlap_tokens") or payload.get("chunk_overlap") or 50
        force_ocr = bool(payload.get("force_ocr", False))

        if not document_id or not session_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'document_id', 'session_id', and 'user_id' must be provided."
            )

        logger.info(
            "DocumentAgent starting execution on document %s (session %s, user %s)",
            document_id,
            session_id,
            user_id,
        )

        db = get_sync_db()


        doc_record = db.documents.find_one(
            {"document_id": document_id, "user_id": user_id, "session_id": session_id}
        )
        if not doc_record:

            any_doc = db.documents.find_one({"document_id": document_id})
            if any_doc:
                raise NonRetryableAgentException(f"Unauthorized access to document '{document_id}'.")
            raise NonRetryableAgentException(f"Document '{document_id}' not found.")

        filename = doc_record.get("filename", "document.pdf")
        storage_path = doc_record.get("storage_path", "")
        meta_extra = doc_record.get("metadata", {}).get("extra", {})


        now_utc = datetime.now(timezone.utc)
        db.documents.update_one(
            {"document_id": document_id},
            {"$set": {"status": DocumentStatus.PROCESSING.value, "updated_at": now_utc}},
        )

        try:
            t0 = time.time()
            content = self._retrieve_bytes(
                storage_path=storage_path,
                user_id=user_id,
                session_id=session_id,
                document_id=document_id,
                filename=filename,
                metadata_extra=meta_extra,
            )
            retrieval_ms = round((time.time() - t0) * 1000, 1)

            ext = filename.lower().split(".")[-1] if "." in filename else ""
            ocr_invoked = False
            page_count = 1
            page_segments: List[Dict[str, Any]] = []
            extracted_tables: List[ExtractedTable] = []
            full_text = ""
            pdf_inspect_ms = 0.0
            text_extract_ms = 0.0
            table_extract_ms = 0.0

            if ext == "pdf":
                t_detect = time.time()
                detect_res = pdf_detection_service.inspect_pdf(content)

                if not detect_res.is_valid_pdf:
                    raise NonRetryableAgentException(
                        f"PDF validation failed: {detect_res.error_message or 'Corrupted PDF structure'}"
                    )

                if detect_res.has_encryption:
                    raise NonRetryableAgentException("PDF document is encrypted or password-protected.")

                page_count = detect_res.page_count
                pdf_inspect_ms = round((time.time() - t_detect) * 1000, 1)

                t_text = time.time()
                if force_ocr or detect_res.requires_ocr:
                    logger.info("PDF requires OCR (scanned or image-based): invoking OCR service for %s", filename)
                    ocr_invoked = True
                    try:
                        full_text, count, segments = ocr_service.ocr_document(content, filename=filename)
                        page_count = count or page_count
                        page_segments = segments
                    except Exception as ocr_exc:
                        logger.error("OCR execution error for document %s: %s", document_id, ocr_exc)
                        raise NonRetryableAgentException(f"OCR processing failed for scanned document: {ocr_exc}")
                else:
                    logger.info("PDF is text-based: extracting text layer directly without OCR for %s", filename)
                    full_text, page_count, page_segments = self._extract_pdf_text_native(content)
                text_extract_ms = round((time.time() - t_text) * 1000, 1)

                t_table = time.time()
                try:
                    extracted_tables = table_extraction_service.extract_tables_from_pdf_bytes(content)
                except Exception as tbl_exc:
                    logger.warning("Table extraction non-fatal warning for %s: %s", document_id, tbl_exc)
                    extracted_tables = []
                table_extract_ms = round((time.time() - t_table) * 1000, 1)

            else:
                t_text = time.time()
                full_text, page_count, page_segments = self._extract_non_pdf_text(filename, content)
                text_extract_ms = round((time.time() - t_text) * 1000, 1)

            t_chunk = time.time()
            parsed_chunks: List[ParsedChunk] = chunking_service.chunk_document_content(
                document_id=document_id,
                session_id=session_id,
                user_id=user_id,
                page_segments=page_segments,
                extracted_tables=extracted_tables,
                target_token_size=chunk_size_tokens,
                overlap_tokens=chunk_overlap_tokens,
                filename=filename,
            )
            chunking_ms = round((time.time() - t_chunk) * 1000, 1)

            t_embed = time.time()
            chunk_texts = [c.text for c in parsed_chunks]
            embeddings = embedding_service.generate_embeddings_batch(chunk_texts)
            embedding_ms = round((time.time() - t_embed) * 1000, 1)

            t_prep = time.time()
            chunks_data: List[Dict[str, Any]] = []
            section_breakdown: Dict[str, int] = {}
            total_tokens = 0

            for idx, c in enumerate(parsed_chunks):
                emb = embeddings[idx] if idx < len(embeddings) else embedding_service.generate_embedding(c.text)
                if not embedding_service.validate_vector(emb):
                    emb = embedding_service.generate_embedding(c.text)

                c.embedding = emb
                sec_name = c.section or "other"
                section_breakdown[sec_name] = section_breakdown.get(sec_name, 0) + 1
                total_tokens += c.token_estimate

                doc_chunk = DocumentChunk(
                    chunk_id=c.chunk_id,
                    document_id=document_id,
                    user_id=user_id,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    source_text=c.source_text,
                    section=c.section,
                    token_estimate=c.token_estimate,
                    character_count=c.character_count,
                    page_number=c.page_number,
                    embedding=c.embedding,
                    metadata={
                        **c.metadata,
                        "content_type": c.content_type,
                        "table_id": c.table_id,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "source_pages": c.source_pages,
                        "extraction_method": c.extraction_method,
                    },
                )
                chunks_data.append(doc_chunk.model_dump())

            word_count = len(full_text.split()) if full_text else sum(len(c.text.split()) for c in parsed_chunks)
            char_count = len(full_text) if full_text else sum(c.character_count for c in parsed_chunks)
            summary_preview = (full_text[:300] + "...") if len(full_text) > 300 else full_text

            stage_timings = {
                "retrieval_ms": retrieval_ms,
                "pdf_inspection_ms": pdf_inspect_ms,
                "text_extraction_ms": text_extract_ms,
                "table_extraction_ms": table_extract_ms,
                "chunking_ms": chunking_ms,
                "embedding_generation_ms": embedding_ms,
                "total_doc_agent_ms": round((time.time() - start_time) * 1000, 1),
            }
            logger.info(
                "DocumentAgent completed stages for %s (%d pages, %d chunks): %s",
                filename,
                page_count,
                len(chunks_data),
                stage_timings,
            )

            doc_meta = DocumentMetadata(
                page_count=page_count,
                word_count=word_count,
                character_count=char_count,
                token_estimate=total_tokens or max(1, char_count // 4),
                sha256=doc_record.get("metadata", {}).get("sha256") or hashlib.sha256(content).hexdigest(),
                chunk_count=len(chunks_data),
                extracted_summary=summary_preview,
                extra={
                    **meta_extra,
                    "ocr_invoked": ocr_invoked,
                    "table_count": len(extracted_tables),
                    "section_breakdown": section_breakdown,
                    "embedding_model": embedding_service.model_name,
                    "embedding_dimension": embedding_service.dimension,
                    "stage_timings": stage_timings,
                },
            )

            updated_at = datetime.now(timezone.utc)

            t_db = time.time()
            db.documents.update_one(
                {"document_id": document_id},
                {
                    "$set": {
                        "status": DocumentStatus.PROCESSED.value,
                        "metadata": doc_meta.model_dump(),
                        "chunks": chunks_data,
                        "error_message": None,
                        "updated_at": updated_at,
                    }
                },
            )
            stage_timings["db_persistence_ms"] = round((time.time() - t_db) * 1000, 1)
            stage_timings["total_doc_agent_ms"] = round((time.time() - start_time) * 1000, 1)

            latency_ms = int((time.time() - start_time) * 1000)



            try:
                from services.retrieval_service import retrieval_service
                cleared = retrieval_service.invalidate_session_cache(session_id, user_id)
                logger.info(
                    "DocumentAgent invalidated retrieval cache for session %s (%d entries cleared)",
                    session_id, cleared,
                )
            except Exception as cache_exc:
                logger.warning("Non-fatal: retrieval cache invalidation failed: %s", cache_exc)

            logger.info(
                "DocumentAgent completed %s: %d pages, %d chunks, %d tables in %dms",
                document_id,
                page_count,
                len(chunks_data),
                len(extracted_tables),
                latency_ms,
            )

            summary = DocumentAgentResultSummary(
                document_id=document_id,
                session_id=session_id,
                filename=filename,
                status=DocumentStatus.PROCESSED.value,
                page_count=page_count,
                chunk_count=len(chunks_data),
                table_count=len(extracted_tables),
                token_count=total_tokens,
                word_count=word_count,
                character_count=char_count,
                section_breakdown=section_breakdown,
                ocr_invoked=ocr_invoked,
                message="Document ingested, parsed, chunked, and vector indexed successfully.",
            )

            return AgentResult(
                success=True,
                task_type=self.default_task_type.value,
                agent_name=self.name,
                summary=summary.model_dump(),
                result_ref=document_id,
                metadata={
                    "page_count": page_count,
                    "chunk_count": len(chunks_data),
                    "table_count": len(extracted_tables),
                    "total_tokens": total_tokens,
                    "ocr_invoked": ocr_invoked,
                    "execution_time_ms": latency_ms,
                },
            )

        except NonRetryableAgentException as exc:
            err_msg = str(exc)
            logger.error("DocumentAgent non-retryable failure for %s: %s", document_id, err_msg)
            db.documents.update_one(
                {"document_id": document_id},
                {
                    "$set": {
                        "status": DocumentStatus.FAILED.value,
                        "error_message": err_msg,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            raise
        except Exception as exc:
            err_msg = str(exc)
            logger.error("DocumentAgent unexpected error for %s: %s", document_id, err_msg)
            db.documents.update_one(
                {"document_id": document_id},
                {
                    "$set": {
                        "status": DocumentStatus.FAILED.value,
                        "error_message": err_msg,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            raise NonRetryableAgentException(f"Document processing failed: {err_msg}")

    def _retrieve_bytes(
        self,
        storage_path: str,
        user_id: str,
        session_id: str,
        document_id: str,
        filename: str,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        Safely fetch raw bytes from Cloudflare R2 or disk fallback.
        """
        extra = metadata_extra or {}
        storage_key = extra.get("storage_key") or storage_path


        if storage_key and r2_storage_service.object_exists(storage_key):
            try:
                return r2_storage_service.get_bytes(storage_key)
            except Exception as exc:
                logger.warning("R2 get_bytes failed for key %s, trying local fallback: %s", storage_key, exc)


        if storage_path:
            try:
                return storage_service.read_file(storage_path)
            except Exception:
                pass


        local_path = extra.get("local_path")
        if local_path and local_path != storage_path:
            try:
                return storage_service.read_file(local_path)
            except Exception:
                pass


        reconstructed = storage_service.get_document_bytes_by_id(user_id, session_id, document_id, filename)
        if reconstructed is not None:
            return reconstructed

        raise NonRetryableAgentException(f"File not found on storage disk or R2 for document '{document_id}'.")

    @staticmethod
    def _extract_pdf_text_native(content: bytes) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Extract text page-by-page from text-based PDF using pypdf.
        """
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
        segments: List[Dict[str, Any]] = []
        full_parts: List[str] = []

        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            clean_text = page_text.strip()
            if clean_text:
                segments.append({"page": idx, "text": clean_text})
                full_parts.append(f"--- [Page {idx}] ---\n{clean_text}")

        full_text = "\n\n".join(full_parts) if full_parts else "PDF contains no extractable text layer."
        return full_text, page_count, segments

    @staticmethod
    def _extract_non_pdf_text(
        filename: str, content: bytes
    ) -> Tuple[str, int, List[Dict[str, Any]]]:
        """
        Extract text from CSV, JSON, MD, TXT documents with multi-encoding fallback.
        """
        import csv
        import json
        from pathlib import Path

        ext = Path(filename).suffix.lower()
        decoded_text = ""
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                decoded_text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not decoded_text and content:
            raise NonRetryableAgentException("Failed to decode text document using supported encodings.")

        if ext in [".csv", ".tsv"]:
            try:
                delimiter = "\t" if ext == ".tsv" else ","
                reader = csv.reader(io.StringIO(decoded_text), delimiter=delimiter)
                rows = list(reader)
                if not rows:
                    return "", 1, [{"page": 1, "text": ""}]
                headers = rows[0]
                header_line = "| " + " | ".join(headers) + " |"
                sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                data_lines = ["| " + " | ".join(row) + " |" for row in rows[1:] if any(cell.strip() for cell in row)]
                table_text = "\n".join([header_line, sep_line] + data_lines)
                return table_text, 1, [{"page": 1, "text": table_text}]
            except Exception:
                return decoded_text, 1, [{"page": 1, "text": decoded_text}]

        if ext == ".json":
            try:
                parsed = json.loads(decoded_text)
                pretty = json.dumps(parsed, indent=2)
                return pretty, 1, [{"page": 1, "text": pretty}]
            except Exception:
                return decoded_text, 1, [{"page": 1, "text": decoded_text}]

        return decoded_text, 1, [{"page": 1, "text": decoded_text}]



document_agent = DocumentAgent("DocumentAgent")
agent_registry.register(document_agent, overwrite=True)


class DocumentProcessingAgent(DocumentAgent):
    """Backward compatible subclass and alias for DocumentAgent."""

    def __init__(self, name: str = "DocumentProcessingAgent") -> None:
        super().__init__(name=name)


document_processing_agent = DocumentProcessingAgent("DocumentProcessingAgent")
agent_registry.register(document_processing_agent, overwrite=True)
