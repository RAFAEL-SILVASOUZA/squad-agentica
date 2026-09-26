import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RecentRuns, type RecentRunItem } from "./recent-runs";
import type { PipelineRun } from "@/lib/types";

function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: "run-1",
    pipelineId: "pipe-1",
    threadId: "thread-1",
    status: "running",
    startedAt: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

describe("RecentRuns", () => {
  it("renders loading skeletons", () => {
    render(<RecentRuns items={[]} loading />);
    expect(screen.queryByText("Nenhuma execução ainda")).not.toBeInTheDocument();
  });

  it("renders empty state when no items and not loading", () => {
    render(<RecentRuns items={[]} />);
    expect(screen.getByText("Nenhuma execução ainda")).toBeInTheDocument();
  });

  it("renders run with pipeline name and status", () => {
    const items: RecentRunItem[] = [
      { run: makeRun(), pipelineName: "Pipeline A" },
    ];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("Pipeline A")).toBeInTheDocument();
    expect(screen.getByText("Executando")).toBeInTheDocument();
  });

  it("falls back to pipelineId when no name", () => {
    const items: RecentRunItem[] = [{ run: makeRun({ pipelineId: "pipe-42" }) }];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("pipe-42")).toBeInTheDocument();
  });

  it("links to the monitor of the run pipeline", () => {
    const items: RecentRunItem[] = [
      { run: makeRun({ pipelineId: "pipe-7" }), pipelineName: "P" },
    ];
    render(<RecentRuns items={items} />);
    const link = screen.getByRole("link", {
      name: /abrir monitor da pipeline p/i,
    });
    expect(link).toHaveAttribute("href", "/pipelines/pipe-7/run");
  });

  it("shows completed status label", () => {
    const items: RecentRunItem[] = [
      { run: makeRun({ status: "completed" }) },
    ];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("Concluído")).toBeInTheDocument();
  });

  it("shows failed status label", () => {
    const items: RecentRunItem[] = [{ run: makeRun({ status: "failed" }) }];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("Falhou")).toBeInTheDocument();
  });

  it("shows paused status label", () => {
    const items: RecentRunItem[] = [{ run: makeRun({ status: "paused" }) }];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("Pausado")).toBeInTheDocument();
  });

  it("shows cancelled status label", () => {
    const items: RecentRunItem[] = [
      { run: makeRun({ status: "cancelled" }) },
    ];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("Cancelado")).toBeInTheDocument();
  });

  it("renders multiple runs", () => {
    const items: RecentRunItem[] = [
      { run: makeRun({ id: "r1", pipelineId: "p1" }), pipelineName: "One" },
      { run: makeRun({ id: "r2", pipelineId: "p2" }), pipelineName: "Two" },
    ];
    render(<RecentRuns items={items} />);
    expect(screen.getByText("One")).toBeInTheDocument();
    expect(screen.getByText("Two")).toBeInTheDocument();
  });
});
