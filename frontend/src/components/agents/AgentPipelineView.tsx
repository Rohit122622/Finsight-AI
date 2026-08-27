import React from "react";
import type { AgentInfo } from "./AgentStatusCard";

interface PipelineStep {
  id: string;
  name: string;
  taskType: string;
  status: "idle" | "running" | "completed" | "failed" | "skipped";
  durationMs?: number;
}

interface AgentPipelineViewProps {
  agents?: AgentInfo[];
  steps?: PipelineStep[];
  currentStepIndex?: number;
}

const DEFAULT_PIPELINE: PipelineStep[] = [
  { id: "1", name: "Document Ingestion", taskType: "DOCUMENT_ANALYSIS", status: "idle" },
  { id: "2", name: "Extraction & Red Flags", taskType: "EXTRACTION", status: "idle" },
  { id: "3", name: "Comparative Audit", taskType: "COMPARISON", status: "idle" },
  { id: "4", name: "Deep Research", taskType: "RESEARCH", status: "idle" },
  { id: "5", name: "Report Synthesis", taskType: "REPORT_GENERATION", status: "idle" },
];

export const AgentPipelineView: React.FC<AgentPipelineViewProps> = ({
  steps = DEFAULT_PIPELINE,
  currentStepIndex,
}) => {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Multi-Agent Orchestration Pipeline
          </h3>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Autonomous pipeline sequence with strict artifact passing and schema validation
          </p>
        </div>
        <span className="badge badge-info">CrewAI + Celery</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
        {steps.map((step, idx) => {
          const isCurrent = currentStepIndex !== undefined && currentStepIndex === idx;
          const isPast = currentStepIndex !== undefined && currentStepIndex > idx;
          const effectiveStatus = isCurrent ? "running" : isPast ? "completed" : step.status;

          return (
            <div
              key={step.id}
              className="flex flex-col p-3 rounded-lg border transition-all duration-200"
              style={{
                backgroundColor: isCurrent ? "var(--brand-primary-light)" : "var(--bg-surface-alt)",
                borderColor: isCurrent
                  ? "var(--brand-primary)"
                  : effectiveStatus === "completed"
                  ? "var(--brand-primary-border)"
                  : "var(--border-subtle)",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span
                  className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{
                    backgroundColor:
                      effectiveStatus === "completed"
                        ? "var(--brand-primary)"
                        : effectiveStatus === "running"
                        ? "var(--accent-gold)"
                        : "var(--bg-surface)",
                    color: effectiveStatus === "completed" || effectiveStatus === "running" ? "#FFFFFF" : "var(--text-muted)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  {effectiveStatus === "completed" ? "✓" : idx + 1}
                </span>
                <span
                  className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor:
                      effectiveStatus === "running"
                        ? "var(--accent-gold-light)"
                        : effectiveStatus === "completed"
                        ? "var(--brand-primary-light)"
                        : "transparent",
                    color:
                      effectiveStatus === "running"
                        ? "var(--accent-gold)"
                        : effectiveStatus === "completed"
                        ? "var(--brand-primary)"
                        : "var(--text-muted)",
                  }}
                >
                  {effectiveStatus}
                </span>
              </div>

              <span className="text-xs font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
                {step.name}
              </span>
              <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                {step.taskType}
              </span>

              {step.durationMs !== undefined && (
                <div className="mt-2 text-[10px] font-tabular" style={{ color: "var(--text-secondary)" }}>
                  {(step.durationMs / 1000).toFixed(2)}s
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
