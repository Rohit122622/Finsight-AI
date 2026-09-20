import { useEffect, useRef, useState } from "react";

export type EmailStatus = "queued" | "sending" | "sent" | "failed" | null | undefined;

interface LockedPdfPanelProps {
  /** Label for the artifact, e.g. "Comparison PDF" or "Report PDF". */
  title: string;
  /** Whether a locked (encrypted) PDF is available. */
  locked: boolean;
  /** Whether a password is retrievable for the authenticated owner. */
  passwordAvailable: boolean;
  /** Current email delivery status. */
  emailStatus: EmailStatus;
  /** True while a download is in progress. */
  downloading: boolean;
  /** Trigger the (encrypted) PDF download. */
  onDownload: () => void;
  /** Resolve the plaintext password for the authenticated owner. */
  onRevealPassword: () => Promise<string>;
  /** Re-queue the email using the already-persisted encrypted PDF. */
  onRetryEmail: () => Promise<void>;
  /** Optional: fetch the latest email_status from the backend (enables polling). */
  onRefreshStatus?: () => Promise<EmailStatus>;
}

const POLL_INTERVAL_MS = 4000;
const MAX_POLLS = 45; // ~3 minutes, then stop polling to avoid running forever

/**
 * Locked-PDF controls: password Reveal/Hide toggle (Copy only while visible),
 * download of the encrypted PDF, and email delivery status that auto-refreshes
 * while queued/sending and stops on sent/failed. The password is fetched only on
 * explicit user action, never persisted to storage or placed in the URL.
 */
export function LockedPdfPanel({
  title,
  locked,
  passwordAvailable,
  emailStatus,
  downloading,
  onDownload,
  onRevealPassword,
  onRetryEmail,
  onRefreshStatus,
}: LockedPdfPanelProps) {
  const [password, setPassword] = useState<string | null>(null); // in-memory only
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [localEmailStatus, setLocalEmailStatus] = useState<EmailStatus>(emailStatus);

  const pollCountRef = useRef(0);

  // Keep local status in sync when the parent supplies a new value.
  useEffect(() => {
    setLocalEmailStatus(emailStatus);
  }, [emailStatus]);

  // Poll for status only while queued/sending; stop on sent/failed (and after a cap).
  useEffect(() => {
    if (!onRefreshStatus) return;
    if (localEmailStatus !== "queued" && localEmailStatus !== "sending") return;

    pollCountRef.current = 0;
    let cancelled = false;
    const timer = setInterval(async () => {
      pollCountRef.current += 1;
      if (pollCountRef.current > MAX_POLLS) {
        clearInterval(timer);
        return;
      }
      try {
        const next = await onRefreshStatus();
        if (cancelled) return;
        if (next) {
          setLocalEmailStatus(next);
          if (next === "sent" || next === "failed") {
            clearInterval(timer);
          }
        }
      } catch {
        /* transient; keep polling until cap */
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [onRefreshStatus, localEmailStatus]);

  const effectiveStatus = localEmailStatus ?? emailStatus;

  const handleToggleVisibility = async () => {
    setPwError(null);
    if (visible) {
      // Hide immediately (mask). Keep the button consistent -> "Reveal Password".
      setVisible(false);
      setCopied(false);
      return;
    }
    // Reveal: fetch on demand if not already in memory.
    setBusy(true);
    try {
      let pw = password;
      if (!pw) {
        pw = await onRevealPassword();
        setPassword(pw);
      }
      setVisible(true);
    } catch {
      setPwError("Could not retrieve password.");
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    // Copy is only offered while the password is visible.
    if (!password) return;
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setPwError("Could not copy password.");
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await onRetryEmail();
      setLocalEmailStatus("queued"); // resumes polling
    } catch {
      setLocalEmailStatus("failed");
    } finally {
      setRetrying(false);
    }
  };

  const renderEmail = () => {
    switch (effectiveStatus) {
      case "sent":
        return <span style={{ color: "var(--brand-emerald, #10b981)" }}>Sent ✓</span>;
      case "sending":
      case "queued":
        return <span style={{ color: "var(--text-secondary, #64748b)" }}>Sending…</span>;
      case "failed":
        return (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={retrying}
            onClick={handleRetry}
            style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
          >
            {retrying ? "Retrying…" : "Failed — Retry Email"}
          </button>
        );
      default:
        return <span style={{ color: "var(--text-secondary, #64748b)" }}>—</span>;
    }
  };

  if (!locked) return null;

  return (
    <div
      data-testid="locked-pdf-panel"
      style={{
        marginTop: "0.75rem",
        padding: "0.875rem 1rem",
        border: "1px solid var(--border-light, #e2e8f0)",
        borderRadius: "0.5rem",
        backgroundColor: "var(--bg-surface, #f8fafc)",
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "1rem",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>
        {title} <span title="Password protected">🔒 Password Protected</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ fontSize: "0.8rem", color: "var(--text-secondary, #64748b)" }}>PDF Password</span>

        {visible && password ? (
          <code
            data-testid="revealed-password"
            style={{ fontSize: "0.8rem", padding: "0.15rem 0.4rem", background: "var(--bg-base,#fff)", borderRadius: 4 }}
          >
            {password}
          </code>
        ) : (
          <span aria-hidden="true" style={{ fontSize: "0.85rem", letterSpacing: "0.15em", color: "var(--text-secondary, #64748b)" }}>
            ••••••••••••
          </span>
        )}

        {/* Single visibility toggle: Reveal Password <-> Hide Password */}
        <button
          type="button"
          className="btn btn-secondary"
          data-testid="toggle-password"
          disabled={busy || !passwordAvailable}
          onClick={handleToggleVisibility}
          style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
        >
          {busy ? "Revealing…" : visible ? "Hide Password" : "Reveal Password"}
        </button>

        {/* Copy is available ONLY while the password is visible. */}
        {visible && password && (
          <button
            type="button"
            className="btn btn-secondary"
            data-testid="copy-password"
            onClick={handleCopy}
            style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
          >
            {copied ? "Copied ✓" : "Copy Password"}
          </button>
        )}
      </div>

      <button
        type="button"
        className="btn btn-secondary"
        disabled={downloading}
        onClick={onDownload}
        style={{ padding: "0.25rem 0.7rem", fontSize: "0.75rem" }}
      >
        {downloading ? "Downloading…" : "Download Locked PDF"}
      </button>

      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem" }}>
        <span style={{ color: "var(--text-secondary, #64748b)" }}>Email</span>
        {renderEmail()}
      </div>

      {pwError && (
        <span style={{ color: "var(--color-risk-500, #ef4444)", fontSize: "0.75rem" }}>{pwError}</span>
      )}
    </div>
  );
}
