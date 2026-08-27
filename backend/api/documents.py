"""
FastAPI router for document upload, parsing, chunk inspection, and session management (Phase 2B).
"""

import logging
from typing import Any, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.constants import AgentTaskType
from core.exceptions import (
    DocumentNotFoundException,
    InvalidDocumentException,
    UnauthorizedDocumentAccessException,
)
from database.connection import get_database
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.document import (
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentProcessRequest,
    DocumentResponse,
)
from schemas.job import JobResponse
from services.document_service import document_service
from services.r2_storage_service import r2_storage_service
from services.storage_service import storage_service
from services.job_service import job_service
from services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=List[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload documents to a research session",
)
async def upload_documents(
    session_id: str = Path(..., description="Research session ID"),
    files: List[UploadFile] = File(..., description="One or more document files to upload"),
    auto_process: bool = Query(True, description="Automatically trigger asynchronous document chunking and processing"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Upload financial documents (PDF, TXT, CSV, MD, JSON) to the specified session.

    Enforces tenant and session isolation, validates file sizes, and stores the file on disk.
    If auto_process is True, dispatches an asynchronous Celery task using DocumentProcessingAgent.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be uploaded.",
        )

    created_docs = []
    user_id = str(current_user.id)

    for upload in files:
        try:
            content = await upload.read()
            doc = await document_service.create_document(
                user_id=user_id,
                session_id=session_id,
                filename=upload.filename or "uploaded_document",
                content=content,
                mime_type=upload.content_type,
            )

            if auto_process:
                try:
                    await job_service.create_and_dispatch_job(
                        user_id=user_id,
                        agent_name="CrewOrchestrator",
                        task_type=AgentTaskType.DOCUMENT_ANALYSIS.value,
                        payload={
                            "document_id": doc.document_id,
                            "session_id": session_id,
                        },
                        session_id=session_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Auto-dispatch job failed for document %s: %s",
                        doc.document_id,
                        exc,
                    )

            created_docs.append(doc)

        except InvalidDocumentException as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )

    return created_docs


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents in a research session",
)
async def list_documents(
    session_id: str = Path(..., description="Research session ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve a paginated list of all documents belonging to the session.
    """
    docs, total = await document_service.list_documents(
        user_id=str(current_user.id),
        session_id=session_id,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(
        documents=[DocumentResponse(**d.to_dict()) for d in docs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Retrieve document metadata and chunks",
)
async def get_document(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Fetch full document details, statistics, and extracted text chunks.
    """
    try:
        doc = await document_service.get_document(
            document_id=document_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        return doc
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )


@router.get(
    "/{document_id}/chunks",
    response_model=List[DocumentChunkResponse],
    summary="Retrieve extracted text chunks for a document",
)
async def get_document_chunks(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    page: Optional[int] = Query(None, ge=1, description="Filter chunks by page number"),
    search: Optional[str] = Query(None, description="Search text within chunks"),
    skip: int = Query(0, ge=0, description="Number of chunks to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max chunks to return"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Fetch individual chunk slices for a document with optional page number and text search filtering.
    """
    try:
        chunks, _ = await document_service.get_document_chunks_filtered(
            document_id=document_id,
            user_id=str(current_user.id),
            session_id=session_id,
            page_number=page,
            search=search,
            skip=skip,
            limit=limit,
        )
        return chunks
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )


@router.get(
    "/{document_id}/download",
    summary="Download original uploaded document file",
)
async def download_document(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Response:
    """
    Stream or download the original raw file from private R2 / disk storage.
    """
    try:
        content, filename, mime_type = await document_service.get_document_bytes(
            document_id=document_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        return Response(
            content=content,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )
    except InvalidDocumentException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{document_id}/presigned-url",
    summary="Generate temporary short-lived presigned URL for private document",
)
async def get_document_presigned_url(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    expires_in: int = Query(3600, ge=60, le=86400, description="Expiration time in seconds"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Generate short-lived signed access URL for private Cloudflare R2 object.
    Enforces user and session ownership.
    """
    try:
        doc = await document_service.get_document(
            document_id=document_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        storage_key = (doc.metadata.extra or {}).get("storage_key") or doc.storage_path
        url = r2_storage_service.generate_presigned_url(
            key=storage_key,
            expires_in_seconds=expires_in,
        )
        return {
            "document_id": document_id,
            "presigned_url": url,
            "expires_in_seconds": expires_in,
        }
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presigned URL: {exc}",
        )


@router.post(
    "/{document_id}/process",
    summary="Trigger processing and chunking for a document",
)
async def process_document_endpoint(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    request: DocumentProcessRequest = DocumentProcessRequest(),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Manually trigger text extraction and chunking for a document.

    If async_mode is True (default), enqueues a Celery job and returns HTTP 202 with JobResponse.
    If async_mode is False, executes synchronously and returns DocumentDetailResponse.
    """
    user_id = str(current_user.id)

    try:
        await document_service.get_document(document_id, user_id, session_id)
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )

    if request.async_mode:
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="CrewOrchestrator",
            task_type=AgentTaskType.DOCUMENT_ANALYSIS.value,
            payload={
                "document_id": document_id,
                "session_id": session_id,
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
            },
            session_id=session_id,
        )
        return job


    processed_doc = await document_service.process_document(
        document_id=document_id,
        user_id=user_id,
        session_id=session_id,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    return processed_doc


@router.delete(
    "/{document_id}",
    summary="Delete a document from session and disk",
)
async def delete_document(
    session_id: str = Path(..., description="Research session ID"),
    document_id: str = Path(..., description="Document UUID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Delete document record from MongoDB and delete physical file from storage.
    """
    try:
        await document_service.delete_document(
            document_id=document_id,
            user_id=str(current_user.id),
            session_id=session_id,
        )
        return {
            "success": True,
            "message": f"Document '{document_id}' deleted successfully.",
        }
    except DocumentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    except UnauthorizedDocumentAccessException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this document is forbidden.",
        )
