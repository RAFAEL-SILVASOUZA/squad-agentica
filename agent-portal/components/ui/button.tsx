"use client";

import * as React from "react";

/**
 * Botão base (design system §2.1).
 * Variantes: default | primary | sm.
 * Sem emojis; ícones via lucide-react com aria-label.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary";
  size?: "lg" | "sm";
  loading?: boolean;
}

export function Button({
  variant = "default",
  size = "lg",
  loading = false,
  disabled,
  children,
  className,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;

  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    borderRadius: "var(--radius-sm)",
    fontSize: "13px",
    fontWeight: 500,
    border: "1px solid var(--border)",
    background: "var(--bg-card)",
    color: "var(--text)",
    cursor: isDisabled ? "not-allowed" : "pointer",
    transition: "background var(--transition), border-color var(--transition), color var(--transition)",
    opacity: isDisabled ? 0.6 : 1,
    fontFamily: "var(--font)",
    lineHeight: 1.4,
  };

  const sizeStyles: React.CSSProperties =
    size === "sm"
      ? { padding: "6px 12px" }
      : { padding: "8px 16px" };

  const variantStyles: React.CSSProperties =
    variant === "primary"
      ? {
          background: "var(--accent)",
          // `border` completo (não `borderColor`): misturar shorthand e
          // longhand gera aviso do React quando a variante muda no rerender.
          border: "1px solid var(--accent)",
          color: "#fff",
        }
      : {};

  return (
    <button
      className={className}
      style={{ ...base, ...sizeStyles, ...variantStyles, ...style }}
      disabled={isDisabled}
      aria-disabled={isDisabled}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden="true"
          style={{
            width: 14,
            height: 14,
            border: "2px solid currentColor",
            borderTopColor: "transparent",
            borderRadius: "50%",
            display: "inline-block",
            animation: "spin 1s linear infinite",
          }}
        />
      ) : null}
      {children}
    </button>
  );
}
