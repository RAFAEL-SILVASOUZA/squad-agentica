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

function TestErrorConsumer() {
  const { addToast } = useToast();
  return (
    <button
      onClick={() =>
        addToast("error", "Não foi possível salvar o agente", {
          detail: "HTTP 404 · POST /api/agents/chat/confirm",
        })
      }
    >
      Add error toast
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

  it("erro fica em aria-live=assertive e some depois de 8000 ms", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <TestErrorConsumer />
      </ToastProvider>
    );
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Add error toast" }));
    });
    const toast = screen.getByRole("alert");
    expect(toast).toHaveTextContent("Não foi possível salvar o agente");
    expect(
      document.querySelector('[aria-live="assertive"]')
    ).not.toBeNull();
    act(() => {
      vi.advanceTimersByTime(7999);
    });
    expect(screen.getByText("Não foi possível salvar o agente")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByText("Não foi possível salvar o agente")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("Ver detalhes mostra o detalhe do erro", () => {
    render(
      <ToastProvider>
        <TestErrorConsumer />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Add error toast" }));
    expect(screen.queryByText(/HTTP 404/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes" }));
    expect(screen.getByText(/HTTP 404/)).toBeVisible();
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
