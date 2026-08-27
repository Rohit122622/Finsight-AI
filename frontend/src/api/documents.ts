



import apiClient from "./client";
import type { DocumentItem, DocumentUploadResponse } from "../types";




export async function uploadDocumentApi(
  sessionId: string,
  file: File,
  onUploadProgress?: (percent: number) => void,
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  
  if (import.meta.env.DEV) {
    const keys: string[] = [];
    formData.forEach((_, key) => keys.push(key));
    console.log("[FinSentry Upload Diagnostic]", {
      isFormData: formData instanceof FormData,
      sessionId,
      fileName: file?.name,
      fileSize: file?.size,
      formDataKeys: keys,
    });
  }

  const response = await apiClient.post<DocumentUploadResponse>(
    "/documents/upload",
    formData,
    {
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onUploadProgress) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total,
          );
          onUploadProgress(percent);
        }
      },
    },
  );

  return response.data;
}




export async function listDocumentsApi(
  sessionId: string,
): Promise<{ documents: DocumentItem[]; total: number }> {
  const response = await apiClient.get<{ documents: DocumentItem[]; total: number }>(
    `/sessions/${encodeURIComponent(sessionId)}/documents`,
  );
  return response.data;
}




export async function getDocumentApi(
  sessionId: string,
  documentId: string,
): Promise<DocumentItem> {
  const response = await apiClient.get<DocumentItem>(
    `/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
  );
  return response.data;
}




export async function deleteDocumentApi(
  sessionId: string,
  documentId: string,
): Promise<{ status: string; document_id: string }> {
  const response = await apiClient.delete<{ status: string; document_id: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
  );
  return response.data;
}




export async function retryDocumentProcessingApi(
  sessionId: string,
  documentId: string,
): Promise<{ message: string; job_id: string }> {
  const response = await apiClient.post<{ message: string; job_id: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/retry`,
  );
  return response.data;
}
