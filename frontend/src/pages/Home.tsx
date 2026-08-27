import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useTheme } from "../context/ThemeContext";

function IconShield() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function IconCpu() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </svg>
  );
}

function IconSun() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function IconMoon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function Home() {
  const { isAuthenticated } = useAuthStore();
  const { resolvedTheme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-base)", color: "var(--text-primary)" }}>
      {}
      <header
        style={{
          height: "64px",
          borderBottom: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-header)",
          backdropFilter: "blur(10px)",
          position: "sticky",
          top: 0,
          zIndex: 50,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 2rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", cursor: "pointer" }} onClick={() => navigate("/")}>
          <div style={{ color: "var(--brand-primary)" }}>
            <IconShield />
          </div>
          <span style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
            FinSentry <span style={{ color: "var(--brand-primary)" }}>AI</span>
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <button
            onClick={toggleTheme}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "34px",
              height: "34px",
              borderRadius: "8px",
              backgroundColor: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
              cursor: "pointer",
            }}
            title={`Switch to ${resolvedTheme === "dark" ? "Light" : "Dark"} theme`}
          >
            {resolvedTheme === "dark" ? <IconSun /> : <IconMoon />}
          </button>

          {isAuthenticated ? (
            <Link to="/dashboard" className="btn btn-primary">
              Enter Workspace
            </Link>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <Link to="/login" className="btn btn-secondary">
                Sign In
              </Link>
              <Link to="/register" className="btn btn-primary">
                Get Started
              </Link>
            </div>
          )}
        </div>
      </header>

      {}
      <section style={{ padding: "5rem 2rem 4rem", maxWidth: "1200px", margin: "0 auto", textAlign: "center" }}>
        <div
          className="badge badge-emerald"
          style={{ marginBottom: "1.5rem", padding: "0.35rem 0.85rem", fontSize: "0.75rem" }}
        >
          Institutional Multi-Agent Intelligence Engine
        </div>

        <h1
          style={{
            fontSize: "clamp(2.2rem, 5vw, 3.75rem)",
            fontWeight: 800,
            lineHeight: 1.15,
            letterSpacing: "-0.03em",
            maxWidth: "900px",
            margin: "0 auto 1.5rem",
          }}
        >
          Autonomous Financial Audit &amp; Forensic Research Platform
        </h1>

        <p
          style={{
            fontSize: "1.1rem",
            color: "var(--text-secondary)",
            maxWidth: "720px",
            margin: "0 auto 2.5rem",
            lineHeight: 1.6,
          }}
        >
          FinSentry AI deploys specialized autonomous agent crews to extract corporate metrics, detect balance sheet anomalies, verify source citations, and synthesize institutional research.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: "1rem", flexWrap: "wrap", marginBottom: "3.5rem" }}>
          <Link
            to={isAuthenticated ? "/dashboard" : "/register"}
            className="btn btn-primary"
            style={{ padding: "0.75rem 2rem", fontSize: "1rem" }}
          >
            {isAuthenticated ? "Go to Command Center" : "Start Analysis Free"}
          </Link>
          <Link
            to="/login"
            className="btn btn-secondary"
            style={{ padding: "0.75rem 1.75rem", fontSize: "1rem" }}
          >
            Sign In with Google / Email
          </Link>
        </div>

        {}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.5rem", textAlign: "left" }}>
          <div className="card p-6">
            <div style={{ color: "var(--brand-primary)", marginBottom: "1rem" }}>
              <IconCpu />
            </div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              CrewAI &amp; Celery Orchestration
            </h3>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Decoupled, asynchronous agent execution pipeline covering ingestion, extraction, comparative audit, and report generation with strict output contracts.
            </p>
          </div>

          <div className="card p-6">
            <div style={{ color: "var(--accent-gold)", marginBottom: "1rem" }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              Cloud LLM Resilience
            </h3>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Powered by Ollama Cloud (120B parameter model) as primary with automated fallback through Google Gemini, Groq, and offline deterministic safety nets.
            </p>
          </div>

          <div className="card p-6">
            <div style={{ color: "var(--accent-info)", marginBottom: "1rem" }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              Evidence-Grounded Research
            </h3>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Generated findings are grounded against retrieved document evidence and accompanied by source citations.
            </p>
          </div>
        </div>
      </section>

      {}
      <footer style={{ borderTop: "1px solid var(--border-subtle)", padding: "2.5rem 2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.825rem" }}>
        <p>© 2026 FinSentry AI. Enterprise Financial Research Platform.</p>
        <p style={{ marginTop: "0.5rem" }}>Engineered with React, TypeScript, FastAPI, Celery, CrewAI &amp; MongoDB Atlas.</p>
      </footer>
    </div>
  );
}
