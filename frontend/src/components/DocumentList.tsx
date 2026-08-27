




import { useState } from "react";
import { deleteDocumentApi, retryDocumentProcessingApi } from "../api/documents";
import { extractErrorMessage } from "../utils/errors";
import type { DocumentItem } from "../types";

interface DocumentListProps {
  sessionId: string;
  documents: DocumentItem[];
  isLoading: boolean;
  onRefresh: () => void;
}

export function DocumentList({ sessionId, documents = [], isLoading, onRefresh }: DocumentListProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionInProgressId, setActionInProgressId] = useState<string | null>(null);

  const formatFileSize = (bytes?: number): string => {
    if (!bytes || isNaN(bytes)) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "N/A";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return "N/A";
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "N/A";
    }
  };

  const handleDelete = async (docId: string) => {
    if (!docId) return;
    if (!window.confirm("Are you sure you want to delete this document and its embeddings?")) return;
    setActionInProgressId(docId);
    setActionError(null);
    try {
      await deleteDocumentApi(sessionId, docId);
      onRefresh();
    } catch (err: unknown) {
      setActionError(extractErrorMessage(err, "Failed to delete document."));
    } finally {
      setActionInProgressId(null);
    }
  };

  const handleRetry = async (docId: string) => {
    if (!docId) return;
    setActionInProgressId(docId);
    setActionError(null);
    try {
      await retryDocumentProcessingApi(sessionId, docId);
      onRefresh();
    } catch (err: unknown) {
      setActionError(extractErrorMessage(err, "Failed to retry document processing."));
    } finally {
      setActionInProgressId(null);
    }
  };

  const getStatusBadgeStyle = (status: string) => {
    switch (status) {
      case "PROCESSED":
        return {
          bg: "rgba(16, 185, 129, 0.15)",
          color: "var(--color-emerald-500)",
          label: "PROCESSED",
        };
      case "PROCESSING":
        return {
          bg: "rgba(245, 158, 11, 0.15)",
          color: "var(--color-amber-500)",
          label: "PROCESSING",
        };
      case "FAILED":
        return {
          bg: "rgba(239, 68, 68, 0.15)",
          color: "var(--color-risk-500)",
          label: "FAILED",
        };
      default:
        return {
          bg: "rgba(148, 163, 184, 0.15)",
          color: "var(--color-text-secondary)",
          label: "UPLOADED",
        };
    }
  };

  return (
    <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
          Session Documents ({documents.length})
        </h2>
        <button
          className="btn btn-secondary"
          onClick={onRefresh}
          disabled={isLoading}
          style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}
        >
          {isLoading ? "Refreshing..." : "↻ Refresh"}
        </button>
      </div>

      {actionError && (
        <div style={{ padding: "0.75rem", backgroundColor: "rgba(239, 68, 68, 0.1)", borderRadius: "0.375rem", marginBottom: "1rem", color: "var(--color-risk-500)", fontSize: "0.8125rem" }}>
          {actionError}
        </div>
      )}

      {documents.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
          No documents uploaded yet in this research session.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border-subtle)", textAlign: "left", color: "var(--color-text-secondary)" }}>
                <th style={{ padding: "0.625rem 0.75rem" }}>Filename</th>
                <th style={{ padding: "0.625rem 0.75rem" }}>Size</th>
                <th style={{ padding: "0.625rem 0.75rem" }}>Status</th>
                <th style={{ padding: "0.625rem 0.75rem" }}>Chunks</th>
                <th style={{ padding: "0.625rem 0.75rem" }}>Uploaded</th>
                <th style={{ padding: "0.625rem 0.75rem", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc, idx) => {
                const docId = doc.document_id || doc.id || `doc-${idx}`;
                const badge = getStatusBadgeStyle(doc.status || "UPLOADED");
                const isProcessing = actionInProgressId === docId;

                return (
                  <tr key={docId} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                    <td style={{ padding: "0.75rem", fontWeight: 500, color: "var(--color-text-primary)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span>📄</span>
                        <span>{doc.filename || "Untitled Document"}</span>
                      </div>
                    </td>
                    <td className="font-tabular" style={{ padding: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {formatFileSize(doc.file_size)}
                    </td>
                    <td style={{ padding: "0.75rem" }}>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.2rem 0.5rem",
                          borderRadius: "9999px",
                          fontWeight: 600,
                          backgroundColor: badge.bg,
                          color: badge.color,
                        }}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td className="font-tabular" style={{ padding: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {doc.metadata?.chunk_count ?? (doc.chunks ? doc.chunks.length : 0)}
                    </td>
                    <td className="font-tabular" style={{ padding: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {formatDate(doc.created_at)}
                    </td>
                    <td style={{ padding: "0.75rem", textAlign: "right" }}>
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                        {doc.status === "FAILED" && (
                          <button
                            className="btn btn-secondary"
                            onClick={() => handleRetry(docId)}
                            disabled={isProcessing}
                            style={{ fontSize: "0.6875rem", padding: "0.25rem 0.5rem", color: "var(--color-amber-500)" }}
                          >
                            Retry
                          </button>
                        )}
                        <button
                          className="btn btn-ghost"
                          onClick={() => handleDelete(docId)}
                          disabled={isProcessing}
                          style={{
                            fontSize: "0.6875rem",
                            padding: "0.25rem 0.5rem",
                            color: "var(--color-risk-500)",
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
