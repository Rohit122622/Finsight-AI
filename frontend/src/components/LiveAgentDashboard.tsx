





import { useState } from "react";
import { triggerLiveAnalysisApi } from "../api/analysis";
import { extractErrorMessage } from "../utils/errors";
import type { LiveAgentStatusEvent, JobProgressEvent } from "../types";

interface LiveAgentDashboardProps {
  sessionId: string;
  isConnected: boolean;
  liveProgress: JobProgressEvent | null;
  agentEvents: LiveAgentStatusEvent[];
  hasDocuments: boolean;
  onAnalysisStarted: (jobId?: string) => void;
}

const AGENT_PIPELINE = [
  { name: "DocumentAgent", label: "Document Ingestion", role: "Parsing & Chunking" },
  { name: "ExtractionAgent", label: "Metric Extraction", role: "Revenue & Margins" },
  { name: "RedFlagAgent", label: "Red Flag Detection", role: "Forensic Anomalies" },
  { name: "ComparisonAgent", label: "Cross-Period Comparison", role: "Variance & Trends" },
  { name: "ReportAgent", label: "Report Synthesis", role: "Executive Summary" },
];

export function LiveAgentDashboard({
  sessionId,
  isConnected,
  liveProgress,
  agentEvents,
  hasDocuments,
  onAnalysisStarted,
}: LiveAgentDashboardProps) {
  const [query, setQuery] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const handleStartAnalysis = async () => {
    if (!hasDocuments) {
      setTriggerError("Please upload at least one document before running live analysis.");
      return;
    }

    setIsStarting(true);
    setTriggerError(null);
    try {
      const resp = await triggerLiveAnalysisApi(sessionId, query);
      onAnalysisStarted(resp.job_id);
    } catch (err: unknown) {
      setTriggerError(extractErrorMessage(err, "Failed to trigger live analysis."));
    } finally {
      setIsStarting(false);
    }
  };

  const progress = liveProgress?.progress_percent ?? 0;
  const currentStep = liveProgress?.current_step ?? "IDLE";
  const isRunning = liveProgress?.status === "PROCESSING" || liveProgress?.status === "QUEUED";

  return (
    <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
            Live Multi-Agent Processing
          </h2>
          <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", marginTop: "0.125rem" }}>
            Autonomous pipeline: Extraction → Forensic Red Flags → Comparison → Synthesis
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span
            style={{
              display: "inline-block",
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              backgroundColor: isConnected ? "var(--color-emerald-500)" : "var(--color-risk-500)",
            }}
          />
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
            {isConnected ? "Live WebSocket Connected" : "Connecting Stream..."}
          </span>
        </div>
      </div>

      {}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem" }}>
        <input
          type="text"
          placeholder="Specific research query (e.g. 'Analyze revenue trends and debt covenants')..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={isRunning || isStarting}
          style={{
            flex: 1,
            backgroundColor: "var(--color-bg-surface-alt)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "0.375rem",
            padding: "0.5rem 0.75rem",
            color: "var(--color-text-primary)",
            fontSize: "0.8125rem",
            outline: "none",
          }}
        />
        <button
          className="btn btn-primary"
          onClick={handleStartAnalysis}
          disabled={isRunning || isStarting || !hasDocuments}
          style={{ padding: "0.5rem 1.25rem", fontSize: "0.8125rem", whiteSpace: "nowrap" }}
        >
          {isStarting ? "Dispatching Agents..." : isRunning ? "Agents Active..." : "Run Multi-Agent Analysis"}
        </button>
      </div>

      {triggerError && (
        <div style={{ padding: "0.75rem", backgroundColor: "rgba(239, 68, 68, 0.1)", borderRadius: "0.375rem", marginBottom: "1rem", color: "var(--color-risk-500)", fontSize: "0.8125rem" }}>
          {triggerError}
        </div>
      )}

      {}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.375rem" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "var(--color-text-secondary)" }}>
            Current Step: <strong style={{ color: "var(--color-text-primary)" }}>{currentStep}</strong>
          </span>
          <span className="font-tabular" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-emerald-500)" }}>
            {progress}%
          </span>
        </div>
        <div
          style={{
            height: "8px",
            width: "100%",
            backgroundColor: "var(--color-border-subtle)",
            borderRadius: "9999px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progress}%`,
              backgroundColor: "var(--color-emerald-500)",
              transition: "width 0.3s ease-in-out",
            }}
          />
        </div>
      </div>

      {}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1.5rem",
        }}
      >
        {AGENT_PIPELINE.map((ag) => {
          const isActive = currentStep.toLowerCase().includes(ag.name.toLowerCase().replace("agent", ""));
          return (
            <div
              key={ag.name}
              style={{
                backgroundColor: "var(--color-bg-surface-alt)",
                border: `1px solid ${isActive ? "var(--color-emerald-500)" : "var(--color-border-subtle)"}`,
                borderRadius: "0.375rem",
                padding: "0.75rem",
                transition: "all 0.2s ease-in-out",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
                  {ag.label}
                </span>
                {isActive && (
                  <span
                    className="animate-spin"
                    style={{
                      width: "10px",
                      height: "10px",
                      border: "2px solid var(--color-emerald-500)",
                      borderTopColor: "transparent",
                      borderRadius: "50%",
                    }}
                  />
                )}
              </div>
              <p style={{ fontSize: "0.6875rem", color: "var(--color-text-secondary)" }}>{ag.role}</p>
            </div>
          );
        })}
      </div>

      {}
      <div>
        <h3 style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: "0.5rem" }}>
          Live Execution Milestones
        </h3>
        <div
          style={{
            maxHeight: "150px",
            overflowY: "auto",
            backgroundColor: "var(--color-bg-surface-alt)",
            borderRadius: "0.375rem",
            padding: "0.75rem",
            fontSize: "0.75rem",
            border: "1px solid var(--color-border-subtle)",
          }}
        >
          {agentEvents.length === 0 ? (
            <span style={{ color: "var(--color-text-secondary)" }}>
              No milestone events received yet. Start analysis to observe real-time agent coordination.
            </span>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              {agentEvents.map((ev, idx) => (
                <div key={idx} style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
                  <span className="font-tabular" style={{ color: "var(--color-text-secondary)", fontSize: "0.6875rem" }}>
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                  <span style={{ color: "var(--color-emerald-500)", fontWeight: 600 }}>
                    [{ev.agent_name}]
                  </span>
                  <span style={{ color: "var(--color-text-primary)" }}>{ev.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
