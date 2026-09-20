import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentItem } from "../../types";
import {
  getCompanyReportApi,
  downloadCompanyReportPdfApi,
  downloadCompanyReportLockedPdfApi,
  type CompanyReportContent,
} from "../../api/analysis";

interface PerCompanyReportsProps {
  sessionId: string;
  documents: DocumentItem[];
}

function stripExt(name?: string): string {
  if (!name) return "Document";
  return name.replace(/\.[a-zA-Z0-9]+$/, "");
}

function severityStyle(sev: string): { bg: string; color: string } {
  const s = (sev || "").toUpperCase();
  if (s === "CRITICAL" || s === "HIGH") return { bg: "rgba(239, 68, 68, 0.15)", color: "var(--accent-risk, #ef4444)" };
  if (s === "MEDIUM") return { bg: "rgba(245, 158, 11, 0.15)", color: "#F59E0B" };
  return { bg: "rgba(16, 185, 129, 0.15)", color: "#10B981" };
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

/**
 * Per-company (individual, single-document) analysis reports.
 *
 * Each uploaded document is a tab. The selected company's report is compiled by the
 * backend from ONLY that document's metrics + red flags (no cross-company leakage) and
 * cached client-side. Selection state (selectedReportDocumentId) is independent of both
 * Research and the Red Flag tab. Individual downloads reuse the shared report compiler.
 */
export function PerCompanyReports({ sessionId, documents }: PerCompanyReportsProps) {
  const [selectedReportDocumentId, setSelectedReportDocumentId] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, CompanyReportContent>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadingLocked, setDownloadingLocked] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const inFlight = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (documents.length === 0) {
      setSelectedReportDocumentId(null);
      return;
    }
    setSelectedReportDocumentId((prev) =>
      prev && documents.some((d) => d.document_id === prev) ? prev : documents[0].document_id,
    );
  }, [documents]);

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
        const data = await getCompanyReportApi(sessionId, docId);
        setCache((prev) => ({ ...prev, [docId]: data }));
      } catch (err: any) {
        setError(err?.response?.data?.detail || err?.message || "Failed to load company report");
      } finally {
        inFlight.current.delete(docId);
        setLoading(false);
      }
    },
    [sessionId, cache],
  );

  useEffect(() => {
    if (selectedReportDocumentId) loadForDoc(selectedReportDocumentId);
  }, [selectedReportDocumentId, loadForDoc]);

  const currentDoc = documents.find((d) => d.document_id === selectedReportDocumentId);
  const report = selectedReportDocumentId ? cache[selectedReportDocumentId] : undefined;
  const companyLabel = report?.company_name || (currentDoc ? stripExt(currentDoc.filename) : "Company");

  const handleDownload = async (locked: boolean) => {
    if (!selectedReportDocumentId) return;
    const setter = locked ? setDownloadingLocked : setDownloading;
    setter(true);
    setDownloadError(null);
    try {
      const blob = locked
        ? await downloadCompanyReportLockedPdfApi(sessionId, selectedReportDocumentId)
        : await downloadCompanyReportPdfApi(sessionId, selectedReportDocumentId);
      const suffix = locked ? "LOCKED_" : "";
      triggerBlobDownload(blob, `FinSentry_${companyLabel.replace(/\s+/g, "")}_${suffix}Report.pdf`);
    } catch (err: any) {
      setDownloadError(
        err?.response?.data?.detail ||
          (locked
            ? "Failed to download locked report. Generate the session report first to enable locked downloads."
            : "Failed to download report."),
      );
    } finally {
      setter(false);
    }
  };

  if (documents.length === 0) return null;

  const metrics = report?.key_financials?.metrics || [];
  const periods = report?.key_financials?.reporting_periods || [];
  const findings = report?.red_flags?.findings || [];

  return (
    <div>
      <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
        Analysis Reports
      </h2>
      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
        Individual company report. Selection is independent of Research and Red Flag.
      </p>

      {/* Per-company tabs */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.5rem", flexWrap: "wrap" }}>
        {documents.map((doc) => {
          const isSelected = selectedReportDocumentId === doc.document_id;
          const label = cache[doc.document_id]?.company_name || stripExt(doc.filename);
          return (
            <button
              key={doc.document_id}
              data-testid={`report-tab-${doc.document_id}`}
              onClick={() => setSelectedReportDocumentId(doc.document_id)}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                fontSize: "0.85rem",
                fontWeight: isSelected ? 600 : 500,
                backgroundColor: isSelected ? "var(--brand-primary-light)" : "transparent",
                color: isSelected ? "var(--brand-primary)" : "var(--text-secondary)",
                border: isSelected ? "1px solid var(--brand-primary-border)" : "1px solid transparent",
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {error && (
        <div style={{ padding: "0.75rem 1rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--accent-risk)", borderRadius: "8px", color: "var(--accent-risk)", marginBottom: "1rem", fontSize: "0.85rem" }}>
          {error}
        </div>
      )}

      {loading && !report ? (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "25vh" }}>
          <div className="animate-spin" style={{ width: "2rem", height: "2rem", border: "3px solid var(--border-subtle)", borderTopColor: "var(--brand-primary)", borderRadius: "50%" }} />
        </div>
      ) : report ? (
        <div className="card p-5">
          <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
            {companyLabel} Financial Analysis Report
          </h3>

          {/* Executive Summary */}
          {report.executive_summary?.narrative && (
            <div style={{ marginBottom: "1.25rem", padding: "0.875rem 1rem", backgroundColor: "var(--bg-surface-alt)", borderLeft: "4px solid var(--brand-primary)", borderRadius: "0.375rem" }}>
              <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.375rem" }}>Executive Summary</div>
              <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{report.executive_summary.narrative}</p>
            </div>
          )}

          {/* Key Financials (this company only) */}
          {metrics.length > 0 && (
            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>Key Financials</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border-subtle)", textAlign: "left" }}>
                      <th style={{ padding: "0.5rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Metric</th>
                      {periods.map((p) => (
                        <th key={p} style={{ padding: "0.5rem 0.75rem", textAlign: "right", color: "var(--text-primary)", fontWeight: 700 }}>{p}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map((m) => (
                      <tr key={m.metric_key} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                        <td style={{ padding: "0.5rem 0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>{m.display_name}</td>
                        {periods.map((p) => {
                          const v = m.values.find((x) => x.fiscal_period === p);
                          return (
                            <td key={p} style={{ padding: "0.5rem 0.75rem", textAlign: "right", fontFamily: "monospace", color: v?.available ? "var(--text-primary)" : "var(--text-muted)" }}>
                              {v?.formatted_value || "N/A"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Red Flags (this company only) */}
          <div style={{ marginBottom: "1.25rem" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
              Red Flags ({findings.length}) — Risk Score {(report.red_flags?.composite_risk_score ?? 0).toFixed(0)}/100
            </div>
            {findings.length === 0 ? (
              <div style={{ padding: "0.75rem", color: "var(--text-secondary)", fontSize: "0.8rem", backgroundColor: "rgba(16,185,129,0.08)", borderRadius: "6px" }}>
                No red flags for this company.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {findings.map((f, idx) => {
                  const badge = severityStyle(f.severity);
                  return (
                    <div key={idx} style={{ border: "1px solid var(--border-subtle)", borderRadius: "6px", padding: "0.625rem 0.875rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.25rem" }}>
                        <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)" }}>{f.title}</span>
                        <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "0.15rem 0.5rem", borderRadius: "9999px", backgroundColor: badge.bg, color: badge.color }}>{(f.severity || "").toUpperCase()}</span>
                      </div>
                      {f.description && <p style={{ fontSize: "0.76rem", color: "var(--text-secondary)" }}>{f.description}</p>}
                      {(f.source_page != null || f.company_name) && (
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                          {f.company_name ? `${f.company_name}` : ""}{f.source_page != null ? ` · p.${f.source_page}` : ""}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {downloadError && (
            <div style={{ padding: "0.6rem 0.85rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--accent-risk)", borderRadius: "8px", color: "var(--accent-risk)", marginBottom: "0.75rem", fontSize: "0.8rem" }}>
              {downloadError}
            </div>
          )}

          {/* Individual report actions */}
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.875rem" }}>
            <button className="btn btn-secondary" disabled={downloading} onClick={() => handleDownload(false)} style={{ fontSize: "0.78rem", padding: "0.4rem 0.85rem" }}>
              {downloading ? "Downloading…" : `Download ${companyLabel} Report`}
            </button>
            <button className="btn btn-secondary" disabled={downloadingLocked} onClick={() => handleDownload(true)} style={{ fontSize: "0.78rem", padding: "0.4rem 0.85rem" }}>
              {downloadingLocked ? "Downloading…" : `Download Locked ${companyLabel} Report`}
            </button>
          </div>
        </div>
      ) : (
        <div className="card p-6" style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-secondary)" }}>
          No individual report available for this company yet.
        </div>
      )}
    </div>
  );
}
