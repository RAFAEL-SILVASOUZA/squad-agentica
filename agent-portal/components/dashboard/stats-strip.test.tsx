import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatsStrip } from "./stats-strip";

const baseStats = {
  runningPipelines: 2,
  recentRuns: 5,
  completedRuns: 3,
  pendingApprovals: 4,
};

describe("StatsStrip", () => {
  it("renders all four stat values", () => {
    render(<StatsStrip stats={baseStats} />);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("renders all four labels", () => {
    render(<StatsStrip stats={baseStats} />);
    expect(screen.getByText("Execuções em andamento")).toBeInTheDocument();
    expect(screen.getByText("Concluídas (24h)")).toBeInTheDocument();
    expect(screen.getByText("Completadas")).toBeInTheDocument();
    expect(screen.getByText("Aprovações pendentes")).toBeInTheDocument();
  });

  it("links the running card to /pipelines?run=running", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /execuções em andamento: 2/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines?run=running");
  });

  it("links the 24h card to /pipelines?since=24h", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /concluídas \(24h\): 5/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines?since=24h");
  });

  it("links the completed card to /pipelines?run=completed", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /completadas: 3/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines?run=completed");
  });

  it("links the approvals card to /approvals", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /aprovações pendentes: 4/i,
    });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("shows zero values when stats are zero", () => {
    render(
      <StatsStrip
        stats={{
          runningPipelines: 0,
          recentRuns: 0,
          completedRuns: 0,
          pendingApprovals: 0,
        }}
      />
    );
    expect(screen.getAllByText("0")).toHaveLength(4);
  });

  it("shows skeletons while loading", () => {
    const { container } = render(<StatsStrip stats={baseStats} loading />);
    expect(container.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });
});
