



export type StreamEventType =
  | "started"
  | "query_understanding"
  | "retrieval"
  | "context"
  | "generation"
  | "citation"
  | "validation"
  | "token"
  | "content_delta"
  | "completed"
  | "refused"
  | "error";

export type ClaimType =
  | "FACT"
  | "METRIC"
  | "TREND"
  | "COMPARISON"
  | "CAUSAL"
  | "RISK"
  | "INTERPRETATION";

export type ClaimSupportStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "UNSUPPORTED";

export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";

export type ValidationStatus = "VALID" | "INVALID" | "MODIFIED" | "REFUSED";

export interface EvidenceRef {
  document_id: string;
  chunk_id: string;
  document_filename?: string | null;
  page_number?: number | null;
  section?: string | null;
  source_reference?: string | null;
}

export interface ResearchClaim {
  claim_id: string;
  claim_text: string;
  claim_type: ClaimType;
  support_status: ClaimSupportStatus;
  evidence_refs: EvidenceRef[];
  confidence: number;
  is_causal: boolean;
  unsupported_reasons: string[];
}

export interface ResearchCitation {
  citation_id: string;
  chunk_id: string;
  document_id: string;
  document_filename?: string | null;
  page_number?: number | null;
  section?: string | null;
  quoted_snippet: string;
  claim_ids: string[];
  is_valid: boolean;
  validation_error?: string | null;
}

export interface EvidenceConflict {
  metric_or_topic: string;
  competing_values: string[];
  evidence_refs: EvidenceRef[];
  description: string;
}

export interface EvidenceSufficiencyAssessment {
  is_sufficient: boolean;
  score: number;
  reasons: string[];
  has_target_metric_match: boolean;
  has_temporal_match: boolean;
  has_section_match: boolean;
  missing_evidence_items: string[];
}

export interface ConfidenceAssessment {
  score: number;
  level: ConfidenceLevel;
  retrieval_relevance: number;
  evidence_coverage: number;
  citation_validity_rate: number;
  supported_claim_ratio: number;
  conflict_penalty: number;
}

export interface ReasoningMetadata {
  total_claims: number;
  supported_claims: number;
  unsupported_claims: number;
  partially_supported_claims: number;
  causal_claims_count: number;
  unsupported_causal_claims_count: number;
  citation_validation_rate: number;
  total_tokens_estimate: number;
  chunks_analyzed: number;
  execution_time_ms: number;
  llm_provider?: string | null;
  llm_model?: string | null;
  is_fallback: boolean;
  fallback_attempts: number;
}

export interface ValidationResult {
  valid: boolean;
  status: ValidationStatus;
  validation_errors: string[];
  validation_warnings: string[];
  validated_claim_count: number;
  supported_claim_count: number;
  unsupported_claim_count: number;
  partially_supported_claim_count: number;
  validated_citation_count: number;
  invalid_citation_count: number;
  duplicate_count: number;
  final_confidence: number;
  confidence_level: ConfidenceLevel;
  refusal_required: boolean;
  refusal_reason?: string | null;
  duplicate_claims: string[];
  duplicate_citations: string[];
  metadata: Record<string, unknown>;
}

export interface ResearchResponse {
  session_id: string;
  user_id: string;
  query: string;
  answer: string;
  refused: boolean;
  refusal_reason?: string | null;
  claims: ResearchClaim[];
  citations: ResearchCitation[];
  confidence: number;
  confidence_level: ConfidenceLevel;
  key_points: string[];
  limitations: string[];
  evidence_conflicts: EvidenceConflict[];
  sufficiency: EvidenceSufficiencyAssessment;
  confidence_assessment: ConfidenceAssessment;
  metadata: ReasoningMetadata;
}

export interface ResearchChatRequest {
  session_id: string;
  message: string;
  conversation_id?: string | null;
  stream?: boolean;
  top_k?: number;
  mode?: "hybrid" | "vector" | "keyword";
  score_threshold?: number;
  document_ids?: string[] | null;
}

export interface ResearchChatResponse {
  conversation_id: string;
  message_id: string;
  session_id: string;
  user_id: string;
  response: ResearchResponse;
  validation: ValidationResult;
  created_at: string;
}

export interface ResearchConversation {
  conversation_id: string;
  session_id: string;
  user_id: string;
  title?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResearchMessage {
  message_id: string;
  conversation_id: string;
  session_id: string;
  user_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  claims?: ResearchClaim[];
  citations?: ResearchCitation[];
  confidence_score?: number | null;
  confidence_tier?: string | null;
  validation_status?: string | null;
  created_at: string;
  
  isStreaming?: boolean;
  isRefusal?: boolean;
  isError?: boolean;
  errorMessage?: string | null;
  structuredResponse?: ResearchResponse | null;
  validationResult?: ValidationResult | null;
}

export interface StreamEvent {
  event: StreamEventType;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface ResearchHistoryResponse {
  session_id: string;
  conversation_id?: string | null;
  messages: ResearchMessage[];
  total_messages: number;
}

export interface SessionMemoryResponse {
  session_id: string;
  user_id: string;
  topic?: string | null;
  entities: string[];
  metrics_discussed: string[];
  periods_discussed: string[];
  prior_queries: string[];
  document_ids: string[];
  updated_at: string;
}

export type ResearchStateStatus =
  | "IDLE"
  | "LOADING"
  | "STREAMING"
  | "VALIDATING"
  | "SUCCESS"
  | "REFUSED"
  | "ERROR"
  | "EMPTY_EVIDENCE"
  | "FALLBACK_PROVIDER";
