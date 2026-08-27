






import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useToast } from "../components/Toast";
import { getGoogleLoginUrl } from "../api/auth";

export default function Register() {
  const navigate = useNavigate();
  const { register, isLoading, error, clearError } = useAuthStore();
  const { addToast } = useToast();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!fullName.trim()) errs.fullName = "Name is required";
    if (!email) errs.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Invalid email format";
    if (!password) errs.password = "Password is required";
    else if (password.length < 8) errs.password = "Password must be at least 8 characters";
    if (password !== confirmPassword) errs.confirmPassword = "Passwords do not match";
    setLocalErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    if (!validate()) return;

    try {
      await register({ full_name: fullName, email, password });
      addToast("Account created successfully!", "success");
      navigate("/dashboard", { replace: true });
    } catch {
      
    }
  };

  const fields = [
    {
      id: "register-name",
      label: "Full Name",
      type: "text",
      value: fullName,
      setter: setFullName,
      error: localErrors.fullName,
      placeholder: "John Doe",
      key: "fullName",
      autoComplete: "name",
    },
    {
      id: "register-email",
      label: "Email",
      type: "email",
      value: email,
      setter: setEmail,
      error: localErrors.email,
      placeholder: "you@example.com",
      key: "email",
      autoComplete: "email",
    },
    {
      id: "register-password",
      label: "Password",
      type: "password",
      value: password,
      setter: setPassword,
      error: localErrors.password,
      placeholder: "Min. 8 characters",
      key: "password",
      autoComplete: "new-password",
    },
    {
      id: "register-confirm",
      label: "Confirm Password",
      type: "password",
      value: confirmPassword,
      setter: setConfirmPassword,
      error: localErrors.confirmPassword,
      placeholder: "Re-enter password",
      key: "confirmPassword",
      autoComplete: "new-password",
    },
  ];

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
          <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>Create account</h1>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
            Get started with FinSentry AI
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

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {fields.map((f) => (
            <div key={f.key}>
              <label
                htmlFor={f.id}
                style={{
                  fontSize: "0.8125rem",
                  fontWeight: 500,
                  marginBottom: "0.375rem",
                  display: "block",
                  color: "var(--color-text-secondary)",
                }}
              >
                {f.label}
              </label>
              <input
                id={f.id}
                type={f.type}
                className={`input ${f.error ? "input-error" : ""}`}
                placeholder={f.placeholder}
                value={f.value}
                onChange={(e) => {
                  f.setter(e.target.value);
                  setLocalErrors((p) => ({ ...p, [f.key]: "" }));
                }}
                autoComplete={f.autoComplete}
              />
              {f.error && (
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--color-amber-500)",
                    marginTop: "0.25rem",
                    display: "block",
                  }}
                >
                  {f.error}
                </span>
              )}
            </div>
          ))}

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
                Creating account…
              </>
            ) : (
              "Create account"
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

        <p
          style={{
            textAlign: "center",
            marginTop: "1.5rem",
            fontSize: "0.8125rem",
            color: "var(--color-text-secondary)",
          }}
        >
          Already have an account?{" "}
          <Link
            to="/login"
            style={{ color: "var(--color-emerald-500)", textDecoration: "none", fontWeight: 500 }}
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
