




import { useState } from "react";
import type { AnalysisReport } from "../types";
import { downloadReportPdfApi, downloadReportLockedPdfApi, revealReportPasswordApi, retryReportEmailApi, listReportsApi } from "../api/analysis";
import { LockedPdfPanel } from "./common/LockedPdfPanel";

interface AnalysisReportViewerProps {
  reports: AnalysisReport[];
  isLoading: boolean;
}

export function AnalysisReportViewer({ reports, isLoading }: AnalysisReportViewerProps) {
  const [selectedReportId, setSelectedReportId] = useState<string | null>(
    reports.length > 0 ? reports[0].report_id : null,
  );
  const [isDownloading, setIsDownloading] = useState(false);
  const [isDownloadingLocked, setIsDownloadingLocked] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const activeReport =
    reports.find((r) => r.report_id === selectedReportId) || (reports.length > 0 ? reports[0] : null);

  const handleDownload = async () => {
    if (!activeReport) return;
    setIsDownloading(true);
    setDownloadError(null);
    try {
      const blob = await downloadReportPdfApi(activeReport.session_id, activeReport.report_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `FinSentry_Report_${activeReport.session_id.slice(0, 8)}_${activeReport.report_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      console.error("Failed to download report PDF:", err);
      if (activeReport.download_url && activeReport.download_url.startsWith("http")) {
        window.open(activeReport.download_url, "_blank");
      } else {
        setDownloadError("Failed to download PDF. Please try again.");
      }
    } finally {
      setIsDownloading(false);
    }
  };

  // Locked download → password-protected AES-256 PDF (encrypted bytes; matches email).
  const handleDownloadLocked = async () => {
    if (!activeReport) return;
    setIsDownloadingLocked(true);
    setDownloadError(null);
    try {
      const blob = await downloadReportLockedPdfApi(activeReport.session_id, activeReport.report_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `FinSentry_Report_LOCKED_${activeReport.session_id.slice(0, 8)}_${activeReport.report_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error("Failed to download locked report PDF:", err);
      setDownloadError("Failed to download the locked Report PDF.");
    } finally {
      setIsDownloadingLocked(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
      case "HIGH":
        return { bg: "rgba(239, 68, 68, 0.15)", color: "var(--color-risk-500)" };
      case "MEDIUM":
        return { bg: "rgba(245, 158, 11, 0.15)", color: "var(--color-amber-500)" };
      default:
        return { bg: "rgba(16, 185, 129, 0.15)", color: "var(--color-emerald-500)" };
    }
  };

  if (isLoading) {
    return (
      <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>Loading research reports...</p>
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
          No analysis reports generated yet. Run the Multi-Agent Analysis pipeline above to generate comprehensive reports.
        </p>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: "1.5rem" }}>
      {downloadError && (
        <div style={{ padding: "0.75rem", marginBottom: "1rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--color-risk-500)", borderRadius: "0.375rem", color: "var(--color-risk-500)", fontSize: "0.8125rem" }}>
          {downloadError}
        </div>
      )}

      {reports.length > 1 && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", overflowX: "auto" }}>
          {reports.map((r, idx) => (
            <button
              key={r.report_id}
              onClick={() => setSelectedReportId(r.report_id)}
              className={activeReport?.report_id === r.report_id ? "btn btn-primary" : "btn btn-secondary"}
              style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}
            >
              Report #{reports.length - idx} ({new Date(r.created_at).toLocaleTimeString()})
            </button>
          ))}
        </div>
      )}

      {activeReport && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--color-text-primary)" }}>
                {activeReport.report_title}
              </h2>
              <span className="font-tabular" style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                Generated {new Date(activeReport.created_at).toLocaleString()}
              </span>
            </div>

            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={isDownloading}
                style={{
                  fontSize: "0.75rem",
                  padding: "0.5rem 0.875rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.375rem",
                  color: "var(--color-brand-500, #10b981)",
                  borderColor: "var(--color-border-subtle)",
                }}
                onClick={handleDownload}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                <span>{isDownloading ? "Downloading..." : "Download PDF"}</span>
              </button>

              <div
                style={{
                  textAlign: "right",
                  padding: "0.5rem 1rem",
                  borderRadius: "0.5rem",
                backgroundColor: "var(--color-bg-surface-alt)",
                border: "1px solid var(--color-border-subtle)",
              }}
            >
              <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)", display: "block" }}>
                Composite Risk Score
              </span>
              <strong
                className="font-tabular"
                style={{
                  fontSize: "1.25rem",
                  color:
                    activeReport.risk_score > 60
                      ? "var(--color-risk-500)"
                      : activeReport.risk_score > 30
                      ? "var(--color-amber-500)"
                      : "var(--color-emerald-500)",
                }}
              >
                {activeReport.risk_score} / 100
              </strong>
              </div>
            </div>
          </div>

          {/* Locked (encrypted) PDF controls: password reveal/copy, download, email status */}
          <LockedPdfPanel
            title="Report PDF"
            locked={true}
            passwordAvailable={activeReport.password_available ?? true}
            emailStatus={activeReport.email_status ?? null}
            downloading={isDownloadingLocked}
            onDownload={handleDownloadLocked}
            onRevealPassword={async () =>
              (await revealReportPasswordApi(activeReport.session_id, activeReport.report_id)).password
            }
            onRetryEmail={async () => {
              await retryReportEmailApi(activeReport.session_id, activeReport.report_id);
            }}
            onRefreshStatus={async () => {
              const { reports: latest } = await listReportsApi(activeReport.session_id);
              return latest.find((r) => r.report_id === activeReport.report_id)?.email_status ?? null;
            }}
          />

          {}
          {activeReport.executive_summary && (
            <div
              style={{
                backgroundColor: "var(--color-bg-surface-alt)",
                borderRadius: "0.5rem",
                padding: "1rem",
                marginBottom: "1.25rem",
                borderLeft: "4px solid var(--color-emerald-500)",
              }}
            >
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "0.375rem" }}>
                Executive Summary
              </h3>
              <p style={{ fontSize: "0.8125rem", color: "var(--color-text-primary)", lineHeight: 1.5 }}>
                {activeReport.executive_summary}
              </p>
            </div>
          )}

          {}
          {activeReport.red_flags && activeReport.red_flags.length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--color-risk-500)", marginBottom: "0.75rem" }}>
                Forensic Red Flags Detected ({activeReport.red_flags.length})
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {activeReport.red_flags.map((rf, idx) => {
                  const badge = getSeverityBadge(rf.severity);
                  return (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: "var(--color-bg-surface-alt)",
                        border: "1px solid var(--color-border-subtle)",
                        borderRadius: "0.5rem",
                        padding: "0.875rem",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.375rem" }}>
                        <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
                          {rf.title}
                        </span>
                        <span
                          style={{
                            fontSize: "0.6875rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.5rem",
                            borderRadius: "9999px",
                            backgroundColor: badge.bg,
                            color: badge.color,
                          }}
                        >
                          {rf.severity}
                        </span>
                      </div>
                      <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", marginBottom: "0.375rem" }}>
                        Evidence: {rf.evidence}
                      </p>
                      <p style={{ fontSize: "0.75rem", color: "var(--color-amber-500)" }}>
                        Action: {rf.recommendation}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Additional Analysis Sections (Executive Summary filtered to avoid duplication) */}
          {activeReport.sections && activeReport.sections.filter((s) => s.title !== "Executive Summary").length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              {activeReport.sections
                .filter((s) => s.title !== "Executive Summary")
                .map((sec, idx) => (
                <div key={idx} style={{ marginBottom: "1.25rem" }}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "0.375rem" }}>
                    {sec.title}
                  </h3>
                  <div style={{ fontSize: "0.8125rem", color: "var(--color-text-primary)", lineHeight: 1.6, whiteSpace: "pre-line" }}>
                    {sec.content}
                  </div>
                  {sec.key_findings && sec.key_findings.length > 0 && (
                    <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem", fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {sec.key_findings.map((kf, kidx) => (
                        <li key={kidx}>{kf}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          {}
          {activeReport.recommendations && activeReport.recommendations.length > 0 && (
            <div
              style={{
                backgroundColor: "var(--color-bg-surface-alt)",
                borderRadius: "0.5rem",
                padding: "1rem",
                border: "1px solid var(--color-border-subtle)",
              }}
            >
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--color-emerald-500)", marginBottom: "0.5rem" }}>
                Strategic Recommendations
              </h3>
              <ul style={{ paddingLeft: "1.25rem", fontSize: "0.8125rem", color: "var(--color-text-primary)", lineHeight: 1.5 }}>
                {activeReport.recommendations.map((rec, idx) => (
                  <li key={idx} style={{ marginBottom: "0.25rem" }}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
