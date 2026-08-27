









import type { ResearchMessage } from "../../types/research";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { RefusalNotice } from "./RefusalNotice";
import { getValidationStatusBadgeProps } from "../../services/research";

interface ChatMessageProps {
  message: ResearchMessage;
  onCitationClick?: (citationId: string) => void;
  onRetry?: () => void;
  onSelectResponse?: () => void;
}

export function ChatMessage({
  message,
  onCitationClick,
  onRetry,
  onSelectResponse,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const structured = message.structuredResponse;
  const isRefusal = message.isRefusal || structured?.refused;
  const isError = message.isError;
  const isStreaming = message.isStreaming;

  const timestamp = message.created_at
    ? new Date(message.created_at).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  if (isUser) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: "1rem",
        }}
      >
        <div
          style={{
            maxWidth: "80%",
            backgroundColor: "var(--color-emerald-600)",
            color: "#ffffff",
            borderRadius: "0.75rem 0.75rem 0.125rem 0.75rem",
            padding: "0.75rem 1rem",
            boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
          }}
        >
          <p style={{ fontSize: "0.875rem", lineHeight: 1.5, margin: 0, wordBreak: "break-word" }}>
            {message.content}
          </p>
          <div
            style={{
              fontSize: "0.625rem",
              color: "rgba(255, 255, 255, 0.75)",
              textAlign: "right",
              marginTop: "0.375rem",
            }}
          >
            {timestamp}
          </div>
        </div>
      </div>
    );
  }

  const validationBadge = getValidationStatusBadgeProps(message.validation_status);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        marginBottom: "1.25rem",
        maxWidth: "92%",
      }}
      onClick={onSelectResponse}
    >
      <div
        style={{
          backgroundColor: "var(--color-bg-surface)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "0.75rem 0.75rem 0.75rem 0.125rem",
          padding: "1rem",
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
        }}
      >
        {}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "0.5rem",
            marginBottom: "0.75rem",
            paddingBottom: "0.5rem",
            borderBottom: "1px solid var(--color-border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "var(--color-emerald-500)",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              Research Agent
            </span>

            {}
            {message.validation_status && (
              <span
                style={{
                  fontSize: "0.625rem",
                  fontWeight: 600,
                  padding: "0.15rem 0.4rem",
                  borderRadius: "4px",
                  backgroundColor: validationBadge.bg,
                  color: validationBadge.color,
                }}
              >
                {validationBadge.label}
              </span>
            )}

            {}
            {structured?.metadata?.is_fallback && (
              <span
                style={{
                  fontSize: "0.625rem",
                  fontWeight: 600,
                  padding: "0.15rem 0.4rem",
                  borderRadius: "4px",
                  backgroundColor: "rgba(245, 158, 11, 0.15)",
                  color: "var(--color-amber-500)",
                }}
                title={`Fallback provider activated (${structured.metadata.llm_provider || "Secondary"})`}
              >
                Fallback Provider
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ConfidenceBadge
              level={message.confidence_tier || structured?.confidence_level}
              score={message.confidence_score ?? structured?.confidence}
            />

            {structured?.metadata?.execution_time_ms ? (
              <span
                className="font-tabular"
                style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}
              >
                {Math.round(structured.metadata.execution_time_ms)}ms
              </span>
            ) : null}

            <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}>
              {timestamp}
            </span>
          </div>
        </div>

        {}
        {isError ? (
          <div
            style={{
              padding: "0.75rem",
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              borderRadius: "0.375rem",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "var(--color-risk-500)",
              fontSize: "0.8125rem",
            }}
          >
            <p style={{ margin: "0 0 0.5rem 0" }}>{message.content}</p>
            {onRetry && (
              <button
                className="btn btn-secondary"
                onClick={onRetry}
                style={{ padding: "0.25rem 0.75rem", fontSize: "0.75rem" }}
              >
                Retry Research Query
              </button>
            )}
          </div>
        ) : isRefusal ? (
          <RefusalNotice
            reason={structured?.refusal_reason || message.content}
            missingItems={structured?.sufficiency?.missing_evidence_items}
          />
        ) : (
          <div>
            {}
            <div
              style={{
                fontSize: "0.875rem",
                color: "var(--color-text-primary)",
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {message.content || (isStreaming ? "Synthesizing evidence-backed findings..." : "")}
            </div>

            {}
            {structured?.key_points && structured.key_points.length > 0 && (
              <div
                style={{
                  marginTop: "0.75rem",
                  padding: "0.625rem 0.75rem",
                  backgroundColor: "var(--color-bg-surface-alt)",
                  borderRadius: "0.375rem",
                  borderLeft: "2px solid var(--color-emerald-500)",
                }}
              >
                <span
                  style={{
                    fontSize: "0.6875rem",
                    fontWeight: 700,
                    color: "var(--color-text-secondary)",
                    textTransform: "uppercase",
                    display: "block",
                    marginBottom: "0.25rem",
                  }}
                >
                  Key Findings:
                </span>
                <ul style={{ paddingLeft: "1.25rem", margin: 0, fontSize: "0.8125rem", color: "var(--color-text-primary)" }}>
                  {structured.key_points.map((kp, idx) => (
                    <li key={idx} style={{ marginBottom: "0.15rem" }}>
                      {kp}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {}
            {message.citations && message.citations.length > 0 && (
              <div
                style={{
                  marginTop: "0.75rem",
                  paddingTop: "0.5rem",
                  borderTop: "1px solid var(--color-border-subtle)",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.375rem",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)", fontWeight: 600 }}>
                  Sources:
                </span>
                {message.citations.map((cit, idx) => (
                  <button
                    key={cit.citation_id || idx}
                    onClick={() => onCitationClick?.(cit.citation_id)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      padding: "0.15rem 0.45rem",
                      borderRadius: "4px",
                      backgroundColor: "var(--color-bg-base)",
                      border: "1px solid var(--color-border-subtle)",
                      color: "var(--color-emerald-500)",
                      fontSize: "0.6875rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                    title={cit.quoted_snippet ? `Source: ${cit.quoted_snippet.slice(0, 100)}...` : undefined}
                  >
                    [{idx + 1}] {cit.document_filename || "Source"}
                    {cit.page_number !== undefined && cit.page_number !== null ? ` (p.${cit.page_number})` : ""}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
