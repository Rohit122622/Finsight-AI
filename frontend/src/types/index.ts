

export interface User {
  id: string;
  full_name: string;
  email: string;
  provider: "local" | "google";
  created_at: string;
  updated_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
}



export interface Session {
  id: string;
  session_id?: string;
  user_id: string;
  session_name: string;
  name?: string;
  description?: string;
  document_count?: number;
  created_at: string;
  updated_at: string | null;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateSessionRequest {
  session_name: string;
}

export interface UpdateSessionRequest {
  session_name: string;
}



export type DocumentStatus = "UPLOADED" | "PROCESSING" | "PROCESSED" | "FAILED";

export interface DocumentChunk {
  chunk_id: string;
  chunk_index: number;
  text: string;
  token_estimate: number;
  character_count: number;
  page_number?: number | null;
  section?: string | null;
}

export interface DocumentMetadata {
  page_count?: number | null;
  word_count: number;
  character_count: number;
  token_estimate: number;
  sha256: string;
  chunk_count: number;
  extracted_summary?: string | null;
}

export interface DocumentItem {
  id: string;
  document_id: string;
  session_id: string;
  user_id: string;
  filename: string;
  file_size: number;
  file_size_bytes?: number;
  file_type?: string;
  mime_type: string;
  storage_path: string;
  status: DocumentStatus;
  error_message?: string | null;
  metadata: DocumentMetadata;
  chunks?: DocumentChunk[];
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  session_id: string;
  user_id: string;
  filename: string;
  file_size: number;
  mime_type: string;
  sha256?: string;
  storage_key?: string;
  status: string;
  job_id?: string | null;
  created_at: string;
  message?: string;
  document?: DocumentItem;
}



export type JobStatus =
  | "QUEUED"
  | "PROCESSING"
  | "EXTRACTING"
  | "EMBEDDING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface LiveAgentStatusEvent {
  agent_name: string;
  status: string;
  session_id: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export interface JobProgressEvent {
  job_id: string;
  progress_percent: number;
  current_step: string;
  status: JobStatus;
  message?: string;
  events?: Array<{ timestamp: string; step: string; message: string }>;
}



export interface ReportSection {
  title: string;
  content: string;
  key_findings: string[];
}

export interface RedFlagItem {
  title: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  category: string;
  evidence: string;
  recommendation: string;
}

export interface AnalysisReport {
  report_id: string;
  session_id: string;
  user_id: string;
  report_title: string;
  executive_summary: string;
  risk_score: number;
  sections: ReportSection[];
  extracted_metrics: Record<string, unknown>[];
  red_flags: RedFlagItem[];
  recommendations: string[];
  status: string;
  created_at: string;
}



export interface ApiError {
  detail: string;
}


export * from "./research";

