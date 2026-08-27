




import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { listDocumentsApi } from "../api/documents";
import { ResearchChat } from "../components/chat/ResearchChat";
import type { DocumentItem, Session } from "../types";

export default function Research() {
  const { sessionId: paramSessionId } = useParams<{ sessionId?: string }>();
  const { sessions, fetchSessions, isLoading: isLoadingSessions } = useSessionStore();
  const navigate = useNavigate();

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const effectiveSessionId =
    paramSessionId ||
    selectedSessionId ||
    (sessions.length > 0 ? sessions[0].id : null);

  
  useEffect(() => {
    if (!effectiveSessionId) return;
    listDocumentsApi(effectiveSessionId)
      .then((resp: { documents: DocumentItem[] }) => {
        setDocuments(resp.documents || []);
      })
      .catch(() => {
        setDocuments([]);
      });
  }, [effectiveSessionId]);

  const activeSession = sessions.find((s: Session) => s.id === effectiveSessionId);

  const handleSessionChange = (newSessionId: string) => {
    setSelectedSessionId(newSessionId);
    navigate(`/research?session=${newSessionId}`, { replace: true });
  };

  if (isLoadingSessions && sessions.length === 0) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem 0" }}>
        <div
          className="animate-spin"
          style={{
            width: "2rem",
            height: "2rem",
            border: "3px solid var(--color-border-subtle)",
            borderTopColor: "var(--color-emerald-500)",
            borderRadius: "50%",
          }}
        />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div
        className="card"
        style={{
          textAlign: "center",
          padding: "4rem 2rem",
          maxWidth: "600px",
          margin: "2rem auto",
        }}
      >
        <div
          style={{
            width: "48px",
            height: "48px",
            borderRadius: "50%",
            backgroundColor: "rgba(16, 185, 129, 0.1)",
            color: "var(--color-emerald-500)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1rem",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>
        <h2 style={{ fontSize: "1.25rem", marginBottom: "0.5rem" }}>No Research Sessions</h2>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
          To conduct evidence-grounded research, create a session and upload financial documents.
        </p>
        <button className="btn btn-primary" onClick={() => navigate("/dashboard")}>
          Go to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "1rem" }}>
      {}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "0.625rem 1rem",
          backgroundColor: "var(--color-bg-surface)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "0.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-secondary)" }}>
            Active Session:
          </span>
          <select
            value={effectiveSessionId || ""}
            onChange={(e) => handleSessionChange(e.target.value)}
            style={{
              backgroundColor: "var(--color-bg-surface-alt)",
              border: "1px solid var(--color-border-subtle)",
              borderRadius: "4px",
              padding: "0.35rem 0.75rem",
              color: "var(--color-text-primary)",
              fontSize: "0.8125rem",
              fontWeight: 500,
              outline: "none",
              cursor: "pointer",
            }}
          >
            {sessions.map((s: Session) => (
              <option key={s.id} value={s.id}>
                {s.session_name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: documents.length > 0 ? "var(--color-emerald-500)" : "var(--color-amber-500)",
              }}
            />
            <span className="font-tabular" style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
              {documents.length} Disclosures Available
            </span>
          </div>

          <button
            className="btn btn-secondary"
            onClick={() => effectiveSessionId && navigate(`/sessions/${effectiveSessionId}`)}
            style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }}
          >
            Manage Documents
          </button>
        </div>
      </div>

      {}
      {effectiveSessionId && (
        <ResearchChat
          sessionId={effectiveSessionId}
          sessionName={activeSession?.session_name || "Research Session"}
          hasDocuments={documents.length > 0}
        />
      )}
    </div>
  );
}
