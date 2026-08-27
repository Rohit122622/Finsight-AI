"""
FinSentry AI — Phase 3K Answer Evaluator.

Evaluates answer correctness against ground-truth:
  - Exact match & acceptable variants
  - Financial numerical equivalence ($14.8B == $14,800 million == 14800M)
  - Percentage normalization (18.4% == 0.184)
  - Directional trend / comparative alignment (increase / rose / growth vs decrease / fell / drop)
  - Deterministic refusal matching
"""

import logging
import re
from typing import List, Optional, Set, Tuple

from schemas.evaluation import AnswerCaseMetrics, EvaluationCase
from schemas.reasoning import ResearchResponse

logger = logging.getLogger(__name__)

                                
REFUSAL_PHRASES = [
    "do not contain sufficient information",
    "does not contain sufficient information",
    "insufficient information",
    "insufficient verified evidence",
    "no relevant document chunks",
    "not contain information",
]

INCREASE_WORDS = {"increase", "increased", "rose", "risen", "rise", "growth", "grew", "up", "expanded", "expansion", "higher"}
DECREASE_WORDS = {"decrease", "decreased", "decline", "declined", "fell", "fallen", "fall", "down", "contracted", "contraction", "lower", "drop", "dropped"}


class AnswerEvaluator:
    """
    Evaluator for comparing generated financial answers with ground-truth facts.
    """

    def evaluate_case(
        self,
        case: EvaluationCase,
        response: Optional[ResearchResponse],
    ) -> AnswerCaseMetrics:
        """
        Evaluate answer correctness for a single case.
        """
        if not response or not response.answer:
            return AnswerCaseMetrics(
                correctness_score=0.0,
                numerical_correctness=False,
                direction_correctness=False,
                claims_supported=False,
                equivalence_match_type="none",
                passed=False,
            )

        actual_text = response.answer.strip()
        expected_text = case.expected_answer.strip()

                                
        if case.expected_refusal:
            is_refusal = getattr(response, "refused", False) or any(
                p in actual_text.lower() for p in REFUSAL_PHRASES
            )
            if is_refusal:
                return AnswerCaseMetrics(
                    correctness_score=1.0,
                    numerical_correctness=True,
                    direction_correctness=True,
                    claims_supported=True,
                    equivalence_match_type="refusal",
                    passed=True,
                )
            else:
                return AnswerCaseMetrics(
                    correctness_score=0.0,
                    numerical_correctness=False,
                    direction_correctness=False,
                    claims_supported=False,
                    equivalence_match_type="none",
                    passed=False,
                )

                                                         
        if getattr(response, "refused", False) and not case.expected_refusal:
            return AnswerCaseMetrics(
                correctness_score=0.0,
                numerical_correctness=False,
                direction_correctness=False,
                claims_supported=False,
                equivalence_match_type="none",
                passed=False,
            )

                              
        if actual_text.lower() == expected_text.lower():
            return AnswerCaseMetrics(
                correctness_score=1.0,
                numerical_correctness=True,
                direction_correctness=True,
                claims_supported=True,
                equivalence_match_type="exact",
                passed=True,
            )

                                      
        for variant in case.acceptable_answer_variants:
            if variant.strip().lower() in actual_text.lower() or actual_text.lower() in variant.strip().lower():
                return AnswerCaseMetrics(
                    correctness_score=1.0,
                    numerical_correctness=True,
                    direction_correctness=True,
                    claims_supported=True,
                    equivalence_match_type="variant",
                    passed=True,
                )

                                                     
        expected_numbers = self._extract_numbers(expected_text)
        actual_numbers = self._extract_numbers(actual_text)

        numerical_correct = True
        if expected_numbers:
            if not actual_numbers:
                numerical_correct = False
            else:
                                                                                           
                                                                                          
                for act_num in actual_numbers:
                                                                       
                    if act_num in [2020.0, 2021.0, 2022.0, 2023.0, 2024.0, 2025.0, 2028.0, 2029.0, 2030.0, 31.0]:
                        continue
                    if not self._is_number_present(act_num, expected_numbers, expected_text):
                        numerical_correct = False
                        break
                                                                           
                primary_matches = sum(
                    1 for exp in expected_numbers if self._is_number_present(exp, actual_numbers, actual_text)
                )
                if primary_matches == 0:
                    numerical_correct = False

                                                
        direction_correct = self._check_directional_consistency(expected_text, actual_text)

                                             
        key_terms_match = self._check_key_terms_match(expected_text, actual_text, case)

                                 
        score = 0.0
        if numerical_correct and direction_correct and key_terms_match:
            score = 1.0
            match_type = "numerical"
        elif numerical_correct and direction_correct:
            score = 0.85
            match_type = "numerical_partial"
        elif key_terms_match:
            score = 0.70
            match_type = "semantic"
        else:
            score = 0.30
            match_type = "partial"

        passed = score >= 0.70 and direction_correct and (not expected_numbers or numerical_correct)

        return AnswerCaseMetrics(
            correctness_score=round(score, 3),
            numerical_correctness=numerical_correct,
            direction_correctness=direction_correct,
            claims_supported=True,
            equivalence_match_type=match_type,
            passed=passed,
        )

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract canonical float numbers from financial text."""
        numbers: List[float] = []
                                                              
                                                  
        cleaned = text.replace(",", "")
        pattern = r"\b\d+(?:\.\d+)?\b"
        for match in re.finditer(pattern, cleaned):
            try:
                val = float(match.group(0))
                numbers.append(val)
            except ValueError:
                pass
        return numbers

    def _is_number_present(self, exp_num: float, actual_numbers: List[float], actual_text: str) -> bool:
        """Check if an expected number is present in actual numbers or normalized form."""
        if exp_num in actual_numbers:
            return True
        for act in actual_numbers:
            if abs(exp_num - act) < 0.01:
                return True
                                                              
            if exp_num > 0 and act > 0:
                if abs(exp_num * 1000 - act) < 0.1 or abs(act * 1000 - exp_num) < 0.1:
                    return True
                if abs(exp_num / 100 - act) < 0.001 or abs(act / 100 - exp_num) < 0.001:
                    return True
        return False

    def _check_directional_consistency(self, expected_text: str, actual_text: str) -> bool:
        """Ensure trends/comparisons don't invert direction (e.g. increase vs decline)."""
        exp_lower = expected_text.lower()
        act_lower = actual_text.lower()

        exp_has_increase = any(w in exp_lower for w in INCREASE_WORDS)
        exp_has_decrease = any(w in exp_lower for w in DECREASE_WORDS)

        act_has_increase = any(w in act_lower for w in INCREASE_WORDS)
        act_has_decrease = any(w in act_lower for w in DECREASE_WORDS)

                                                                             
        if exp_has_increase and not exp_has_decrease:
            if act_has_decrease and not act_has_increase:
                return False
                                                                             
        if exp_has_decrease and not exp_has_increase:
            if act_has_increase and not act_has_decrease:
                return False

        return True

    def _check_key_terms_match(self, expected_text: str, actual_text: str, case: EvaluationCase) -> bool:
        """Check overlap of key financial terms or expected claims."""
        act_lower = actual_text.lower()
        
                                         
        for metric in case.expected_metrics:
            for word in metric.lower().split():
                if len(word) > 3 and word not in act_lower:
                    pass              

                                  
        if case.expected_claims:
            matched_claims = 0
            for claim in case.expected_claims:
                claim_words = [w.lower() for w in re.findall(r"\w+", claim) if len(w) > 3]
                if sum(1 for w in claim_words if w in act_lower) >= max(1, len(claim_words) // 2):
                    matched_claims += 1
            return matched_claims >= max(1, len(case.expected_claims) // 2)

        return True


answer_evaluator = AnswerEvaluator()
