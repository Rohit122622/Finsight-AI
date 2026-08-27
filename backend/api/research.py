"""
FastAPI router for Semantic Search, Agentic Research, Financial Metric Extraction (Phase 2C),
and Hybrid Retrieval (Phase 3A).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status

from agents.extraction.extraction_agent import extraction_agent
from agents.research.research_agent import research_agent
from core.constants import AgentTaskType
from middleware.auth_middleware import get_current_user
from middleware.owner_middleware import require_session_owner
from models.session import SessionModel
from models.user import UserModel
from schemas.job import JobResponse
from schemas.research import (
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
