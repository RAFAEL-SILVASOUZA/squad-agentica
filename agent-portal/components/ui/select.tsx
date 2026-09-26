"use client";

import * as React from "react";

/**
 * Select (design system §2.3).
 * Label opcional; erro com aria-describedby.
 */
export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
  onValueChange?: (value: string) => void;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  function Select(
    {
      label,
      error,
      options,
      placeholder,
      onValueChange,
      id,
      className,
      style,
      value,
      onChange,
      ...rest
    },
    ref
  ) {
    const selectId =
      id ?? (label ? `select-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
    const errorId = error ? `${selectId}-error` : undefined;
    const describedBy = errorId;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {label && (
          <label
            htmlFor={selectId}
            style={{
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--text)",
            }}
          >
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={className}
          value={value}
          aria-describedby={describedBy}
          aria-invalid={!!error}
          onChange={(e) => {
            onChange?.(e);
            onValueChange?.(e.target.value);
          }}
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
            cursor: "pointer",
            ...style,
          }}
          {...rest}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && (
          <p id={errorId} style={{ fontSize: "12px", color: "var(--error)", margin: 0 }}>
            {error}
          </p>
        )}
      </div>
    );
  }
);
