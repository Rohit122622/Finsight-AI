






import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { getGoogleLoginUrl } from "../api/auth";
import { useToast } from "../components/Toast";

export default function Login() {
  const navigate = useNavigate();
  const { login, isLoading, error, clearError } = useAuthStore();
  const { addToast } = useToast();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localErrors, setLocalErrors] = useState<{ email?: string; password?: string }>({});

  const validate = (): boolean => {
    const errs: { email?: string; password?: string } = {};
    if (!email) errs.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Invalid email format";
    if (!password) errs.password = "Password is required";
    setLocalErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    if (!validate()) return;

    try {
      await login({ email, password });
      addToast("Welcome back!", "success");
      navigate("/dashboard", { replace: true });
    } catch {
      
    }
  };

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
      <div
        className="card animate-fade-in"
        style={{ width: "100%", maxWidth: "420px", padding: "2.5rem 2rem" }}
      >
        {}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>
            Welcome back
          </h1>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
            Sign in to your FinSentry AI account
          </p>
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
            }}
          >
            {error}
          </div>
        )}

        {}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label
              htmlFor="login-email"
              style={{ fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", display: "block", color: "var(--color-text-secondary)" }}
            >
              Email
            </label>
            <input
              id="login-email"
              type="email"
              className={`input ${localErrors.email ? "input-error" : ""}`}
              placeholder="you@example.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setLocalErrors((p) => ({ ...p, email: undefined })); }}
              autoComplete="email"
            />
            {localErrors.email && (
              <span style={{ fontSize: "0.75rem", color: "var(--color-amber-500)", marginTop: "0.25rem", display: "block" }}>
                {localErrors.email}
              </span>
            )}
          </div>

          <div>
            <label
              htmlFor="login-password"
              style={{ fontSize: "0.8125rem", fontWeight: 500, marginBottom: "0.375rem", display: "block", color: "var(--color-text-secondary)" }}
            >
              Password
            </label>
            <input
              id="login-password"
              type="password"
              className={`input ${localErrors.password ? "input-error" : ""}`}
              placeholder="••••••••"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setLocalErrors((p) => ({ ...p, password: undefined })); }}
              autoComplete="current-password"
            />
            {localErrors.password && (
              <span style={{ fontSize: "0.75rem", color: "var(--color-amber-500)", marginTop: "0.25rem", display: "block" }}>
                {localErrors.password}
              </span>
            )}
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading}
            style={{ width: "100%", marginTop: "0.5rem" }}
          >
            {isLoading ? (
              <>
                <div
                  className="animate-spin"
                  style={{
                    width: "1rem",
                    height: "1rem",
                    border: "2px solid rgba(255,255,255,0.3)",
                    borderTopColor: "white",
                    borderRadius: "50%",
                  }}
                />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </form>

        {}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            margin: "1.25rem 0",
          }}
        >
          <div style={{ flex: 1, height: "1px", background: "var(--color-border-subtle)" }} />
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>or</span>
          <div style={{ flex: 1, height: "1px", background: "var(--color-border-subtle)" }} />
        </div>

        {}
        <a
          href={getGoogleLoginUrl()}
          className="btn btn-secondary"
          style={{ width: "100%", textDecoration: "none" }}
        >
          <svg width="18" height="18" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Continue with Google
        </a>

        {}
        <p
          style={{
            textAlign: "center",
            marginTop: "1.5rem",
            fontSize: "0.8125rem",
            color: "var(--color-text-secondary)",
          }}
        >
          Don&apos;t have an account?{" "}
          <Link
            to="/register"
            style={{ color: "var(--color-emerald-500)", textDecoration: "none", fontWeight: 500 }}
          >
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
