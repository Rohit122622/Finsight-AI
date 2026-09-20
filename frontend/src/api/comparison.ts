import apiClient from "./client";

export interface CompanyInfo {
  document_id: string;
  company_name: string;
  filing_type?: string;
  reporting_currency?: string;
  reporting_scale?: string;
  fiscal_year?: string;
}

export interface MetricValue {
  document_id: string;
  company_name: string;
  fiscal_period: string;
  value: number | null;
  available: boolean;
  unit?: string;
  currency?: string;
  provenance?: {
    page_number?: number;
    chunk_id?: string;
    section?: string;
    evidence_snippet?: string;
    [key: string]: unknown;
  };
}

export interface PercentileEntry {
  document_id: string;
  company_name: string;
  percentile: number | null;
}

export interface PeerStatistics {
  valid_count: number;
  peer_average: number | null;
  highest?: {
    document_id?: string;
    company_name?: string;
    company?: string;
    value?: number;
  };
  lowest?: {
    document_id?: string;
    company_name?: string;
    company?: string;
    value?: number;
  };
  percentile_ranks?: PercentileEntry[];
}

export interface ComparisonMetricPeriod {
  fiscal_period: string;
  values: MetricValue[];
  peer_statistics: PeerStatistics;
  unit_compatible?: boolean;
  unit_mismatch_detail?: string;
}

export interface ComparisonMetric {
  metric_name: string;
  display_name?: string;
  periods: ComparisonMetricPeriod[];
}

export interface ComparisonOutput {
  session_id: string;
  companies: CompanyInfo[];
  fiscal_periods: string[];
  common_periods?: string[];
  company_only_periods?: Record<string, string[]>;
  has_common_periods?: boolean;
  comparison_note?: string;
  metrics: ComparisonMetric[];
  generated_at?: string;
  metadata?: Record<string, unknown>;
  summary_insights?: string[];
}

export type EmailStatus = "queued" | "sending" | "sent" | "failed" | null;

export interface ComparisonResponse {
  status?: string;
  comparison?: ComparisonOutput;
  company_names?: string[];
  document_ids?: string[];
  pdf_available?: boolean;
  pdf_locked?: boolean;
  email_status?: EmailStatus;
  password_available?: boolean;
}

export async function compareCompaniesApi(
  sessionId: string,
  documentIds: string[],
  asyncMode = false,
): Promise<ComparisonResponse> {
  const response = await apiClient.post<ComparisonResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/compare`,
    {
      document_ids: documentIds,
      async_mode: asyncMode,
    },
  );
  return response.data;
}

export async function getComparisonResultApi(
  sessionId: string,
): Promise<ComparisonResponse> {
  const response = await apiClient.get<ComparisonResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/compare`,
  );
  return response.data;
}

/** Normal download: UNLOCKED comparison PDF (decrypted server-side, owner only). */
export async function downloadComparisonPdfApi(
  sessionId: string,
): Promise<Blob> {
  const response = await apiClient.get<Blob>(
    `/sessions/${encodeURIComponent(sessionId)}/compare/download`,
    { responseType: "blob" },
  );
  return response.data;
}

/** Locked download: password-protected AES-256 comparison PDF (encrypted bytes). */
export async function downloadComparisonLockedPdfApi(
  sessionId: string,
): Promise<Blob> {
  const response = await apiClient.get<Blob>(
    `/sessions/${encodeURIComponent(sessionId)}/compare/download/locked`,
    { responseType: "blob" },
  );
  return response.data;
}

export async function revealComparisonPasswordApi(
  sessionId: string,
): Promise<{ session_id: string; password: string }> {
  const response = await apiClient.get<{ session_id: string; password: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/compare/password`,
  );
  return response.data;
}

export async function retryComparisonEmailApi(
  sessionId: string,
): Promise<{ session_id: string; email_status: EmailStatus }> {
  const response = await apiClient.post<{ session_id: string; email_status: EmailStatus }>(
    `/sessions/${encodeURIComponent(sessionId)}/compare/email/retry`,
  );
  return response.data;
}
