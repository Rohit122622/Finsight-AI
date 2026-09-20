import { useEffect, useState } from "react";
import type { DocumentItem } from "../../types";
import {
  compareCompaniesApi,
  getComparisonResultApi,
  downloadComparisonPdfApi,
  downloadComparisonLockedPdfApi,
  revealComparisonPasswordApi,
  retryComparisonEmailApi,
  type ComparisonResponse,
  type ComparisonMetric,
  type MetricValue,
  type ComparisonOutput,
} from "../../api/comparison";
import { LockedPdfPanel } from "../common/LockedPdfPanel";

interface CompanyComparisonViewerProps {
  sessionId: string;
  documents: DocumentItem[];
}

function formatComparisonValue(
  metricName: string,
  valObj: MetricValue | null | undefined,
): string {
  if (!valObj || !valObj.available || valObj.value === null || valObj.value === undefined) {
    return "Not Available";
  }

  const val = valObj.value;
  const mLower = metricName.toLowerCase();

  // Explicit genuine zero
  if (val === 0) {
    if (mLower.includes("margin") || mLower.includes("pct") || mLower.includes("percent") || mLower.includes("growth")) {
      return "0.0%";
    }
    return "0.0";
  }

  // Percentage & Margin metrics
  if (mLower.includes("margin") || mLower.includes("pct") || mLower.includes("percent") || mLower.includes("growth") || mLower.includes("yoy")) {
    const pct = Math.abs(val) <= 1.0 ? val * 100.0 : val;
    return `${pct.toFixed(2)}%`;
  }

  // Ratio metrics (e.g. debt-to-equity)
  if (mLower.includes("ratio") || mLower.includes("debt_to_equity")) {
    return `${val.toFixed(2)}x`;
  }

  // EPS
  if (mLower === "eps" || mLower.includes("earnings_per_share")) {
    return `$${val.toFixed(2)}`;
  }

  // Currency amounts (Revenue, Net Income, Debt, Cash, etc.)
  const unit = valObj.unit || valObj.currency || "";
  const unitLower = unit.toLowerCase();

  if (unitLower.includes("million")) {
    const numStr = Number.isInteger(val) ? val.toLocaleString() : val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    return `$${numStr}M`;
  } else if (unitLower.includes("crore")) {
    const numStr = Number.isInteger(val) ? val.toLocaleString() : val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    return `₹${numStr} Cr`;
  } else if (unitLower.includes("thousand")) {
    const numStr = Number.isInteger(val) ? val.toLocaleString() : val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    return `$${numStr}K`;
  }

  if (Math.abs(val) >= 1_000_000_000) {
    return `$${(val / 1_000_000_000).toFixed(2)}B`;
  } else if (Math.abs(val) >= 1_000_000) {
    return `$${(val / 1_000_000).toFixed(1)}M`;
  } else if (Math.abs(val) >= 1_000) {
    return `$${val.toLocaleString()}`;
  }
  return `$${val.toFixed(2)}`;
}

export function CompanyComparisonViewer({
  sessionId,
  documents,
}: CompanyComparisonViewerProps) {
  const processedDocs = documents.filter(
    (d) => d.status === "PROCESSED",
  );

  const [selectedDocIds, setSelectedDocIds] = useState<string[]>(
    processedDocs.map((d) => d.document_id),
  );
  const [loading, setLoading] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingLocked, setDownloadingLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [comparisonData, setComparisonData] = useState<ComparisonResponse | null>(null);

  // Sync selectedDocIds when documents change if empty
  useEffect(() => {
    if (selectedDocIds.length === 0 && processedDocs.length >= 2) {
      setSelectedDocIds(processedDocs.map((d) => d.document_id));
    }
  }, [processedDocs, selectedDocIds.length]);

  // Load existing comparison on mount
  useEffect(() => {
    let isMounted = true;
    async function loadExisting() {
      try {
        const res = await getComparisonResultApi(sessionId);
        if (isMounted && res && res.comparison && res.status !== "NOT_RUN") {
          setComparisonData(res);
        }
      } catch {
        // silent fallback if none exists yet
      }
    }
    if (sessionId) {
      loadExisting();
    }
    return () => {
      isMounted = false;
    };
  }, [sessionId]);

  const handleToggleDoc = (docId: string) => {
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    );
  };

  const handleRunComparison = async () => {
    if (selectedDocIds.length < 2) {
      setError("Please select at least 2 company documents to compare.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await compareCompaniesApi(sessionId, selectedDocIds, false);
      setComparisonData(res);
    } catch (err: unknown) {
      console.error("Comparison execution error:", err);
      const errMsg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : "Failed to generate comparison. Please ensure documents have extracted metrics.";
      setError(errMsg || "Comparison failed.");
    } finally {
      setLoading(false);
    }
  };

  const triggerBlobDownload = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  // Normal download → UNLOCKED PDF (decrypted server-side).
  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    setDownloadError(null);
    try {
      const blob = await downloadComparisonPdfApi(sessionId);
      triggerBlobDownload(blob, `FinSentry_Comparison_${sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error("Download comparison PDF error:", err);
      setDownloadError("Failed to download Comparison PDF. Please ensure comparison has been run.");
    } finally {
      setDownloadingPdf(false);
    }
  };

  // Locked download → password-protected AES-256 PDF (encrypted bytes; matches email).
  const handleDownloadLockedPdf = async () => {
    setDownloadingLocked(true);
    setDownloadError(null);
    try {
      const blob = await downloadComparisonLockedPdfApi(sessionId);
      triggerBlobDownload(blob, `FinSentry_Comparison_LOCKED_${sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error("Download locked comparison PDF error:", err);
      setDownloadError("Failed to download the locked Comparison PDF.");
    } finally {
      setDownloadingLocked(false);
    }
  };

  const comparison: ComparisonOutput | null =
    comparisonData?.comparison ||
    (comparisonData && "metrics" in (comparisonData as unknown as Record<string, unknown>)
      ? (comparisonData as unknown as ComparisonOutput)
      : null);
  const companies = comparison?.companies || [];
  const metrics: ComparisonMetric[] = comparison?.metrics || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header & Controls Card */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-text-primary)", marginBottom: "0.25rem" }}>
              Comparative Financial Audit
            </h2>
            <p style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
              Side-by-side metric benchmarking and peer percentile statistics across company filings in this session.
            </p>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            disabled={loading || selectedDocIds.length < 2 || processedDocs.length < 2}
            onClick={handleRunComparison}
            style={{
              padding: "0.5rem 1.25rem",
              fontSize: "0.875rem",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            {loading ? (
              <>
                <div
                  className="spinner"
                  style={{
                    width: "14px",
                    height: "14px",
                    borderWidth: "2px",
                  }}
                />
                <span>Comparing...</span>
              </>
            ) : (
              <>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 20V10" />
                  <path d="M12 20V4" />
                  <path d="M6 20v-6" />
                </svg>
                <span>Compare Selected Companies</span>
              </>
            )}
          </button>
        </div>

        {/* Company Document Selector */}
        <div>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: "0.5rem" }}>
            Select Companies for Comparison ({selectedDocIds.length} of {processedDocs.length} selected):
          </span>

          {processedDocs.length < 2 ? (
            <div
              style={{
                padding: "0.875rem 1rem",
                borderRadius: "0.5rem",
                backgroundColor: "var(--color-bg-surface-alt)",
                border: "1px dashed var(--color-border-subtle)",
                color: "var(--color-text-secondary)",
                fontSize: "0.8125rem",
              }}
            >
              Comparison requires at least two processed company filings. Upload an additional company 10-K or annual report to enable peer benchmarking.
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
              {processedDocs.map((doc) => {
                const isSelected = selectedDocIds.includes(doc.document_id);
                const displayName = doc.company_name || doc.filename.replace(/\.[^/.]+$/, "");
                return (
                  <button
                    key={doc.document_id}
                    type="button"
                    onClick={() => handleToggleDoc(doc.document_id)}
                    style={{
                      padding: "0.375rem 0.75rem",
                      borderRadius: "0.375rem",
                      border: isSelected
                        ? "1px solid var(--color-brand-500, #10b981)"
                        : "1px solid var(--color-border-subtle)",
                      backgroundColor: isSelected
                        ? "rgba(16, 185, 129, 0.12)"
                        : "var(--color-bg-surface-alt)",
                      color: isSelected
                        ? "var(--color-brand-500, #10b981)"
                        : "var(--color-text-primary)",
                      fontSize: "0.8125rem",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.375rem",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <span>{isSelected ? "✓" : "+"}</span>
                    <strong>{displayName}</strong>
                    <span style={{ fontSize: "0.6875rem", opacity: 0.8 }}>({doc.fiscal_year || "Latest"})</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {error && (
          <div style={{ marginTop: "1rem", padding: "0.75rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--color-risk-500)", borderRadius: "0.375rem", color: "var(--color-risk-500)", fontSize: "0.8125rem" }}>
            {error}
          </div>
        )}
      </div>

      {/* Comparison Results Card */}
      {comparison && companies.length > 0 && metrics.length > 0 && (
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--color-text-primary)", margin: 0 }}>
                Side-by-Side Financial Benchmark ({companies.length} Companies, {metrics.length} Metrics)
              </h3>
              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginTop: "0.25rem", fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                {comparison.common_periods && comparison.common_periods.length > 0 ? (
                  <span>
                    <strong>Common Periods:</strong> {comparison.common_periods.join(", ")}
                  </span>
                ) : (
                  <span style={{ color: "var(--color-amber-600, #d97706)" }}>
                    <strong>Common Periods:</strong> None
                  </span>
                )}
                {comparison.company_only_periods && Object.keys(comparison.company_only_periods).length > 0 && (
                  <span>
                    <strong>Company-Specific:</strong>{" "}
                    {Object.entries(comparison.company_only_periods)
                      .map(([c, pers]) => `${c} (${pers.join(", ")})`)
                      .join("; ")}
                  </span>
                )}
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={downloadingPdf}
                onClick={handleDownloadPdf}
                style={{
                  padding: "0.4rem 0.875rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  gap: "0.375rem",
                }}
              >
                {downloadingPdf ? (
                  <>
                    <div className="spinner" style={{ width: "12px", height: "12px", borderWidth: "2px" }} />
                    <span>Preparing PDF...</span>
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    <span>Download Comparison PDF</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Fiscal Period Alignment Notice (if no common periods) */}
          {(!comparison.has_common_periods || (comparison.common_periods && comparison.common_periods.length === 0)) && (
            <div
              style={{
                marginBottom: "1rem",
                padding: "0.75rem 1rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(245, 158, 11, 0.08)",
                border: "1px solid var(--color-amber-500, #f59e0b)",
                color: "var(--color-text-primary)",
                fontSize: "0.8125rem",
                lineHeight: 1.5,
              }}
            >
              <strong>Notice on Fiscal Period Alignment:</strong>{" "}
              {comparison.comparison_note ||
                "No common fiscal reporting periods are available across the selected companies. Individual company financial data is shown for reference; peer-relative statistics (Peer Average, Highest/Lowest, Percentiles) are unavailable."}
            </div>
          )}

          {downloadError && (
            <div style={{ marginBottom: "1rem", padding: "0.625rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--color-risk-500)", borderRadius: "0.375rem", color: "var(--color-risk-500)", fontSize: "0.8125rem" }}>
              {downloadError}
            </div>
          )}

          {/* Locked (encrypted) PDF controls: password reveal/copy, download, email status */}
          {comparison && (
            <LockedPdfPanel
              title="Comparison PDF"
              locked={true}
              passwordAvailable={comparisonData?.password_available ?? true}
              emailStatus={comparisonData?.email_status ?? null}
              downloading={downloadingLocked}
              onDownload={handleDownloadLockedPdf}
              onRevealPassword={async () => (await revealComparisonPasswordApi(sessionId)).password}
              onRetryEmail={async () => {
                await retryComparisonEmailApi(sessionId);
              }}
              onRefreshStatus={async () => (await getComparisonResultApi(sessionId)).email_status ?? null}
            />
          )}

          {/* Side-by-Side Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--color-border-subtle)", textAlign: "left" }}>
                  <th style={{ padding: "0.75rem 1rem", color: "var(--color-text-secondary)", fontWeight: 600 }}>Metric</th>
                  <th style={{ padding: "0.75rem 1rem", color: "var(--color-text-secondary)", fontWeight: 600 }}>Period</th>
                  {companies.map((c) => (
                    <th key={c.document_id || c.company_name} style={{ padding: "0.75rem 1rem", color: "var(--color-text-primary)", fontWeight: 700 }}>
                      <div>{c.company_name}</div>
                      {c.filing_type && (
                        <div style={{ fontSize: "0.6875rem", fontWeight: 400, color: "var(--color-text-secondary)" }}>
                          {c.filing_type}
                        </div>
                      )}
                    </th>
                  ))}
                  <th style={{ padding: "0.75rem 1rem", color: "var(--color-text-secondary)", fontWeight: 600 }}>Peer Stats</th>
                </tr>
              </thead>
              <tbody>
                {metrics.flatMap((m) => {
                  const metricLabel = m.display_name || m.metric_name.replace(/_/g, " ").toUpperCase();
                  const periods = m.periods && m.periods.length > 0 ? m.periods : [];

                  return periods.map((periodData, pIdx) => {
                    const periodName = periodData.fiscal_period;
                    const stats = periodData.peer_statistics;
                    const validCount = stats?.valid_count ?? 0;
                    const hasPeerStats = validCount >= 2 && stats?.peer_average !== null && stats?.peer_average !== undefined;
                    const valList = periodData.values || [];
                    const valMap = new Map<string, MetricValue>();
                    valList.forEach((v) => {
                      if (v.company_name) valMap.set(v.company_name, v);
                      if (v.document_id) valMap.set(v.document_id, v);
                    });

                    const peerAvgFormatted = hasPeerStats
                      ? formatComparisonValue(m.metric_name, {
                          document_id: "",
                          company_name: "Peer Average",
                          fiscal_period: periodName,
                          value: stats.peer_average,
                          available: true,
                        })
                      : "—";

                    const highestCompany = hasPeerStats ? (stats?.highest?.company_name || stats?.highest?.company) : null;
                    const highestVal = hasPeerStats ? stats?.highest?.value : undefined;
                    const lowestCompany = hasPeerStats ? (stats?.lowest?.company_name || stats?.lowest?.company) : null;
                    const lowestVal = hasPeerStats ? stats?.lowest?.value : undefined;

                    return (
                      <tr
                        key={`${m.metric_name}-${periodName}-${pIdx}`}
                        style={{
                          borderBottom: "1px solid var(--color-border-subtle)",
                          backgroundColor: pIdx % 2 === 1 ? "var(--color-bg-surface-alt)" : "transparent",
                        }}
                      >
                        <td style={{ padding: "0.75rem 1rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
                          {metricLabel}
                        </td>
                        <td style={{ padding: "0.75rem 1rem", color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                          {periodName}
                        </td>
                        {companies.map((c) => {
                          const valObj = valMap.get(c.company_name) || valMap.get(c.document_id);
                          const isAvail = valObj && valObj.available && valObj.value !== null && valObj.value !== undefined;
                          const formatted = formatComparisonValue(m.metric_name, valObj);

                          const pRankEntry = stats?.percentile_ranks?.find(
                            (pr) => pr.company_name === c.company_name || pr.document_id === c.document_id,
                          );
                          const rankPct =
                            pRankEntry && pRankEntry.percentile !== null && pRankEntry.percentile !== undefined
                              ? Math.round(pRankEntry.percentile * 100)
                              : null;

                          return (
                            <td
                              key={c.document_id || c.company_name}
                              style={{
                                padding: "0.75rem 1rem",
                                fontVariantNumeric: "tabular-nums",
                                fontWeight: isAvail ? 600 : 400,
                                color: isAvail ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                              }}
                            >
                              {isAvail ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                                  <div style={{ fontSize: "0.875rem", fontWeight: 600 }}>{formatted}</div>
                                  {rankPct !== null && (
                                    <div>
                                      <span
                                        style={{
                                          fontSize: "0.6875rem",
                                          padding: "0.15rem 0.375rem",
                                          borderRadius: "4px",
                                          backgroundColor: rankPct >= 50 ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                                          color: rankPct >= 50 ? "var(--color-emerald-500, #10b981)" : "var(--color-amber-500, #f59e0b)",
                                          fontWeight: 700,
                                          display: "inline-block",
                                        }}
                                        title={`Peer percentile rank: ${rankPct}%`}
                                      >
                                        Percentile: {rankPct}
                                      </span>
                                    </div>
                                  )}
                                  {valObj?.provenance?.page_number && (
                                    <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)", display: "block" }}>
                                      p. {valObj.provenance.page_number}
                                    </span>
                                  )}
                                </div>
                              ) : (
                                <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", fontStyle: "italic" }}>
                                  Not Available
                                </span>
                              )}
                            </td>
                          );
                        })}
                        <td style={{ padding: "0.75rem 1rem", fontSize: "0.75rem" }}>
                          {hasPeerStats ? (
                            <>
                              <div style={{ color: "var(--color-brand-500, #10b981)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                                Avg: {peerAvgFormatted}
                              </div>
                              {highestCompany && highestVal !== undefined && (
                                <div style={{ color: "var(--color-text-secondary)", fontSize: "0.6875rem" }}>
                                  High: {highestCompany} ({formatComparisonValue(m.metric_name, { document_id: "", company_name: highestCompany, fiscal_period: periodName, value: highestVal, available: true })})
                                </div>
                              )}
                              {lowestCompany && lowestVal !== undefined && (
                                <div style={{ color: "var(--color-text-secondary)", fontSize: "0.6875rem" }}>
                                  Low: {lowestCompany} ({formatComparisonValue(m.metric_name, { document_id: "", company_name: lowestCompany, fiscal_period: periodName, value: lowestVal, available: true })})
                                </div>
                              )}
                            </>
                          ) : (
                            <span style={{ color: "var(--color-text-secondary)", fontStyle: "italic" }}>
                              {validCount === 1 ? "Unavailable (1 company)" : "Unavailable (0 data)"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  });
                })}
              </tbody>
            </table>
          </div>

          {/* Summary Insights */}
          {comparison.summary_insights && comparison.summary_insights.length > 0 && (
            <div style={{ marginTop: "1.5rem", padding: "1rem", backgroundColor: "var(--color-bg-surface-alt)", borderRadius: "0.5rem", borderLeft: "3px solid var(--color-brand-500, #10b981)" }}>
              <h4 style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--color-text-primary)", marginBottom: "0.5rem" }}>
                Key Comparison Takeaways
              </h4>
              <ul style={{ margin: 0, paddingLeft: "1.25rem", fontSize: "0.8125rem", color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
                {comparison.summary_insights.map((insight, idx) => (
                  <li key={idx}>{insight}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
