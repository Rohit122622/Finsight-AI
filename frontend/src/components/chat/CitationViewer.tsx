





import { useState } from "react";
import type { ResearchCitation, ResearchClaim } from "../../types/research";

interface CitationViewerProps {
  citations: ResearchCitation[];
  claims?: ResearchClaim[];
  onCitationSelect?: (citationId: string) => void;
  selectedCitationId?: string | null;
}

export function CitationViewer({
  citations,
  claims = [],
  onCitationSelect,
  selectedCitationId,
}: CitationViewerProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!citations || citations.length === 0) {
    return (
      <div
        style={{
          padding: "1rem",
          textAlign: "center",
          color: "var(--color-text-secondary)",
          fontSize: "0.75rem",
          backgroundColor: "var(--color-bg-surface-alt)",
          borderRadius: "0.5rem",
          border: "1px solid var(--color-border-subtle)",
        }}
      >
        No source citations available for this turn.
      </div>
    );
  }

  const activeExpanded = selectedCitationId ?? expandedId;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Verified Source Citations ({citations.length})
        </span>
        <span style={{ fontSize: "0.6875rem", color: "var(--color-emerald-500)", fontWeight: 500 }}>
          Grounded in Evidence
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {citations.map((cit, idx) => {
          const isSelected = activeExpanded === cit.citation_id;
          const supportedClaims = claims.filter((c) =>
            cit.claim_ids?.includes(c.claim_id) ||
            c.evidence_refs?.some((ref) => ref.chunk_id === cit.chunk_id),
          );

          return (
            <div
              key={cit.citation_id || idx}
              style={{
                backgroundColor: isSelected
                  ? "var(--color-bg-surface-alt)"
                  : "var(--color-bg-surface)",
                border: `1px solid ${isSelected ? "var(--color-emerald-500)" : "var(--color-border-subtle)"}`,
                borderRadius: "0.5rem",
                padding: "0.75rem",
                transition: "all 0.15s ease",
                cursor: "pointer",
              }}
              onClick={() => {
                const nextId = isSelected ? null : cit.citation_id;
                setExpandedId(nextId);
                onCitationSelect?.(cit.citation_id);
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  const nextId = isSelected ? null : cit.citation_id;
                  setExpandedId(nextId);
                  onCitationSelect?.(cit.citation_id);
                }
              }}
              aria-expanded={isSelected}
            >
              {}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "20px",
                      height: "20px",
                      borderRadius: "4px",
                      backgroundColor: "rgba(16, 185, 129, 0.15)",
                      color: "var(--color-emerald-500)",
                      fontSize: "0.6875rem",
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {idx + 1}
                  </span>

                  <span
                    style={{
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      color: "var(--color-text-primary)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={cit.document_filename || "Verified Source Document"}
                  >
                    {cit.document_filename || "Source Document"}
                  </span>
                </div>

                <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0, alignItems: "center" }}>
                  {cit.page_number !== undefined && cit.page_number !== null && (
                    <span
                      className="font-tabular"
                      style={{
                        fontSize: "0.6875rem",
                        padding: "0.1rem 0.35rem",
                        borderRadius: "3px",
                        backgroundColor: "var(--color-bg-base)",
                        color: "var(--color-text-secondary)",
                        border: "1px solid var(--color-border-subtle)",
                      }}
                    >
                      Page {cit.page_number}
                    </span>
                  )}
                  {cit.section && (
                    <span
                      style={{
                        fontSize: "0.6875rem",
                        padding: "0.1rem 0.35rem",
                        borderRadius: "3px",
                        backgroundColor: "var(--color-bg-base)",
                        color: "var(--color-text-secondary)",
                        border: "1px solid var(--color-border-subtle)",
                        maxWidth: "90px",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={cit.section}
                    >
                      {cit.section}
                    </span>
                  )}
                </div>
              </div>

              {}
              {cit.quoted_snippet && (
                <div
                  style={{
                    marginTop: "0.5rem",
                    padding: "0.5rem 0.625rem",
                    backgroundColor: "var(--color-bg-base)",
                    borderRadius: "0.375rem",
                    borderLeft: "2px solid var(--color-emerald-500)",
                    fontSize: "0.75rem",
                    color: "var(--color-text-secondary)",
                    fontStyle: "italic",
                    lineHeight: 1.4,
                  }}
                >
                  "{isSelected ? cit.quoted_snippet : cit.quoted_snippet.slice(0, 140) + (cit.quoted_snippet.length > 140 ? "…" : "")}"
                </div>
              )}

              {}
              {isSelected && supportedClaims.length > 0 && (
                <div style={{ marginTop: "0.625rem", borderTop: "1px solid var(--color-border-subtle)", paddingTop: "0.5rem" }}>
                  <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)", fontWeight: 600, display: "block", marginBottom: "0.25rem" }}>
                    Supports Verified Assertions:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    {supportedClaims.map((claim) => (
                      <div
                        key={claim.claim_id}
                        style={{
                          fontSize: "0.6875rem",
                          color: "var(--color-text-primary)",
                          padding: "0.25rem 0.5rem",
                          borderRadius: "4px",
                          backgroundColor: "var(--color-bg-base)",
                        }}
                      >
                        • {claim.claim_text}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {cit.validation_error && (
                <div
                  style={{
                    marginTop: "0.375rem",
                    fontSize: "0.6875rem",
                    color: "var(--color-risk-500)",
                  }}
                >
                  Warning: {cit.validation_error}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
