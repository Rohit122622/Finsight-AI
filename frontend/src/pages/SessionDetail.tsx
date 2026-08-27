









import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { getSessionApi } from "../api/sessions";
import { listDocumentsApi } from "../api/documents";
import { listReportsApi, getLiveProgressApi } from "../api/analysis";
import { useSessionWebSocket } from "../hooks/useWebSocket";
import { DocumentUploadZone } from "../components/DocumentUploadZone";
import { DocumentList } from "../components/DocumentList";
import { LiveAgentDashboard } from "../components/LiveAgentDashboard";
import { AnalysisReportViewer } from "../components/AnalysisReportViewer";
import { ResearchChat } from "../components/chat/ResearchChat";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { extractErrorMessage } from "../utils/errors";
import { AgentPipelineView } from "../components/agents/AgentPipelineView";
import type { Session, DocumentItem, AnalysisReport, JobProgressEvent } from "../types";

function IconArrowLeft() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
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

function IconChat() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconDocuments() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function IconReports() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const tabParam = searchParams.get("tab");
  const activeTab = tabParam === "documents" || tabParam === "reports" || tabParam === "overview" ? tabParam : "research";

  const [session, setSession] = useState<Session | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [reports, setReports] = useState<AnalysisReport[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [polledProgress, setPolledProgress] = useState<JobProgressEvent | null>(null);

  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isLoadingReports, setIsLoadingReports] = useState(false);
  const [error, setError] = useState<string | null>(null);

  
  const { isConnected, agentEvents, latestJobProgress } = useSessionWebSocket(sessionId);

  
  const loadSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      const s = await getSessionApi(sessionId);
      setSession(s);
    } catch (err: unknown) {
      setError(extractErrorMessage(err, "Session not found"));
    } finally {
      setIsLoadingSession(false);
    }
  }, [sessionId]);

  
  const loadDocuments = useCallback(async () => {
    if (!sessionId) return;
    setIsLoadingDocuments(true);
    try {
      const resp = await listDocumentsApi(sessionId);
      setDocuments(resp.documents || []);
    } catch {
      
    } finally {
      setIsLoadingDocuments(false);
    }
  }, [sessionId]);

  
  const loadReports = useCallback(async () => {
    if (!sessionId) return;
    setIsLoadingReports(true);
    try {
      const resp = await listReportsApi(sessionId);
      setReports(resp.reports || []);
    } catch {
      
    } finally {
      setIsLoadingReports(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
    loadDocuments();
    loadReports();
  }, [loadSession, loadDocuments, loadReports]);

  
  useEffect(() => {
    if (!sessionId || !activeJobId) return;

    let consecutiveErrors = 0;

    const interval = setInterval(async () => {
      try {
        const prog = await getLiveProgressApi(sessionId, activeJobId);
        consecutiveErrors = 0;
        setPolledProgress(prog);
        if (
          prog.status === "COMPLETED" ||
          prog.status === "FAILED" ||
          prog.status === "CANCELLED"
        ) {
          setActiveJobId(null);
          loadReports();
          loadDocuments();
        }
      } catch {
        consecutiveErrors += 1;
        
        if (consecutiveErrors >= 3) {
          setActiveJobId(null);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [sessionId, activeJobId, loadReports, loadDocuments]);

  
  useEffect(() => {
    if (
      latestJobProgress?.status === "COMPLETED" ||
      latestJobProgress?.status === "FAILED" ||
      latestJobProgress?.status === "CANCELLED"
    ) {
      loadReports();
      loadDocuments();
      if (activeJobId && latestJobProgress.job_id === activeJobId) {
        setActiveJobId(null);
      }
    }
  }, [latestJobProgress?.status, latestJobProgress?.job_id, activeJobId, loadReports, loadDocuments]);

  
  useEffect(() => {
    if (!sessionId) return;
    const hasPendingDocs = documents.some(
      (d) => d.status === "UPLOADED" || d.status === "PROCESSING"
    );
    if (!hasPendingDocs) return;

    const interval = setInterval(() => {
      loadDocuments();
      loadSession();
    }, 2500);

    return () => clearInterval(interval);
  }, [sessionId, documents, loadDocuments, loadSession]);

  const setTab = (tab: "overview" | "research" | "documents" | "reports") => {
    setSearchParams({ tab });
  };

  if (isLoadingSession) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "60vh" }}>
        <div
          className="animate-spin"
          style={{
            width: "2rem",
            height: "2rem",
            border: "3px solid var(--border-subtle)",
            borderTopColor: "var(--brand-primary)",
            borderRadius: "50%",
          }}
        />
      </div>
    );
  }

  if (error || !session) {
    return (
      <div style={{ padding: "4rem 2rem", textAlign: "center" }}>
        <p style={{ color: "var(--accent-risk)", marginBottom: "1rem", fontSize: "0.95rem" }}>
          {error ?? "Workspace session not found"}
        </p>
        <button onClick={() => navigate("/sessions")} className="btn btn-secondary">
          <IconArrowLeft />
          <span>Back to Workspaces</span>
        </button>
      </div>
    );
  }

  const effectiveJobProgress = polledProgress || latestJobProgress;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {}
      <div
        style={{
          padding: "0.875rem 1.5rem",
          backgroundColor: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "1rem",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <button
            onClick={() => navigate("/sessions")}
            className="btn btn-ghost"
            style={{ padding: "0.4rem 0.6rem" }}
            title="Back to Sessions"
          >
            <IconArrowLeft />
          </button>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
              <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.015em", color: "var(--text-primary)" }}>
                {session.name || session.session_name}
              </h1>
              <span className="badge badge-emerald">
                Active Session
              </span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
              {session.description || "Forensic financial intelligence & multi-agent research."}
            </div>
          </div>
        </div>

        {}
        <div
          style={{
            display: "flex",
            backgroundColor: "var(--bg-base)",
            padding: "3px",
            borderRadius: "8px",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <button
            onClick={() => setTab("overview")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.35rem 0.85rem",
              borderRadius: "6px",
              fontSize: "0.8rem",
              fontWeight: activeTab === "overview" ? 600 : 500,
              backgroundColor: activeTab === "overview" ? "var(--bg-surface)" : "transparent",
              color: activeTab === "overview" ? "var(--brand-primary)" : "var(--text-secondary)",
              border: "none",
              cursor: "pointer",
              boxShadow: activeTab === "overview" ? "var(--card-shadow)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            <IconFolder />
            <span>Overview</span>
          </button>

          <button
            onClick={() => setTab("research")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.35rem 0.85rem",
              borderRadius: "6px",
              fontSize: "0.8rem",
              fontWeight: activeTab === "research" ? 600 : 500,
              backgroundColor: activeTab === "research" ? "var(--bg-surface)" : "transparent",
              color: activeTab === "research" ? "var(--brand-primary)" : "var(--text-secondary)",
              border: "none",
              cursor: "pointer",
              boxShadow: activeTab === "research" ? "var(--card-shadow)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            <IconChat />
            <span>Research Agent</span>
          </button>

          <button
            onClick={() => setTab("documents")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.35rem 0.85rem",
              borderRadius: "6px",
              fontSize: "0.8rem",
              fontWeight: activeTab === "documents" ? 600 : 500,
              backgroundColor: activeTab === "documents" ? "var(--bg-surface)" : "transparent",
              color: activeTab === "documents" ? "var(--brand-primary)" : "var(--text-secondary)",
              border: "none",
              cursor: "pointer",
              boxShadow: activeTab === "documents" ? "var(--card-shadow)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            <IconDocuments />
            <span>Documents ({documents.length})</span>
          </button>

          <button
            onClick={() => setTab("reports")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.35rem 0.85rem",
              borderRadius: "6px",
              fontSize: "0.8rem",
              fontWeight: activeTab === "reports" ? 600 : 500,
              backgroundColor: activeTab === "reports" ? "var(--bg-surface)" : "transparent",
              color: activeTab === "reports" ? "var(--brand-primary)" : "var(--text-secondary)",
              border: "none",
              cursor: "pointer",
              boxShadow: activeTab === "reports" ? "var(--card-shadow)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            <IconReports />
            <span>Audit Reports ({reports.length})</span>
          </button>
        </div>
      </div>

      {}
      <div style={{ flex: 1, minHeight: 0, overflowY: activeTab === "research" ? "hidden" : "auto", display: "flex", flexDirection: "column" }}>
        {}
        {activeTab === "overview" && (
          <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto", width: "100%" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem", marginBottom: "2rem" }}>
              <div className="card p-5">
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
                  Disclosures Ingested
                </div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {documents.length}
                </div>
                <button onClick={() => setTab("documents")} className="btn btn-ghost" style={{ padding: 0, marginTop: "0.75rem", fontSize: "0.75rem" }}>
                  Upload more documents →
                </button>
              </div>

              <div className="card p-5">
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
                  Synthesized Reports
                </div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {reports.length}
                </div>
                <button onClick={() => setTab("reports")} className="btn btn-ghost" style={{ padding: 0, marginTop: "0.75rem", fontSize: "0.75rem" }}>
                  View live reports →
                </button>
              </div>

              <div className="card p-5">
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
                  Forensic Research
                </div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--brand-primary)", marginTop: "0.25rem" }}>
                  Ready to Query
                </div>
                <button onClick={() => setTab("research")} className="btn btn-ghost" style={{ padding: 0, marginTop: "0.75rem", fontSize: "0.75rem" }}>
                  Launch chat agent →
                </button>
              </div>
            </div>

            <AgentPipelineView />
          </div>
        )}

        {}
        {activeTab === "research" && (
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <ErrorBoundary>
              <ResearchChat sessionId={sessionId!} />
            </ErrorBoundary>
          </div>
        )}

        {}
        {activeTab === "documents" && (
          <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto", width: "100%", display: "flex", flexDirection: "column", gap: "2rem" }}>
            <DocumentUploadZone
              sessionId={sessionId!}
              onUploadSuccess={(response) => {
                if (response?.job_id) {
                  setActiveJobId(response.job_id);
                }
                loadDocuments();
                loadSession();
              }}
            />
            <DocumentList
              sessionId={sessionId!}
              documents={documents}
              isLoading={isLoadingDocuments}
              onRefresh={() => {
                loadDocuments();
                loadSession();
              }}
            />
          </div>
        )}

        {}
        {activeTab === "reports" && (
          <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto", width: "100%", display: "flex", flexDirection: "column", gap: "2rem" }}>
            <LiveAgentDashboard
              sessionId={sessionId!}
              isConnected={isConnected}
              liveProgress={effectiveJobProgress}
              agentEvents={agentEvents}
              hasDocuments={documents.length > 0}
              onAnalysisStarted={(jobId) => {
                if (jobId) setActiveJobId(jobId);
              }}
            />
            <AnalysisReportViewer reports={reports} isLoading={isLoadingReports} />
          </div>
        )}
      </div>
    </div>
  );
}
