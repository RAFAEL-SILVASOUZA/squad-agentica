"use client";

import * as React from "react";

/**
 * Input de texto (design system §2.2).
 * Label opcional; erro com aria-describedby.
 */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input(
    { label, error, hint, id, className, style, ...rest },
    ref
  ) {
    const inputId = id ?? (label ? `input-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
    const errorId = error ? `${inputId}-error` : undefined;
    const hintId = hint ? `${inputId}-hint` : undefined;
    const describedBy =
      [errorId, hintId].filter(Boolean).join(" ") || undefined;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {label && (
          <label
            htmlFor={inputId}
            style={{
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--text)",
            }}
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={className}
          aria-describedby={describedBy}
          aria-invalid={!!error}
          style={{
            padding: "10px 14px",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${error ? "var(--error)" : "var(--border)"}`,
            background: "var(--bg-elevated)",
            color: "var(--text)",
            fontSize: "13px",
            fontFamily: "var(--font)",
            outline: "none",
            transition: "border-color var(--transition)",
            width: "100%",
            ...style,
          }}
          {...rest}
        />
        {hint && !error && (
          <p id={hintId} style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
            {hint}
          </p>
        )}
        {error && (
          <p id={errorId} style={{ fontSize: "12px", color: "var(--error)", margin: 0 }}>
            {error}
          </p>
        )}
      </div>
    );
  }
);
