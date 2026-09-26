import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Badge } from "./badge";

describe("Badge", () => {
  it("renders with status and label", () => {
    render(<Badge status="running" label="Running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders dot with correct color for success", () => {
    render(<Badge status="success" label="OK" />);
    const dot = screen.getByText("OK").previousElementSibling as HTMLElement;
    expect(dot).toHaveStyle({ background: "var(--success)" });
  });

  it("renders dot with correct color for error", () => {
    render(<Badge status="error" label="Error" />);
    const dot = screen.getByText("Error").previousElementSibling as HTMLElement;
    expect(dot).toHaveStyle({ background: "var(--error)" });
  });

  it("renders dot with correct color for warning", () => {
    render(<Badge status="warning" label="Warning" />);
    const dot = screen.getByText("Warning").previousElementSibling as HTMLElement;
    expect(dot).toHaveStyle({ background: "var(--warning)" });
  });

  it("renders dot with correct color for info", () => {
    render(<Badge status="info" label="Info" />);
    const dot = screen.getByText("Info").previousElementSibling as HTMLElement;
    expect(dot).toHaveStyle({ background: "var(--info)" });
  });

  it("applies pulse animation when pulse is true", () => {
    render(<Badge status="running" label="Running" pulse />);
    const dot = screen.getByText("Running").previousElementSibling as HTMLElement;
    expect(dot).toHaveStyle({ animation: "pulse 2s ease-in-out infinite" });
  });

  it("does not apply pulse animation by default", () => {
    render(<Badge status="running" label="Running" />);
    const dot = screen.getByText("Running").previousElementSibling as HTMLElement;
    expect(dot.style.animation).toBe("");
  });

  it("renders without label (dot only)", () => {
    render(<Badge status="success" />);
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
  });
});
