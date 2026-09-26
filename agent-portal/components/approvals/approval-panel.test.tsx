import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ApprovalPanel } from "./approval-panel";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import type { ApprovalRequest } from "@/lib/types";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockList = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string; details?: Record<string, unknown> }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
      this.details = body.details;
    }
  },
}));

// ─── Test data ───────────────────────────────────────────────────────────────

function makeApproval(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    id: "appr-1",
    pipelineId: "pipe-1",
    agentId: "agent-1",
    checkpointId: "cp-1",
    message: "Aprovar deploy para produção?",
    context: { output: "build #47" },
    status: "pending",
    channel: "in-app",
    sentAt: "2026-09-26T10:00:00Z",
    retryCount: 0,
    maxRetries: 3,
    attemptedChannels: ["in-app"],
    fallbackChannel: null,
    timeoutSeconds: 300,
    ...overrides,
  } as ApprovalRequest;
}

function renderPanel(props: Partial<React.ComponentProps<typeof ApprovalPanel>> = {}) {
  const utils = render(
    <ToastProvider>
      <ApprovalPanel {...props} />
    </ToastProvider>
  );
  return utils;
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ApprovalPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
  });

  it("renders loading skeletons on initial load", () => {
    mockList.mockReturnValue(new Promise(() => {})); // never resolves
    renderPanel();
    // Should show skeleton, not empty state
    expect(screen.queryByText("Nenhuma aprovação pendente")).not.toBeInTheDocument();
  });

  it("renders empty state when no pending approvals", async () => {
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText("Nenhuma aprovação pendente")).toBeInTheDocument();
    });
  });

  it("renders approval cards with message, pipeline, node, and time", async () => {
    const approval = makeApproval({
      message: "Aprovar deploy?",
      pipelineId: "pipe-42",
    } as Partial<ApprovalRequest> & { nodeId?: string });
    (approval as unknown as Record<string, unknown>).nodeId = "node-7";
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText("Aprovar deploy?")).toBeInTheDocument();
    });
    expect(screen.getByText(/pipe-42/)).toBeInTheDocument();
    expect(screen.getByText(/node-7/)).toBeInTheDocument();
  });

  it("shows urgent styling for approvals with warning context", async () => {
    const approval = makeApproval({
      context: { urgent: true },
    });
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText("Aprovar deploy para produção?")).toBeInTheDocument();
    });
    // The card should have a warning left border (urgent)
    const card = screen.getByText("Aprovar deploy para produção?").closest("[data-approval-card]");
    expect(card).toHaveAttribute("data-urgent", "true");
  });

  it("calls respond with approved when Aprovar is clicked", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    mockPost.mockResolvedValue({ approvalId: "appr-1", status: "approved", respondedAt: "2026-09-26T11:00:00Z" });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /aprovar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /aprovar/i }));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/approvals/appr-1/respond",
        { decision: "approved", response: null }
      );
    });
  });

  it("calls respond with rejected when Rejeitar is clicked", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    mockPost.mockResolvedValue({ approvalId: "appr-1", status: "rejected", respondedAt: "2026-09-26T11:00:00Z" });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /rejeitar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /rejeitar/i }));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/approvals/appr-1/respond",
        { decision: "rejected", response: null }
      );
    });
  });

  it("opens argument textarea when Argumentar is clicked", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /argumentar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /argumentar/i }));
    // Textarea should appear
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("submits revised with response text when argument is submitted", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    mockPost.mockResolvedValue({ approvalId: "appr-1", status: "revised", respondedAt: "2026-09-26T11:00:00Z" });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /argumentar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /argumentar/i }));
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Precisa corrigir o bug antes" } });
    // Submit the argument (button changes to "Enviar argumento" or similar)
    const submitBtn = screen.getByRole("button", { name: /enviar argumento|enviar/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/approvals/appr-1/respond",
        { decision: "revised", response: "Precisa corrigir o bug antes" }
      );
    });
  });

  it("disables submit argument button when textarea is empty", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /argumentar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /argumentar/i }));
    const submitBtn = screen.getByRole("button", { name: /enviar argumento|enviar/i });
    expect(submitBtn).toBeDisabled();
  });

  it("shows toast on 409 already_responded", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    const apiError = new ApiError(409, { error: "conflict", code: "already_responded" });
    mockPost.mockRejectedValue(apiError);
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /aprovar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /aprovar/i }));
    await waitFor(() => {
      expect(screen.getByText(/já respondida/i)).toBeInTheDocument();
    });
  });

  it("shows toast on 409 for cancelled run", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    const apiError = new ApiError(409, { error: "conflict", code: "already_responded" });
    mockPost.mockRejectedValue(apiError);
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /rejeitar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /rejeitar/i }));
    await waitFor(() => {
      expect(screen.getByText(/já respondida|cancelada/i)).toBeInTheDocument();
    });
  });

  it("links to the run monitor", async () => {
    const approval = makeApproval({ pipelineId: "pipe-99" });
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText("Aprovar deploy para produção?")).toBeInTheDocument();
    });
    const monitorLink = screen.getByRole("link", { name: /monitor/i });
    expect(monitorLink).toHaveAttribute("href", "/pipelines/pipe-99/run");
  });

  it("calls DELETE when Cancelar is clicked", async () => {
    const approval = makeApproval();
    mockList.mockResolvedValue({ items: [approval], total: 1, page: 1, limit: 20 });
    mockDelete.mockResolvedValue({ approvalId: "appr-1", status: "cancelled" });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /cancelar/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/approvals/appr-1");
    });
  });

  it("shows error state with retry on fetch failure", async () => {
    mockList.mockRejectedValue(new Error("network error"));
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText("network error")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("refetches on retry button click", async () => {
    mockList.mockRejectedValueOnce(new Error("network error"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2);
    });
  });
});
