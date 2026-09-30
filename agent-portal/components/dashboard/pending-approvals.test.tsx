import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PendingApprovals } from "./pending-approvals";
import type { ApprovalRequest } from "@/lib/types";

function makeApproval(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    id: "appr-1",
    pipelineId: "pipe-1",
    agentId: "agent-1",
    checkpointId: "cp-1",
    message: "Aprovar deploy?",
    context: {},
    status: "pending",
    channel: "in-app",
    sentAt: "2026-09-26T10:00:00Z",
    retryCount: 0,
    maxRetries: 3,
    attemptedChannels: ["in-app"],
    fallbackChannel: null,
    timeoutSeconds: 300,
    ...overrides,
  };
}

describe("PendingApprovals", () => {
  it("renders loading skeletons", () => {
    const { container } = render(<PendingApprovals items={[]} loading />);
    expect(screen.queryByText("Nenhuma aprovação pendente")).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });

  it("renders empty state when no items and not loading", () => {
    render(<PendingApprovals items={[]} />);
    expect(screen.getByText("Nenhuma aprovação pendente")).toBeInTheDocument();
  });

  it("renders approval message and pipeline id", () => {
    render(<PendingApprovals items={[makeApproval()]} />);
    expect(screen.getByText("Aprovar deploy?")).toBeInTheDocument();
    expect(screen.getByText(/Pipeline pipe-1/)).toBeInTheDocument();
  });

  it("links to /approvals", () => {
    render(<PendingApprovals items={[makeApproval()]} />);
    const link = screen.getByRole("link", {
      name: /abrir aprovações: aprovar deploy\?/i,
    });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("renders multiple approvals", () => {
    render(
      <PendingApprovals
        items={[
          makeApproval({ id: "a1", message: "Primeira" }),
          makeApproval({ id: "a2", message: "Segunda" }),
        ]}
      />
    );
    expect(screen.getByText("Primeira")).toBeInTheDocument();
    expect(screen.getByText("Segunda")).toBeInTheDocument();
  });

  it("shows relative time for recent approval", () => {
    const now = new Date();
    const fiveMinAgo = new Date(now.getTime() - 5 * 60_000).toISOString();
    render(<PendingApprovals items={[makeApproval({ sentAt: fiveMinAgo })]} />);
    expect(screen.getByText(/há 5 min/)).toBeInTheDocument();
  });

  it("shows 'agora' for missing sentAt", () => {
    const approval = { ...makeApproval(), sentAt: undefined } as unknown as ApprovalRequest;
    render(<PendingApprovals items={[approval]} />);
    expect(screen.getByText(/agora/)).toBeInTheDocument();
  });
});
