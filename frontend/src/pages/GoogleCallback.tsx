








import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useToast } from "../components/Toast";
import apiClient from "../api/client";
import type { TokenResponse } from "../types";

import { extractErrorMessage } from "../utils/errors";

export default function GoogleCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setTokensFromOAuth, hydrate } = useAuthStore();
  const { addToast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const oauthError = searchParams.get("error");

    if (oauthError) {
      setError(`Google authorization failed: ${oauthError}`);
      return;
    }

    if (!code || !state) {
      setError("Missing authorization parameters from Google");
      return;
    }

    
    apiClient
      .get<TokenResponse>("/auth/google/callback", {
        params: { code, state },
      })
      .then(async (resp) => {
        const { access_token, refresh_token } = resp.data;
        setTokensFromOAuth(access_token, refresh_token);
        await hydrate();
        addToast("Signed in with Google!", "success");
        navigate("/dashboard", { replace: true });
      })
      .catch((err: unknown) => {
        const detail = extractErrorMessage(err, "Google sign-in failed. Please try again.");
        setError(detail);
      });
  }, [searchParams, setTokensFromOAuth, hydrate, addToast, navigate]);

  if (error) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--color-bg-base)",
          padding: "1rem",
        }}
      >
        <div className="card animate-fade-in" style={{ maxWidth: "420px", padding: "2rem", textAlign: "center" }}>
          <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>⚠</div>
          <h2 style={{ marginBottom: "0.75rem" }}>Sign-in Failed</h2>
          <p style={{ color: "var(--color-amber-100)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
            {error}
          </p>
          <button className="btn btn-primary" onClick={() => navigate("/login", { replace: true })}>
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--color-bg-base)",
        gap: "1rem",
      }}
    >
      <div
        className="animate-spin"
        style={{
          width: "2.5rem",
          height: "2.5rem",
          border: "3px solid var(--color-border-subtle)",
          borderTopColor: "var(--color-emerald-500)",
          borderRadius: "50%",
        }}
      />
      <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
        Completing sign-in…
      </p>
    </div>
  );
}
