import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PendingApprovals } from "./pending-approvals";
import { ToastProvider } from "@/components/ui/toast";
import type { ApprovalRequest } from "@/lib/types";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: { post: vi.fn().mockResolvedValue({}) },
}));

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

const show = (props: { items: ApprovalRequest[]; loading?: boolean }) =>
  render(<ToastProvider><PendingApprovals {...props} /></ToastProvider>);

describe("PendingApprovals", () => {
  it("renders loading skeletons", () => {
    const { container } = show({ items: [], loading: true });
    expect(screen.queryByText("Nenhuma aprovação pendente")).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });

  it("renders empty state when no items and not loading", () => {
    show({ items: [] });
    expect(screen.getByText("Nenhuma aprovação pendente")).toBeInTheDocument();
  });

  it("renders approval message and pipeline id", () => {
    show({ items: [makeApproval()] });
    expect(screen.getByText("Aprovar deploy?")).toBeInTheDocument();
    expect(screen.getByText(/Pipeline pipe-1/)).toBeInTheDocument();
  });

  it("links to /approvals", () => {
    show({ items: [makeApproval()] });
    const link = screen.getByRole("link", { name: "Aprovar deploy?" });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("renders multiple approvals", () => {
    show({
      items: [
        makeApproval({ id: "a1", message: "Primeira" }),
        makeApproval({ id: "a2", message: "Segunda" }),
      ],
    });
    expect(screen.getByText("Primeira")).toBeInTheDocument();
    expect(screen.getByText("Segunda")).toBeInTheDocument();
  });

  it("shows relative time for recent approval", () => {
    const now = new Date();
    const fiveMinAgo = new Date(now.getTime() - 5 * 60_000).toISOString();
    show({ items: [makeApproval({ sentAt: fiveMinAgo })] });
    expect(screen.getByText(/há 5 min/)).toBeInTheDocument();
  });

  it("shows 'agora' for missing sentAt", () => {
    const approval = { ...makeApproval(), sentAt: undefined } as unknown as ApprovalRequest;
    show({ items: [approval] });
    expect(screen.getByText(/agora/)).toBeInTheDocument();
  });

  it("has Aprovar and Rejeitar buttons inline", () => {
    show({ items: [makeApproval()] });
    expect(screen.getByRole("button", { name: /Aprovar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rejeitar/ })).toBeInTheDocument();
  });
});
