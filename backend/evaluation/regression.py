"""
FinSentry AI — Phase 3K Regression Comparison Module.

Compares a baseline evaluation report with a current evaluation run:
  - Metric-level delta calculation (Hit@k, MRR, Citations, Answer, Hallucination, Refusal, Overall)
  - Regression detection threshold checking
  - Case-level regression tracking (which case passed before but fails now)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from schemas.evaluation import (
    AggregateMetrics,
    EvaluationReport,
    MetricDelta,
    RegressionComparison,
)

logger = logging.getLogger(__name__)

                                    
REGRESSION_TOLERANCE = 0.001                                         


class RegressionComparator:
    """
    Compares baseline and current RAG evaluation reports to identify performance regressions.
    """

    def compare_reports(
        self,
        baseline_report: EvaluationReport,
        current_report: EvaluationReport,
        tolerance: float = REGRESSION_TOLERANCE,
    ) -> RegressionComparison:
        """
        Compare baseline and current evaluation reports and detect regressions.
        """
        base_agg = baseline_report.aggregate_metrics
        curr_agg = current_report.aggregate_metrics

        metric_deltas: List[MetricDelta] = []
        regressions_detected: List[str] = []

                                                
        higher_better_metrics = [
            ("retrieval_hit_at_1", base_agg.retrieval_hit_at_1, curr_agg.retrieval_hit_at_1),
            ("retrieval_hit_at_3", base_agg.retrieval_hit_at_3, curr_agg.retrieval_hit_at_3),
            ("retrieval_hit_at_5", base_agg.retrieval_hit_at_5, curr_agg.retrieval_hit_at_5),
            ("retrieval_hit_at_10", base_agg.retrieval_hit_at_10, curr_agg.retrieval_hit_at_10),
            ("mrr", base_agg.mrr, curr_agg.mrr),
            ("citation_precision", base_agg.citation_precision, curr_agg.citation_precision),
            ("citation_recall", base_agg.citation_recall, curr_agg.citation_recall),
            ("citation_accuracy", base_agg.citation_accuracy, curr_agg.citation_accuracy),
            ("answer_accuracy", base_agg.answer_accuracy, curr_agg.answer_accuracy),
            ("refusal_accuracy", base_agg.refusal_accuracy, curr_agg.refusal_accuracy),
            ("overall_score", base_agg.overall_score, curr_agg.overall_score),
            ("pass_rate", base_agg.pass_rate, curr_agg.pass_rate),
        ]

        for name, base_val, curr_val in higher_better_metrics:
            delta = curr_val - base_val
            degraded = delta < -tolerance
            metric_deltas.append(
                MetricDelta(
                    metric_name=name,
                    baseline_value=round(base_val, 4),
                    current_value=round(curr_val, 4),
                    delta=round(delta, 4),
                    degraded=degraded,
                )
            )
            if degraded:
                regressions_detected.append(f"{name} decreased from {base_val:.4f} to {curr_val:.4f} (delta: {delta:+.4f})")

                                                           
        hal_delta = curr_agg.hallucination_rate - base_agg.hallucination_rate
        hal_degraded = hal_delta > tolerance
        metric_deltas.append(
            MetricDelta(
                metric_name="hallucination_rate",
                baseline_value=round(base_agg.hallucination_rate, 4),
                current_value=round(curr_agg.hallucination_rate, 4),
                delta=round(hal_delta, 4),
                degraded=hal_degraded,
            )
        )
        if hal_degraded:
            regressions_detected.append(
                f"hallucination_rate increased from {base_agg.hallucination_rate:.4f} to {curr_agg.hallucination_rate:.4f} (delta: {hal_delta:+.4f})"
            )

                             
        base_cases = {c.case_id: c.passed for c in baseline_report.case_results}
        curr_cases = {c.case_id: c.passed for c in current_report.case_results}

        regressed_cases: List[str] = []
        improved_cases: List[str] = []

        for cid, curr_passed in curr_cases.items():
            base_passed = base_cases.get(cid)
            if base_passed is True and curr_passed is False:
                regressed_cases.append(cid)
            elif base_passed is False and curr_passed is True:
                improved_cases.append(cid)

        overall_score_delta = curr_agg.overall_score - base_agg.overall_score
        is_regression = len(regressions_detected) > 0 or len(regressed_cases) > 0

        return RegressionComparison(
            baseline_version=baseline_report.dataset_version,
            current_version=current_report.dataset_version,
            baseline_timestamp=baseline_report.evaluation_timestamp,
            current_timestamp=current_report.evaluation_timestamp,
            overall_score_delta=round(overall_score_delta, 4),
            is_regression=is_regression,
            regressions_detected=regressions_detected,
            metric_deltas=metric_deltas,
            regressed_cases=regressed_cases,
            improved_cases=improved_cases,
        )

    def load_report_from_file(self, filepath: str) -> EvaluationReport:
        """Load an EvaluationReport from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return EvaluationReport(**data)

    def save_report_to_file(self, report: EvaluationReport, filepath: str) -> None:
        """Save an EvaluationReport to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)


regression_comparator = RegressionComparator()
