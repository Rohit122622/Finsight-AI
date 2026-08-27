import React from "react";

export interface TimelineEvent {
  id: string;
  agentName: string;
  status: "SUCCESS" | "RUNNING" | "FAILED" | "QUEUED";
  message: string;
  timestamp: string;
  latencyMs?: number;
  details?: Record<string, any>;
}

interface AgentExecutionTimelineProps {
  events: TimelineEvent[];
  title?: string;
}

export const AgentExecutionTimeline: React.FC<AgentExecutionTimelineProps> = ({
  events,
  title = "Agent Execution Trace Log",
}) => {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {title}
        </h3>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {events.length} trace events
        </span>
      </div>

      {events.length === 0 ? (
        <div className="p-8 text-center" style={{ color: "var(--text-muted)" }}>
          <p className="text-xs">No agent execution events recorded for this session.</p>
        </div>
      ) : (
        <div className="space-y-3 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-[var(--border-subtle)]">
          {events.map((evt) => {
            const isSuccess = evt.status === "SUCCESS";
            const isFailed = evt.status === "FAILED";
            const isRunning = evt.status === "RUNNING";

            return (
              <div key={evt.id} className="relative flex items-start gap-4 pl-2">
                <div
                  className="w-3.5 h-3.5 rounded-full mt-1 border-2 shrink-0 z-10"
                  style={{
                    backgroundColor: isSuccess
                      ? "var(--brand-primary)"
                      : isFailed
                      ? "var(--accent-risk)"
                      : isRunning
                      ? "var(--accent-gold)"
                      : "var(--bg-surface)",
                    borderColor: "var(--bg-base)",
                  }}
                />

                <div
                  className="flex-1 p-3 rounded-lg border text-xs"
                  style={{
                    backgroundColor: "var(--bg-surface-alt)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                        {evt.agentName}
                      </span>
                      <span
                        className="badge"
                        style={{
                          backgroundColor: isSuccess
                            ? "var(--brand-primary-light)"
                            : isFailed
                            ? "var(--accent-risk-light)"
                            : "var(--accent-gold-light)",
                          color: isSuccess
                            ? "var(--brand-primary)"
                            : isFailed
                            ? "var(--accent-risk)"
                            : "var(--accent-gold)",
                        }}
                      >
                        {evt.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                      {evt.latencyMs !== undefined && (
                        <span className="font-tabular">{evt.latencyMs.toFixed(1)}ms</span>
                      )}
                      <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                    </div>
                  </div>

                  <p style={{ color: "var(--text-secondary)" }}>{evt.message}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
