import apiClient from "./client";

export interface ExtractedMetricItem {
  metric_name: string;
  display_name?: string;
  value: number | null;
  prior_value?: number | null;
  unit?: string;
  currency?: string;
  period?: string;
  prior_period?: string;
  confidence?: number;
  confidence_category?: string;
  source_chunk_ids?: string[];
  page_numbers?: number[];
  evidence_snippet?: string;
  is_reported?: boolean;
  flag_reason?: string | null;
}

export interface ExtractedDocument {
  _id?: string;
  document_id: string;
  session_id: string;
  document_filename?: string;
  company_name?: string;
  company?: string;
  filing_type?: string;
  reporting_period?: string;
  prior_period?: string;
  reporting_currency?: string;
  reporting_scale?: string;
  metrics?: ExtractedMetricItem[];
  metrics_dict?: Record<string, number | null>;
  multi_year_data?: Record<string, Record<string, number | null>>;
  confidence_average?: number;
  confidence_scores?: Record<string, number>;
  provenance_map?: Record<string, any>;
  chunks_analyzed?: number;
  financial_chunks_count?: number;
  retry_attempted?: boolean;
  retry_success?: boolean | null;
}

export interface ExtractionResponse {
  status: string;
  session_id: string;
  count: number;
  documents: ExtractedDocument[];
}

export async function getExtractedMetricsApi(
  sessionId: string,
  documentId?: string,
): Promise<ExtractionResponse> {
  const params: Record<string, string> = {};
  if (documentId) {
    params.document_id = documentId;
  }
  const response = await apiClient.get<ExtractionResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/extraction`,
    { params },
  );
  return response.data;
}

export async function extractMetricsApi(
  sessionId: string,
  documentId?: string,
  targetFields?: string[],
  asyncMode = false,
): Promise<any> {
  const response = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/extract`,
    {
      document_id: documentId,
      target_fields: targetFields,
      async_mode: asyncMode,
    },
  );
  return response.data;
}
