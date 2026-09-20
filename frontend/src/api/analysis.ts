



import apiClient from "./client";
import type { AnalysisReport, JobProgressEvent } from "../types";




export async function triggerLiveAnalysisApi(
  sessionId: string,
  query?: string,
  asyncMode = true,
): Promise<{ job_id?: string; report?: AnalysisReport }> {
  const response = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/analyze`,
    {
      query: query || "Perform forensic financial analysis and extract key metrics.",
      async_mode: asyncMode,
    },
  );
  return response.data;
}




export async function getLiveProgressApi(
  sessionId: string,
  jobId: string,
): Promise<JobProgressEvent> {
  const response = await apiClient.get<JobProgressEvent>(
    `/sessions/${encodeURIComponent(sessionId)}/progress/${encodeURIComponent(jobId)}`,
  );
  return response.data;
}




export async function listReportsApi(
  sessionId: string,
): Promise<{ reports: AnalysisReport[]; total: number }> {
  const response = await apiClient.get<{ reports: AnalysisReport[]; total: number }>(
    `/sessions/${encodeURIComponent(sessionId)}/reports`,
  );
  return response.data;
}




export async function getReportApi(
  sessionId: string,
  reportId: string,
): Promise<AnalysisReport> {
  const response = await apiClient.get<AnalysisReport>(
    `/sessions/${encodeURIComponent(sessionId)}/reports/${encodeURIComponent(reportId)}`,
  );
  return response.data;
}

export interface SessionRedFlagsResponse {
  session_id: string;
  document_id?: string | null;
  company_name?: string | null;
  status: "NOT_RUN" | "RUNNING" | "COMPLETED_WITH_FLAGS" | "COMPLETED_NO_FLAGS" | "FAILED";
  total_flags: number;
  high_severity_count: number;
  risk_score: number;
  overall_assessment?: string;
  flags: Array<{
    severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
    category: string;
    title: string;
    description: string;
    source?: string;
    evidence_snippet?: string;
    recommendation?: string;
    page_number?: number;
    section?: string;
    document_filename?: string;
    document_id?: string;
  }>;
  documents?: Array<{
    document_id?: string;
    company_name?: string;
    total_flags: number;
    high_severity_count: number;
    risk_score: number;
    overall_assessment?: string;
    flags: Array<Record<string, unknown>>;
  }>;
}




export async function getSessionRedFlagsApi(
  sessionId: string,
  documentId?: string,
): Promise<SessionRedFlagsResponse> {
  const params = new URLSearchParams();
  if (documentId) {
    params.set("document_id", documentId);
  }
  const qs = params.toString();
  const url = `/sessions/${encodeURIComponent(sessionId)}/red-flags${qs ? `?${qs}` : ""}`;
  const response = await apiClient.get<SessionRedFlagsResponse>(url);
  return response.data;
}

/** Normal download: UNLOCKED report PDF (decrypted server-side, owner only). */
export async function downloadReportPdfApi(
  sessionId: string,
  reportId: string,
): Promise<Blob> {
  const response = await apiClient.get(
    `/sessions/${encodeURIComponent(sessionId)}/reports/${encodeURIComponent(reportId)}/download`,
    { responseType: "blob" }
  );
  return response.data;
}

/** Locked download: password-protected AES-256 report PDF (encrypted bytes). */
export async function downloadReportLockedPdfApi(
  sessionId: string,
  reportId: string,
): Promise<Blob> {
  const response = await apiClient.get(
    `/sessions/${encodeURIComponent(sessionId)}/reports/${encodeURIComponent(reportId)}/download/locked`,
    { responseType: "blob" }
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Per-company (individual, single-document) reports — company-isolated
// ---------------------------------------------------------------------------

export interface CompanyReportContent {
  company_name?: string;
  document_id?: string;
  metadata?: { companies?: string[]; report_title?: string; reporting_periods?: string[] };
  executive_summary?: {
    narrative?: string;
    key_strengths?: string[];
    key_weaknesses?: string[];
  };
  key_financials?: {
    reporting_periods?: string[];
    metrics?: Array<{
      metric_key: string;
      display_name: string;
      category?: string;
      values: Array<{
        company_name: string;
        fiscal_period: string;
        formatted_value: string;
        available: boolean;
      }>;
    }>;
  };
  red_flags?: {
    total_flags?: number;
    composite_risk_score?: number;
    findings?: Array<{
      title: string;
      severity: string;
      category?: string;
      description?: string;
      evidence?: string;
      recommendation?: string;
      source_page?: number | null;
      company_name?: string;
    }>;
  };
}

export async function getCompanyReportApi(
  sessionId: string,
  documentId: string,
): Promise<CompanyReportContent> {
  const response = await apiClient.get<CompanyReportContent>(
    `/sessions/${encodeURIComponent(sessionId)}/reports/company/${encodeURIComponent(documentId)}`,
  );
  return response.data;
}

/** Individual company report — UNLOCKED PDF. */
export async function downloadCompanyReportPdfApi(
  sessionId: string,
  documentId: string,
): Promise<Blob> {
  const response = await apiClient.get(
    `/sessions/${encodeURIComponent(sessionId)}/reports/company/${encodeURIComponent(documentId)}/download`,
    { responseType: "blob" },
  );
  return response.data;
}

/** Individual company report — LOCKED (AES-256) PDF. */
export async function downloadCompanyReportLockedPdfApi(
  sessionId: string,
  documentId: string,
): Promise<Blob> {
  const response = await apiClient.get(
    `/sessions/${encodeURIComponent(sessionId)}/reports/company/${encodeURIComponent(documentId)}/download/locked`,
    { responseType: "blob" },
  );
  return response.data;
}

export async function revealReportPasswordApi(
  sessionId: string,
  reportId: string,
): Promise<{ report_id: string; password: string }> {
  const response = await apiClient.get<{ report_id: string; password: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/reports/${encodeURIComponent(reportId)}/password`,
  );
  return response.data;
}

export async function retryReportEmailApi(
  sessionId: string,
  reportId: string,
): Promise<{ report_id: string; email_status: string }> {
  const response = await apiClient.post<{ report_id: string; email_status: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/reports/${encodeURIComponent(reportId)}/email/retry`,
  );
  return response.data;
}
