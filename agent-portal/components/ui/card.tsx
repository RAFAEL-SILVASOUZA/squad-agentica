"use client";

import * as React from "react";

/**
 * Card (design system §2.7/§2.8).
 * Container com border, radius, padding.
 * Variantes: default (card de agente) | stat (card de estatística).
 */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "stat";
  hoverable?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  function Card({ variant = "default", hoverable = false, children, className, style, ...rest }, ref) {
    const base: React.CSSProperties = {
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius)",
      position: "relative",
      overflow: "hidden",
    };

    const variantStyles: React.CSSProperties =
      variant === "stat"
        ? {
            padding: "12px 14px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }
        : {
            padding: "14px",
            display: "flex",
            flexDirection: "column",
            minHeight: 128,
          };

    const hoverStyles: React.CSSProperties = hoverable
      ? {
          cursor: "pointer",
          transition: "box-shadow var(--transition), border-color var(--transition)",
        }
      : {};

    return (
      <div
        ref={ref}
        className={className}
        style={{ ...base, ...variantStyles, ...hoverStyles, ...style }}
        onMouseEnter={(e) => {
          if (hoverable) {
            e.currentTarget.style.boxShadow = "var(--shadow)";
            e.currentTarget.style.borderColor = "var(--accent)";
          }
          rest.onMouseEnter?.(e);
        }}
        onMouseLeave={(e) => {
          if (hoverable) {
            e.currentTarget.style.boxShadow = "";
            e.currentTarget.style.borderColor = "var(--border)";
          }
          rest.onMouseLeave?.(e);
        }}
        {...rest}
      >
        {children}
      </div>
    );
  }
);
