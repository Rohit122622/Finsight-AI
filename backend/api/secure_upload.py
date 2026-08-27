"""
Secure Document Upload API endpoint for FinSentry AI (Phase 2D).

Orchestrates authentication, session verification, extension/MIME/signature checks,
PDF integrity & page limits, malware scanning, SHA-256 duplicate detection,
private R2 object storage, rollback handling, and asynchronous Celery job creation.
"""

import hashlib
import io
import logging
from pathlib import Path
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from core.config import get_settings
from core.constants import AgentTaskType, DocumentStatus
from core.exceptions import (
    CorruptedDocumentException,
    DuplicateDocumentException,
    InvalidDocumentException,
    MalwareDetectedException,
    PageLimitExceededException,
    ScannerUnavailableException,
    StorageServiceException,
    UploadRateLimitException,
)
from database.connection import mongodb
from middleware.auth_middleware import get_current_user
from models.document import DocumentMetadata, DocumentModel
from models.user import UserModel
from schemas.document import SecureUploadResponse
from services.job_service import job_service
from services.malware_scanner import malware_scanner
from services.r2_storage_service import r2_storage_service
from services.storage_service import StorageService, storage_service
from services.upload_rate_limiter import upload_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/upload",
    response_model=SecureUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Production-grade secure document upload pipeline (Phase 2D)",
)
async def upload_document_secure(
    file: UploadFile = File(..., description="Document file (PDF, TXT, CSV, MD, JSON)"),
    session_id: str = Form(..., description="Target research session ID"),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Secure document ingestion endpoint.

    Performs full verification pipeline:
    1. Upload rate limiting
    2. Session ownership validation
    3. Extension & MIME validation
    4. PDF magic bytes signature check
    5. PDF structural integrity & page count limit
    6. Antivirus / malware scan
    7. SHA-256 duplicate detection
    8. Private Cloudflare R2 object storage
    9. MongoDB document metadata persistence (with rollback)
    10. Asynchronous Celery job creation & immediate return
    """
    settings = get_settings()
    user_id = str(current_user.id)
    db = mongodb.get_db()


    try:
        upload_rate_limiter.check_rate_limit(user_id)
    except UploadRateLimitException as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )


    try:
        obj_id = ObjectId(session_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )

    session_doc = await db.research_sessions.find_one({"_id": obj_id, "user_id": user_id})
    if not session_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )


    raw_filename = file.filename or ""
    clean_filename = StorageService.sanitize_filename(raw_filename)
    if not clean_filename or clean_filename == "unnamed_document":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or empty filename provided.",
        )

    ext = Path(clean_filename).suffix.lower()
    if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not supported. Allowed: {settings.ALLOWED_DOCUMENT_EXTENSIONS}",
        )


    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if file_size > settings.MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
            detail=f"File size exceeds limit of {settings.MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)}MB.",
        )


    detected_mime = storage_service.detect_mime_type(clean_filename)
    page_count = None

    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF header signature. File is not a genuine PDF.",
            )

        try:
            reader = PdfReader(io.BytesIO(content))
            page_count = len(reader.pages)
            if page_count == 0:
                raise CorruptedDocumentException("PDF structure is invalid: 0 pages found.")
        except Exception as exc:
            logger.warning("PDF corruption validation error for %s: %s", clean_filename, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Corrupted or invalid PDF structure: {exc}",
            )

        if page_count > settings.MAX_DOCUMENT_PAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document exceeds maximum page limit ({page_count}/{settings.MAX_DOCUMENT_PAGES} pages).",
            )
    else:

        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File content cannot be decoded as valid text.",
                )


    try:
        malware_scanner.scan_bytes(content, clean_filename)
    except MalwareDetectedException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ScannerUnavailableException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


    sha256_hash = hashlib.sha256(content).hexdigest()

    existing_doc = await db.documents.find_one({
        "user_id": user_id,
        "session_id": session_id,
        "metadata.sha256": sha256_hash,
    })
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate document detected. This exact file has already been uploaded to this session (document_id: {existing_doc.get('document_id')}).",
        )


    document_id = str(ObjectId())
    storage_key = r2_storage_service.generate_storage_key(user_id, document_id, ext=ext)

    try:
        r2_storage_service.upload_bytes(storage_key, content, content_type=detected_mime)

        local_path = storage_service.save_file(user_id, session_id, document_id, clean_filename, content)
    except StorageServiceException as exc:
        logger.error("Failed to upload document to R2 storage: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service failure while uploading document.",
        )


    meta = DocumentMetadata(
        page_count=page_count,
        character_count=file_size,
        token_estimate=max(1, file_size // 4),
        sha256=sha256_hash,
        extra={
            "storage_key": storage_key,
            "local_path": local_path,
        },
    )

    doc_model = DocumentModel(
        document_id=document_id,
        session_id=session_id,
        user_id=user_id,
        filename=clean_filename,
        file_size=file_size,
        mime_type=detected_mime,
        storage_path=local_path,
        status=DocumentStatus.UPLOADED.value,
        metadata=meta,
    )

    try:
        await db.documents.insert_one(doc_model.to_dict())
    except Exception as exc:
        logger.error("MongoDB document insert failed; rolling back R2 storage: %s", exc)
        r2_storage_service.delete_object(storage_key)
        storage_service.delete_file(local_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist document metadata in database.",
        )


    job_id = None
    try:
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="CrewOrchestrator",
            task_type=AgentTaskType.DOCUMENT_ANALYSIS.value,
            payload={"document_id": document_id, "session_id": session_id, "user_id": user_id},
            session_id=session_id,
        )
        job_id = job.job_id
    except Exception as exc:
        logger.warning(
            "Asynchronous Celery dispatch for document %s failed (%s); document remains in UPLOADED state.",
            document_id,
            exc,
        )

    return SecureUploadResponse(
        document_id=document_id,
        session_id=session_id,
        user_id=user_id,
        filename=clean_filename,
        file_size=file_size,
        mime_type=detected_mime,
        sha256=sha256_hash,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED.value,
        job_id=job_id,
        created_at=doc_model.created_at,
        message="Document uploaded securely and queued for background processing.",
    )
