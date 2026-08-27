"""
FinSentry AI — Phase 3K RAG Evaluation Schemas.

Defines strongly-typed Pydantic contracts for:
  1. Evaluation cases, datasets, and ground-truth specifications.
  2. Per-case retrieval, citation, answer, hallucination, and refusal metrics.
  3. Aggregate evaluation metrics and scoring models.
  4. Regression baseline comparison and trend detection.
  5. Evaluation report generation and serialization.
  6. Evaluation API contracts.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


                                                                       

class EvaluationCategory(str, Enum):
    FACTUAL = "factual"
    FINANCIAL_METRIC = "financial_metric"
    COMPARISON = "comparison"
    TREND = "trend"
    CAUSAL = "causal"
    RISK = "risk"
    DOCUMENT_LOOKUP = "document_lookup"
    MULTI_STEP = "multi_step"
    FOLLOW_UP = "follow_up"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvaluationDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ExecutionMode(str, Enum):
    DETERMINISTIC_MOCK = "DETERMINISTIC_MOCK"
    LIVE_LLM = "LIVE_LLM"


                                                                       

class MultiTurnMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class EvaluationCase(BaseModel):
    """
    Structured representation of a single ground-truth RAG evaluation test case.
    """
    case_id: str = Field(..., description="Unique case identifier (e.g. 'case-01')")
    question: str = Field(..., description="The user question to evaluate")
    session_id: str = Field(default="eval-session-001", description="Session ID for evaluation")
    user_id: str = Field(default="eval-user-001", description="User ID for evaluation isolation")
    
                               
    expected_answer: str = Field(..., description="Primary ground-truth answer text")
    acceptable_answer_variants: List[str] = Field(
        default_factory=list,
        description="List of acceptable semantically or numerically equivalent answer variations",
    )
    
                                   
    expected_document_id: Optional[str] = Field(None, description="Expected source document ID")
    expected_document_name: Optional[str] = Field(None, description="Expected source document filename")
    expected_page: Optional[int] = Field(None, description="Expected source page number")
    expected_section: Optional[str] = Field(None, description="Expected section heading")
    expected_citation: Optional[str] = Field(None, description="Expected citation format string")
    expected_claims: List[str] = Field(default_factory=list, description="Expected factual claims")
    expected_metrics: List[str] = Field(default_factory=list, description="Key financial metrics expected in answer")
    
                                   
    expected_refusal: bool = Field(default=False, description="True if query should produce a safe refusal")
    expected_refusal_reason: Optional[str] = Field(None, description="Expected refusal rationale if applicable")
    verified_negative: bool = Field(
        default=False,
        description="True if query asks for an item verified to be $0 or none (must not refuse)",
    )
    
                               
    category: EvaluationCategory = Field(..., description="Primary question category")
    difficulty: EvaluationDifficulty = Field(default=EvaluationDifficulty.MEDIUM, description="Case difficulty")
    multi_turn_history: List[MultiTurnMessage] = Field(
        default_factory=list,
        description="Prior conversation history for multi-turn follow-up cases",
    )
    notes: Optional[str] = Field(None, description="Evaluation annotator notes")


class EvaluationDataset(BaseModel):
    """
    Versioned collection of evaluation cases.
    """
    dataset_version: str = Field(default="1.0.0", description="Dataset semantic version")
    description: str = Field(
        default="FinSentry AI Financial RAG Production Evaluation Benchmark",
        description="Dataset description",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    cases: List[EvaluationCase] = Field(default_factory=list, description="Evaluation cases")

    @property
    def total_cases(self) -> int:
        return len(self.cases)


                                                                       

class RetrievalCaseMetrics(BaseModel):
    """Retrieval performance metrics for a single case."""
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    hit_at_10: bool = False
    reciprocal_rank: float = 0.0
    expected_document_id: Optional[str] = None
    expected_page: Optional[int] = None
    retrieved_documents: List[str] = Field(default_factory=list)
    retrieved_pages: List[int] = Field(default_factory=list)
    total_retrieved: int = 0
    passed: bool = False


class CitationCaseMetrics(BaseModel):
    """Citation performance metrics for a single case."""
    total_citations: int = 0
    valid_citations: int = 0
    document_matches: int = 0
    page_matches: int = 0
    precision: float = 0.0
    recall: float = 0.0
    accuracy: float = 0.0
    supports_claims: bool = True
    actual_citations: List[str] = Field(default_factory=list)
    passed: bool = False


class AnswerCaseMetrics(BaseModel):
    """Answer correctness metrics for a single case."""
    correctness_score: float = 0.0
    numerical_correctness: bool = True
    direction_correctness: bool = True
    claims_supported: bool = True
    equivalence_match_type: str = "none"                                                                     
    passed: bool = False


class HallucinationCaseMetrics(BaseModel):
    """Hallucination detection metrics for a single case."""
    hallucinated_claims_count: int = 0
    unsupported_numbers_count: int = 0
    fabricated_citations_count: int = 0
    hallucination_detected: bool = False
    hallucination_details: List[str] = Field(default_factory=list)
    passed: bool = True


class RefusalCaseMetrics(BaseModel):
    """Refusal safety metrics for a single case."""
    expected_refusal: bool = False
    actual_refusal: bool = False
    correct_refusal: bool = False
    incorrect_refusal: bool = False
    false_positive_refusal: bool = False
    verified_negative_finding: bool = False
    passed: bool = True


class PerCaseResult(BaseModel):
    """
    Complete evaluation results and diagnostics for a single case.
    """
    case_id: str
    question: str
    category: EvaluationCategory
    difficulty: EvaluationDifficulty
    
                        
    expected_answer: str
    actual_answer: str
    expected_source: Optional[str] = None
    actual_sources: List[str] = Field(default_factory=list)
    expected_page: Optional[int] = None
    actual_pages: List[int] = Field(default_factory=list)
    expected_citations: List[str] = Field(default_factory=list)
    actual_citations: List[str] = Field(default_factory=list)
    
                                   
    retrieval_metrics: RetrievalCaseMetrics
    citation_metrics: CitationCaseMetrics
    answer_metrics: AnswerCaseMetrics
    hallucination_metrics: HallucinationCaseMetrics
    refusal_metrics: RefusalCaseMetrics
    
                         
    trace_id: Optional[str] = None
    latency_ms: float = 0.0
    confidence_score: float = 0.0
    provider_used: Optional[str] = None
    fallback_used: bool = False
    
                          
    passed: bool = False
    failure_reasons: List[str] = Field(default_factory=list)


                                                                       

class AggregateMetrics(BaseModel):
    """
    Aggregated summary metrics across an entire evaluation run.
    """
    dataset_version: str = "1.0.0"
    evaluation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC_MOCK
    
                 
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate: float = 0.0
    
                       
    retrieval_hit_at_1: float = 0.0
    retrieval_hit_at_3: float = 0.0
    retrieval_hit_at_5: float = 0.0
    retrieval_hit_at_10: float = 0.0
    mrr: float = 0.0
    
                      
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    citation_accuracy: float = 0.0
    
                        
    answer_accuracy: float = 0.0
    
                          
    hallucination_count: int = 0
    hallucination_rate: float = 0.0
    refusal_accuracy: float = 0.0
    refusal_precision: float = 0.0
    refusal_recall: float = 0.0
    
                                                  
    overall_score: float = 0.0
    average_latency_ms: float = 0.0


                                                                       

class MetricDelta(BaseModel):
    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    degraded: bool = False


class RegressionComparison(BaseModel):
    """
    Detailed regression comparison between a baseline evaluation and current run.
    """
    baseline_version: str
    current_version: str
    baseline_timestamp: Optional[datetime] = None
    current_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    overall_score_delta: float = 0.0
    is_regression: bool = False
    regressions_detected: List[str] = Field(default_factory=list)
    
    metric_deltas: List[MetricDelta] = Field(default_factory=list)
    regressed_cases: List[str] = Field(default_factory=list)
    improved_cases: List[str] = Field(default_factory=list)


                                                                       

class EvaluationReport(BaseModel):
    """
    Complete structured evaluation report artifact.
    """
    report_id: str
    dataset_version: str
    evaluation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC_MOCK
    
    aggregate_metrics: AggregateMetrics
    case_results: List[PerCaseResult] = Field(default_factory=list)
    regression_comparison: Optional[RegressionComparison] = None
    
                         
    category_performance: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    summary_markdown: Optional[str] = None


                                                                       

class EvaluationRunRequest(BaseModel):
    dataset_path: Optional[str] = None
    case_id: Optional[str] = None
    category: Optional[EvaluationCategory] = None
    live_mode: bool = False
    compare_baseline_path: Optional[str] = None
    save_as_baseline: bool = False


class EvaluationRunResponse(BaseModel):
    report_id: str
    dataset_version: str
    execution_mode: ExecutionMode
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_score: float
    aggregate_metrics: AggregateMetrics
    case_results: List[PerCaseResult]
    regression_comparison: Optional[RegressionComparison] = None
    message: str = "Evaluation completed successfully"
