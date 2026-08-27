





import { useState, useRef, useEffect, type KeyboardEvent, type FormEvent } from "react";

interface ChatInputProps {
  onSendMessage: (query: string, options?: { mode?: "hybrid" | "vector" | "keyword"; top_k?: number }) => void;
  onStopGeneration?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSendMessage,
  onStopGeneration,
  isStreaming,
  disabled = false,
  placeholder = "Ask a financial research question (e.g. 'Compare FY23 vs FY24 revenue and analyze margin compression')...",
}: ChatInputProps) {
  const [query, setQuery] = useState("");
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "vector" | "keyword">("hybrid");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  
  useEffect(() => {
    if (!disabled && !isStreaming) {
      textareaRef.current?.focus();
    }
  }, [disabled, isStreaming]);

  const handleSubmit = (e?: FormEvent) => {
    if (e) e.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery || isStreaming || disabled) return;

    onSendMessage(cleanQuery, { mode: retrievalMode, top_k: 5 });
    setQuery("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const charCount = query.length;
  const isTooLong = charCount > 10000;

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        backgroundColor: "var(--color-bg-surface)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "0.75rem",
        padding: "0.75rem",
        boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      {}
      <textarea
        ref={textareaRef}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || isStreaming}
        rows={2}
        style={{
          width: "100%",
          backgroundColor: "transparent",
          border: "none",
          color: "var(--color-text-primary)",
          fontSize: "0.875rem",
          fontFamily: "var(--font-sans)",
          lineHeight: 1.5,
          resize: "none",
          outline: "none",
        }}
        aria-label="Financial research query input"
      />

      {}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          paddingTop: "0.375rem",
          borderTop: "1px solid var(--color-border-subtle)",
        }}
      >
        {}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}>
              Mode:
            </span>
            <select
              value={retrievalMode}
              onChange={(e) => setRetrievalMode(e.target.value as any)}
              disabled={disabled || isStreaming}
              style={{
                backgroundColor: "var(--bg-surface-alt)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "4px",
                color: "var(--text-primary)",
                fontSize: "0.6875rem",
                padding: "0.15rem 0.35rem",
                outline: "none",
                cursor: "pointer",
              }}
              aria-label="Retrieval mode selection"
            >
              <option value="hybrid" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)" }}>
                Hybrid (Dense + Sparse)
              </option>
              <option value="vector" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)" }}>
                Dense Vector
              </option>
              <option value="keyword" style={{ backgroundColor: "var(--bg-surface)", color: "var(--text-primary)" }}>
                BM25 Keyword
              </option>
            </select>
          </div>

          <span
            className="font-tabular"
            style={{
              fontSize: "0.6875rem",
              color: isTooLong ? "var(--color-risk-500)" : "var(--color-text-secondary)",
            }}
          >
            {charCount}/10,000
          </span>
        </div>

        {}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {isStreaming ? (
            <button
              type="button"
              onClick={onStopGeneration}
              className="btn"
              style={{
                backgroundColor: "rgba(239, 68, 68, 0.15)",
                color: "var(--color-risk-500)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                padding: "0.375rem 0.875rem",
                fontSize: "0.75rem",
              }}
              aria-label="Stop research generation"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
              Stop Generation
            </button>
          ) : (
            <button
              type="submit"
              disabled={!query.trim() || disabled || isTooLong}
              className="btn btn-primary"
              style={{
                padding: "0.375rem 1rem",
                fontSize: "0.75rem",
              }}
              aria-label="Execute research query"
            >
              <span>Research</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
