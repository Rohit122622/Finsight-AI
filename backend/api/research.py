import io
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse

from agents.extraction.extraction_agent import extraction_agent
from agents.research.research_agent import research_agent
from core.constants import AgentTaskType
from database.connection import mongodb
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.job import JobResponse
from schemas.research import (
    ComparisonQueryRequest,
    ExtractionQueryRequest,
    ExtractionResultResponse,
    ResearchQueryRequest,
    ResearchResultResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResultChunk,
)
from schemas.context import (
    ContextBuildingRequest,
    ResearchContext,
)
from schemas.prompt import (
    PromptBuildRequest,
    PromptPackage,
)
from schemas.reasoning import (
    ReasonQueryRequest,
    ResearchResponse,
)
from schemas.query_understanding import (
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from schemas.retrieval import (
    RetrievalRequest,
    RetrievalResponse,
)
from schemas.output_validation import (
    ValidateOutputRequest,
    ValidateOutputResponse,
    ValidationResult,
)
from services.context_builder_service import context_builder_service
from services.embedding_service import embedding_service
from services.evidence_reasoning_service import evidence_reasoning_service
from services.job_service import job_service
from services.output_validation_service import output_validation_service
from services.prompt_builder_service import prompt_builder
from services.query_understanding_service import query_understanding_service
from services.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/search",
    response_model=SemanticSearchResponse,
    summary="Semantic vector search across session documents",
)
async def semantic_search(
    session_id: str = Path(..., description="Research session ID"),
    request: SemanticSearchRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Query processed document chunks within the session using semantic cosine similarity.

    Guarantees multi-tenant isolation — only returns chunks from documents owned by the user.
    """
    user_id = str(current_user.id)
    matches = await embedding_service.search_session_chunks(
        user_id=user_id,
        session_id=session_id,
        query=request.query,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        document_ids=request.document_ids,
    )

    results = [SemanticSearchResultChunk(**m) for m in matches]
    return SemanticSearchResponse(
        query=request.query,
        session_id=session_id,
        results=results,
        total_results=len(results),
    )





@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    summary="Phase 3A hybrid retrieval across session documents",
)
async def hybrid_retrieve(
    session_id: str = Path(..., description="Research session ID"),
    request: RetrievalRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Execute Phase 3A retrieval: vector, keyword, or hybrid search across session documents.

    Supports metadata filtering, configurable top-K, and Redis caching.
    Guarantees session-scoped, user-isolated retrieval with full citation metadata.
    """
    user_id = str(current_user.id)
    try:
        response = await retrieval_service.retrieve(
            session_id=session_id,
            user_id=user_id,
            request=request,
        )
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )





@router.post(
    "/understand-query",
    response_model=QueryUnderstandingResult,
    summary="Phase 3B query understanding and intent classification",
)
async def understand_query(
    session_id: str = Path(..., description="Research session ID"),
    request: QueryUnderstandingRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Analyze, normalize, and classify a financial research query.

    Extracts financial metrics, currencies, percentages, and temporal signals,
    detects multi-step and follow-up dependencies, and produces structured output.
    Does NOT answer the financial question.
    """
    try:
        req = QueryUnderstandingRequest(
            query=request.query,
            conversation_history=request.conversation_history,
            session_id=session_id,
        )
        return query_understanding_service.understand_query(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )





@router.post(
    "/build-context",
    response_model=ResearchContext,
    summary="Phase 3C multi-source evidence aggregation and context assembly",
)
async def build_research_context(
    session_id: str = Path(..., description="Research session ID"),
    request: ContextBuildingRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Assemble, deduplicate, prioritize, rank, compress, and limit multi-source
    financial research context ready for Research Agent reasoning.
    Does NOT generate the final financial answer.
    """
    try:
        return await context_builder_service.build_context(
            session_id=session_id,
            user_id=str(current_user.id),
            query=request.query,
            retrieved_results=request.retrieved_results,
            financial_metrics=request.financial_metrics,
            red_flags=request.red_flags,
            comparisons=request.comparisons,
            chat_history=request.chat_history,
            session_memory=request.session_memory,
            limits=request.limits,
            auto_retrieve=request.auto_retrieve,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error in build_research_context: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context building failed: {exc}",
        )





@router.post(
    "/build-prompt",
    response_model=PromptPackage,
    summary="Phase 3D modular prompt package generation",
)
async def build_research_prompt_endpoint(
    session_id: str = Path(..., description="Research session ID"),
    request: PromptBuildRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Assemble modular system and user prompt components into a structured PromptPackage.
    Does NOT invoke LLM inference or generate final financial answers.
    """
    try:
        return await prompt_builder.build_prompt_package(
            session_id=session_id,
            user_id=str(current_user.id),
            query=request.query,
            context=request.context,
            query_understanding=request.query_understanding,
            config=request.config,
            limits=request.limits,
            auto_build_context=request.auto_build_context,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error in build_research_prompt_endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt building failed: {exc}",
        )





@router.post(
    "/reason",
    response_model=ResearchResponse,
    summary="Phase 3E grounded evidence-based research reasoning",
)
async def reason_research_query_endpoint(
    session_id: str = Path(..., description="Research session ID"),
    request: ReasonQueryRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Execute full end-to-end evidence reasoning pipeline:
    Query Understanding -> Retrieval -> Context Building -> Prompt Building -> LLM -> Evidence Validation.
    """
    try:
        return await evidence_reasoning_service.reason(
            session_id=session_id,
            user_id=str(current_user.id),
            query=request.query,
            context=request.context,
            query_understanding=request.query_understanding,
            prompt_config=request.prompt_config,
            limits=request.limits,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error in reason_research_query_endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evidence reasoning failed: {exc}",
        )





@router.post(
    "/validate-output",
    response_model=ValidateOutputResponse,
    summary="Phase 3G standalone output validation for research responses",
)
async def validate_research_output_endpoint(
    session_id: str = Path(..., description="Research session ID"),
    request: ValidateOutputRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Validate a Research Agent response against strict Pydantic structure,
    claim grounding, citation validity, multi-tenant security, and confidence calibration.
    """
    try:
        user_id = str(current_user.id)
        validated_resp, val_result = output_validation_service.validate_response(
            response=request.response,
            context=request.context,
            session_id=session_id,
            user_id=user_id,
            config=request.config,
        )
        return ValidateOutputResponse(
            validated_response=validated_resp,
            validation_result=val_result,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Error in validate_research_output_endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Output validation failed: {exc}",
        )


@router.post(
    "/research",
    summary="Execute grounded financial research Q&A",
)
async def run_financial_research(
    session_id: str = Path(..., description="Research session ID"),
    request: ResearchQueryRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Execute context-grounded agentic financial research over session documents.

    If async_mode is True (default), enqueues a Celery job with ResearchAgent and returns HTTP 202.
    If async_mode is False, executes synchronously and returns ResearchResultResponse.
    """
    user_id = str(current_user.id)

    payload = {
        "query": request.query,
        "session_id": session_id,
        "document_ids": request.document_ids,
        "top_k": request.top_k,
        "score_threshold": request.score_threshold,
    }

    if request.async_mode:
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="ResearchAgent",
            task_type=AgentTaskType.RESEARCH.value,
            payload=payload,
            session_id=session_id,
        )
        return job


    result = research_agent.execute(payload=payload, context={"user_id": user_id})
    summary = result.summary or {}

    return ResearchResultResponse(
        query=summary.get("query", request.query),
        session_id=session_id,
        answer=summary.get("answer", ""),
        citations=summary.get("citations", []),
        chunks_retrieved=summary.get("chunks_retrieved", 0),
    )


@router.post(
    "/extract",
    summary="Extract structured financial metrics and KPIs",
)
async def extract_financial_metrics(
    session_id: str = Path(..., description="Research session ID"),
    request: ExtractionQueryRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Extract verified financial metrics from session documents into structured JSON.

    If async_mode is True (default), enqueues a Celery job with ExtractionAgent and returns HTTP 202.
    If async_mode is False, executes synchronously and returns ExtractionResultResponse.
    """
    user_id = str(current_user.id)

    payload = {
        "session_id": session_id,
        "document_id": request.document_id,
        "target_fields": request.target_fields,
    }

    if request.async_mode:
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="ExtractionAgent",
            task_type=AgentTaskType.EXTRACTION.value,
            payload=payload,
            session_id=session_id,
        )
        return job


    result = extraction_agent.execute(payload=payload, context={"user_id": user_id})
    summary = result.summary or {}

    return ExtractionResultResponse(
        session_id=session_id,
        document_id=summary.get("document_id"),
        target_fields=summary.get("target_fields", []),
        extracted_data=summary.get("extracted_data", {}),
        chunks_analyzed=summary.get("chunks_analyzed", 0),
    )


@router.get(
    "/extract",
    summary="Get canonical extracted financial metrics for session",
)
@router.get(
    "/extraction",
    summary="Get canonical extracted financial metrics for session",
)
@router.get(
    "/extracted-metrics",
    summary="Get canonical extracted financial metrics for session",
)
async def get_extracted_metrics(
    session_id: str = Path(..., description="Research session ID"),
    document_id: Optional[str] = Query(None, description="Optional document ID filter"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve canonical financial metrics extracted for this research session from MongoDB.
    Enforces multi-tenant authorization.
    Returns per-document canonical metrics, multi-year data, provenance, confidence scores, and filing details.
    """
    user_id = str(current_user.id)
    db = mongodb.get_db()

    query: dict[str, Any] = {"session_id": session_id, "user_id": user_id}
    if document_id:
        query["document_id"] = document_id

    records = await db.extracted_metrics.find(query).to_list(length=100)
    if not records:
        fallback_query: dict[str, Any] = {"session_id": session_id}
        if document_id:
            fallback_query["document_id"] = document_id
        records = await db.extracted_metrics.find(fallback_query).to_list(length=100)

    docs_out = []
    for r in records:
        r_dict = dict(r)
        if "_id" in r_dict:
            r_dict["_id"] = str(r_dict["_id"])
        docs_out.append(r_dict)

    status_val = "COMPLETED" if docs_out else "NOT_RUN"
    return {
        "status": status_val,
        "session_id": session_id,
        "count": len(docs_out),
        "documents": docs_out,
    }


async def _finalize_comparison_locked_pdf(user_id: str, session_id: str) -> dict:
    """
    Ensure a password-protected (encrypted) comparison PDF exists and is persisted,
    then queue the automatic email of that SAME artifact to the authenticated user.

    Thin async wrapper over the canonical synchronous finalizer (single source of truth,
    shared with the Celery async path). Idempotent — reuses an existing locked artifact
    and does not re-queue email, preserving comparison caching/idempotency.
    """
    import asyncio

    from services.comparison_pdf_service import finalize_comparison_locked_pdf_sync

    return await asyncio.to_thread(finalize_comparison_locked_pdf_sync, user_id, session_id)


@router.post(
    "/compare",
    summary="Compare financial metrics across multiple companies",
)
async def compare_companies(
    session_id: str = Path(..., description="Research session ID"),
    request: ComparisonQueryRequest = ...,
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Compare extracted financial metrics across 2+ companies within the same research session.

    Produces chart-ready peer comparison output with deterministic statistics
    (peer average, highest, lowest, percentile ranks).

    If async_mode is True (default), enqueues a Celery job and returns HTTP 202.
    If async_mode is False, executes synchronously and returns ComparisonResultResponse.
    """
    user_id = str(current_user.id)

    if len(request.document_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comparison requires at least 2 document IDs.",
        )

    payload = {
        "session_id": session_id,
        "document_ids": request.document_ids,
    }

    if request.async_mode:
        job = await job_service.create_and_dispatch_job(
            user_id=user_id,
            agent_name="ComparisonAgent",
            task_type=AgentTaskType.COMPARISON.value,
            payload=payload,
            session_id=session_id,
        )
        # Immediately queue the locked-PDF finalize + email. The finalize task waits
        # (bounded retries) for the ComparisonAgent to persist results, then generates,
        # encrypts, persists, and emails — WITHOUT requiring a manual Download click.
        try:
            from workers.email_tasks import finalize_comparison_email

            finalize_comparison_email.apply_async(
                kwargs={"user_id": user_id, "session_id": session_id},
                countdown=3,
            )
        except Exception as exc:  # noqa: BLE001 - never block comparison dispatch
            logger.warning("Could not queue async comparison finalize (type=%s)", type(exc).__name__)
        return job

    from agents.comparison.comparison_agent import comparison_agent
    result = comparison_agent.execute(payload=payload, context={"user_id": user_id})
    comp_data = result.summary or {}

    c_names = [
        c.get("company_name") if isinstance(c, dict) else str(c)
        for c in comp_data.get("companies", [])
    ]
    d_ids = [
        c.get("document_id") if isinstance(c, dict) else str(c)
        for c in comp_data.get("companies", [])
    ]

    # Generate + encrypt + persist the comparison PDF and queue the automatic email.
    # PDF/email failures never invalidate the successful comparison result.
    pdf_info: dict = {"pdf_available": False, "pdf_locked": False, "email_status": None, "password_available": False}
    try:
        pdf_info = await _finalize_comparison_locked_pdf(user_id, session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Comparison locked-PDF finalization failed (non-fatal): %s", type(exc).__name__)

    return {
        "status": "COMPLETED",
        "comparison": comp_data,
        "company_names": c_names,
        "document_ids": d_ids,
        "pdf_available": pdf_info.get("pdf_available", False),
        "pdf_locked": pdf_info.get("pdf_locked", False),
        "email_status": pdf_info.get("email_status"),
        "password_available": pdf_info.get("password_available", False),
    }


@router.get(
    "/compare",
    summary="Get latest multi-company comparison result for session",
)
async def get_comparison_result(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Retrieve the most recent comparison result for this research session.
    """
    user_id = str(current_user.id)
    db = mongodb.get_db()
    result = await db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id},
        sort=[("updated_at", -1)],
    )
    if not result:
        result = await db.comparison_results.find_one(
            {"session_id": session_id},
            sort=[("updated_at", -1)],
        )
    if not result:
        return {"status": "NOT_RUN", "comparison": None}

    comp_data = result.get("comparison") or result.get("comparison_output") or result
    if isinstance(comp_data, dict):
        if "_id" in comp_data and not isinstance(comp_data["_id"], str):
            comp_data["_id"] = str(comp_data["_id"])
        c_names = result.get("company_names") or [
            c.get("company_name") if isinstance(c, dict) else str(c)
            for c in comp_data.get("companies", [])
        ]
        d_ids = result.get("document_ids") or [
            c.get("document_id") if isinstance(c, dict) else str(c)
            for c in comp_data.get("companies", [])
        ]
    else:
        c_names = result.get("company_names", [])
        d_ids = result.get("document_ids", [])

    return {
        "status": "COMPLETED",
        "comparison": comp_data,
        "company_names": c_names,
        "document_ids": d_ids,
        "pdf_available": bool(result.get("object_key")) or bool(result.get("pdf_locked")),
        "pdf_locked": bool(result.get("pdf_locked", False)),
        "email_status": result.get("email_status"),
        "password_available": bool(result.get("pdf_password_enc")),
    }


async def _load_comparison_locked(user_id: str, session_id: str):
    """
    Ensure the encrypted comparison artifact exists and return
    (object_key, encrypted_bytes, plaintext_password). Owner-scoped.
    The unlocked PDF is never persisted; the encrypted artifact is canonical.
    """
    from services.r2_storage_service import r2_storage_service
    from utils.pdf_security import decrypt_password_at_rest

    pdf_info = await _finalize_comparison_locked_pdf(user_id, session_id)
    if not pdf_info.get("pdf_available"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No comparison results found for this session. Please run comparison first.",
        )
    object_key = pdf_info.get("object_key") or f"comparisons/{user_id}/{session_id}/comparison.pdf"
    try:
        encrypted_bytes = r2_storage_service.get_bytes(object_key)
    except Exception as exc:
        logger.error("Failed to load encrypted comparison PDF: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load comparison PDF.",
        )
    db = mongodb.get_db()
    record = await db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id}, sort=[("updated_at", -1)]
    )
    password = decrypt_password_at_rest((record or {}).get("pdf_password_enc")) if record else None
    return object_key, encrypted_bytes, password


@router.get(
    "/compare/download",
    summary="Download UNLOCKED Comparative Financial Audit PDF (owner only)",
)
async def download_comparison_pdf(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Normal download: returns the UNLOCKED PDF. The canonical persisted artifact is the
    AES-256 encrypted PDF; this endpoint decrypts it IN MEMORY (using the server-side
    protected report password) and streams the unlocked bytes to the authenticated owner.
    The unlocked bytes are NEVER persisted.
    """
    import io as _io

    from utils.pdf_security import decrypt_pdf_bytes

    user_id = str(current_user.id)
    _object_key, encrypted_bytes, password = await _load_comparison_locked(user_id, session_id)
    if not password:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparison PDF password unavailable; cannot produce unlocked copy.",
        )
    try:
        unlocked = decrypt_pdf_bytes(encrypted_bytes, password)  # in-memory only
    except Exception as exc:
        logger.error("Failed to decrypt comparison PDF for unlocked download: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare unlocked comparison PDF.",
        )

    filename = f"FinSentry_Comparison_{session_id[:8]}.pdf"
    return StreamingResponse(
        _io.BytesIO(unlocked),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(unlocked)),
        },
    )


@router.get(
    "/compare/download/locked",
    summary="Download LOCKED (password-protected AES-256) Comparison PDF (owner only)",
)
async def download_comparison_locked_pdf(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """
    Locked download: returns the persisted ENCRYPTED bytes directly (never decrypted).
    This is byte-identical to the email attachment.
    """
    user_id = str(current_user.id)
    _object_key, encrypted_bytes, _password = await _load_comparison_locked(user_id, session_id)

    filename = f"FinSentry_Comparison_LOCKED_{session_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(encrypted_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(encrypted_bytes)),
        },
    )


@router.get(
    "/compare/password",
    summary="Reveal the comparison PDF password (authenticated owner only)",
)
async def reveal_comparison_password(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """Return the password for the encrypted comparison PDF to the authenticated owner only."""
    from utils.pdf_security import decrypt_password_at_rest

    user_id = str(current_user.id)
    db = mongodb.get_db()
    record = await db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id}, sort=[("updated_at", -1)]
    )
    if not record or not record.get("pdf_password_enc"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No comparison PDF password available. Please run comparison first.",
        )
    password = decrypt_password_at_rest(record.get("pdf_password_enc"))
    if not password:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No comparison PDF password available.",
        )
    return {"session_id": session_id, "password": password}


@router.post(
    "/compare/email/retry",
    summary="Retry emailing the encrypted comparison PDF to the authenticated user",
)
async def retry_comparison_email(
    session_id: str = Path(..., description="Research session ID"),
    current_user: UserModel = Depends(get_current_user),
    session: SessionModel = Depends(require_session_owner),
) -> Any:
    """Re-queue the comparison email using the already-persisted encrypted PDF (no regeneration)."""
    user_id = str(current_user.id)
    db = mongodb.get_db()
    record = await db.comparison_results.find_one(
        {"session_id": session_id, "user_id": user_id}, sort=[("updated_at", -1)]
    )
    if not record or not record.get("object_key"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No comparison PDF available to email. Please run comparison first.",
        )

    object_key = record.get("object_key")
    doc_ids_hash = record.get("document_ids_hash")
    update_query: dict[str, Any] = {"session_id": session_id}
    if doc_ids_hash:
        update_query["document_ids_hash"] = doc_ids_hash

    email_status = "queued"
    try:
        from workers.email_tasks import send_locked_pdf_email

        send_locked_pdf_email.apply_async(kwargs={
            "kind": "comparison",
            "user_id": user_id,
            "session_id": session_id,
            "ref_id": doc_ids_hash or "",
            "object_key": object_key,
        })
    except Exception:
        email_status = "failed"
    await db.comparison_results.update_one(update_query, {"$set": {"email_status": email_status}})
    return {"session_id": session_id, "email_status": email_status}
