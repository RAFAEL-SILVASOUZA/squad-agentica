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
    expect(screen.getByText("Pipelines em execução")).toBeInTheDocument();
    expect(screen.getByText("Runs nas últimas 24h")).toBeInTheDocument();
    expect(screen.getByText("Runs concluídos")).toBeInTheDocument();
    expect(screen.getByText("Aprovações pendentes")).toBeInTheDocument();
  });

  it("links running pipelines card to the monitor of the running pipeline", () => {
    render(
      <StatsStrip
        stats={baseStats}
        runningPipelineId="pipe-1"
        recentRunPipelineId="pipe-2"
      />
    );
    const link = screen.getByRole("link", {
      name: /pipelines em execução: 2/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines/pipe-1/run");
  });

  it("links approvals card to /approvals", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /aprovações pendentes: 4/i,
    });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("falls back to /approvals when no running pipeline id", () => {
    render(<StatsStrip stats={baseStats} />);
    const link = screen.getByRole("link", {
      name: /pipelines em execução: 2/i,
    });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("links recent runs card to the monitor of the recent run pipeline", () => {
    render(
      <StatsStrip stats={baseStats} recentRunPipelineId="pipe-9" />
    );
    const link = screen.getByRole("link", {
      name: /runs nas últimas 24h: 5/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines/pipe-9/run");
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
});
