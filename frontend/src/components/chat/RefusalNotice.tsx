




interface RefusalNoticeProps {
  reason?: string | null;
  missingItems?: string[];
}

export function RefusalNotice({
  reason,
  missingItems = [],
}: RefusalNoticeProps) {
  const displayMessage =
    reason ||
    "The provided documents do not contain sufficient information to answer this question.";

  return (
    <div
      style={{
        backgroundColor: "rgba(245, 158, 11, 0.08)",
        border: "1px solid rgba(245, 158, 11, 0.3)",
        borderRadius: "0.5rem",
        padding: "1rem 1.25rem",
        marginTop: "0.5rem",
        marginBottom: "0.5rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-amber-500)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ flexShrink: 0, marginTop: "2px" }}
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>

        <div style={{ flex: 1 }}>
          <h4
            style={{
              fontSize: "0.875rem",
              fontWeight: 600,
              color: "var(--color-amber-500)",
              marginBottom: "0.25rem",
            }}
          >
            Sufficient Evidence Unavailable
          </h4>
          <p
            style={{
              fontSize: "0.8125rem",
              color: "var(--color-text-primary)",
              lineHeight: 1.4,
            }}
          >
            {displayMessage}
          </p>

          {missingItems.length > 0 && (
            <div style={{ marginTop: "0.5rem" }}>
              <span
                style={{
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                  display: "block",
                  marginBottom: "0.25rem",
                }}
              >
                Missing Disclosures:
              </span>
              <ul
                style={{
                  paddingLeft: "1.25rem",
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                }}
              >
                {missingItems.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
