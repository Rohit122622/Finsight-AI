








import { useState, useCallback, createContext, useContext, type ReactNode } from "react";

export type ToastType = "success" | "warning" | "error";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  addToast: () => {},
});

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = "success") => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div
        style={{
          position: "fixed",
          top: "1rem",
          right: "1rem",
          zIndex: 9999,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          maxWidth: "360px",
        }}
      >
        {toasts.map((toast) => {
          const bg =
            toast.type === "success"
              ? "rgba(5, 150, 105, 0.95)"
              : toast.type === "error"
              ? "rgba(220, 38, 38, 0.95)"
              : "rgba(245, 158, 11, 0.95)";
          const color =
            toast.type === "success"
              ? "#D1FAE5"
              : toast.type === "error"
              ? "#FEE2E2"
              : "#FEF3C7";
          const border =
            toast.type === "success"
              ? "rgba(16, 185, 129, 0.5)"
              : toast.type === "error"
              ? "rgba(239, 68, 68, 0.5)"
              : "rgba(245, 158, 11, 0.5)";
          const icon = toast.type === "success" ? "✓" : toast.type === "error" ? "✕" : "⚠";

          return (
            <div
              key={toast.id}
              className="animate-toast"
              style={{
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                fontSize: "0.875rem",
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
                background: bg,
                color: color,
                border: `1px solid ${border}`,
                boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
              }}
              onClick={() => removeToast(toast.id)}
            >
              <span style={{ fontSize: "1rem" }}>{icon}</span>
              {toast.message}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
