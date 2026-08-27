



import apiClient from "./client";
import type {
  CreateSessionRequest,
  Session,
  SessionListResponse,
  UpdateSessionRequest,
} from "../types";

export async function createSessionApi(
  data: CreateSessionRequest,
): Promise<Session> {
  const resp = await apiClient.post<Session>("/sessions", data);
  return resp.data;
}

export async function listSessionsApi(
  page = 1,
  pageSize = 20,
): Promise<SessionListResponse> {
  const resp = await apiClient.get<SessionListResponse>("/sessions", {
    params: { page, page_size: pageSize },
  });
  return resp.data;
}

export async function getSessionApi(sessionId: string): Promise<Session> {
  const resp = await apiClient.get<Session>(`/sessions/${sessionId}`);
  return resp.data;
}

export async function updateSessionApi(
  sessionId: string,
  data: UpdateSessionRequest,
): Promise<Session> {
  const resp = await apiClient.patch<Session>(`/sessions/${sessionId}`, data);
  return resp.data;
}

export async function deleteSessionApi(sessionId: string): Promise<void> {
  await apiClient.delete(`/sessions/${sessionId}`);
}
