"""
FinSentry AI — Phase 3K RAG Evaluation Package.
"""

from evaluation.dataset import (
    CURRENT_DATASET_VERSION,
    EVALUATION_CASES,
    filter_by_case_id,
    filter_by_category,
    get_evaluation_dataset,
)
from evaluation.fixtures import (
    EVALUATION_DOCUMENT_FIXTURES,
    get_all_fixture_chunks,
    seed_evaluation_documents,
)
from evaluation.regression import RegressionComparator, regression_comparator
from evaluation.runner import RAGEvaluationRunner, rag_evaluation_runner

__all__ = [
    "CURRENT_DATASET_VERSION",
    "EVALUATION_CASES",
    "EVALUATION_DOCUMENT_FIXTURES",
    "RAGEvaluationRunner",
    "RegressionComparator",
    "filter_by_case_id",
    "filter_by_category",
    "get_all_fixture_chunks",
    "get_evaluation_dataset",
    "rag_evaluation_runner",
    "regression_comparator",
    "seed_evaluation_documents",
]
