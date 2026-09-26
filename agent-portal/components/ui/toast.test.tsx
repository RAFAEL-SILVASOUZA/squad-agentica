import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ToastProvider, useToast } from "./toast";

function TestToastConsumer() {
  const { addToast } = useToast();
  return (
    <button onClick={() => addToast("success", "Saved!")}>
      Add toast
    </button>
  );
}

describe("Toast", () => {
  it("renders children inside provider", () => {
    render(
      <ToastProvider>
        <div>Child content</div>
      </ToastProvider>
    );
    expect(screen.getByText("Child content")).toBeInTheDocument();
  });

  it("adds a toast when addToast is called", () => {
    render(
      <ToastProvider>
        <TestToastConsumer />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Add toast" }));
    expect(screen.getByText("Saved!")).toBeInTheDocument();
  });

  it("shows success icon for success toast", () => {
    render(
      <ToastProvider>
        <TestToastConsumer />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Add toast" }));
    const toast = screen.getByRole("status");
    expect(toast).toBeInTheDocument();
  });

  it("removes toast when close button is clicked", () => {
    render(
      <ToastProvider>
        <TestToastConsumer />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Add toast" }));
    const closeBtn = screen.getByRole("button", { name: "Fechar notificação" });
    fireEvent.click(closeBtn);
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
  });

  it("auto-dismisses toast after 3 seconds", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <TestToastConsumer />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Add toast" }));
    });
    expect(screen.getByText("Saved!")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});
