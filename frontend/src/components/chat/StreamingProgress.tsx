




interface StreamingProgressProps {
  currentStep: string | null;
  onStop?: () => void;
}

export function StreamingProgress({
  currentStep,
  onStop,
}: StreamingProgressProps) {
  if (!currentStep) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.5rem 0.875rem",
        backgroundColor: "var(--color-bg-surface-alt)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "0.375rem",
        marginBottom: "0.75rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
        <span
          className="animate-spin"
          style={{
            width: "12px",
            height: "12px",
            border: "2px solid var(--color-emerald-500)",
            borderTopColor: "transparent",
            borderRadius: "50%",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--color-text-secondary)",
            fontWeight: 500,
          }}
        >
          {currentStep}
        </span>
      </div>

      {onStop && (
        <button
          onClick={onStop}
          style={{
            background: "transparent",
            border: "1px solid rgba(239, 68, 68, 0.4)",
            borderRadius: "0.25rem",
            color: "var(--color-risk-500)",
            fontSize: "0.6875rem",
            padding: "0.2rem 0.5rem",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "0.25rem",
            transition: "all 0.15s ease",
          }}
          title="Cancel active research generation"
          aria-label="Stop generation"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
          Stop
        </button>
      )}
    </div>
  );
}
