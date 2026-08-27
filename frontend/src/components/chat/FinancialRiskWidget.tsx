












import { useEffect, useState, useCallback } from "react";
import type { ResearchResponse } from "../../types/research";
import { extractRiskInfo } from "../../services/research";
import { getSessionRedFlagsApi, type SessionRedFlagsResponse } from "../../api/analysis";

interface FinancialRiskWidgetProps {
  sessionId?: string;
  response?: ResearchResponse | null;
}

export function FinancialRiskWidget({ sessionId, response }: FinancialRiskWidgetProps) {
  const [sessionRedFlags, setSessionRedFlags] = useState<SessionRedFlagsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const loadRedFlags = useCallback(async () => {
    if (!sessionId) return;
    try {
      setIsLoading(true);
      setFetchError(null);
      const rawData: any = await getSessionRedFlagsApi(sessionId);
      if (Array.isArray(rawData)) {
        setSessionRedFlags({
          session_id: sessionId,
          status: rawData.length > 0 ? "COMPLETED_WITH_FLAGS" : "COMPLETED_NO_FLAGS",
          total_flags: rawData.length,
          high_severity_count: rawData.filter((f: any) => ["HIGH", "CRITICAL"].includes(String(f.severity).toUpperCase())).length,
          risk_score: 0.0,
          flags: rawData,
        });
      } else if (rawData && typeof rawData === "object") {
        setSessionRedFlags(rawData);
      }
    } catch {
      setFetchError("Unable to load session risk data");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadRedFlags();
  }, [loadRedFlags, response]);

  
  useEffect(() => {
    if (sessionRedFlags?.status === "RUNNING") {
      const interval = setInterval(loadRedFlags, 2500);
      return () => clearInterval(interval);
    }
  }, [sessionRedFlags?.status, loadRedFlags]);

  const getSeverityStyle = (sev: string) => {
    const upper = (sev || "MEDIUM").toUpperCase();
    switch (upper) {
      case "CRITICAL":
      case "HIGH":
        return {
          bg: "rgba(239, 68, 68, 0.12)",
          color: "var(--color-risk-500, #ef4444)",
          border: "rgba(239, 68, 68, 0.3)",
        };
      case "MEDIUM":
        return {
          bg: "rgba(245, 158, 11, 0.12)",
          color: "var(--color-amber-500, #f59e0b)",
          border: "rgba(245, 158, 11, 0.3)",
        };
      case "LOW":
      default:
        return {
          bg: "rgba(16, 185, 129, 0.12)",
          color: "var(--color-emerald-500, #10b981)",
          border: "rgba(16, 185, 129, 0.25)",
        };
    }
  };

  
  if (isLoading && !sessionRedFlags) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>
        <div
          className="animate-spin"
          style={{
            width: "1.5rem",
            height: "1.5rem",
            border: "2px solid var(--color-border-subtle)",
            borderTopColor: "var(--color-emerald-500)",
            borderRadius: "50%",
            margin: "0 auto 0.5rem",
          }}
        />
        <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
          Loading forensic risk analysis…
        </span>
      </div>
    );
  }

  
  const status = sessionRedFlags?.status || "NOT_RUN";

  
  if (status === "RUNNING") {
    return (
      <div
        style={{
          padding: "1.5rem",
          backgroundColor: "var(--color-bg-surface)",
          border: "1px solid rgba(245, 158, 11, 0.3)",
          borderRadius: "0.5rem",
          textAlign: "center",
        }}
      >
        <div
          className="animate-spin"
          style={{
            width: "2rem",
            height: "2rem",
            border: "2px solid rgba(245, 158, 11, 0.2)",
            borderTopColor: "var(--color-amber-500)",
            borderRadius: "50%",
            margin: "0 auto 0.75rem",
          }}
        />
        <h4 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--color-amber-500)", marginBottom: "0.35rem" }}>
          Risk Assessment in Progress…
        </h4>
        <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", lineHeight: 1.4 }}>
          The RedFlagAgent is scanning debt trajectories, margin compression, auditor qualifications, and SEC disclosures.
        </p>
      </div>
    );
  }

  
  if (status === "FAILED" || fetchError) {
    return (
      <div
        style={{
          padding: "1.25rem",
          backgroundColor: "rgba(239, 68, 68, 0.08)",
          border: "1px solid rgba(239, 68, 68, 0.25)",
          borderRadius: "0.5rem",
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>⚠️</div>
        <h4 style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-risk-500)", marginBottom: "0.25rem" }}>
          Risk Assessment Failed
        </h4>
        <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", marginBottom: "0.75rem" }}>
          {fetchError || sessionRedFlags?.overall_assessment || "Forensic audit encountered an error. Please retry."}
        </p>
        <button
          onClick={loadRedFlags}
          className="btn btn-secondary"
          style={{ padding: "0.25rem 0.625rem", fontSize: "0.6875rem" }}
        >
          Retry Analysis
        </button>
      </div>
    );
  }

  
  if (status === "NOT_RUN") {
    
    const responseRisk = extractRiskInfo(response);
    if (!responseRisk.hasRiskData) {
      return (
        <div
          style={{
            padding: "1.5rem",
            backgroundColor: "var(--color-bg-surface)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "0.5rem",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "50%",
              backgroundColor: "rgba(100, 116, 139, 0.15)",
              color: "var(--color-text-secondary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 0.5rem",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h4 style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "0.25rem" }}>
            Risk Assessment Not Yet Run
          </h4>
          <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", lineHeight: 1.4 }}>
            Upload financial disclosures to this session to trigger automated forensic audit analysis across solvency, profitability, and accounting disclosures.
          </p>
        </div>
      );
    }
  }

  
  if (status === "COMPLETED_NO_FLAGS") {
    return (
      <div
        style={{
          padding: "1.5rem",
          backgroundColor: "var(--color-bg-surface)",
          border: "1px solid rgba(16, 185, 129, 0.3)",
          borderRadius: "0.5rem",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            backgroundColor: "rgba(16, 185, 129, 0.12)",
            color: "var(--color-emerald-500)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 0.5rem",
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <h4 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--color-emerald-500)", marginBottom: "0.25rem" }}>
          No Material Red Flags Detected
        </h4>
        <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", lineHeight: 1.4, marginBottom: "0.75rem" }}>
          {sessionRedFlags?.overall_assessment ||
            "Forensic screening completed with zero material anomalies. Financial metrics and qualitative disclosures meet standard institutional benchmarks."}
        </p>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.25rem 0.625rem",
            backgroundColor: "var(--color-bg-surface-alt)",
            borderRadius: "12px",
            fontSize: "0.6875rem",
            color: "var(--color-text-secondary)",
          }}
        >
          <span>Risk Score:</span>
          <strong style={{ color: "var(--color-emerald-500)" }}>0.0/100 (Safe)</strong>
        </div>
      </div>
    );
  }

  
  const flags = sessionRedFlags?.flags || [];
  const riskScore = sessionRedFlags?.risk_score ?? 0.0;
  const highCount = sessionRedFlags?.high_severity_count ?? flags.filter((f) => f.severity === "HIGH").length;

  const riskLevelLabel =
    riskScore >= 50 ? "CRITICAL RISK" : riskScore >= 25 ? "HIGH RISK" : riskScore >= 10 ? "MEDIUM RISK" : "LOW RISK";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {}
      <div
        style={{
          padding: "1rem",
          backgroundColor: "var(--color-bg-surface)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "0.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <span
            style={{
              fontSize: "0.6875rem",
              color: "var(--color-text-secondary)",
              textTransform: "uppercase",
              fontWeight: 600,
              letterSpacing: "0.05em",
            }}
          >
            Forensic Risk Level
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.125rem" }}>
            <span
              style={{
                fontSize: "1rem",
                fontWeight: 700,
                color:
                  riskScore >= 25
                    ? "var(--color-risk-500, #ef4444)"
                    : riskScore >= 10
                    ? "var(--color-amber-500, #f59e0b)"
                    : "var(--color-emerald-500, #10b981)",
              }}
            >
              {riskLevelLabel}
            </span>
          </div>
          <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}>
            {flags.length} findings ({highCount} high priority)
          </span>
        </div>

        <div style={{ textAlign: "right" }}>
          <span style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)", display: "block" }}>
            Risk Score
          </span>
          <span
            className="font-tabular"
            style={{
              fontSize: "1.25rem",
              fontWeight: 700,
              color:
                riskScore >= 25
                  ? "var(--color-risk-500, #ef4444)"
                  : riskScore >= 10
                  ? "var(--color-amber-500, #f59e0b)"
                  : "var(--color-emerald-500, #10b981)",
            }}
          >
            {riskScore.toFixed(1)}/100
          </span>
        </div>
      </div>

      {}
      {sessionRedFlags?.overall_assessment && (
        <div
          style={{
            padding: "0.625rem 0.75rem",
            backgroundColor: "var(--color-bg-surface-alt)",
            borderRadius: "0.375rem",
            border: "1px solid var(--color-border-subtle)",
            fontSize: "0.75rem",
            color: "var(--color-text-secondary)",
            lineHeight: 1.4,
          }}
        >
          {sessionRedFlags.overall_assessment}
        </div>
      )}

      {}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <span
          style={{
            fontSize: "0.6875rem",
            fontWeight: 600,
            color: "var(--color-text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Verified Red Flags ({flags.length})
        </span>

        {flags.map((flag, idx) => {
          const style = getSeverityStyle(flag.severity);
          return (
            <div
              key={idx}
              style={{
                backgroundColor: "var(--color-bg-surface)",
                border: `1px solid ${style.border}`,
                borderRadius: "0.375rem",
                padding: "0.75rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                  marginBottom: "0.25rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
                    {flag.title}
                  </span>
                  {flag.category && (
                    <span
                      style={{
                        fontSize: "0.625rem",
                        padding: "0.05rem 0.35rem",
                        borderRadius: "3px",
                        backgroundColor: "var(--color-bg-surface-alt)",
                        color: "var(--color-text-secondary)",
                        border: "1px solid var(--color-border-subtle)",
                      }}
                    >
                      {flag.category}
                    </span>
                  )}
                </div>

                <span
                  style={{
                    fontSize: "0.625rem",
                    fontWeight: 700,
                    padding: "0.1rem 0.35rem",
                    borderRadius: "3px",
                    backgroundColor: style.bg,
                    color: style.color,
                    textTransform: "uppercase",
                    flexShrink: 0,
                  }}
                >
                  {flag.severity}
                </span>
              </div>

              <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", lineHeight: 1.4, margin: "0.25rem 0" }}>
                {flag.description}
              </p>

              {flag.evidence_snippet && (
                <div
                  style={{
                    margin: "0.35rem 0",
                    padding: "0.35rem 0.5rem",
                    backgroundColor: "var(--color-bg-base)",
                    borderLeft: `2px solid ${style.color}`,
                    borderRadius: "2px",
                    fontSize: "0.6875rem",
                    color: "var(--color-text-secondary)",
                    fontStyle: "italic",
                  }}
                >
                  &ldquo;{flag.evidence_snippet}&rdquo;
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: "0.35rem",
                  fontSize: "0.6875rem",
                  color: "var(--color-text-secondary)",
                }}
              >
                <span>
                  {flag.document_filename && `Source: ${flag.document_filename}`}
                  {flag.page_number ? ` (Page ${flag.page_number})` : ""}
                  {!flag.document_filename && flag.source && `Source: ${flag.source}`}
                </span>
              </div>

              {flag.recommendation && (
                <div
                  style={{
                    marginTop: "0.35rem",
                    paddingTop: "0.35rem",
                    borderTop: "1px dashed var(--color-border-subtle)",
                    fontSize: "0.6875rem",
                    color: "var(--color-text-primary)",
                  }}
                >
                  <strong>Recommendation:</strong> {flag.recommendation}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
