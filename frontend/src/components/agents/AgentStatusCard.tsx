import React from "react";

export interface AgentInfo {
  name: string;
  task_type: string;
  description: string;
  is_active: boolean;
  lastExecutionMs?: number;
  successRate?: number;
}

interface AgentStatusCardProps {
  agent: AgentInfo;
  status?: "idle" | "running" | "completed" | "failed";
  onSelect?: () => void;
}

export const AgentStatusCard: React.FC<AgentStatusCardProps> = ({
  agent,
  status = "idle",
  onSelect,
}) => {
  const getBadgeClass = () => {
    switch (status) {
      case "running":
        return "badge-gold";
      case "completed":
        return "badge-emerald";
      case "failed":
        return "badge-risk";
      default:
        return "badge-info";
    }
  };

  return (
    <div
      onClick={onSelect}
      className={`card p-4 transition-all duration-200 ${
        onSelect ? "card-interactive cursor-pointer" : ""
      } flex flex-col justify-between`}
      style={{ minHeight: "140px" }}
    >
      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{
                backgroundColor:
                  status === "running"
                    ? "var(--accent-gold)"
                    : status === "completed"
                    ? "var(--brand-primary)"
                    : status === "failed"
                    ? "var(--accent-risk)"
                    : "var(--text-muted)",
              }}
            />
            <h4 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
              {agent.name}
            </h4>
          </div>
          <span className={`badge ${getBadgeClass()}`}>{status}</span>
        </div>

        <p className="text-xs mb-3 line-clamp-2" style={{ color: "var(--text-secondary)" }}>
          {agent.description}
        </p>
      </div>

      <div
        className="flex items-center justify-between text-xs pt-2 border-t"
        style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}
      >
        <span>Type: <strong style={{ color: "var(--text-secondary)" }}>{agent.task_type}</strong></span>
        {agent.lastExecutionMs !== undefined && (
          <span className="font-tabular">{agent.lastExecutionMs.toFixed(0)} ms</span>
        )}
      </div>
    </div>
  );
};
