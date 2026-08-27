










import apiClient, { API_BASE_URL, getAccessToken } from "./client";
import type {
  ResearchChatRequest,
  ResearchChatResponse,
  ResearchConversation,
  ResearchHistoryResponse,
  ResearchMessage,
  SessionMemoryResponse,
  StreamEvent,
  StreamEventType,
} from "../types/research";




export async function postResearchChatApi(
  data: ResearchChatRequest,
): Promise<ResearchChatResponse> {
  const resp = await apiClient.post<ResearchChatResponse>("/research/chat", {
    ...data,
    stream: false,
  });
  return resp.data;
}








export async function streamResearchChatApi(
  data: ResearchChatRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}/research/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...data, stream: true }),
    signal,
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = typeof errJson.detail === "string"
          ? errJson.detail
          : JSON.stringify(errJson.detail);
      }
    } catch {
      
    }
    throw new Error(errorDetail);
  }

  if (!response.body) {
    throw new Error("ReadableStream not supported or response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  let currentEventType: StreamEventType = "started";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          continue;
        }

        if (trimmed.startsWith("event:")) {
          currentEventType = trimmed.slice(6).trim() as StreamEventType;
        } else if (trimmed.startsWith("data:")) {
          const rawData = trimmed.slice(5).trim();
          if (rawData) {
            try {
              const parsedData = JSON.parse(rawData);
              onEvent({
                event: currentEventType,
                data: parsedData,
                timestamp: new Date().toISOString(),
              });
            } catch {
              
              onEvent({
                event: currentEventType,
                data: { text: rawData },
                timestamp: new Date().toISOString(),
              });
            }
          }
        }
      }
    }

    
    if (buffer.trim().length > 0) {
      const trimmed = buffer.trim();
      if (trimmed.startsWith("data:")) {
        const rawData = trimmed.slice(5).trim();
        if (rawData) {
          try {
            const parsedData = JSON.parse(rawData);
            onEvent({
              event: currentEventType,
              data: parsedData,
              timestamp: new Date().toISOString(),
            });
          } catch {
            onEvent({
              event: currentEventType,
              data: { text: rawData },
              timestamp: new Date().toISOString(),
            });
          }
        }
      }
    }
  } catch (err: any) {
    if (signal?.aborted || err.name === "AbortError") {
      
      return;
    }
    throw err;
  }
}




export async function listSessionConversationsApi(
  sessionId: string,
): Promise<ResearchConversation[]> {
  const resp = await apiClient.get<ResearchConversation[]>(
    `/research/sessions/${encodeURIComponent(sessionId)}/conversations`,
  );
  return resp.data;
}




export async function getConversationApi(
  conversationId: string,
): Promise<ResearchConversation> {
  const resp = await apiClient.get<ResearchConversation>(
    `/research/conversations/${conversationId}`,
  );
  return resp.data;
}




export async function getConversationMessagesApi(
  conversationId: string,
  limit = 50,
): Promise<ResearchMessage[]> {
  const resp = await apiClient.get<ResearchMessage[]>(
    `/research/conversations/${conversationId}/messages`,
    { params: { limit } },
  );
  return resp.data;
}




export async function getSessionResearchHistoryApi(
  sessionId: string,
  conversationId?: string,
  limit = 50,
): Promise<ResearchHistoryResponse> {
  const params: Record<string, any> = { limit };
  if (conversationId) {
    params.conversation_id = conversationId;
  }
  const resp = await apiClient.get<ResearchHistoryResponse>(
    `/research/sessions/${sessionId}/history`,
    { params },
  );
  return resp.data;
}




export async function getSessionMemoryApi(
  sessionId: string,
): Promise<SessionMemoryResponse> {
  const resp = await apiClient.get<SessionMemoryResponse>(
    `/research/sessions/${sessionId}/memory`,
  );
  return resp.data;
}




export async function deleteConversationApi(
  conversationId: string,
): Promise<{ status: string; conversation_id: string; messages_deleted: number }> {
  const resp = await apiClient.delete<{
    status: string;
    conversation_id: string;
    messages_deleted: number;
  }>(`/research/conversations/${conversationId}`);
  return resp.data;
}
