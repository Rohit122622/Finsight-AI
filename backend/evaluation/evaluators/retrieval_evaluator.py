"""
FinSentry AI — Phase 3K Retrieval Evaluator.

Measures retrieval quality:
  - Hit@1, Hit@3, Hit@5, Hit@10
  - Reciprocal Rank (RR) and Mean Reciprocal Rank (MRR)
  - Document and Page level ground-truth matching
"""

import logging
from typing import List, Optional

from schemas.evaluation import EvaluationCase, RetrievalCaseMetrics
from schemas.retrieval import RetrievalResponse, RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalEvaluator:
    """
    Evaluates whether retrieval candidates contain expected ground-truth sources.
    """

    def evaluate_case(
        self,
        case: EvaluationCase,
        retrieval_response: Optional[RetrievalResponse],
    ) -> RetrievalCaseMetrics:
        """
        Evaluate retrieval metrics for a single evaluation case.
        """
        if case.expected_document_id is None:
                                                                                   
            return RetrievalCaseMetrics(
                hit_at_1=True,
                hit_at_3=True,
                hit_at_5=True,
                hit_at_10=True,
                reciprocal_rank=1.0,
                expected_document_id=None,
                expected_page=None,
                retrieved_documents=[],
                retrieved_pages=[],
                total_retrieved=len(retrieval_response.results) if retrieval_response else 0,
                passed=True,
            )

        if not retrieval_response or not retrieval_response.results:
            return RetrievalCaseMetrics(
                hit_at_1=False,
                hit_at_3=False,
                hit_at_5=False,
                hit_at_10=False,
                reciprocal_rank=0.0,
                expected_document_id=case.expected_document_id,
                expected_page=case.expected_page,
                retrieved_documents=[],
                retrieved_pages=[],
                total_retrieved=0,
                passed=False,
            )

        results = retrieval_response.results
        retrieved_docs: List[str] = []
        retrieved_pages: List[int] = []

        first_match_rank: Optional[int] = None

        for rank, res in enumerate(results, start=1):
            doc_id = getattr(res, "document_id", "")
            page = getattr(res, "page_number", None)
            fname = getattr(res, "document_filename", None) or getattr(res, "filename", None) or ""
            retrieved_docs.append(doc_id)
            if page is not None:
                retrieved_pages.append(page)

                                             
            doc_match = (
                doc_id == case.expected_document_id
                or (case.expected_document_name and case.expected_document_name.lower() in fname.lower())
            )
            page_match = (case.expected_page is None) or (page == case.expected_page)

            if doc_match and page_match and first_match_rank is None:
                first_match_rank = rank

        hit_at_1 = first_match_rank == 1
        hit_at_3 = first_match_rank is not None and first_match_rank <= 3
        hit_at_5 = first_match_rank is not None and first_match_rank <= 5
        hit_at_10 = first_match_rank is not None and first_match_rank <= 10
        reciprocal_rank = 1.0 / first_match_rank if first_match_rank is not None else 0.0

        passed = hit_at_5

        return RetrievalCaseMetrics(
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            hit_at_5=hit_at_5,
            hit_at_10=hit_at_10,
            reciprocal_rank=reciprocal_rank,
            expected_document_id=case.expected_document_id,
            expected_page=case.expected_page,
            retrieved_documents=retrieved_docs,
            retrieved_pages=retrieved_pages,
            total_retrieved=len(results),
            passed=passed,
        )


retrieval_evaluator = RetrievalEvaluator()
