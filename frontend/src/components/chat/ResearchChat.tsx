









import { useEffect, useState } from "react";
import { useResearchStore } from "../../store/researchStore";
import { ResearchHistory } from "./ResearchHistory";
import { ChatMessageList } from "./ChatMessageList";
import { ChatInput } from "./ChatInput";
import { StreamingProgress } from "./StreamingProgress";
import { CitationViewer } from "./CitationViewer";
import { FinancialRiskWidget } from "./FinancialRiskWidget";
import { FinancialCharts } from "./FinancialCharts";
import { extractFinancialMetricsFromResponse } from "../../services/research";

interface ResearchChatProps {
  sessionId: string;
  sessionName?: string;
  hasDocuments?: boolean;
}

export function ResearchChat({
  sessionId,
  sessionName = "Research Session",
  hasDocuments = true,
}: ResearchChatProps) {
  const {
    activeSessionId,
    activeConversationId,
    conversations,
    messages,
    activeResponse,
    isStreaming,
    streamingStep,
    isLoading,
    error,
    setSessionId,
    selectConversation,
    startNewConversation,
    sendMessage,
    stopGeneration,
    retryLastMessage,
    deleteConversation,
    clearError,
  } = useResearchStore();

  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<"citations" | "risk" | "charts">("citations");
  const [showHistoryMobile, setShowHistoryMobile] = useState(false);
  const [showEvidenceMobile, setShowEvidenceMobile] = useState(false);

  
  useEffect(() => {
    if (sessionId && sessionId !== activeSessionId) {
      setSessionId(sessionId);
    }
  }, [sessionId, activeSessionId, setSessionId]);

  
  const activeConversation = conversations.find(
    (c) => c.conversation_id === activeConversationId,
  );

  const handleCitationSelect = (citId: string) => {
    setSelectedCitationId(citId);
    setRightTab("citations");
    setShowEvidenceMobile(true);
  };

  const handleSelectPrompt = (prompt: string) => {
    sendMessage(prompt);
  };

  
  const lastAssistantMsg = [...messages].reverse().find((m) => m.role === "assistant");
  const currentResponse = activeResponse || lastAssistantMsg?.structuredResponse;
  const currentCitations = currentResponse?.citations || lastAssistantMsg?.citations || [];
  const currentClaims = currentResponse?.claims || lastAssistantMsg?.claims || [];

  return (
    <div
      style={{
        display: "flex",
        height: "calc(100vh - 120px)",
        minHeight: "540px",
        backgroundColor: "var(--color-bg-base)",
        borderRadius: "0.75rem",
        border: "1px solid var(--color-border-subtle)",
        overflow: "hidden",
        position: "relative",
      }}
    >
      {}
      <div
        style={{
          width: "260px",
          flexShrink: 0,
          display: showHistoryMobile ? "flex" : undefined,
        }}
        className={`history-panel ${showHistoryMobile ? "mobile-open" : ""}`}
      >
        <ResearchHistory
          conversations={conversations}
          activeConversationId={activeConversationId}
          isLoading={isLoading}
          onSelectConversation={(id) => {
            selectConversation(id);
            setShowHistoryMobile(false);
          }}
          onNewConversation={() => {
            startNewConversation();
            setShowHistoryMobile(false);
          }}
          onDeleteConversation={deleteConversation}
        />
      </div>

      {}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          backgroundColor: "var(--color-bg-base)",
        }}
      >
        {}
        <div
          style={{
            height: "52px",
            padding: "0 1.25rem",
            backgroundColor: "var(--color-bg-surface)",
            borderBottom: "1px solid var(--color-border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
            {}
            <button
              onClick={() => setShowHistoryMobile(!showHistoryMobile)}
              className="btn-ghost"
              style={{
                padding: "0.35rem",
                borderRadius: "4px",
                border: "none",
                background: "transparent",
                color: "var(--color-text-secondary)",
                cursor: "pointer",
                display: "none", 
              }}
              aria-label="Toggle history menu"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            <div style={{ minWidth: 0 }}>
              <h2
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: "var(--color-text-primary)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {activeConversation?.title || "New Research Inquiry"}
              </h2>
              <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}>
                Session: {sessionName}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {}
            <button
              onClick={() => setShowEvidenceMobile(!showEvidenceMobile)}
              className="btn btn-secondary"
              style={{ padding: "0.25rem 0.5rem", fontSize: "0.6875rem" }}
            >
              Evidence & Risk ({currentCitations.length})
            </button>
          </div>
        </div>

        {}
        {error && (
          <div
            style={{
              padding: "0.5rem 1rem",
              backgroundColor: "rgba(239, 68, 68, 0.12)",
              borderBottom: "1px solid rgba(239, 68, 68, 0.3)",
              color: "var(--color-risk-500)",
              fontSize: "0.75rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{error}</span>
            <button
              onClick={clearError}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--color-text-secondary)",
                cursor: "pointer",
              }}
            >
              ✕
            </button>
          </div>
        )}

        {}
        <ChatMessageList
          messages={messages}
          isStreaming={isStreaming}
          onCitationClick={handleCitationSelect}
          onRetry={retryLastMessage}
          onSelectPrompt={handleSelectPrompt}
        />

        {}
        <div
          style={{
            padding: "0.75rem 1.25rem 1rem",
            backgroundColor: "var(--color-bg-base)",
          }}
        >
          {isStreaming && (
            <StreamingProgress
              currentStep={streamingStep}
              onStop={stopGeneration}
            />
          )}

          <ChatInput
            onSendMessage={(msg, opts) => sendMessage(msg, opts)}
            onStopGeneration={stopGeneration}
            isStreaming={isStreaming}
            disabled={!hasDocuments}
            placeholder={
              !hasDocuments
                ? "Upload financial documents to this session to enable evidence-grounded research..."
                : "Ask about revenue, EBITDA, debt covenants, margins, or forensic anomalies..."
            }
          />
        </div>
      </div>

      {}
      <div
        style={{
          width: "340px",
          flexShrink: 0,
          backgroundColor: "var(--color-bg-surface)",
          borderLeft: "1px solid var(--color-border-subtle)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        className={`evidence-panel ${showEvidenceMobile ? "mobile-open" : ""}`}
      >
        {}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid var(--color-border-subtle)",
            backgroundColor: "var(--color-bg-surface-alt)",
          }}
        >
          <button
            onClick={() => setRightTab("citations")}
            style={{
              flex: 1,
              padding: "0.625rem 0.25rem",
              fontSize: "0.6875rem",
              fontWeight: 600,
              border: "none",
              borderBottom: rightTab === "citations" ? "2px solid var(--color-emerald-500)" : "2px solid transparent",
              backgroundColor: rightTab === "citations" ? "var(--color-bg-surface)" : "transparent",
              color: rightTab === "citations" ? "var(--color-emerald-500)" : "var(--color-text-secondary)",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            Citations ({currentCitations.length})
          </button>

          <button
            onClick={() => setRightTab("risk")}
            style={{
              flex: 1,
              padding: "0.625rem 0.25rem",
              fontSize: "0.6875rem",
              fontWeight: 600,
              border: "none",
              borderBottom: rightTab === "risk" ? "2px solid var(--color-amber-500)" : "2px solid transparent",
              backgroundColor: rightTab === "risk" ? "var(--color-bg-surface)" : "transparent",
              color: rightTab === "risk" ? "var(--color-amber-500)" : "var(--color-text-secondary)",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            Risk & Flags
          </button>

          <button
            onClick={() => setRightTab("charts")}
            style={{
              flex: 1,
              padding: "0.625rem 0.25rem",
              fontSize: "0.6875rem",
              fontWeight: 600,
              border: "none",
              borderBottom: rightTab === "charts" ? "2px solid var(--color-emerald-500)" : "2px solid transparent",
              backgroundColor: rightTab === "charts" ? "var(--color-bg-surface)" : "transparent",
              color: rightTab === "charts" ? "var(--color-emerald-500)" : "var(--color-text-secondary)",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            Trends
          </button>
        </div>

        {}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem" }}>
          {rightTab === "citations" && (
            <CitationViewer
              citations={currentCitations}
              claims={currentClaims}
              selectedCitationId={selectedCitationId}
              onCitationSelect={(id) => setSelectedCitationId(id)}
            />
          )}

          {rightTab === "risk" && (
            <FinancialRiskWidget sessionId={sessionId} response={currentResponse} />
          )}

          {rightTab === "charts" && (
            <div>
              <FinancialCharts response={currentResponse} />
              {(!currentResponse || extractFinancialMetricsFromResponse(currentResponse).length === 0) && (
                <div
                  style={{
                    padding: "1.5rem 1rem",
                    textAlign: "center",
                    color: "var(--color-text-secondary)",
                    fontSize: "0.75rem",
                    backgroundColor: "var(--color-bg-surface-alt)",
                    borderRadius: "0.5rem",
                    border: "1px solid var(--color-border-subtle)",
                  }}
                >
                  <p style={{ margin: 0 }}>
                    No multi-period structured financial series available to chart for this query.
                  </p>
                  <span style={{ fontSize: "0.6875rem", display: "block", marginTop: "0.5rem", color: "var(--color-emerald-500)" }}>
                    FinSentry strictly charts verified numerical data points only.
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
