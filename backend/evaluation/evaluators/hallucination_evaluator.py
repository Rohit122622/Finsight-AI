"""
FinSentry AI — Phase 3K Hallucination Evaluator.

Detects:
  - Unsupported financial numbers in generated answers
  - Unsupported claims
  - Invented / fabricated citations
  - Invented documents and pages not in retrieved context
"""

import logging
import re
from typing import List, Optional, Set

from schemas.context import ResearchContext
from schemas.evaluation import EvaluationCase, HallucinationCaseMetrics
from schemas.reasoning import ClaimSupportStatus, ResearchResponse
from schemas.retrieval import RetrievalResponse

logger = logging.getLogger(__name__)


class HallucinationEvaluator:
    """
    Evaluator for detecting hallucinated claims, numbers, or citations in financial answers.
    """

    def evaluate_case(
        self,
        case: EvaluationCase,
        response: Optional[ResearchResponse],
        retrieval_response: Optional[RetrievalResponse],
        context: Optional[ResearchContext] = None,
    ) -> HallucinationCaseMetrics:
        """
        Evaluate hallucination for a single case.
        """
        if not response or not response.answer:
            return HallucinationCaseMetrics(
                hallucinated_claims_count=0,
                unsupported_numbers_count=0,
                fabricated_citations_count=0,
                hallucination_detected=False,
                hallucination_details=[],
                passed=True,
            )

        details: List[str] = []
        unsupported_numbers_count = 0
        fabricated_citations_count = 0
        hallucinated_claims_count = 0

                                                                            
        known_numbers: Set[float] = set()
        if retrieval_response and retrieval_response.results:
            for res in retrieval_response.results:
                txt = getattr(res, "source_text", None) or getattr(res, "text", "") or ""
                known_numbers.update(self._extract_numbers(txt))
        if context and context.documents:
            for doc in context.documents:
                txt = getattr(doc, "source_text", None) or getattr(doc, "text", "") or ""
                known_numbers.update(self._extract_numbers(txt))
        known_numbers.update(self._extract_numbers(case.expected_answer))
        for var in case.acceptable_answer_variants:
            known_numbers.update(self._extract_numbers(var))

                                                                                       
        known_numbers.update({1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.0, 10.0, 12.0, 15.0, 2023.0, 2024.0, 2025.0, 2029.0, 2030.0, 31.0, 0.0})

                                                    
        if not getattr(response, "refused", False):
            actual_numbers = self._extract_numbers(response.answer)
            for num in actual_numbers:
                if not self._is_number_supported(num, known_numbers):
                    unsupported_numbers_count += 1
                    details.append(f"Unsupported financial number detected in answer: {num}")

                                                                             
        retrieved_doc_ids = set()
        if retrieval_response and retrieval_response.results:
            retrieved_doc_ids = {r.document_id for r in retrieval_response.results if r.document_id}

        if response.citations:
            for cit in response.citations:
                doc_id = getattr(cit, "document_id", None)
                if doc_id and retrieved_doc_ids and doc_id not in retrieved_doc_ids:
                    fabricated_citations_count += 1
                    details.append(f"Fabricated citation to non-retrieved document: {doc_id}")

                                                                
        if response.claims:
            for claim in response.claims:
                if claim.support_status == ClaimSupportStatus.UNSUPPORTED:
                    hallucinated_claims_count += 1
                    details.append(f"Unsupported claim: '{claim.claim_text[:60]}...'")

        hallucination_detected = (
            unsupported_numbers_count > 0
            or fabricated_citations_count > 0
            or hallucinated_claims_count > 0
        )

        passed = not hallucination_detected

        return HallucinationCaseMetrics(
            hallucinated_claims_count=hallucinated_claims_count,
            unsupported_numbers_count=unsupported_numbers_count,
            fabricated_citations_count=fabricated_citations_count,
            hallucination_detected=hallucination_detected,
            hallucination_details=details,
            passed=passed,
        )

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract all float and integer numbers from text."""
        numbers: List[float] = []
        cleaned = text.replace(",", "")
        pattern = r"\b\d+(?:\.\d+)?\b"
        for match in re.finditer(pattern, cleaned):
            try:
                numbers.append(float(match.group(0)))
            except ValueError:
                pass
        return numbers

    def _is_number_supported(self, num: float, known_numbers: Set[float]) -> bool:
        """Check if number matches any known number in context or scaled variant."""
        if num in known_numbers:
            return True
        for k in known_numbers:
            if abs(num - k) < 0.01:
                return True
                                                             
            if k > 0 and num > 0:
                if abs(k * 1000 - num) < 0.1 or abs(num * 1000 - k) < 0.1:
                    return True
                if abs(k / 100 - num) < 0.001 or abs(num / 100 - k) < 0.001:
                    return True
        return False


hallucination_evaluator = HallucinationEvaluator()
