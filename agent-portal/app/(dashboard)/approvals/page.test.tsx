import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ApprovalsPage from "./page";
import { ToastProvider } from "@/components/ui/toast";

// Mock ApprovalQueue to isolate the page's own logic.
const mockQueueRender = vi.fn();
vi.mock("@/components/approvals/approval-queue", () => ({
  ApprovalQueue: (props: { status?: string; onPendingCountChange?: (count: number) => void }) => {
    mockQueueRender(props);
    return <div data-testid="approval-queue" />;
  },
}));

function renderPage() {
  return render(
    <ToastProvider>
      <ApprovalsPage />
    </ToastProvider>
  );
}

describe("ApprovalsPage", () => {
  it("renders the page title", () => {
    renderPage();
    expect(screen.getByText("Aprovações")).toBeInTheDocument();
  });

  it("renders a subtitle with context", () => {
    renderPage();
    expect(screen.getByText(/aguardando sua decisão|fila de aprovações/i)).toBeInTheDocument();
  });

  it("renders the ApprovalQueue", () => {
    renderPage();
    expect(screen.getByTestId("approval-queue")).toBeInTheDocument();
  });

  it("passes onPendingCountChange callback to ApprovalQueue", () => {
    renderPage();
    expect(mockQueueRender).toHaveBeenCalled();
    const props = mockQueueRender.mock.calls[0][0];
    expect(typeof props.onPendingCountChange).toBe("function");
  });

  it("renders tabs Pendentes and Respondidas", () => {
    renderPage();
    expect(screen.getByRole("tab", { name: /Pendentes/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Respondidas/ })).toBeInTheDocument();
  });
});
