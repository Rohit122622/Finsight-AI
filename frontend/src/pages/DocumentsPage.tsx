import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { listDocumentsApi } from "../api/documents";
import type { DocumentItem, Session } from "../types";

function IconFolder() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

export default function DocumentsPage() {
  const { sessions, fetchSessions } = useSessionStore();
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
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
    setLoadingDocs(true);
    listDocumentsApi(selectedSessionId)
      .then((res) => setDocuments(res.documents || []))
      .catch(() => setDocuments([]))
      .finally(() => setLoadingDocs(false));
  }, [selectedSessionId]);

  return (
    <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
      {}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, letterSpacing: "-0.025em" }}>
            Financial Disclosures &amp; Document Ingestion
          </h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
            Manage parsed 10-K, 10-Q, earnings calls, and private financial PDF filings across active workspaces.
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
                    {sName} ({s.document_count || 0} docs)
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
            Create a workspace first to upload and index financial disclosures.
          </p>
          <button onClick={() => navigate("/sessions")} className="btn btn-primary">
            Go to Workspaces
          </button>
        </div>
      ) : (
        <div className="card p-6">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>
              Ingested Documents ({documents.length})
            </h3>
            {selectedSessionId && (
              <button
                onClick={() => navigate(`/sessions/${selectedSessionId}?tab=documents`)}
                className="btn btn-primary"
                style={{ fontSize: "0.8rem" }}
              >
                Upload to this Workspace →
              </button>
            )}
          </div>

          {loadingDocs ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
              <div className="animate-spin" style={{ display: "inline-block", width: "24px", height: "24px", border: "2px solid var(--border-subtle)", borderTopColor: "var(--brand-primary)", borderRadius: "50%", marginBottom: "0.5rem" }} />
              <p style={{ fontSize: "0.85rem" }}>Retrieving document records...</p>
            </div>
          ) : documents.length === 0 ? (
            <div style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-secondary)" }}>
              <p style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
                No documents uploaded to this workspace yet.
              </p>
              {selectedSessionId && (
                <button
                  onClick={() => navigate(`/sessions/${selectedSessionId}?tab=documents`)}
                  className="btn btn-secondary"
                >
                  Upload Initial Document
                </button>
              )}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", textAlign: "left", borderCollapse: "collapse", fontSize: "0.825rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
                    <th style={{ padding: "0.75rem" }}>Filename</th>
                    <th style={{ padding: "0.75rem" }}>Type</th>
                    <th style={{ padding: "0.75rem" }}>Size</th>
                    <th style={{ padding: "0.75rem" }}>Status</th>
                    <th style={{ padding: "0.75rem" }}>Ingested</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.document_id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {doc.filename}
                      </td>
                      <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                        {doc.mime_type || "PDF"}
                      </td>
                      <td style={{ padding: "0.75rem", fontFamily: "var(--font-mono)" }}>
                        {((doc.file_size_bytes || doc.file_size || 0) / (1024 * 1024)).toFixed(2)} MB
                      </td>
                      <td style={{ padding: "0.75rem" }}>
                        <span className="badge badge-emerald">
                          {doc.status || "PROCESSED"}
                        </span>
                      </td>
                      <td style={{ padding: "0.75rem", color: "var(--text-muted)" }}>
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
