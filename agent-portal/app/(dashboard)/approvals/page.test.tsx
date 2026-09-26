import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ApprovalsPage from "./page";
import { ToastProvider } from "@/components/ui/toast";

// Mock ApprovalPanel to isolate the page's own logic.
const mockPanelRender = vi.fn();
vi.mock("@/components/approvals/approval-panel", () => ({
  ApprovalPanel: (props: { onPendingCountChange?: (count: number) => void }) => {
    mockPanelRender(props);
    return <div data-testid="approval-panel" />;
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

  it("renders the ApprovalPanel", () => {
    renderPage();
    expect(screen.getByTestId("approval-panel")).toBeInTheDocument();
  });

  it("passes onPendingCountChange callback to ApprovalPanel", () => {
    renderPage();
    expect(mockPanelRender).toHaveBeenCalled();
    const props = mockPanelRender.mock.calls[0][0];
    expect(typeof props.onPendingCountChange).toBe("function");
  });
});
