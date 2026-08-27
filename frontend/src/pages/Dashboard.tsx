










import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { useAuthStore } from "../store/authStore";
import { useToast } from "../components/Toast";
import { listReportsApi } from "../api/analysis";
import { getSessionResearchHistoryApi } from "../api/research";
import type { Session } from "../types";
import type { ResearchMessage } from "../types/research";



function IconPlus() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function IconFolder() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconDocuments() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function IconResearch() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconReports() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function IconArrowRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}



function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "var(--modal-backdrop)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem",
      }}
      onClick={onClose}
    >
      <div
        className="card animate-fade-in"
        style={{ width: "100%", maxWidth: "480px", padding: "1.75rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

interface RecentActivityItem {
  id: string;
  sessionId: string;
  sessionName: string;
  query: string;
  status: string;
  timestamp: string;
}

export default function Dashboard() {
  const { user } = useAuthStore();
  const { sessions, total, isLoading, fetchSessions, createSession } = useSessionStore();
  const { addToast } = useToast();
  const navigate = useNavigate();

  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [totalReportsCount, setTotalReportsCount] = useState<number>(0);
  const [recentActivities, setRecentActivities] = useState<RecentActivityItem[]>([]);
  const [inquiriesCount, setInquiriesCount] = useState<number>(0);

  useEffect(() => {
    fetchSessions(1);
  }, [fetchSessions]);

  
  useEffect(() => {
    if (!sessions || sessions.length === 0) {
      setTotalReportsCount(0);
      setRecentActivities([]);
      setInquiriesCount(0);
      return;
    }

    let isMounted = true;

    async function loadDashboardMetrics() {
      try {
        let reportsCount = 0;
        const activities: RecentActivityItem[] = [];
        let totalQuestions = 0;

        
        for (const s of sessions.slice(0, 6)) {
          const sId = s.id || s.session_id;
          const sName = s.name || s.session_name || "Workspace";
          if (!sId) continue;

          
          try {
            const repData = await listReportsApi(sId);
            reportsCount += repData.total || (repData.reports?.length ?? 0);
          } catch {
            
          }

          
          try {
            const histData = await getSessionResearchHistoryApi(sId, undefined, 10);
            if (histData && histData.messages) {
              const userQueries = histData.messages.filter((m: ResearchMessage) => m.role === "user");
              totalQuestions += userQueries.length;
              userQueries.forEach((m: ResearchMessage) => {
                activities.push({
                  id: m.message_id || `${sId}-${m.created_at}`,
                  sessionId: sId,
                  sessionName: sName,
                  query: m.content,
                  status: m.validation_status || "GROUNDED",
                  timestamp: m.created_at || new Date().toISOString(),
                });
              });
            }
          } catch {
            
          }
        }

        if (isMounted) {
          setTotalReportsCount(reportsCount);
          
          activities.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
          setRecentActivities(activities.slice(0, 5));
          setInquiriesCount(totalQuestions);
        }
      } catch {
        
      }
    }

    loadDashboardMetrics();

    return () => {
      isMounted = false;
    };
  }, [sessions]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;
    setCreateLoading(true);
    try {
      const created = await createSession(createName.trim());
      const sessionDisplayName = created.name || created.session_name;
      const targetId = created.id || created.session_id;
      addToast(`Workspace "${sessionDisplayName}" initialized`, "success");
      setCreateName("");
      setShowCreate(false);
      navigate(`/sessions/${targetId}`);
    } catch {
      addToast("Failed to create workspace", "error");
    } finally {
      setCreateLoading(false);
    }
  };

  
  const totalWorkspaces = total || sessions.length;
  const totalDocuments = sessions.reduce((acc, s) => acc + (s.document_count || 0), 0);
  const recentSessions = sessions.slice(0, 6);
  const latestSessionId = sessions.length > 0 ? (sessions[0].id || sessions[0].session_id) : null;

  return (
    <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
      {}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, letterSpacing: "-0.025em" }}>
            Executive Command Center
          </h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Welcome back, {user?.full_name || "Analyst"}. Institutional financial intelligence workstation &amp; research console.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          {latestSessionId && (
            <button
              onClick={() => navigate(`/sessions/${latestSessionId}?tab=research`)}
              className="btn btn-secondary"
            >
              <IconResearch />
              <span>Continue Research</span>
            </button>
          )}
          <button
            onClick={() => setShowCreate(true)}
            className="btn btn-primary"
          >
            <IconPlus />
            <span>New Research Workspace</span>
          </button>
        </div>
      </div>

      {}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1.25rem", marginBottom: "2rem" }}>
        {}
        <div className="card p-5">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Active Workspaces
            </span>
            <div style={{ color: "var(--brand-primary)" }}>
              <IconFolder />
            </div>
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }} className="font-tabular">
            {totalWorkspaces}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Multi-tenant financial sessions
          </div>
        </div>

        {}
        <div className="card p-5">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Ingested Documents
            </span>
            <div style={{ color: "var(--accent-info)" }}>
              <IconDocuments />
            </div>
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }} className="font-tabular">
            {totalDocuments}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Parsed financial SEC &amp; PDF filings
          </div>
        </div>

        {}
        <div className="card p-5">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Research Activity
            </span>
            <div style={{ color: "var(--brand-primary)" }}>
              <IconResearch />
            </div>
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }} className="font-tabular">
            {inquiriesCount > 0 ? inquiriesCount : totalWorkspaces}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            {inquiriesCount > 0 ? "Evidence-grounded inquiry turns" : "Multi-turn research sessions"}
          </div>
        </div>

        {}
        <div className="card p-5">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Generated Reports
            </span>
            <div style={{ color: "var(--accent-gold)" }}>
              <IconReports />
            </div>
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }} className="font-tabular">
            {totalReportsCount}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Institutional audit &amp; diligence deliverables
          </div>
        </div>
      </div>

      {}
      <div style={{ display: "grid", gridTemplateColumns: recentActivities.length > 0 ? "minmax(0, 2fr) minmax(0, 1fr)" : "1fr", gap: "1.5rem", marginBottom: "2rem" }}>
        
        {}
        <div className="card p-6">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 600, letterSpacing: "-0.015em" }}>
                Recent Financial Workspaces
              </h2>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                Direct access to interactive research, audited evidence, and executive reports
              </p>
            </div>

            <button
              onClick={() => navigate("/sessions")}
              className="btn btn-ghost"
              style={{ fontSize: "0.8rem" }}
            >
              <span>View All ({totalWorkspaces})</span>
              <IconArrowRight />
            </button>
          </div>

          {isLoading && sessions.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
              <div className="animate-spin" style={{ display: "inline-block", width: "24px", height: "24px", border: "2px solid var(--border-subtle)", borderTopColor: "var(--brand-primary)", borderRadius: "50%", marginBottom: "0.5rem" }} />
              <p style={{ fontSize: "0.85rem" }}>Loading financial sessions...</p>
            </div>
          ) : recentSessions.length === 0 ? (
            <div style={{ padding: "3.5rem 1.5rem", textAlign: "center", color: "var(--text-secondary)", border: "1px dashed var(--border-subtle)", borderRadius: "8px" }}>
              <div style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                <IconFolder />
              </div>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                No research workspaces initialized
              </h3>
              <p style={{ fontSize: "0.8rem", maxWidth: "400px", margin: "0 auto 1.25rem" }}>
                Create your first financial research workspace to ingest 10-K filings, inspect metrics, and generate reports.
              </p>
              <button onClick={() => setShowCreate(true)} className="btn btn-primary">
                <IconPlus />
                <span>Create Initial Workspace</span>
              </button>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
              {recentSessions.map((session: Session) => {
                const sessionId = session.id || session.session_id || "";
                const sessionName = session.name || session.session_name || "Financial Workspace";
                const docCount = session.document_count || 0;
                return (
                  <div
                    key={sessionId}
                    onClick={() => navigate(`/sessions/${sessionId}`)}
                    className="card card-interactive p-4 flex flex-col justify-between"
                    style={{ minHeight: "140px" }}
                  >
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem", gap: "0.5rem" }}>
                        <h4 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }} className="line-clamp-1" title={sessionName}>
                          {sessionName}
                        </h4>
                        <span className="badge badge-emerald">
                          Active
                        </span>
                      </div>

                      <p style={{ fontSize: "0.775rem", color: "var(--text-secondary)", marginBottom: "0.875rem" }} className="line-clamp-2">
                        {session.description || "Evidence-grounded financial intelligence and filing analysis."}
                      </p>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.725rem", color: "var(--text-muted)", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.5rem" }}>
                      <span>{docCount} {docCount === 1 ? "Document" : "Documents"}</span>
                      <span className="font-tabular">{new Date(session.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {}
        {recentActivities.length > 0 && (
          <div className="card p-6">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 600, letterSpacing: "-0.015em" }}>
                  Recent Research Inquiries
                </h2>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                  Evidence-grounded research questions
                </p>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {recentActivities.map((act) => (
                <div
                  key={act.id}
                  onClick={() => navigate(`/sessions/${act.sessionId}?tab=research`)}
                  className="p-3 rounded-lg border cursor-pointer transition-all duration-150"
                  style={{
                    backgroundColor: "var(--bg-surface-alt)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", marginBottom: "0.35rem" }}>
                    <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }} className="line-clamp-2">
                      "{act.query}"
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.725rem", color: "var(--text-muted)" }}>
                    <span style={{ color: "var(--brand-primary)", fontWeight: 500 }} className="line-clamp-1">
                      {act.sessionName}
                    </span>
                    <span className="font-tabular">{new Date(act.timestamp).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {}
      <Modal open={showCreate} onClose={() => setShowCreate(false)}>
        <form onSubmit={handleCreate}>
          <h3 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            Initialize Research Workspace
          </h3>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
            Define an institutional workspace for financial disclosures, balance sheet verification, and research threads.
          </p>

          <div style={{ marginBottom: "1.25rem" }}>
            <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 500, marginBottom: "0.4rem", color: "var(--text-secondary)" }}>
              Workspace / Company Name *
            </label>
            <input
              type="text"
              className="input"
              placeholder="e.g. Apple Inc. (AAPL) — FY24 Q4 Audit"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="btn btn-secondary"
              disabled={createLoading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={createLoading || !createName.trim()}
            >
              {createLoading ? "Initializing..." : "Create Workspace"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
