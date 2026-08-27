"""
FinSentry AI — Phase 3K Evaluation API Router.

Exposes internal, authenticated REST endpoints for:
  - POST /api/v1/evaluation/run: Trigger an evaluation benchmark run
  - GET  /api/v1/evaluation/dataset: Retrieve dataset summary & test cases
  - GET  /api/v1/evaluation/latest: Retrieve the latest evaluation report
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from evaluation.dataset import get_evaluation_dataset
from evaluation.regression import regression_comparator
from evaluation.runner import rag_evaluation_runner
from middleware.auth_middleware import get_current_user
from models.user import UserModel
from schemas.evaluation import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationReport,
    EvaluationRunRequest,
    EvaluationRunResponse,
    ExecutionMode,
)

logger = logging.getLogger(__name__)

router = APIRouter()


_latest_report: Optional[EvaluationReport] = None


@router.post(
    "/run",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger RAG evaluation run",
)
async def trigger_evaluation_run(
    request: EvaluationRunRequest = EvaluationRunRequest(),
    current_user: UserModel = Depends(get_current_user),
) -> EvaluationRunResponse:
    """
    Trigger evaluation benchmark run across dataset cases.
    Requires user authentication.
    """
    global _latest_report
    user_id = str(current_user.id)
    session_id = f"eval-session-{user_id[:8]}"

    mode = ExecutionMode.LIVE_LLM if request.live_mode else ExecutionMode.DETERMINISTIC_MOCK

    try:
        report = await rag_evaluation_runner.run_evaluation(
            category=request.category,
            case_id=request.case_id,
            mode=mode,
            session_id=session_id,
            user_id=user_id,
        )
        _latest_report = report

        return EvaluationRunResponse(
            report_id=report.report_id,
            dataset_version=report.dataset_version,
            execution_mode=report.execution_mode,
            total_cases=report.aggregate_metrics.total_cases,
            passed_cases=report.aggregate_metrics.passed_cases,
            failed_cases=report.aggregate_metrics.failed_cases,
            overall_score=report.aggregate_metrics.overall_score,
            aggregate_metrics=report.aggregate_metrics,
            case_results=report.case_results,
            regression_comparison=report.regression_comparison,
            message="Evaluation run completed successfully",
        )
    except Exception as exc:
        logger.error("Evaluation run failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(exc)}",
        )


@router.get(
    "/dataset",
    status_code=status.HTTP_200_OK,
    summary="Retrieve evaluation dataset information",
)
async def get_dataset_info(
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get evaluation dataset version, metadata, and case definitions.
    """
    dataset = get_evaluation_dataset()
    return {
        "dataset_version": dataset.dataset_version,
        "description": dataset.description,
        "total_cases": dataset.total_cases,
        "cases": [c.model_dump() for c in dataset.cases],
    }


@router.get(
    "/latest",
    response_model=Optional[EvaluationReport],
    status_code=status.HTTP_200_OK,
    summary="Retrieve latest evaluation report",
)
async def get_latest_evaluation_report(
    current_user: UserModel = Depends(get_current_user),
) -> Optional[EvaluationReport]:
    """
    Retrieve the most recent evaluation report in memory.
    """
    if _latest_report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation runs have been executed yet.",
        )
    return _latest_report
