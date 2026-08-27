"""
FinSentry AI — Phase 3K Evaluation CLI Entry Point.

Usage:
  python -m backend.evaluation.run [options]
  python -m evaluation.run [options]

Options:
  --dataset <file>         Path to custom evaluation dataset JSON file
  --case <case_id>         Run single case (e.g. --case case-01)
  --category <category>    Filter by category (e.g. --category comparison)
  --live                   Execute in LIVE LLM mode rather than DETERMINISTIC_MOCK
  --baseline <file>        Compare current run against baseline JSON report
  --save-baseline <file>   Save this run as baseline JSON file
  --output <file>          Save output evaluation report to JSON file
  --verbose                Show detailed case logs
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

                                                  
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database.connection import mongodb
from evaluation.dataset import get_evaluation_dataset
from evaluation.regression import regression_comparator
from evaluation.runner import rag_evaluation_runner
from schemas.evaluation import EvaluationCategory, EvaluationDataset, ExecutionMode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FinSentry AI RAG Evaluation Runner")
    parser.add_argument("--dataset", type=str, default=None, help="Path to evaluation dataset JSON")
    parser.add_argument("--case", type=str, default=None, help="Specific case ID to run (e.g. case-01)")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=[c.value for c in EvaluationCategory],
        help="Category to evaluate",
    )
    parser.add_argument("--live", action="store_true", help="Run with live LLM instead of deterministic mock")
    parser.add_argument("--baseline", type=str, default=None, help="Path to baseline report JSON for regression diff")
    parser.add_argument("--save-baseline", type=str, default=None, help="Save report as baseline JSON")
    parser.add_argument("--output", type=str, default=None, help="Save evaluation report to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Verbose debug output")
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    print("\n" + "=" * 70)
    print(" FINsentry AI — Phase 3K Production RAG Evaluation")
    print("=" * 70)

                                  
    try:
        await mongodb.connect()
    except Exception as exc:
        if args.verbose:
            print(f"[NOTE] MongoDB connection: {exc}")

                     
    dataset: EvaluationDataset
    if args.dataset and os.path.exists(args.dataset):
        with open(args.dataset, "r", encoding="utf-8") as f:
            data = json.load(f)
        dataset = EvaluationDataset(**data)
        print(f"Loaded custom dataset from {args.dataset} (v{dataset.dataset_version}, {dataset.total_cases} cases)")
    else:
        dataset = get_evaluation_dataset()
        print(f"Using default production dataset (v{dataset.dataset_version}, {dataset.total_cases} cases)")

                                 
    mode = ExecutionMode.LIVE_LLM if args.live else ExecutionMode.DETERMINISTIC_MOCK
    print(f"Execution Mode: {mode.value}")
    if args.category:
        print(f"Category Filter: {args.category}")
    if args.case:
        print(f"Case Filter: {args.case}")

    cat_enum = EvaluationCategory(args.category) if args.category else None

                       
    print("\nExecuting evaluation pipeline across test cases...")
    report = await rag_evaluation_runner.run_evaluation(
        dataset=dataset,
        category=cat_enum,
        case_id=args.case,
        mode=mode,
    )

                                         
    if args.baseline and os.path.exists(args.baseline):
        try:
            baseline_report = regression_comparator.load_report_from_file(args.baseline)
            diff = regression_comparator.compare_reports(baseline_report, report)
            report.regression_comparison = diff
            print(f"\n[REGRESSION COMPARISON] Baseline: {args.baseline}")
            if diff.is_regression:
                print(f"  [ALERT] Regression detected! Delta: {diff.overall_score_delta:+.4f}")
                for reg in diff.regressions_detected:
                    print(f"    - {reg}")
            else:
                print(f"  [OK] No regressions detected! Delta: {diff.overall_score_delta:+.4f}")
        except Exception as exc:
            print(f"[WARNING] Baseline comparison failed: {exc}")

                                   
    agg = report.aggregate_metrics
    print("\n" + "-" * 70)
    print(f" EVALUATION REPORT: {report.report_id}")
    print("-" * 70)
    print(f" Total Cases       : {agg.total_cases}")
    print(f" Passed Cases      : {agg.passed_cases}")
    print(f" Failed Cases      : {agg.failed_cases}")
    print(f" Pass Rate         : {agg.pass_rate * 100:.1f}%")
    print(f" Overall Score     : {agg.overall_score * 100:.1f}%")
    print("-" * 70)
    print(f" Retrieval Hit@1   : {agg.retrieval_hit_at_1 * 100:.1f}%")
    print(f" Retrieval Hit@3   : {agg.retrieval_hit_at_3 * 100:.1f}%")
    print(f" Retrieval Hit@5   : {agg.retrieval_hit_at_5 * 100:.1f}%")
    print(f" Retrieval Hit@10  : {agg.retrieval_hit_at_10 * 100:.1f}%")
    print(f" Retrieval MRR     : {agg.mrr:.4f}")
    print("-" * 70)
    print(f" Citation Precision: {agg.citation_precision * 100:.1f}%")
    print(f" Citation Recall   : {agg.citation_recall * 100:.1f}%")
    print(f" Citation Accuracy : {agg.citation_accuracy * 100:.1f}%")
    print("-" * 70)
    print(f" Answer Accuracy   : {agg.answer_accuracy * 100:.1f}%")
    print(f" Hallucination Rate: {agg.hallucination_rate * 100:.1f}% ({agg.hallucination_count} detected)")
    print(f" Refusal Accuracy  : {agg.refusal_accuracy * 100:.1f}% (Prec: {agg.refusal_precision * 100:.1f}%, Rec: {agg.refusal_recall * 100:.1f}%)")
    print(f" Average Latency   : {agg.average_latency_ms:.1f} ms")
    print("=" * 70)

                             
    print("\nCATEGORY PERFORMANCE:")
    print(f"{'Category':<25} | {'Passed/Total':<15} | {'Pass Rate':<10}")
    print("-" * 55)
    for cat, pdata in report.category_performance.items():
        pass_ratio = f"{int(pdata['passed'])}/{int(pdata['total'])}"
        rate_str = f"{pdata['pass_rate'] * 100:.1f}%"
        print(f"{cat:<25} | {pass_ratio:<15} | {rate_str:<10}")

                             
    print("\nPER-CASE RESULTS:")
    print(f"{'Case ID':<10} | {'Category':<22} | {'Verdict':<8} | {'Latency':<8} | {'Question'}")
    print("-" * 75)
    for r in report.case_results:
        verdict = "PASSED" if r.passed else "FAILED"
        print(f"{r.case_id:<10} | {r.category.value:<22} | {verdict:<8} | {r.latency_ms:<6.1f}ms | {r.question[:30]}...")

                                            
    if args.save_baseline:
        regression_comparator.save_report_to_file(report, args.save_baseline)
        print(f"\nSaved evaluation as baseline to: {args.save_baseline}")

    if args.output:
        regression_comparator.save_report_to_file(report, args.output)
        print(f"Saved evaluation report to: {args.output}")

                        
    try:
        await mongodb.disconnect()
    except Exception:
        pass

    return 0 if agg.failed_cases == 0 else 1


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
