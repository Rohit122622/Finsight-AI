











import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { useToast } from "../components/Toast";
import type { Session } from "../types";



function IconPlus() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function IconEdit() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function IconTrash() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3,6 5,6 21,6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function IconFolder() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--color-emerald-500)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconChevron({ direction }: { direction: "left" | "right" }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {direction === "left" ? <polyline points="15,18 9,12 15,6" /> : <polyline points="9,6 15,12 9,18" />}
    </svg>
  );
}

function IconChat() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
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
        background: "rgba(0, 0, 0, 0.6)",
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
        style={{ width: "100%", maxWidth: "440px", padding: "1.5rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}



export default function Sessions() {
  const { sessions, total, page, pageSize, isLoading, error, fetchSessions, createSession, renameSession, deleteSession, clearError } = useSessionStore();
  const { addToast } = useToast();
  const navigate = useNavigate();

  const [searchTerm, setSearchTerm] = useState("");

  
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  const [renameTarget, setRenameTarget] = useState<Session | null>(null);
  const [renameName, setRenameName] = useState("");

  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const filteredSessions = sessions.filter((s) =>
    s.session_name.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;
    setCreateLoading(true);
    try {
      const created = await createSession(createName.trim());
      addToast("Session created successfully!", "success");
      setShowCreate(false);
      setCreateName("");
      navigate(`/sessions/${created.id}`);
    } catch {
      addToast("Failed to create session", "warning");
    }
    setCreateLoading(false);
  };

  const handleRename = async (e: FormEvent) => {
    e.preventDefault();
    if (!renameTarget || !renameName.trim()) return;
    await renameSession(renameTarget.id, renameName.trim());
    addToast("Session renamed", "success");
    setRenameTarget(null);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    await deleteSession(deleteTarget.id);
    addToast("Session deleted", "success");
    setDeleteTarget(null);
    setDeleteLoading(false);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="animate-fade-in" style={{ maxWidth: "1280px", margin: "0 auto" }}>
      {}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={{ fontSize: "1.5rem", marginBottom: "0.25rem", fontWeight: 700 }}>
            Research Sessions
          </h1>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
            {total > 0
              ? `${total} active research session${total !== 1 ? "s" : ""}`
              : "Manage and launch your financial research workspaces"}
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {}
          <div
            style={{
              position: "relative",
              display: "flex",
              alignItems: "center",
            }}
          >
            <span
              style={{
                position: "absolute",
                left: "0.75rem",
                color: "var(--color-text-secondary)",
                pointerEvents: "none",
                display: "flex",
                alignItems: "center",
              }}
            >
              <IconSearch />
            </span>
            <input
              type="text"
              placeholder="Search sessions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                backgroundColor: "var(--color-bg-surface)",
                border: "1px solid var(--color-border-subtle)",
                borderRadius: "8px",
                padding: "0.5rem 0.875rem 0.5rem 2.25rem",
                color: "var(--color-text-primary)",
                fontSize: "0.875rem",
                outline: "none",
                width: "220px",
              }}
            />
          </div>

          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus />
            New Session
          </button>
        </div>
      </div>

      {}
      {error && (
        <div
          style={{
            padding: "0.625rem 0.875rem",
            borderRadius: "8px",
            background: "rgba(245, 158, 11, 0.1)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
            color: "var(--color-amber-100)",
            fontSize: "0.8125rem",
            marginBottom: "1rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          {error}
          <button
            className="btn-ghost"
            style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", border: "none", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer" }}
            onClick={clearError}
          >
            ✕
          </button>
        </div>
      )}

      {}
      {isLoading && sessions.length === 0 && (
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
      )}

      {}
      {!isLoading && sessions.length === 0 && (
        <div
          className="card"
          style={{
            textAlign: "center",
            padding: "4rem 2rem",
          }}
        >
          <IconFolder />
          <h3 style={{ marginTop: "1rem", marginBottom: "0.5rem" }}>No research sessions yet</h3>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
            Create your first session to start uploading disclosures and executing research queries.
          </p>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus />
            New Session
          </button>
        </div>
      )}

      {}
      {filteredSessions.length > 0 && (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: "1rem",
            }}
          >
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                className="card"
                style={{
                  padding: "1.25rem",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
                onClick={() => navigate(`/sessions/${session.id}`)}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
                    <h3
                      style={{
                        fontSize: "1rem",
                        fontWeight: 600,
                        color: "var(--color-text-primary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        flex: 1,
                        marginRight: "0.5rem",
                      }}
                    >
                      {session.session_name}
                    </h3>
                    <div style={{ display: "flex", gap: "0.25rem", flexShrink: 0 }}>
                      <button
                        className="btn-ghost"
                        style={{
                          padding: "0.375rem",
                          borderRadius: "6px",
                          border: "none",
                          background: "transparent",
                          color: "var(--color-text-secondary)",
                          cursor: "pointer",
                        }}
                        title="Rename"
                        onClick={(e) => {
                          e.stopPropagation();
                          setRenameTarget(session);
                          setRenameName(session.session_name);
                        }}
                      >
                        <IconEdit />
                      </button>
                      <button
                        className="btn-ghost"
                        style={{
                          padding: "0.375rem",
                          borderRadius: "6px",
                          border: "none",
                          background: "transparent",
                          color: "var(--color-text-secondary)",
                          cursor: "pointer",
                        }}
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(session);
                        }}
                      >
                        <IconTrash />
                      </button>
                    </div>
                  </div>

                  <p
                    className="font-tabular"
                    style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", marginBottom: "1rem" }}
                  >
                    Created {formatDate(session.created_at)}
                  </p>
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    paddingTop: "0.75rem",
                    borderTop: "1px solid var(--color-border-subtle)",
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.375rem",
                      fontSize: "0.75rem",
                      color: "var(--color-emerald-500)",
                      fontWeight: 500,
                    }}
                  >
                    <IconChat />
                    Research Agent
                  </span>

                  <button
                    className="btn btn-secondary"
                    style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/sessions/${session.id}`);
                    }}
                  >
                    Open Workspace →
                  </button>
                </div>
              </div>
            ))}
          </div>

          {}
          {totalPages > 1 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.75rem",
                marginTop: "1.5rem",
              }}
            >
              <button
                className="btn btn-secondary"
                style={{ padding: "0.5rem" }}
                disabled={page <= 1}
                onClick={() => fetchSessions(page - 1)}
              >
                <IconChevron direction="left" />
              </button>
              <span
                className="font-tabular"
                style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}
              >
                Page {page} of {totalPages}
              </span>
              <button
                className="btn btn-secondary"
                style={{ padding: "0.5rem" }}
                disabled={page >= totalPages}
                onClick={() => fetchSessions(page + 1)}
              >
                <IconChevron direction="right" />
              </button>
            </div>
          )}
        </>
      )}

      {}
      <Modal open={showCreate} onClose={() => setShowCreate(false)}>
        <h2 style={{ marginBottom: "0.5rem", fontSize: "1.25rem", fontWeight: 700 }}>New Research Session</h2>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)", marginBottom: "1rem" }}>
          Create an isolated financial research workspace to ingest 10-K, 10-Q, and research reports.
        </p>
        <form onSubmit={handleCreate}>
          <input
            className="input"
            placeholder="e.g. Apple Inc. FY24 Q4 Analysis"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            autoFocus
            maxLength={256}
          />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={!createName.trim() || createLoading}>
              {createLoading ? "Creating…" : "Create Workspace"}
            </button>
          </div>
        </form>
      </Modal>

      {}
      <Modal open={!!renameTarget} onClose={() => setRenameTarget(null)}>
        <h2 style={{ marginBottom: "1rem", fontSize: "1.25rem", fontWeight: 700 }}>Rename Session</h2>
        <form onSubmit={handleRename}>
          <input
            className="input"
            placeholder="New session name"
            value={renameName}
            onChange={(e) => setRenameName(e.target.value)}
            autoFocus
            maxLength={256}
          />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setRenameTarget(null)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={!renameName.trim()}>
              Rename
            </button>
          </div>
        </form>
      </Modal>

      {}
      <Modal open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <h2 style={{ marginBottom: "0.5rem", fontSize: "1.25rem", fontWeight: 700 }}>Delete Session</h2>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem", marginBottom: "1rem" }}>
          Are you sure you want to permanently delete{" "}
          <strong style={{ color: "var(--color-text-primary)" }}>
            {deleteTarget?.session_name}
          </strong>
          ? All documents, extracted metrics, and research conversations will be deleted.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={() => setDeleteTarget(null)}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={handleDelete} disabled={deleteLoading}>
            {deleteLoading ? "Deleting…" : "Delete Session"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
