import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentItem } from "../../types";
import { getSessionRedFlagsApi, type SessionRedFlagsResponse } from "../../api/analysis";

interface RedFlagViewerProps {
  sessionId: string;
  documents: DocumentItem[];
}

function stripExt(name?: string): string {
  if (!name) return "Document";
  return name.replace(/\.[a-zA-Z0-9]+$/, "");
}

function severityStyle(sev: string): { bg: string; color: string } {
  const s = sev.toUpperCase();
  if (s === "CRITICAL" || s === "HIGH") return { bg: "rgba(239, 68, 68, 0.15)", color: "var(--accent-risk, #ef4444)" };
  if (s === "MEDIUM") return { bg: "rgba(245, 158, 11, 0.15)", color: "#F59E0B" };
  return { bg: "rgba(16, 185, 129, 0.15)", color: "#10B981" };
}

function riskLevel(score: number): { label: string; color: string } {
  if (score >= 75) return { label: "Severe", color: "var(--accent-risk, #ef4444)" };
  if (score >= 50) return { label: "Elevated", color: "#ef4444" };
  if (score >= 25) return { label: "Moderate", color: "#F59E0B" };
  if (score > 0) return { label: "Low", color: "#10B981" };
  return { label: "Clean", color: "#10B981" };
}

/**
 * Canonical, document/company-specific Red Flag viewer.
 *
 * Each uploaded document gets a selectable tab. The selected document's PERSISTED
 * red flag analysis is fetched (owner-scoped) and cached. Selection state is fully
 * independent of Research — Research queries never change which document is shown here.
 * No red flag calculation happens in React; results are rendered as persisted.
 */
export function RedFlagViewer({ sessionId, documents }: RedFlagViewerProps) {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, SessionRedFlagsResponse>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef<Set<string>>(new Set());

  // Default to the first document; reset when the session/document set changes.
  useEffect(() => {
    if (documents.length === 0) {
      setSelectedDocId(null);
      return;
    }
    setSelectedDocId((prev) =>
      prev && documents.some((d) => d.document_id === prev) ? prev : documents[0].document_id,
    );
  }, [documents]);

  // Reset cache when switching sessions to avoid cross-session bleed.
  useEffect(() => {
    setCache({});
    inFlight.current.clear();
  }, [sessionId]);

  const loadForDoc = useCallback(
    async (docId: string) => {
      if (!docId || cache[docId] || inFlight.current.has(docId)) return;
      inFlight.current.add(docId);
      setLoading(true);
      setError(null);
      try {
        const resp = await getSessionRedFlagsApi(sessionId, docId);
        setCache((prev) => ({ ...prev, [docId]: resp }));
      } catch (err: any) {
        setError(err?.response?.data?.detail || err?.message || "Failed to load red flag analysis");
      } finally {
        inFlight.current.delete(docId);
        setLoading(false);
      }
    },
    [sessionId, cache],
  );

  useEffect(() => {
    if (selectedDocId) loadForDoc(selectedDocId);
  }, [selectedDocId, loadForDoc]);

  const current = selectedDocId ? cache[selectedDocId] : undefined;
  const currentDoc = documents.find((d) => d.document_id === selectedDocId);
  const flags = current?.flags || [];
  const score = current?.risk_score ?? 0;
  const level = riskLevel(score);
  const companyLabel =
    current?.company_name || (currentDoc ? stripExt(currentDoc.filename) : "Company");

  return (
    <div style={{ padding: "1.5rem 2rem", maxWidth: "1280px", margin: "0 auto", width: "100%" }}>
      <div style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>Red Flag Analysis</h2>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
          Forensic risk findings per company/document. Selection is independent of Research.
        </p>
      </div>

      {documents.length === 0 ? (
        <div className="card p-6" style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
          No documents in this session yet. Upload a filing to view its red flag analysis.
        </div>
      ) : (
        <div>
          {/* Per-document tabs (dynamic for any number of documents) */}
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.5rem", flexWrap: "wrap" }}>
            {documents.map((doc) => {
              const isSelected = selectedDocId === doc.document_id;
              const label = cache[doc.document_id]?.company_name || stripExt(doc.filename);
              return (
                <button
                  key={doc.document_id}
                  data-testid={`redflag-tab-${doc.document_id}`}
                  onClick={() => setSelectedDocId(doc.document_id)}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: "6px",
                    fontSize: "0.85rem",
                    fontWeight: isSelected ? 600 : 500,
                    backgroundColor: isSelected ? "var(--brand-primary-light)" : "transparent",
                    color: isSelected ? "var(--brand-primary)" : "var(--text-secondary)",
                    border: isSelected ? "1px solid var(--brand-primary-border)" : "1px solid transparent",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {error && (
            <div style={{ padding: "0.75rem 1rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--accent-risk)", borderRadius: "8px", color: "var(--accent-risk)", marginBottom: "1.5rem", fontSize: "0.85rem" }}>
              {error}
            </div>
          )}

          {loading && !current ? (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "30vh" }}>
              <div className="animate-spin" style={{ width: "2rem", height: "2rem", border: "3px solid var(--border-subtle)", borderTopColor: "var(--brand-primary)", borderRadius: "50%" }} />
            </div>
          ) : current ? (
            <div>
              {/* Summary metadata card */}
              <div className="card p-5 mb-6" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", backgroundColor: "var(--bg-surface-alt)" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Company / Entity</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "2px" }}>{companyLabel}</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>{currentDoc ? currentDoc.filename : selectedDocId}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Risk Score</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: level.color, marginTop: "2px" }}>{score.toFixed(0)} / 100</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Finding Count</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "2px" }}>{current.total_flags ?? flags.length}</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>{current.high_severity_count ?? 0} high severity</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Risk Level</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: level.color, marginTop: "2px" }}>{level.label}</div>
                </div>
              </div>

              {/* Verified findings */}
              <div className="card p-5">
                <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
                  Verified Red Flags ({flags.length})
                </h3>
                {flags.length === 0 ? (
                  <div style={{ padding: "1.25rem", textAlign: "center", color: "var(--text-secondary)", backgroundColor: "rgba(16,185,129,0.08)", borderRadius: "8px" }}>
                    No red flags detected for this document. {current.overall_assessment || ""}
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    {flags.map((f, idx) => {
                      const badge = severityStyle(f.severity);
                      return (
                        <div key={idx} style={{ border: "1px solid var(--border-subtle)", borderRadius: "8px", padding: "0.875rem 1rem", backgroundColor: "var(--bg-surface)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.375rem" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                              <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>{f.title}</span>
                              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", backgroundColor: "var(--bg-surface-alt)", padding: "2px 6px", borderRadius: "4px" }}>{f.category}</span>
                            </div>
                            <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.2rem 0.55rem", borderRadius: "9999px", backgroundColor: badge.bg, color: badge.color }}>
                              {(f.severity || "").toUpperCase()}
                            </span>
                          </div>
                          {f.description && (
                            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.4rem" }}>{f.description}</p>
                          )}
                          {f.evidence_snippet && (
                            <div style={{ padding: "0.5rem 0.6rem", backgroundColor: "var(--bg-surface-alt)", borderRadius: "6px", fontFamily: "monospace", fontSize: "0.75rem", color: "var(--text-primary)", marginBottom: "0.4rem" }}>
                              "{f.evidence_snippet}"
                            </div>
                          )}
                          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                            {f.document_filename && <span>Source: {f.document_filename}</span>}
                            {f.page_number != null && <span>Page {f.page_number}</span>}
                            {f.section && <span>Section: {f.section}</span>}
                          </div>
                          {f.recommendation && (
                            <p style={{ fontSize: "0.75rem", color: "#F59E0B", marginTop: "0.4rem" }}>Action: {f.recommendation}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="card p-6" style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-secondary)" }}>
              No red flag analysis available for this document yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
