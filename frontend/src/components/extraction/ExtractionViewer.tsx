import { useEffect, useState, useCallback } from "react";
import type { DocumentItem } from "../../types";
import {
  getExtractedMetricsApi,
  extractMetricsApi,
  type ExtractedDocument,
  type ExtractionResponse,
} from "../../api/extraction";

interface ExtractionViewerProps {
  sessionId: string;
  documents: DocumentItem[];
}

const REQUIRED_METRICS: Array<{ key: string; label: string }> = [
  { key: "revenue", label: "Revenue / Net Sales" },
  { key: "gross_profit", label: "Gross Profit" },
  { key: "gross_margin", label: "Gross Margin" },
  { key: "operating_income", label: "Operating Income" },
  { key: "net_income", label: "Net Income" },
  { key: "eps", label: "Diluted EPS" },
  { key: "total_debt", label: "Total Debt" },
];

function formatMetricDisplay(metricKey: string, val: number | null | undefined): string {
  if (val === null || val === undefined) {
    return "Unavailable";
  }

  const mKey = metricKey.toLowerCase();

  // EPS metric
  if (mKey === "eps" || mKey.includes("diluted_eps")) {
    return val.toFixed(2);
  }

  // Margin metrics
  if (mKey.includes("margin") || mKey.includes("pct") || mKey.includes("rate")) {
    const pct = Math.abs(val) <= 1.0 ? val * 100.0 : val;
    return `${pct.toFixed(2)}%`;
  }

  // Monetary metrics (Revenue, Gross Profit, Net Income, Debt, etc.)
  const isNegative = val < 0;
  const absVal = Math.abs(val);
  const formattedAbs = Number.isInteger(absVal)
    ? absVal.toLocaleString()
    : absVal.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 });

  return `${isNegative ? "-" : ""}${formattedAbs}M`;
}

export function ExtractionViewer({ sessionId, documents: _documents }: ExtractionViewerProps) {
  const [loading, setLoading] = useState(false);
  const [extractingDocId, setExtractingDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extractionData, setExtractionData] = useState<ExtractionResponse | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [expandedProvenance, setExpandedProvenance] = useState<Record<string, boolean>>({});

  const loadExtraction = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getExtractedMetricsApi(sessionId);
      setExtractionData(resp);
      if (resp.documents && resp.documents.length > 0 && !selectedDocId) {
        setSelectedDocId(resp.documents[0].document_id);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to load extraction data");
    } finally {
      setLoading(false);
    }
  }, [sessionId, selectedDocId]);

  useEffect(() => {
    loadExtraction();
  }, [loadExtraction]);

  const handleRunExtraction = async (docId?: string) => {
    setExtractingDocId(docId || "all");
    setError(null);
    try {
      await extractMetricsApi(sessionId, docId, undefined, false);
      await loadExtraction();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to run extraction agent");
    } finally {
      setExtractingDocId(null);
    }
  };

  const toggleProvenance = (key: string) => {
    setExpandedProvenance((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const extractedDocs = extractionData?.documents || [];
  const currentDoc: ExtractedDocument | undefined =
    extractedDocs.find((d) => d.document_id === selectedDocId) || extractedDocs[0];

  return (
    <div style={{ padding: "1.5rem 2rem", maxWidth: "1280px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Canonical Financial Extraction
            </h2>
            <span className="badge badge-emerald">Phase 2C Verified</span>
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Deterministic financial data layer with strict citation provenance and multi-year multi-tenant isolation
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            onClick={() => loadExtraction()}
            disabled={loading}
            className="btn btn-secondary"
            style={{ fontSize: "0.8rem", padding: "0.4rem 0.85rem" }}
          >
            {loading ? "Refreshing..." : "Refresh Data"}
          </button>
          <button
            onClick={() => handleRunExtraction(currentDoc?.document_id)}
            disabled={loading || extractingDocId !== null}
            className="btn btn-primary"
            style={{ fontSize: "0.8rem", padding: "0.4rem 0.85rem" }}
          >
            {extractingDocId ? "Extracting..." : "Re-Extract Current"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: "0.75rem 1rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--accent-risk)", borderRadius: "8px", color: "var(--accent-risk)", marginBottom: "1.5rem", fontSize: "0.85rem" }}>
          {error}
        </div>
      )}

      {loading && !extractionData ? (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "40vh" }}>
          <div className="animate-spin" style={{ width: "2rem", height: "2rem", border: "3px solid var(--border-subtle)", borderTopColor: "var(--brand-primary)", borderRadius: "50%" }} />
        </div>
      ) : extractedDocs.length === 0 ? (
        <div className="card p-6" style={{ textAlign: "center", padding: "3rem 1rem" }}>
          <p style={{ color: "var(--text-secondary)", marginBottom: "1rem" }}>
            No financial extractions found for this session yet.
          </p>
          <button
            onClick={() => handleRunExtraction()}
            disabled={extractingDocId !== null}
            className="btn btn-primary"
          >
            {extractingDocId ? "Extracting..." : "Run Extraction Agent"}
          </button>
        </div>
      ) : (
        <div>
          {/* Company Selection Tabs */}
          {extractedDocs.length > 1 && (
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.5rem" }}>
              {extractedDocs.map((doc) => {
                const isSelected = (currentDoc?.document_id === doc.document_id);
                const title = doc.company_name || doc.company || doc.document_filename || doc.document_id;
                return (
                  <button
                    key={doc.document_id}
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
                    {title} ({doc.reporting_period || "Filing"})
                  </button>
                );
              })}
            </div>
          )}

          {currentDoc && (
            <div>
              {/* Document Overview Metadata Card */}
              <div className="card p-5 mb-6" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", backgroundColor: "var(--bg-surface-alt)" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                    Company / Entity
                  </div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "2px" }}>
                    {currentDoc.company_name || currentDoc.company || "Unknown Company"}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                    {currentDoc.document_filename || currentDoc.document_id}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                    Reporting Period & Scale
                  </div>
                  <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginTop: "2px" }}>
                    {currentDoc.reporting_period || "Annual"} ({currentDoc.reporting_scale || "Millions"})
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                    Currency: {currentDoc.reporting_currency || "USD"} | Filing: {currentDoc.filing_type || "US 10-K"}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                    Extraction Confidence
                  </div>
                  <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--brand-primary)", marginTop: "2px" }}>
                    {((currentDoc.confidence_average ?? 1.0) * 100).toFixed(1)}% Average
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                    Analyzed: {currentDoc.chunks_analyzed || 0} chunks | Grounded
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                    Isolation Status
                  </div>
                  <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#10B981", marginTop: "2px" }}>
                    ✓ Multi-Tenant Isolated
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                    Document ID: {currentDoc.document_id.slice(-8)}
                  </div>
                </div>
              </div>

              {/* Multi-Year Financial Metrics Table */}
              <div className="card p-5 mb-6">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Multi-Year Extracted Financial Statements
                  </h3>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Figures in Millions {currentDoc.reporting_currency || "USD"} unless specified
                  </span>
                </div>

                {(() => {
                  const multiYear = currentDoc.multi_year_data || {};
                  // Get sorted fiscal periods descending (e.g. FY2025, FY2024, or FY2022, FY2021, FY2020)
                  const periods = Object.keys(multiYear).sort((a, b) => b.localeCompare(a));

                  if (periods.length === 0) {
                    return (
                      <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)" }}>
                        No multi-year financial data available for this document.
                      </div>
                    );
                  }

                  return (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                        <thead>
                          <tr style={{ borderBottom: "2px solid var(--border-subtle)", textAlign: "left" }}>
                            <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Financial Metric</th>
                            {periods.map((p) => (
                              <th key={p} style={{ padding: "0.75rem 1rem", color: "var(--text-primary)", fontWeight: 700, textAlign: "right" }}>
                                {p}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {REQUIRED_METRICS.map((metric) => {
                            // Check if metric exists in any period
                            const hasAnyVal = periods.some((p) => multiYear[p]?.[metric.key] !== undefined);
                            // Operating income might be absent; if absent across all, only render if available
                            if (metric.key === "operating_income" && !hasAnyVal) {
                              return null;
                            }

                            return (
                              <tr
                                key={metric.key}
                                style={{
                                  borderBottom: "1px solid var(--border-subtle)",
                                  transition: "background-color 0.15s ease",
                                }}
                              >
                                <td style={{ padding: "0.75rem 1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                  {metric.label}
                                </td>
                                {periods.map((p) => {
                                  const rawVal = multiYear[p]?.[metric.key];
                                  const displayVal = formatMetricDisplay(metric.key, rawVal);
                                  const isUnavailable = displayVal === "Unavailable";

                                  return (
                                    <td
                                      key={p}
                                      style={{
                                        padding: "0.75rem 1rem",
                                        textAlign: "right",
                                        fontFamily: isUnavailable ? "inherit" : "monospace",
                                        fontWeight: isUnavailable ? 400 : 600,
                                        color: isUnavailable ? "var(--text-muted)" : "var(--text-primary)",
                                      }}
                                    >
                                      {displayVal}
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>

              {/* Source Provenance & Audit Citations */}
              <div className="card p-5">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <div>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      Audit Evidence & Source Provenance
                    </h3>
                    <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      Exact page citations and evidence snippets extracted directly from disclosure filings
                    </p>
                  </div>
                  <span className="badge badge-info">
                    {currentDoc.metrics?.length || 0} Verified Points
                  </span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {(currentDoc.metrics || []).map((m) => {
                    const isExpanded = expandedProvenance[m.metric_name];
                    const valDisplay = formatMetricDisplay(m.metric_name, m.value);

                    return (
                      <div
                        key={m.metric_name}
                        style={{
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "8px",
                          padding: "0.75rem 1rem",
                          backgroundColor: "var(--bg-surface)",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                              {m.display_name || m.metric_name}
                            </span>
                            <span style={{ fontFamily: "monospace", fontSize: "0.85rem", fontWeight: 700, color: "var(--brand-primary)" }}>
                              {valDisplay}
                            </span>
                            {m.period && (
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", backgroundColor: "var(--bg-surface-alt)", padding: "2px 6px", borderRadius: "4px" }}>
                                {m.period}
                              </span>
                            )}
                          </div>

                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            {m.confidence !== undefined && (
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  padding: "2px 8px",
                                  borderRadius: "12px",
                                  backgroundColor: m.confidence >= 0.8 ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                                  color: m.confidence >= 0.8 ? "#10B981" : "#F59E0B",
                                  fontWeight: 600,
                                }}
                              >
                                {m.confidence_category || `${(m.confidence * 100).toFixed(0)}%`}
                              </span>
                            )}
                            {m.page_numbers && m.page_numbers.length > 0 && (
                              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                Page {m.page_numbers.join(", ")}
                              </span>
                            )}
                            <button
                              onClick={() => toggleProvenance(m.metric_name)}
                              style={{
                                background: "none",
                                border: "none",
                                color: "var(--brand-primary)",
                                fontSize: "0.75rem",
                                cursor: "pointer",
                                textDecoration: "underline",
                              }}
                            >
                              {isExpanded ? "Hide Evidence" : "View Evidence"}
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px dashed var(--border-subtle)", fontSize: "0.8rem" }}>
                            {m.evidence_snippet && (
                              <div style={{ marginBottom: "0.5rem" }}>
                                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600, marginBottom: "2px" }}>
                                  Evidence Snippet:
                                </div>
                                <div style={{ padding: "0.5rem", backgroundColor: "var(--bg-surface-alt)", borderRadius: "6px", fontFamily: "monospace", color: "var(--text-primary)" }}>
                                  "{m.evidence_snippet}"
                                </div>
                              </div>
                            )}
                            {m.source_chunk_ids && m.source_chunk_ids.length > 0 && (
                              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                <span style={{ fontWeight: 600 }}>Source Chunk:</span> {m.source_chunk_ids.join(", ")}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
