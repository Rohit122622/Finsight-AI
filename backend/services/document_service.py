"""
Document Service for FinSentry AI (Phase 2F).

Manages document upload, multi-format parsing (PDF, TXT, MD, CSV, JSON),
financial-aware text chunking, vector embedding generation, and MongoDB lifecycle
persistence with multi-tenant isolation.
"""

import csv
import hashlib
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pypdf
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database

from core.config import get_settings
from core.constants import DocumentStatus
from core.exceptions import (
    DocumentNotFoundException,
    InvalidDocumentException,
    UnauthorizedDocumentAccessException,
)
from database.connection import get_sync_db, mongodb
from models.document import DocumentChunk, DocumentMetadata, DocumentModel
from services.embedding_service import embedding_service
from services.r2_storage_service import r2_storage_service
from services.storage_service import storage_service

logger = logging.getLogger(__name__)

                                                                            
FINANCIAL_SECTION_PATTERNS = [
    (re.compile(r"item\s+1a?[\.\:\s]+risk\s+factors", re.IGNORECASE), "Item 1A - Risk Factors"),
    (re.compile(r"item\s+1[\.\:\s]+business", re.IGNORECASE), "Item 1 - Business"),
    (re.compile(r"item\s+7[\.\:\s]+management['\’]?s\s+discussion", re.IGNORECASE), "Item 7 - MD&A"),
    (re.compile(r"item\s+8[\.\:\s]+financial\s+statements", re.IGNORECASE), "Item 8 - Financial Statements"),
    (re.compile(r"consolidated\s+balance\s+sheets?", re.IGNORECASE), "Consolidated Balance Sheets"),
    (re.compile(r"consolidated\s+statements?\s+of\s+(operations|income)", re.IGNORECASE), "Consolidated Income Statements"),
    (re.compile(r"consolidated\s+statements?\s+of\s+cash\s+flows?", re.IGNORECASE), "Consolidated Cash Flows"),
    (re.compile(r"notes?\s+to\s+consolidated\s+financial\s+statements?", re.IGNORECASE), "Notes to Financial Statements"),
    (re.compile(r"auditor['\’]?s\s+report|report\s+of\s+independent\s+registered", re.IGNORECASE), "Independent Auditor Report"),
    (re.compile(r"executive\s+summary|overview", re.IGNORECASE), "Executive Summary"),
]


class DocumentService:
    """
    Business logic for document parsing, chunking, and session-scoped management.
    """

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db

    def _get_db(self) -> AsyncIOMotorDatabase:
        if self._db is not None:
            return self._db
        return mongodb.get_db()

                                                                                

    @staticmethod
    def extract_text_from_bytes(
        filename: str, content: bytes
    ) -> Tuple[str, Optional[int], List[Dict[str, Any]]]:
        """
        Extract text from file bytes based on format (PDF, TXT, MD, CSV, JSON).

        Returns:
            Tuple of (full_text, page_count, page_segments)
            where page_segments is a list of dicts with {"page": int, "text": str}.
        """
        ext = Path(filename).suffix.lower()

                                                                       
        if ext == ".pdf":
            try:
                from services.pdf_detection_service import pdf_detection_service
                from services.ocr_service import ocr_service

                detect_res = pdf_detection_service.inspect_pdf(content)
                if not detect_res.is_valid_pdf:
                    raise InvalidDocumentException(detect_res.error_message or "Failed to parse PDF document.")
                if detect_res.has_encryption:
                    raise InvalidDocumentException("PDF is password protected or encrypted.")

                if detect_res.requires_ocr:
                    try:
                        return ocr_service.ocr_document(content, filename=filename)
                    except Exception as ocr_exc:
                        logger.warning("OCR attempt failed for %s: %s", filename, ocr_exc)

                reader = pypdf.PdfReader(io.BytesIO(content))
                page_count = len(reader.pages)
                segments = []
                full_text_parts = []

                for idx, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text() or ""
                    clean_page_text = page_text.strip()
                    if clean_page_text:
                        segments.append({"page": idx, "text": clean_page_text})
                        full_text_parts.append(f"--- [Page {idx}] ---\n{clean_page_text}")

                full_text = "\n\n".join(full_text_parts) if full_text_parts else "PDF contains no extractable text layer."
                return full_text, page_count, segments
            except InvalidDocumentException:
                raise
            except Exception as exc:
                logger.error("PDF parsing failed for '%s': %s", filename, exc)
                raise InvalidDocumentException(f"Failed to parse PDF document: {exc}")

                                                       
        decoded_text = ""
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                decoded_text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not decoded_text and content:
            raise InvalidDocumentException("Failed to decode text document using supported encodings.")

                                      
        if ext in [".csv", ".tsv"]:
            try:
                delimiter = "\t" if ext == ".tsv" else ","
                reader = csv.reader(io.StringIO(decoded_text), delimiter=delimiter)
                rows = list(reader)
                if not rows:
                    return "", None, [{"page": 1, "text": ""}]

                                                     
                headers = rows[0]
                header_line = "| " + " | ".join(headers) + " |"
                sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                data_lines = ["| " + " | ".join(row) + " |" for row in rows[1:] if any(cell.strip() for cell in row)]
                table_text = "\n".join([header_line, sep_line] + data_lines)
                return table_text, None, [{"page": 1, "text": table_text}]
            except Exception as exc:
                logger.warning("CSV tabular parsing fallback for '%s': %s", filename, exc)
                return decoded_text, None, [{"page": 1, "text": decoded_text}]

                         
        if ext == ".json":
            try:
                parsed_json = json.loads(decoded_text)
                pretty_json = json.dumps(parsed_json, indent=2)
                return pretty_json, None, [{"page": 1, "text": pretty_json}]
            except Exception as exc:
                logger.warning("JSON formatting fallback for '%s': %s", filename, exc)
                return decoded_text, None, [{"page": 1, "text": decoded_text}]

                           
        return decoded_text, None, [{"page": 1, "text": decoded_text}]

                                                                                

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        page_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> List[DocumentChunk]:
        """
        Segment text into overlapping sliding-window chunks with financial section metadata.
        """
        settings = get_settings()
        size = chunk_size or settings.DEFAULT_CHUNK_SIZE
        overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP

        if overlap >= size:
            overlap = max(0, size // 5)

        chunks: List[DocumentChunk] = []
        clean_text = text.strip()
        if not clean_text:
            return chunks

        stride = size - overlap
        start = 0
        chunk_index = 0
        total_len = len(clean_text)

        while start < total_len:
            end = min(start + size, total_len)

                                                                           
            if end < total_len:
                boundary = clean_text.rfind("\n\n", start + size // 2, end)
                if boundary == -1:
                    boundary = clean_text.rfind("\n", start + size // 2, end)
                if boundary == -1:
                    boundary = clean_text.rfind(". ", start + size // 2, end)
                if boundary != -1:
                    end = boundary + 1

            chunk_slice = clean_text[start:end].strip()
            if chunk_slice:
                token_estimate = max(1, len(chunk_slice) // 4)

                                                         
                page_num = None
                if page_segments:
                    probe = chunk_slice[:40]
                    for seg in page_segments:
                        if probe in seg.get("text", ""):
                            page_num = seg.get("page")
                            break

                                             
                detected_section = None
                for pat, sec_name in FINANCIAL_SECTION_PATTERNS:
                    if pat.search(chunk_slice):
                        detected_section = sec_name
                        break

                chunk_metadata: Dict[str, Any] = {
                    "start_char": start,
                    "end_char": end,
                }
                if detected_section:
                    chunk_metadata["section_type"] = detected_section

                chunks.append(
                    DocumentChunk(
                        chunk_id=str(uuid.uuid4()),
                        chunk_index=chunk_index,
                        text=chunk_slice,
                        token_estimate=token_estimate,
                        character_count=len(chunk_slice),
                        page_number=page_num,
                        metadata=chunk_metadata,
                    )
                )
                chunk_index += 1

            start += stride
            if start >= total_len or stride <= 0:
                break

        return chunks

                                                                                

    async def create_document(
        self,
        user_id: str,
        session_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
    ) -> DocumentModel:
        """
        Persist document file to disk and record metadata in MongoDB with UPLOADED status.
        """
        document_id = str(uuid.uuid4())
        detected_mime = mime_type or storage_service.detect_mime_type(filename)

                                 
        storage_path = storage_service.save_file(
            user_id=user_id,
            session_id=session_id,
            document_id=document_id,
            filename=filename,
            content=content,
        )

                                   
        sha256_hash = hashlib.sha256(content).hexdigest()
        now = datetime.now(timezone.utc)

        doc = DocumentModel(
            document_id=document_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_size=len(content),
            mime_type=detected_mime,
            storage_path=storage_path,
            status=DocumentStatus.UPLOADED.value,
            metadata=DocumentMetadata(
                sha256=sha256_hash,
                character_count=0,
                word_count=0,
                token_estimate=0,
                chunk_count=0,
            ),
            chunks=[],
            created_at=now,
            updated_at=now,
        )

        db = self._get_db()
        await db.documents.insert_one(doc.to_dict())
        logger.info(
            "Created document %s in session %s for user %s",
            document_id,
            session_id,
            user_id,
        )
        return doc

    def _retrieve_content(
        self,
        storage_path: str,
        user_id: str,
        session_id: str,
        document_id: str,
        filename: str,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        Robust multi-strategy document content retrieval for both API and Celery workers:
        1. If R2 object exists (live Cloudflare R2 or process-local mock), fetch from R2.
        2. If storage_path exists as a direct or relative file path on disk, read it.
        3. If metadata_extra contains 'local_path', try reading it.
        4. Reconstruct local path from user_id, session_id, document_id, filename.
        5. Raise InvalidDocumentException if file cannot be found.
        """
        extra = metadata_extra or {}
        storage_key = extra.get("storage_key") or storage_path

                                                             
        if storage_key and r2_storage_service.object_exists(storage_key):
            try:
                return r2_storage_service.get_bytes(storage_key)
            except Exception as exc:
                logger.warning("R2 get_bytes failed for key %s, trying local storage: %s", storage_key, exc)

                                                                  
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

        raise InvalidDocumentException("File not found on storage disk.")

    async def process_document(
        self,
        document_id: str,
        user_id: str,
        session_id: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> DocumentModel:
        """
        Extract text, generate chunks, compute statistics, and transition status to PROCESSED.
        """
        doc = await self.get_document(document_id, user_id, session_id)
        db = self._get_db()

                                     
        now = datetime.now(timezone.utc)
        await db.documents.update_one(
            {"document_id": document_id, "user_id": user_id, "session_id": session_id},
            {"$set": {"status": DocumentStatus.PROCESSING.value, "updated_at": now}},
        )

        try:
            content = self._retrieve_content(
                storage_path=doc.storage_path,
                user_id=user_id,
                session_id=session_id,
                document_id=document_id,
                filename=doc.filename,
                metadata_extra=doc.metadata.extra if doc.metadata else None,
            )

            full_text, page_count, page_segments = self.extract_text_from_bytes(
                doc.filename, content
            )

            chunks = self.chunk_text(
                full_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                page_segments=page_segments,
            )

            word_count = len(full_text.split())
            char_count = len(full_text)
            token_estimate = max(1, char_count // 4) if char_count > 0 else 0
            summary_preview = (
                (full_text[:300] + "...") if len(full_text) > 300 else full_text
            )

            meta = DocumentMetadata(
                page_count=page_count,
                word_count=word_count,
                character_count=char_count,
                token_estimate=token_estimate,
                sha256=doc.metadata.sha256 or hashlib.sha256(content).hexdigest(),
                chunk_count=len(chunks),
                extracted_summary=summary_preview,
            )

            chunks_data = []
            for c in chunks:
                c_dict = c.model_dump()
                try:
                    emb = embedding_service.generate_embedding(c.text)
                    c_dict["embedding"] = emb
                    if "metadata" not in c_dict or not isinstance(c_dict["metadata"], dict):
                        c_dict["metadata"] = {}
                    c_dict["metadata"]["embedding"] = emb
                except Exception as emb_exc:
                    logger.warning("Embedding generation error for chunk %s: %s", c.chunk_id, emb_exc)
                chunks_data.append(c_dict)

            updated_at = datetime.now(timezone.utc)

            await db.documents.update_one(
                {"document_id": document_id, "user_id": user_id, "session_id": session_id},
                {
                    "$set": {
                        "status": DocumentStatus.PROCESSED.value,
                        "metadata": meta.model_dump(),
                        "chunks": chunks_data,
                        "error_message": None,
                        "updated_at": updated_at,
                    }
                },
            )

            doc.status = DocumentStatus.PROCESSED.value
            doc.metadata = meta
            doc.chunks = chunks
            doc.error_message = None
            doc.updated_at = updated_at

            logger.info(
                "Document %s processed successfully: %d chunks, %d words",
                document_id,
                len(chunks),
                word_count,
            )
            return doc

        except Exception as exc:
            err_msg = str(exc)
            logger.error("Processing failed for document %s: %s", document_id, err_msg)
            await db.documents.update_one(
                {"document_id": document_id, "user_id": user_id, "session_id": session_id},
                {
                    "$set": {
                        "status": DocumentStatus.FAILED.value,
                        "error_message": err_msg,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = err_msg
            return doc

    def process_document_sync(
        self,
        document_id: str,
        user_id: str,
        session_id: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous processing helper for Celery workers without asyncio collisions.
        """
        db: Database = get_sync_db()
        record = db.documents.find_one(
            {"document_id": document_id, "user_id": user_id, "session_id": session_id}
        )
        if not record:
            raise DocumentNotFoundException(document_id)

        now = datetime.now(timezone.utc)
        db.documents.update_one(
            {"document_id": document_id},
            {"$set": {"status": DocumentStatus.PROCESSING.value, "updated_at": now}},
        )

        try:
            storage_path = record.get("storage_path", "")
            meta_extra = record.get("metadata", {}).get("extra", {})
            content = self._retrieve_content(
                storage_path=storage_path,
                user_id=user_id,
                session_id=session_id,
                document_id=document_id,
                filename=record.get("filename", ""),
                metadata_extra=meta_extra,
            )

            full_text, page_count, page_segments = self.extract_text_from_bytes(
                record["filename"], content
            )

            chunks = self.chunk_text(
                full_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                page_segments=page_segments,
            )

            word_count = len(full_text.split())
            char_count = len(full_text)
            token_estimate = max(1, char_count // 4) if char_count > 0 else 0
            summary_preview = (
                (full_text[:300] + "...") if len(full_text) > 300 else full_text
            )

            meta = DocumentMetadata(
                page_count=page_count,
                word_count=word_count,
                character_count=char_count,
                token_estimate=token_estimate,
                sha256=record.get("metadata", {}).get("sha256") or hashlib.sha256(content).hexdigest(),
                chunk_count=len(chunks),
                extracted_summary=summary_preview,
            )

            chunks_data = []
            for c in chunks:
                c_dict = c.model_dump()
                try:
                    emb = embedding_service.generate_embedding(c.text)
                    c_dict["embedding"] = emb
                    if "metadata" not in c_dict or not isinstance(c_dict["metadata"], dict):
                        c_dict["metadata"] = {}
                    c_dict["metadata"]["embedding"] = emb
                except Exception as emb_exc:
                    logger.warning("Embedding generation error for chunk %s: %s", c.chunk_id, emb_exc)
                chunks_data.append(c_dict)

            updated_at = datetime.now(timezone.utc)

            db.documents.update_one(
                {"document_id": document_id},
                {
                    "$set": {
                        "status": DocumentStatus.PROCESSED.value,
                        "metadata": meta.model_dump(),
                        "chunks": chunks_data,
                        "error_message": None,
                        "updated_at": updated_at,
                    }
                },
            )

            return {
                "document_id": document_id,
                "status": DocumentStatus.PROCESSED.value,
                "chunk_count": len(chunks),
                "word_count": word_count,
                "character_count": char_count,
            }

        except Exception as exc:
            err_msg = str(exc)
            logger.error("Sync processing failed for document %s: %s", document_id, err_msg)
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
            return {
                "document_id": document_id,
                "status": DocumentStatus.FAILED.value,
                "error": err_msg,
            }

    async def get_document(
        self, document_id: str, user_id: str, session_id: str
    ) -> DocumentModel:
        """
        Fetch document enforcing user and session compound isolation.
        """
        db = self._get_db()
        doc = await db.documents.find_one(
            {"document_id": document_id, "user_id": user_id, "session_id": session_id}
        )
        if not doc:
                                                                                 
            exists_any = await db.documents.find_one({"document_id": document_id})
            if exists_any:
                logger.warning(
                    "User %s attempted unauthorized access to document %s",
                    user_id,
                    document_id,
                )
                raise UnauthorizedDocumentAccessException()
            raise DocumentNotFoundException(document_id)

        return DocumentModel.from_mongo(doc)

    async def list_documents(
        self, user_id: str, session_id: str, skip: int = 0, limit: int = 20
    ) -> Tuple[List[DocumentModel], int]:
        """
        List documents belonging to a specific session with pagination.
        """
        db = self._get_db()
        query = {"user_id": user_id, "session_id": session_id}
        total = await db.documents.count_documents(query)

        cursor = (
            db.documents.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [DocumentModel.from_mongo(d) for d in docs], total

    async def get_document_bytes(
        self, document_id: str, user_id: str, session_id: str
    ) -> Tuple[bytes, str, str]:
        """
        Retrieve raw binary bytes for a document enforcing tenant and session boundaries.
        Prefers R2 storage and falls back to local storage.

        Returns:
            Tuple of (content_bytes, filename, mime_type)
        """
        doc = await self.get_document(document_id, user_id, session_id)
        content = self._retrieve_content(
            storage_path=doc.storage_path,
            user_id=user_id,
            session_id=session_id,
            document_id=document_id,
            filename=doc.filename,
            metadata_extra=doc.metadata.extra if doc.metadata else None,
        )

        return content, doc.filename, doc.mime_type

    async def delete_document(
        self, document_id: str, user_id: str, session_id: str
    ) -> bool:
        """
        Delete document record from MongoDB, R2 private object storage, and disk.
        """
        doc = await self.get_document(document_id, user_id, session_id)
        storage_key = (doc.metadata.extra or {}).get("storage_key") if doc.metadata else doc.storage_path

                                           
        if storage_key and r2_storage_service.object_exists(storage_key):
            r2_storage_service.delete_object(storage_key)

                                                      
        if doc.storage_path:
            storage_service.delete_file(doc.storage_path)

        target_path = storage_service.get_document_path(user_id, session_id, document_id, doc.filename)
        storage_service.delete_file(str(target_path))

                                                
        db = self._get_db()
        await db.documents.delete_one(
            {"document_id": document_id, "user_id": user_id, "session_id": session_id}
        )

                                                        
        try:
            from services.retrieval_service import retrieval_service
            retrieval_service.invalidate_session_cache(session_id, user_id)
            logger.info("Invalidated retrieval cache after deleting document %s", document_id)
        except Exception as cache_exc:
            logger.warning("Non-fatal: cache invalidation after delete failed: %s", cache_exc)

        return True

    async def get_document_chunks_filtered(
        self,
        document_id: str,
        user_id: str,
        session_id: str,
        page_number: Optional[int] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[DocumentChunk], int]:
        """
        Retrieve chunks for a document with optional page and text search filtering.
        """
        doc = await self.get_document(document_id, user_id, session_id)
        chunks = doc.chunks

        if page_number is not None:
            chunks = [c for c in chunks if c.page_number == page_number]

        if search:
            query_lower = search.lower().strip()
            chunks = [c for c in chunks if query_lower in c.text.lower()]

        total_matching = len(chunks)
        paginated_chunks = chunks[skip : skip + limit]
        return paginated_chunks, total_matching


document_service = DocumentService()
