"use client";

import * as React from "react";

/**
 * Toggle (design system §2.5).
 * Switch on/off com label.
 */
export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  id?: string;
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  id,
}: ToggleProps) {
  const toggleId = id ?? `toggle-${label.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        padding: "8px 0",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <label
          htmlFor={toggleId}
          style={{
            fontSize: "13px",
            fontWeight: 500,
            color: "var(--text)",
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          {label}
        </label>
        {description && (
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            {description}
          </span>
        )}
      </div>
      <button
        id={toggleId}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        style={{
          width: 40,
          height: 22,
          borderRadius: 11,
          border: "1px solid var(--border)",
          background: checked ? "var(--accent)" : "var(--bg-hover)",
          position: "relative",
          cursor: disabled ? "not-allowed" : "pointer",
          transition: "background var(--transition), border-color var(--transition)",
          flexShrink: 0,
          opacity: disabled ? 0.6 : 1,
          padding: 0,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            top: 2,
            left: checked ? 20 : 2,
            width: 16,
            height: 16,
            borderRadius: "50%",
            background: "#fff",
            transition: "left var(--transition)",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
          }}
        />
      </button>
    </div>
  );
}
