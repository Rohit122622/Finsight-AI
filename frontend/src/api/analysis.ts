



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
  }>;
}




export async function getSessionRedFlagsApi(
  sessionId: string,
): Promise<SessionRedFlagsResponse> {
  const response = await apiClient.get<SessionRedFlagsResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/red-flags`,
  );
  return response.data;
}
