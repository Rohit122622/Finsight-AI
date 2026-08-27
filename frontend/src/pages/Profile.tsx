import { useAuthStore } from "../store/authStore";
import { useTheme } from "../context/ThemeContext";

function IconUser() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function IconPalette() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="13.5" cy="6.5" r=".5" fill="currentColor" />
      <circle cx="17.5" cy="10.5" r=".5" fill="currentColor" />
      <circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />
      <circle cx="6.5" cy="12.5" r=".5" fill="currentColor" />
      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
    </svg>
  );
}

export default function Profile() {
  const { user } = useAuthStore();
  const { theme, setTheme } = useTheme();

  return (
    <div style={{ padding: "2.5rem 2rem", maxWidth: "960px", margin: "0 auto" }}>
      {}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 700, letterSpacing: "-0.025em" }}>
          Analyst Profile &amp; Settings
        </h1>
        <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
          Manage your account identity, display theme preferences, and review active AI infrastructure.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
        {}
        <div className="card p-6">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
            <div style={{ color: "var(--brand-primary)" }}>
              <IconUser />
            </div>
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Identity &amp; Credentials</h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Authenticated user details</p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem" }}>
            <div>
              <div style={{ fontSize: "0.725rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Full Name
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginTop: "0.2rem" }}>
                {user?.full_name || "Financial Analyst"}
              </div>
            </div>

            <div>
              <div style={{ fontSize: "0.725rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Email Address
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginTop: "0.2rem" }}>
                {user?.email}
              </div>
            </div>

            <div>
              <div style={{ fontSize: "0.725rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Authentication Provider
              </div>
              <div style={{ marginTop: "0.25rem" }}>
                <span className="badge badge-emerald">
                  {user?.provider?.toUpperCase() || "LOCAL"}
                </span>
              </div>
            </div>

            <div>
              <div style={{ fontSize: "0.725rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Account User ID
              </div>
              <div style={{ fontSize: "0.8rem", fontFamily: "var(--font-mono)", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                {user?.id}
              </div>
            </div>
          </div>
        </div>

        {}
        <div className="card p-6">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
            <div style={{ color: "var(--accent-gold)" }}>
              <IconPalette />
            </div>
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Theme &amp; Appearance</h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Choose your preferred interface theme</p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", maxWidth: "540px" }}>
            <button
              onClick={() => setTheme("dark")}
              className={`p-4 rounded-lg border text-left transition-all ${
                theme === "dark" ? "border-[var(--brand-primary)] bg-[var(--brand-primary-light)]" : "border-[var(--border-subtle)] bg-[var(--bg-surface-alt)]"
              }`}
            >
              <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>Dark</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>Bloomberg / Palantir workstation</div>
            </button>

            <button
              onClick={() => setTheme("light")}
              className={`p-4 rounded-lg border text-left transition-all ${
                theme === "light" ? "border-[var(--brand-primary)] bg-[var(--brand-primary-light)]" : "border-[var(--border-subtle)] bg-[var(--bg-surface-alt)]"
              }`}
            >
              <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>Light</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>High-clarity institutional</div>
            </button>

            <button
              onClick={() => setTheme("system")}
              className={`p-4 rounded-lg border text-left transition-all ${
                theme === "system" ? "border-[var(--brand-primary)] bg-[var(--brand-primary-light)]" : "border-[var(--border-subtle)] bg-[var(--bg-surface-alt)]"
              }`}
            >
              <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>System</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>Match operating system</div>
            </button>
          </div>
        </div>

        {}
        <div className="card p-6">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
            <div style={{ color: "var(--accent-info)" }}>
              <IconShield />
            </div>
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Active LLM Provider Architecture</h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Resilient cloud inference &amp; secret protection</p>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div className="p-3 rounded-lg border flex items-center justify-between" style={{ backgroundColor: "var(--bg-surface-alt)", borderColor: "var(--border-subtle)" }}>
              <div>
                <span className="badge badge-emerald" style={{ marginRight: "0.5rem" }}>1. Primary</span>
                <strong style={{ fontSize: "0.85rem" }}>Ollama Cloud (120B)</strong>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>gpt-oss:120b-cloud via https://api.groq.com/openai/v1</span>
              </div>
              <span className="badge badge-emerald">Online</span>
            </div>

            <div className="p-3 rounded-lg border flex items-center justify-between" style={{ backgroundColor: "var(--bg-surface-alt)", borderColor: "var(--border-subtle)" }}>
              <div>
                <span className="badge badge-info" style={{ marginRight: "0.5rem" }}>2. Secondary</span>
                <strong style={{ fontSize: "0.85rem" }}>Google Gemini 2.5 Flash</strong>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>High-speed reasoning fallback</span>
              </div>
              <span className="badge badge-info">Standby</span>
            </div>

            <div className="p-3 rounded-lg border flex items-center justify-between" style={{ backgroundColor: "var(--bg-surface-alt)", borderColor: "var(--border-subtle)" }}>
              <div>
                <span className="badge badge-gold" style={{ marginRight: "0.5rem" }}>3. Tertiary</span>
                <strong style={{ fontSize: "0.85rem" }}>Groq LPUs</strong>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>qwen/qwen3.6-27b / llama-3.3</span>
              </div>
              <span className="badge badge-gold">Standby</span>
            </div>

            <div className="p-3 rounded-lg border flex items-center justify-between" style={{ backgroundColor: "var(--bg-surface-alt)", borderColor: "var(--border-subtle)" }}>
              <div>
                <span className="badge badge-risk" style={{ marginRight: "0.5rem" }}>4. Ultimate Safety</span>
                <strong style={{ fontSize: "0.85rem" }}>Deterministic Offline Rule Engine</strong>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>Zero-outage offline financial extraction</span>
              </div>
              <span className="badge badge-emerald">Ready</span>
            </div>
          </div>

          <div style={{ marginTop: "1rem", padding: "0.75rem", borderRadius: "6px", backgroundColor: "var(--brand-primary-light)", border: "1px solid var(--brand-primary-border)", fontSize: "0.75rem", color: "var(--brand-primary)" }}>
            ✓ <strong>Zero Client Key Policy:</strong> API credentials never traverse to the frontend. All LLM and MongoDB queries are authenticated server-side with strict tenant isolation.
          </div>
        </div>
      </div>
    </div>
  );
}
