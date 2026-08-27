import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { listReportsApi } from "../api/analysis";
import { AnalysisReportViewer } from "../components/AnalysisReportViewer";
import type { AnalysisReport, Session } from "../types";

function IconFolder() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

export default function ReportsPage() {
  const { sessions, fetchSessions } = useSessionStore();
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [reports, setReports] = useState<AnalysisReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchSessions(1);
  }, [fetchSessions]);

  useEffect(() => {
    if (sessions.length > 0 && !selectedSessionId) {
      const firstId = sessions[0].id || sessions[0].session_id || "";
      setSelectedSessionId(firstId);
    }
  }, [sessions, selectedSessionId]);

  useEffect(() => {
    if (!selectedSessionId) return;
    setLoadingReports(true);
    listReportsApi(selectedSessionId)
      .then((res) => setReports(res.reports || []))
      .catch(() => setReports([]))
      .finally(() => setLoadingReports(false));
  }, [selectedSessionId]);

  return (
    <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
      {}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, letterSpacing: "-0.025em" }}>
            Synthesized Financial Audit Reports
          </h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Forensic audit dossiers, extracted financial statements, and multi-agent synthesis deliverables.
          </p>
        </div>

        {sessions.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <label style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Active Workspace:</label>
            <select
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              className="input"
              style={{ width: "260px", padding: "0.45rem 0.75rem" }}
            >
              {sessions.map((s: Session) => {
                const sId = s.id || s.session_id || "";
                const sName = s.name || s.session_name || "Workspace";
                return (
                  <option key={sId} value={sId}>
                    {sName}
                  </option>
                );
              })}
            </select>
          </div>
        )}
      </div>

      {sessions.length === 0 ? (
        <div className="card p-12 text-center">
          <div style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>
            <IconFolder />
          </div>
          <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            No financial workspaces found
          </h3>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
            Create a workspace and run an agent pipeline to generate executive audit reports.
          </p>
          <button onClick={() => navigate("/sessions")} className="btn btn-primary">
            Go to Workspaces
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <AnalysisReportViewer reports={reports} isLoading={loadingReports} />
        </div>
      )}
    </div>
  );
}
