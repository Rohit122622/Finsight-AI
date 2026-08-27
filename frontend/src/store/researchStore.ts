











import { create } from "zustand";
import {
  deleteConversationApi,
  getConversationMessagesApi,
  getSessionResearchHistoryApi,
  listSessionConversationsApi,
  streamResearchChatApi,
} from "../api/research";
import type {
  ResearchChatRequest,
  ResearchConversation,
  ResearchMessage,
  ResearchResponse,
  StreamEvent,
  ValidationResult,
} from "../types/research";

interface ResearchStoreState {
  activeSessionId: string | null;
  activeConversationId: string | null;
  conversations: ResearchConversation[];
  messages: ResearchMessage[];
  activeResponse: ResearchResponse | null;
  activeValidation: ValidationResult | null;

  isLoading: boolean;
  isStreaming: boolean;
  streamingStep: string | null;
  streamingDelta: string;
  error: string | null;
  lastFailedQuery: string | null;

  
  setSessionId: (sessionId: string) => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  startNewConversation: () => void;
  loadSessionHistory: (sessionId: string) => Promise<void>;
  sendMessage: (
    message: string,
    options?: Partial<ResearchChatRequest>,
  ) => Promise<void>;
  stopGeneration: () => void;
  retryLastMessage: () => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  clearError: () => void;
  setActiveResponse: (response: ResearchResponse | null) => void;
}

function extractError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  return fallback;
}

let activeAbortController: AbortController | null = null;

export const useResearchStore = create<ResearchStoreState>((set, get) => ({
  activeSessionId: null,
  activeConversationId: null,
  conversations: [],
  messages: [],
  activeResponse: null,
  activeValidation: null,

  isLoading: false,
  isStreaming: false,
  streamingStep: null,
  streamingDelta: "",
  error: null,
  lastFailedQuery: null,

  



  setSessionId: async (sessionId: string) => {
    const current = get().activeSessionId;
    if (current === sessionId && get().conversations.length > 0) {
      return;
    }

    
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }

    
    set({
      activeSessionId: sessionId,
      activeConversationId: null,
      conversations: [],
      messages: [],
      activeResponse: null,
      activeValidation: null,
      isLoading: true,
      isStreaming: false,
      streamingStep: null,
      streamingDelta: "",
      error: null,
      lastFailedQuery: null,
    });

    try {
      await get().loadSessionHistory(sessionId);
    } catch (err: unknown) {
      set({
        isLoading: false,
        error: extractError(err, "Failed to load session research history"),
      });
    }
  },

  


  loadSessionHistory: async (sessionId: string) => {
    set({ isLoading: true, error: null });
    try {
      const [backendConvs, history] = await Promise.all([
        listSessionConversationsApi(sessionId).catch(() => [] as ResearchConversation[]),
        getSessionResearchHistoryApi(sessionId, undefined, 100).catch(() => ({ messages: [] })),
      ]);

      const convMap = new Map<string, ResearchConversation>();

      
      for (const c of backendConvs) {
        convMap.set(c.conversation_id, c);
      }

      
      for (const msg of history.messages) {
        if (!convMap.has(msg.conversation_id)) {
          convMap.set(msg.conversation_id, {
            conversation_id: msg.conversation_id,
            session_id: sessionId,
            user_id: msg.user_id,
            title: msg.role === "user" ? msg.content.slice(0, 60) : "Research Query",
            message_count: 1,
            created_at: msg.created_at,
            updated_at: msg.created_at,
          });
        } else {
          const c = convMap.get(msg.conversation_id)!;
          c.message_count = Math.max(c.message_count || 0, 1);
          if (new Date(msg.created_at) > new Date(c.updated_at || c.created_at)) {
            c.updated_at = msg.created_at;
          }
        }
      }

      const conversations = Array.from(convMap.values()).sort(
        (a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime(),
      );

      const currentConvId = get().activeConversationId;
      const targetConvId = currentConvId || (conversations.length > 0 ? conversations[0].conversation_id : null);

      set({
        conversations,
        activeConversationId: targetConvId,
        isLoading: false,
      });

      
      if (targetConvId) {
        const convMessages = history.messages.filter(
          (m) => m.conversation_id === targetConvId,
        );
        if (convMessages.length > 0) {
          const lastAssistant = [...convMessages].reverse().find((m) => m.role === "assistant");
          set({
            messages: convMessages,
            activeResponse: (lastAssistant?.structuredResponse as ResearchResponse) || null,
            activeValidation: (lastAssistant?.validationResult as ValidationResult) || null,
          });
        } else {
          
          await get().selectConversation(targetConvId);
        }
      }
    } catch (err: unknown) {
      set({
        isLoading: false,
        error: extractError(err, "Failed to load research history"),
      });
    }
  },

  


  selectConversation: async (conversationId: string) => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }

    set({
      activeConversationId: conversationId,
      isLoading: true,
      error: null,
      isStreaming: false,
      streamingStep: null,
      streamingDelta: "",
      activeResponse: null,
      activeValidation: null,
    });

    try {
      const messages = await getConversationMessagesApi(conversationId, 100);
      
      const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

      set({
        messages,
        isLoading: false,
        activeResponse: (lastAssistant?.structuredResponse as ResearchResponse) || null,
        activeValidation: (lastAssistant?.validationResult as ValidationResult) || null,
      });
    } catch (err: unknown) {
      set({
        isLoading: false,
        error: extractError(err, "Failed to load conversation messages"),
      });
    }
  },

  


  startNewConversation: () => {
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }

    set({
      activeConversationId: null,
      messages: [],
      activeResponse: null,
      activeValidation: null,
      error: null,
      isStreaming: false,
      streamingStep: null,
      streamingDelta: "",
      lastFailedQuery: null,
    });
  },

  


  sendMessage: async (
    queryText: string,
    options?: Partial<ResearchChatRequest>,
  ) => {
    const { activeSessionId, activeConversationId } = get();
    const cleanMessage = queryText.trim();
    if (!cleanMessage || !activeSessionId) return;

    
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }

    const controller = new AbortController();
    activeAbortController = controller;

    const userMessageId = `user_${Date.now()}`;
    const assistantMessageId = `asst_${Date.now()}`;

    const userMsg: ResearchMessage = {
      message_id: userMessageId,
      conversation_id: activeConversationId || "pending",
      session_id: activeSessionId,
      user_id: "current",
      role: "user",
      content: cleanMessage,
      created_at: new Date().toISOString(),
    };

    const initialAssistantMsg: ResearchMessage = {
      message_id: assistantMessageId,
      conversation_id: activeConversationId || "pending",
      session_id: activeSessionId,
      user_id: "assistant",
      role: "assistant",
      content: "",
      isStreaming: true,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMsg, initialAssistantMsg],
      isStreaming: true,
      streamingStep: "Initializing research pipeline...",
      streamingDelta: "",
      error: null,
      lastFailedQuery: cleanMessage,
    }));

    let accumulatedContent = "";

    try {
      const requestPayload: ResearchChatRequest = {
        session_id: activeSessionId,
        message: cleanMessage,
        conversation_id: activeConversationId,
        stream: true,
        top_k: options?.top_k ?? 5,
        mode: options?.mode ?? "hybrid",
        score_threshold: options?.score_threshold ?? 0.0,
        document_ids: options?.document_ids,
      };

      await streamResearchChatApi(
        requestPayload,
        (event: StreamEvent) => {
          const { event: evtType, data } = event;

          switch (evtType) {
            case "started":
              set({
                streamingStep: "Started analytical research pipeline...",
              });
              break;

            case "query_understanding":
              set({
                streamingStep: `Query Understanding: Intent classified as ${String(data?.intent || "financial analysis")}`,
              });
              break;

            case "retrieval":
              set({
                streamingStep: `Hybrid Retrieval: Found ${String(data?.chunks_retrieved || 0)} evidence chunks`,
              });
              break;

            case "context":
              set({
                streamingStep: "Building evidence context window...",
              });
              break;

            case "generation":
              set({
                streamingStep: "Reasoning over verified evidence...",
              });
              break;

            case "citation":
              set({
                streamingStep: "Verifying citations against document chunks...",
              });
              break;

            case "token":
            case "content_delta": {
              const delta = String(data?.text || data?.delta || "");
              if (delta) {
                accumulatedContent += delta;
                set((state) => ({
                  streamingDelta: accumulatedContent,
                  messages: state.messages.map((m) =>
                    m.message_id === assistantMessageId
                      ? { ...m, content: accumulatedContent }
                      : m,
                  ),
                }));
              }
              break;
            }

            case "validation":
              set({
                streamingStep: "Strict output validation & claim grounding...",
              });
              break;

            case "completed": {
              const chatResponse = data as Record<string, unknown>;
              const res = chatResponse?.response as ResearchResponse | undefined;
              const val = chatResponse?.validation as ValidationResult | undefined;
              const newConvId = (chatResponse?.conversation_id as string) || activeConversationId;

              const finalContent = res?.answer || accumulatedContent;

              set((state) => {
                const updatedMessages = state.messages.map((m) => {
                  if (m.message_id === assistantMessageId) {
                    return {
                      ...m,
                      conversation_id: newConvId || m.conversation_id,
                      content: finalContent,
                      claims: res?.claims || [],
                      citations: res?.citations || [],
                      confidence_score: res?.confidence ?? val?.final_confidence ?? null,
                      confidence_tier: res?.confidence_level ?? val?.confidence_level ?? null,
                      validation_status: val?.status ?? "VALID",
                      isStreaming: false,
                      isRefusal: res?.refused ?? false,
                      structuredResponse: res || null,
                      validationResult: val || null,
                    };
                  }
                  if (m.message_id === userMessageId) {
                    return {
                      ...m,
                      conversation_id: newConvId || m.conversation_id,
                    };
                  }
                  return m;
                });

                return {
                  messages: updatedMessages,
                  activeConversationId: newConvId || state.activeConversationId,
                  activeResponse: res || null,
                  activeValidation: val || null,
                  isStreaming: false,
                  streamingStep: null,
                  streamingDelta: "",
                  lastFailedQuery: null,
                };
              });

              
              if (activeSessionId) {
                get().loadSessionHistory(activeSessionId);
              }
              break;
            }

            case "refused": {
              const refusalReason =
                String(data?.refusal_reason || data?.reason || "") ||
                "The provided documents do not contain sufficient information to answer this question.";

              set((state) => ({
                isStreaming: false,
                streamingStep: null,
                messages: state.messages.map((m) =>
                  m.message_id === assistantMessageId
                    ? {
                        ...m,
                        content: refusalReason,
                        isStreaming: false,
                        isRefusal: true,
                        validation_status: "REFUSED",
                      }
                    : m,
                ),
              }));
              break;
            }

            case "error": {
              const errorMsg =
                String(data?.message || data?.error || data?.detail || "") ||
                "An error occurred during research.";
              set((state) => ({
                isStreaming: false,
                streamingStep: null,
                error: errorMsg,
                messages: state.messages.map((m) =>
                  m.message_id === assistantMessageId
                    ? {
                        ...m,
                        content: `Error: ${errorMsg}`,
                        isStreaming: false,
                        isError: true,
                        errorMessage: errorMsg,
                      }
                    : m,
                ),
              }));
              break;
            }
          }
        },
        controller.signal,
      );
    } catch (err: unknown) {
      if (controller.signal.aborted) {
        
        set((state) => ({
          isStreaming: false,
          streamingStep: null,
          messages: state.messages.map((m) =>
            m.message_id === assistantMessageId
              ? {
                  ...m,
                  content: accumulatedContent || "Generation stopped by user.",
                  isStreaming: false,
                }
              : m,
          ),
        }));
        return;
      }

      const errorMessage = extractError(
        err,
        "Failed to execute research. Please verify network and backend service.",
      );
      set((state) => ({
        isStreaming: false,
        streamingStep: null,
        error: errorMessage,
        messages: state.messages.map((m) =>
          m.message_id === assistantMessageId
            ? {
                ...m,
                content: `Unable to complete research query: ${errorMessage}`,
                isStreaming: false,
                isError: true,
                errorMessage,
              }
            : m,
        ),
      }));
    } finally {
      activeAbortController = null;
    }
  },

  


  stopGeneration: () => {
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }
    set({
      isStreaming: false,
      streamingStep: null,
    });
  },

  


  retryLastMessage: async () => {
    const { lastFailedQuery, sendMessage } = get();
    if (lastFailedQuery) {
      await sendMessage(lastFailedQuery);
    }
  },

  


  deleteConversation: async (conversationId: string) => {
    const { activeSessionId, activeConversationId } = get();
    try {
      await deleteConversationApi(conversationId);
      if (activeConversationId === conversationId) {
        set({
          activeConversationId: null,
          messages: [],
          activeResponse: null,
          activeValidation: null,
        });
      }
      if (activeSessionId) {
        await get().loadSessionHistory(activeSessionId);
      }
    } catch (err: unknown) {
      set({
        error: extractError(err, "Failed to delete conversation"),
      });
    }
  },

  clearError: () => set({ error: null }),
  setActiveResponse: (response) => set({ activeResponse: response }),
}));
