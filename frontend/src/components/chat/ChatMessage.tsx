









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

function renderInlineFormatted(text: string) {
  // Replace inline bold, code, and unescape backslashes
  const clean = text
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, "\\");

  const parts = clean.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
      return (
        <strong key={i} style={{ fontWeight: 600, color: "var(--color-text-primary)" }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return (
        <code
          key={i}
          style={{
            backgroundColor: "var(--color-bg-surface-alt)",
            padding: "0.1rem 0.3rem",
            borderRadius: "3px",
            fontFamily: "monospace",
            fontSize: "0.8125rem",
          }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function FormattedMarkdownContent({ content }: { content: string }) {
  if (!content) return null;

  // Unescape escaped newlines and literal slashes
  const normalized = content
    .replace(/\\n/g, "\n")
    .replace(/\r\n/g, "\n");

  const lines = normalized.split("\n");
  const elements: React.ReactNode[] = [];
  let inList: "ul" | "ol" | null = null;
  let listItems: string[] = [];
  let inTable = false;
  let tableRows: string[][] = [];

  const flushList = () => {
    if (inList && listItems.length > 0) {
      const items = [...listItems];
      const type = inList;
      elements.push(
        type === "ul" ? (
          <ul key={`list-${elements.length}`} style={{ margin: "0.5rem 0", paddingLeft: "1.25rem" }}>
            {items.map((it, idx) => (
              <li key={idx} style={{ marginBottom: "0.25rem", fontSize: "0.875rem" }}>
                {renderInlineFormatted(it)}
              </li>
            ))}
          </ul>
        ) : (
          <ol key={`list-${elements.length}`} style={{ margin: "0.5rem 0", paddingLeft: "1.25rem" }}>
            {items.map((it, idx) => (
              <li key={idx} style={{ marginBottom: "0.25rem", fontSize: "0.875rem" }}>
                {renderInlineFormatted(it)}
              </li>
            ))}
          </ol>
        )
      );
      listItems = [];
      inList = null;
    }
  };

  const flushTable = () => {
    if (inTable && tableRows.length > 0) {
      const rows = [...tableRows];
      const headerRow = rows[0];
      const bodyRows = rows.slice(1).filter((r) => !r.every((c) => /^-+$/.test(c.trim())));

      elements.push(
        <div
          key={`table-${elements.length}`}
          style={{
            overflowX: "auto",
            margin: "0.75rem 0",
            borderRadius: "0.375rem",
            border: "1px solid var(--color-border-subtle)",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ backgroundColor: "var(--color-bg-surface-alt)", borderBottom: "1px solid var(--color-border-subtle)" }}>
                {headerRow.map((cell, cidx) => (
                  <th key={cidx} style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600 }}>
                    {renderInlineFormatted(cell.trim())}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, ridx) => (
                <tr key={ridx} style={{ borderBottom: ridx < bodyRows.length - 1 ? "1px solid var(--color-border-subtle)" : "none" }}>
                  {row.map((cell, cidx) => (
                    <td key={cidx} style={{ padding: "0.5rem 0.75rem" }}>
                      {renderInlineFormatted(cell.trim())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (!line) {
      flushList();
      flushTable();
      continue;
    }

    // Markdown Table check: starts with | and ends with |
    if (line.startsWith("|") && line.endsWith("|")) {
      flushList();
      inTable = true;
      const cells = line.slice(1, -1).split("|");
      tableRows.push(cells);
      continue;
    } else {
      flushTable();
    }

    // Headings
    if (line.startsWith("### ")) {
      flushList();
      elements.push(
        <h4 key={`h4-${elements.length}`} style={{ fontSize: "0.9375rem", fontWeight: 600, margin: "0.75rem 0 0.375rem 0", color: "var(--color-text-primary)" }}>
          {renderInlineFormatted(line.slice(4))}
        </h4>
      );
      continue;
    }
    if (line.startsWith("## ")) {
      flushList();
      elements.push(
        <h3 key={`h3-${elements.length}`} style={{ fontSize: "1rem", fontWeight: 700, margin: "0.875rem 0 0.5rem 0", color: "var(--color-text-primary)" }}>
          {renderInlineFormatted(line.slice(3))}
        </h3>
      );
      continue;
    }
    if (line.startsWith("# ")) {
      flushList();
      elements.push(
        <h2 key={`h2-${elements.length}`} style={{ fontSize: "1.125rem", fontWeight: 700, margin: "1rem 0 0.5rem 0", color: "var(--color-text-primary)" }}>
          {renderInlineFormatted(line.slice(2))}
        </h2>
      );
      continue;
    }

    // Unordered list
    if (/^[-*]\s+/.test(line)) {
      if (inList !== "ul") {
        flushList();
        inList = "ul";
      }
      listItems.push(line.replace(/^[-*]\s+/, ""));
      continue;
    }

    // Ordered list
    if (/^\d+\.\s+/.test(line)) {
      if (inList !== "ol") {
        flushList();
        inList = "ol";
      }
      listItems.push(line.replace(/^\d+\.\s+/, ""));
      continue;
    }

    flushList();

    // Normal paragraph
    elements.push(
      <p key={`p-${elements.length}`} style={{ margin: "0.375rem 0", lineHeight: 1.6, fontSize: "0.875rem", color: "var(--color-text-primary)" }}>
        {renderInlineFormatted(line)}
      </p>
    );
  }

  flushList();
  flushTable();

  return <>{elements}</>;
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
        {/* Header Bar */}
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
            {/* Formatted Markdown Body */}
            <div
              style={{
                fontSize: "0.875rem",
                color: "var(--color-text-primary)",
                lineHeight: 1.6,
                wordBreak: "break-word",
              }}
            >
              {message.content ? (
                <FormattedMarkdownContent content={message.content} />
              ) : isStreaming ? (
                "Synthesizing evidence-backed findings..."
              ) : (
                ""
              )}
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
