





import { useEffect, useRef } from "react";
import type { ResearchMessage } from "../../types/research";
import { ChatMessage } from "./ChatMessage";

interface ChatMessageListProps {
  messages: ResearchMessage[];
  isStreaming: boolean;
  onCitationClick?: (citationId: string) => void;
  onRetry?: () => void;
  onSelectPrompt?: (prompt: string) => void;
}

const SUGGESTED_QUERIES = [
  "What was total revenue and EBITDA in the most recent fiscal year?",
  "Are there any disclosed debt covenant restrictions or liquidity risks?",
  "Compare operating expenses and gross profit margins across reported periods.",
  "Identify critical forensic red flags or unusual accounting variances.",
];

export function ChatMessageList({
  messages,
  isStreaming,
  onCitationClick,
  onRetry,
  onSelectPrompt,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem 1.5rem",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: "48px",
            height: "48px",
            borderRadius: "50%",
            backgroundColor: "rgba(16, 185, 129, 0.12)",
            color: "var(--color-emerald-500)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "1rem",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
        </div>

        <h3 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "0.375rem" }}>
          Autonomous Financial Research Agent
        </h3>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)", maxWidth: "480px", marginBottom: "1.5rem", lineHeight: 1.5 }}>
          Ask in-depth questions regarding financial disclosures, covenants, operating margins, or accounting anomalies. Every assertion is strictly validated against verified source chunks.
        </p>

        {}
        <div style={{ width: "100%", maxWidth: "560px", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Suggested Research Inquiries:
          </span>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "0.5rem" }}>
            {SUGGESTED_QUERIES.map((q, idx) => (
              <button
                key={idx}
                onClick={() => onSelectPrompt?.(q)}
                style={{
                  backgroundColor: "var(--color-bg-surface)",
                  border: "1px solid var(--color-border-subtle)",
                  borderRadius: "0.5rem",
                  padding: "0.625rem 0.75rem",
                  color: "var(--color-text-primary)",
                  fontSize: "0.75rem",
                  textAlign: "left",
                  cursor: "pointer",
                  lineHeight: 1.35,
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-emerald-500)";
                  e.currentTarget.style.backgroundColor = "var(--color-bg-surface-alt)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-border-subtle)";
                  e.currentTarget.style.backgroundColor = "var(--color-bg-surface)";
                }}
              >
                "{q}"
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem 1.5rem" }}>
      {messages.map((msg) => (
        <ChatMessage
          key={msg.message_id}
          message={msg}
          onCitationClick={onCitationClick}
          onRetry={onRetry}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
