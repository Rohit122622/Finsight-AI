





import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { uploadDocumentApi } from "../api/documents";
import { extractErrorMessage } from "../utils/errors";
import type { DocumentUploadResponse } from "../types";

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; 
const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".md", ".csv", ".json"];

export type UploadStage =
  | "IDLE"
  | "VALIDATING"
  | "UPLOADING"
  | "QUEUED"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED";

interface DocumentUploadZoneProps {
  sessionId: string;
  onUploadSuccess: (response?: DocumentUploadResponse) => void;
}

export function DocumentUploadZone({ sessionId, onUploadSuccess }: DocumentUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [stage, setStage] = useState<UploadStage>("IDLE");
  const [progressPercent, setProgressPercent] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number): string => {
    if (!bytes || isNaN(bytes)) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const validateFile = (file: File): string | null => {
    if (!file) {
      return "No file selected.";
    }
    if (file.size === 0) {
      return "File is empty (0 bytes). Please select a valid document.";
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `File size (${formatFileSize(file.size)}) exceeds the maximum allowed limit of 50 MB.`;
    }
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file extension (${ext}). Allowed formats: ${ALLOWED_EXTENSIONS.join(", ")}.`;
    }
    return null;
  };

  const handleFileProcess = async (file: File) => {
    if (!file) return;
    setSelectedFile(file);
    setValidationError(null);
    setServerError(null);
    setStage("VALIDATING");

    const error = validateFile(file);
    if (error) {
      setValidationError(error);
      setStage("FAILED");
      return;
    }

    
    setStage("UPLOADING");
    setProgressPercent(0);

    try {
      const result = await uploadDocumentApi(sessionId, file, (percent) => {
        setProgressPercent(percent);
        if (percent === 100) {
          setStage("QUEUED");
        }
      });

      setStage("COMPLETED");
      onUploadSuccess(result);
    } catch (err: unknown) {
      setStage("FAILED");
      const message = extractErrorMessage(
        err,
        "Upload failed. Please check network connectivity or file integrity.",
      );
      setServerError(message);
    }
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const onDragLeave = () => {
    setIsDragOver(false);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileProcess(e.dataTransfer.files[0]);
    }
  };

  const onFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileProcess(e.target.files[0]);
    }
  };

  const handleRetry = () => {
    if (selectedFile) {
      handleFileProcess(selectedFile);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setValidationError(null);
    setServerError(null);
    setStage("IDLE");
    setProgressPercent(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
          Secure Document Ingestion
        </h2>
        <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
          Max 50MB • PDF, TXT, MD, CSV, JSON
        </span>
      </div>

      {}
      <input
        type="file"
        ref={fileInputRef}
        onChange={onFileInputChange}
        accept=".pdf,.txt,.md,.csv,.json"
        style={{ display: "none" }}
      />

      {}
      {stage === "IDLE" && (
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${isDragOver ? "var(--color-emerald-500)" : "var(--color-border-subtle)"}`,
            backgroundColor: isDragOver ? "rgba(16, 185, 129, 0.05)" : "var(--color-bg-surface-alt)",
            borderRadius: "0.5rem",
            padding: "2.5rem 1.5rem",
            textAlign: "center",
            cursor: "pointer",
            transition: "all 0.2s ease-in-out",
          }}
        >
          <svg
            width="36"
            height="36"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--color-emerald-500)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ margin: "0 auto 1rem auto" }}
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <p style={{ fontSize: "0.9375rem", fontWeight: 500, color: "var(--color-text-primary)", marginBottom: "0.375rem" }}>
            Drag & drop your financial documents here
          </p>
          <p style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
            or click to browse files from your computer
          </p>
        </div>
      )}

      {}
      {stage !== "IDLE" && (
        <div
          style={{
            backgroundColor: "var(--color-bg-surface-alt)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "0.5rem",
            padding: "1.25rem",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <div>
              <p style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
                {selectedFile?.name}
              </p>
              <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                {selectedFile ? formatFileSize(selectedFile.size) : ""}
              </p>
            </div>

            {}
            <span
              style={{
                fontSize: "0.75rem",
                padding: "0.25rem 0.625rem",
                borderRadius: "9999px",
                fontWeight: 500,
                backgroundColor:
                  stage === "COMPLETED"
                    ? "rgba(16, 185, 129, 0.15)"
                    : stage === "FAILED"
                    ? "rgba(239, 68, 68, 0.15)"
                    : "rgba(245, 158, 11, 0.15)",
                color:
                  stage === "COMPLETED"
                    ? "var(--color-emerald-500)"
                    : stage === "FAILED"
                    ? "var(--color-risk-500)"
                    : "var(--color-amber-500)",
              }}
            >
              {stage}
            </span>
          </div>

          {}
          {(stage === "UPLOADING" || stage === "QUEUED" || stage === "VALIDATING") && (
            <div style={{ marginBottom: "0.75rem" }}>
              <div
                style={{
                  height: "6px",
                  width: "100%",
                  backgroundColor: "var(--color-border-subtle)",
                  borderRadius: "9999px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${stage === "VALIDATING" ? 15 : stage === "QUEUED" ? 100 : progressPercent}%`,
                    backgroundColor: "var(--color-emerald-500)",
                    transition: "width 0.2s ease-in-out",
                  }}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.375rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                  {stage === "VALIDATING"
                    ? "Validating security & MIME signatures..."
                    : stage === "QUEUED"
                    ? "Queued for Celery multi-agent background worker..."
                    : `Uploading to Cloudflare R2: ${progressPercent}%`}
                </span>
                <span className="font-tabular" style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                  {progressPercent}%
                </span>
              </div>
            </div>
          )}

          {}
          {stage === "COMPLETED" && (
            <div style={{ marginTop: "0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--color-emerald-500)" }}>
                ✓ Securely stored & ingested. Background processing enqueued.
              </span>
              <button className="btn btn-secondary" onClick={handleReset} style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}>
                Upload Another
              </button>
            </div>
          )}

          {}
          {stage === "FAILED" && (
            <div style={{ marginTop: "0.5rem" }}>
              <p style={{ fontSize: "0.8125rem", color: "var(--color-risk-500)", marginBottom: "0.75rem" }}>
                ✕ {validationError || serverError || "An error occurred during upload."}
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  className="btn"
                  onClick={handleRetry}
                  style={{
                    backgroundColor: "var(--color-amber-500)",
                    color: "#0B1220",
                    fontSize: "0.75rem",
                    padding: "0.375rem 0.75rem",
                    fontWeight: 600,
                  }}
                >
                  Retry Upload
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={handleReset}
                  style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
