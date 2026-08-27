"""
FinSentry AI — Phase 3K Citation Evaluator.

Evaluates:
  - Citation precision (valid document citations / total citations)
  - Citation recall (expected document citations captured / expected count)
  - Document and page accuracy
  - Support of factual claims
"""

import logging
from typing import List, Optional

from schemas.evaluation import CitationCaseMetrics, EvaluationCase
from schemas.reasoning import ResearchCitation, ResearchResponse

logger = logging.getLogger(__name__)


class CitationEvaluator:
    """
    Evaluates whether the Research Agent's generated citations accurately reflect ground-truth sources.
    """

    def evaluate_case(
        self,
        case: EvaluationCase,
        response: Optional[ResearchResponse],
    ) -> CitationCaseMetrics:
        """
        Evaluate citation metrics for a single response.
        """
        if case.expected_refusal or case.expected_document_id is None:
                                              
            actual_cit_count = len(response.citations) if response else 0
            passed = actual_cit_count == 0
            return CitationCaseMetrics(
                total_citations=actual_cit_count,
                valid_citations=0,
                document_matches=0,
                page_matches=0,
                precision=1.0 if actual_cit_count == 0 else 0.0,
                recall=1.0,
                accuracy=1.0 if actual_cit_count == 0 else 0.0,
                supports_claims=True,
                actual_citations=[c.format_string() if hasattr(c, "format_string") else str(c) for c in getattr(response, "citations", [])],
                passed=passed,
            )

        if not response or not response.citations:
            return CitationCaseMetrics(
                total_citations=0,
                valid_citations=0,
                document_matches=0,
                page_matches=0,
                precision=0.0,
                recall=0.0,
                accuracy=0.0,
                supports_claims=False,
                actual_citations=[],
                passed=False,
            )

        citations = response.citations
        total_citations = len(citations)
        document_matches = 0
        page_matches = 0
        valid_citations = 0

        actual_citation_strs = []

        for cit in citations:
            cit_str = cit.format_string() if hasattr(cit, "format_string") else str(cit)
            actual_citation_strs.append(cit_str)

            doc_id = getattr(cit, "document_id", None)
            doc_name = getattr(cit, "document_name", None) or getattr(cit, "source_document", None) or ""
            page = getattr(cit, "page_number", None)

                                  
            doc_match = (
                doc_id == case.expected_document_id
                or (case.expected_document_name and case.expected_document_name.lower() in str(doc_name).lower())
            )
            if doc_match:
                document_matches += 1

                              
            page_match = (case.expected_page is None) or (page == case.expected_page)
            if page_match and doc_match:
                page_matches += 1

            if doc_match:
                valid_citations += 1

        precision = (valid_citations / total_citations) if total_citations > 0 else 0.0
        recall = 1.0 if document_matches > 0 else 0.0
        accuracy = (precision + recall) / 2.0 if total_citations > 0 else 0.0

                                                                         
        supports_claims = True
        if response.claims:
            claims_with_citations = sum(
                1 for c in response.claims if getattr(c, "evidence_refs", None) or getattr(c, "citations", None)
            )
            supports_claims = claims_with_citations > 0

        passed = document_matches > 0 and (case.expected_page is None or page_matches > 0)

        return CitationCaseMetrics(
            total_citations=total_citations,
            valid_citations=valid_citations,
            document_matches=document_matches,
            page_matches=page_matches,
            precision=round(precision, 4),
            recall=round(recall, 4),
            accuracy=round(accuracy, 4),
            supports_claims=supports_claims,
            actual_citations=actual_citation_strs,
            passed=passed,
        )


citation_evaluator = CitationEvaluator()
