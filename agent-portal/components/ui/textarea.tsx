"use client";

import * as React from "react";

/**
 * Textarea (design system §2.4).
 * Label opcional; erro com aria-describedby.
 */
export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    { label, error, hint, id, className, style, rows = 4, ...rest },
    ref
  ) {
    const textareaId =
      id ??
      (label ? `textarea-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
    const errorId = error ? `${textareaId}-error` : undefined;
    const hintId = hint ? `${textareaId}-hint` : undefined;
    const describedBy =
      [errorId, hintId].filter(Boolean).join(" ") || undefined;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {label && (
          <label
            htmlFor={textareaId}
            style={{
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--text)",
            }}
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={className}
          rows={rows}
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
            resize: "vertical",
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
