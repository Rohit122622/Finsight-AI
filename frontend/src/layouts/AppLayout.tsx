









import { useState, useRef, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useToast } from "../components/Toast";
import { useTheme } from "../context/ThemeContext";



function IconDashboard() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function IconSessions() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
      <path d="M6 6h10" />
      <path d="M6 10h10" />
    </svg>
  );
}

function IconResearch() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M8 9h8" />
      <path d="M8 13h5" />
    </svg>
  );
}

function IconDocuments() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </svg>
  );
}

function IconReports() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function IconUser() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function IconLogout() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
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



const primaryNav = [
  { to: "/dashboard", label: "Executive Dashboard", icon: <IconDashboard /> },
  { to: "/sessions", label: "Workspaces & Sessions", icon: <IconSessions /> },
  { to: "/research", label: "Research Intelligence", icon: <IconResearch /> },
  { to: "/documents", label: "Document Ingestion", icon: <IconDocuments /> },
  { to: "/reports", label: "Analysis Reports", icon: <IconReports /> },
];

export default function AppLayout() {
  const { user, logout } = useAuthStore();
  const { addToast } = useToast();
  const { resolvedTheme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const [profileOpen, setProfileOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = async () => {
    setProfileOpen(false);
    await logout();
    addToast("Logged out successfully", "success");
    navigate("/login", { replace: true });
  };

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "FA";

  
  const getBreadcrumbs = () => {
    const path = location.pathname;
    if (path === "/dashboard") return "Command Center / Overview";
    if (path === "/sessions") return "Workspaces / Financial Sessions";
    if (path.startsWith("/sessions/")) return "Workspaces / Active Session";
    if (path === "/research") return "Intelligence / Interactive Research";
    if (path === "/documents") return "Repository / Document Pipeline";
    if (path === "/reports") return "Deliverables / Executive Reports";
    if (path === "/profile") return "Account / Settings & Security";
    return "FinSentry AI";
  };

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw", overflow: "hidden", background: "var(--bg-base)" }}>
      {}
      <aside
        style={{
          width: "250px",
          height: "100vh",
          backgroundColor: "var(--bg-sidebar)",
          borderRight: "1px solid var(--border-subtle)",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
          zIndex: 40,
        }}
      >
        {}
        <div
          style={{
            padding: "1.25rem 1.25rem 1rem",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            borderBottom: "1px solid var(--border-subtle)",
            cursor: "pointer",
          }}
          onClick={() => navigate("/dashboard")}
        >
          <div
            style={{
              padding: "6px",
              borderRadius: "8px",
              backgroundColor: "var(--brand-primary-light)",
              color: "var(--brand-primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <IconShield />
          </div>
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
              FinSentry <span style={{ color: "var(--brand-primary)" }}>AI</span>
            </div>
            <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>
              Financial Intelligence
            </div>
          </div>
        </div>

        {}
        <nav style={{ flex: 1, padding: "1rem 0.75rem", overflowY: "auto", display: "flex", flexDirection: "column", gap: "4px" }}>
          <div style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", padding: "0 0.5rem 0.5rem" }}>
            Navigation
          </div>

          {primaryNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                padding: "0.625rem 0.75rem",
                borderRadius: "6px",
                fontSize: "0.85rem",
                fontWeight: isActive ? 600 : 500,
                color: isActive ? "var(--brand-primary)" : "var(--text-secondary)",
                backgroundColor: isActive ? "var(--brand-primary-light)" : "transparent",
                borderLeft: isActive ? "3px solid var(--brand-primary)" : "3px solid transparent",
                textDecoration: "none",
                transition: "all 0.15s ease",
              })}
            >
              <span style={{ display: "flex", alignItems: "center" }}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {}
        <div
          style={{
            padding: "0.875rem 0.75rem",
            borderTop: "1px solid var(--border-subtle)",
            backgroundColor: "var(--bg-surface)",
            marginTop: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          {}
          <div
            onClick={() => navigate("/profile")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.625rem",
              padding: "0.5rem",
              borderRadius: "6px",
              cursor: "pointer",
              transition: "background 0.15s ease",
            }}
            className="hover:bg-[var(--bg-surface-hover)]"
          >
            <div
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                backgroundColor: "var(--brand-primary)",
                color: "#FFFFFF",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.725rem",
                fontWeight: 700,
              }}
            >
              {initials}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {user?.full_name || "Analyst"}
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {user?.email}
              </div>
            </div>
          </div>

          {}
          <button
            onClick={handleLogout}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.625rem",
              padding: "0.5rem 0.75rem",
              width: "100%",
              borderRadius: "6px",
              fontSize: "0.8rem",
              fontWeight: 500,
              color: "var(--accent-risk)",
              backgroundColor: "transparent",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "all 0.15s ease",
              textAlign: "left",
            }}
            className="hover:bg-[var(--accent-risk-light)] hover:border-[rgba(239,68,68,0.25)]"
          >
            <IconLogout />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "100vh", minWidth: 0, overflow: "hidden" }}>
        {}
        <header
          style={{
            height: "54px",
            backgroundColor: "var(--bg-header)",
            backdropFilter: "blur(8px)",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 1.5rem",
            position: "relative",
            flexShrink: 0,
            zIndex: 30,
          }}
        >
          {}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.825rem", fontWeight: 500, color: "var(--text-secondary)" }}>
              {getBreadcrumbs()}
            </span>
          </div>

          {}
          <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
            {}
            <div
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border"
              style={{
                backgroundColor: "var(--brand-primary-light)",
                borderColor: "var(--brand-primary-border)",
                color: "var(--brand-primary)",
              }}
              title="FinSentry AI Institutional Intelligence Engine Online"
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "var(--brand-primary)" }} />
              <span className="text-[11px] font-semibold">System Operational</span>
            </div>

            {}
            <button
              onClick={toggleTheme}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "32px",
                height: "32px",
                borderRadius: "6px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-secondary)",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              className="hover:text-[var(--text-primary)] hover:border-[var(--border-hover)]"
              title={`Switch to ${resolvedTheme === "dark" ? "Light" : "Dark"} mode`}
            >
              {resolvedTheme === "dark" ? <IconSun /> : <IconMoon />}
            </button>

            {}
            <div className="relative" ref={dropdownRef}>
              <div
                onClick={() => setProfileOpen(!profileOpen)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "3px 8px 3px 4px",
                  borderRadius: "20px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-subtle)",
                  cursor: "pointer",
                  userSelect: "none",
                }}
                className="hover:border-[var(--border-hover)]"
              >
                <div
                  style={{
                    width: "26px",
                    height: "26px",
                    borderRadius: "50%",
                    backgroundColor: "var(--brand-primary)",
                    color: "#FFFFFF",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.725rem",
                    fontWeight: 700,
                  }}
                >
                  {initials}
                </div>
                <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--text-primary)" }}>
                  {user?.full_name?.split(" ")[0] || "Account"}
                </span>
              </div>

              {}
              {profileOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "calc(100% + 6px)",
                    right: 0,
                    width: "220px",
                    backgroundColor: "var(--bg-surface)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "8px",
                    boxShadow: "var(--card-shadow)",
                    padding: "0.5rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                    zIndex: 50,
                  }}
                  className="animate-fade-in"
                >
                  <div style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid var(--border-subtle)", marginBottom: "4px" }}>
                    <div style={{ fontSize: "0.825rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      {user?.full_name || "Analyst"}
                    </div>
                    <div style={{ fontSize: "0.725rem", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {user?.email}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setProfileOpen(false);
                      navigate("/profile");
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.5rem 0.75rem",
                      borderRadius: "6px",
                      fontSize: "0.8rem",
                      color: "var(--text-primary)",
                      backgroundColor: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                    className="hover:bg-[var(--bg-surface-alt)]"
                  >
                    <IconUser />
                    <span>Profile & Settings</span>
                  </button>

                  <button
                    onClick={handleLogout}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.5rem 0.75rem",
                      borderRadius: "6px",
                      fontSize: "0.8rem",
                      color: "var(--accent-risk)",
                      backgroundColor: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                    className="hover:bg-[var(--accent-risk-light)]"
                  >
                    <IconLogout />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {}
        <main
          style={{
            flex: 1,
            overflowY: "auto",
            backgroundColor: "var(--bg-base)",
            position: "relative",
          }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
