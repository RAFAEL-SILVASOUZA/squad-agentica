"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";

/**
 * Toast (design system §2.16).
 * Container fixo bottom-right. Tipos: success | error | info | warning.
 * Auto-dismiss em 3s.
 */
export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  toasts: ToastItem[];
  addToast: (type: ToastType, message: string) => void;
  removeToast: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast deve ser usado dentro de <ToastProvider>");
  }
  return ctx;
}

const TOAST_ICONS: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle2 size={16} aria-hidden="true" style={{ color: "var(--success)" }} />,
  error: <XCircle size={16} aria-hidden="true" style={{ color: "var(--error)" }} />,
  info: <Info size={16} aria-hidden="true" style={{ color: "var(--info)" }} />,
  warning: <AlertTriangle size={16} aria-hidden="true" style={{ color: "var(--warning)" }} />,
};

const TOAST_BORDERS: Record<ToastType, string> = {
  success: "var(--success)",
  error: "var(--error)",
  info: "var(--info)",
  warning: "var(--warning)",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);

  const removeToast = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = React.useCallback(
    (type: ToastType, message: string) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, type, message }]);

      setTimeout(() => removeToast(id), 3000);
    },
    [removeToast]
  );

  const value = React.useMemo(
    () => ({ toasts, addToast, removeToast }),
    [toasts, addToast, removeToast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {typeof document !== "undefined" &&
        createPortal(
          <div
            aria-live="polite"
            style={{
              position: "fixed",
              bottom: 20,
              right: 20,
              zIndex: 9999,
              pointerEvents: "none",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            {toasts.map((toast) => (
              <div
                key={toast.id}
                role="status"
                style={{
                  pointerEvents: "auto",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "12px 18px",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderLeft: `3px solid ${TOAST_BORDERS[toast.type]}`,
                  boxShadow: "var(--shadow-lg)",
                  fontSize: "13px",
                  color: "var(--text)",
                  maxWidth: 360,
                  animation: "toast-in 0.3s ease",
                }}
              >
                {TOAST_ICONS[toast.type]}
                <span style={{ flex: 1 }}>{toast.message}</span>
                <button
                  onClick={() => removeToast(toast.id)}
                  aria-label="Fechar notificação"
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: 2,
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}
