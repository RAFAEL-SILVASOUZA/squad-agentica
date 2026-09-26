import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AgentChat } from "./agent-chat";
import { ToastProvider } from "@/components/ui/toast";

vi.mock("@/lib/agent-chat", () => ({
  sendAgentChat: vi.fn(),
}));

import { sendAgentChat } from "@/lib/agent-chat";

const sendMock = sendAgentChat as unknown as ReturnType<typeof vi.fn>;

function renderChat(props: Partial<React.ComponentProps<typeof AgentChat>> = {}) {
  return render(
    <ToastProvider>
      <AgentChat
        chatPath="/api/agents/chat"
        draftId={null}
        {...props}
      />
    </ToastProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AgentChat", () => {
  it("shows initial assistant message", () => {
    renderChat({ initialAssistantMessage: "Olá! Como posso ajudar?" });
    expect(screen.getByText("Olá! Como posso ajudar?")).toBeInTheDocument();
  });

  it("sends a message and appends the assistant reply", async () => {
    sendMock.mockImplementation(
      (_path: string, _msg: string, _draft: string | null, cb: any) => {
        cb.onText("Claro, vou montar esse agente.");
        cb.onDone("d-1");
        return Promise.resolve({ rateLimited: false, draftId: "d-1" });
      }
    );

    const onDraftId = vi.fn();
    renderChat({ onDraftId });

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "crie um agente dev" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Claro, vou montar esse agente.")
      ).toBeInTheDocument();
    });

    expect(onDraftId).toHaveBeenCalledWith("d-1");
    expect(sendMock).toHaveBeenCalledWith(
      "/api/agents/chat",
      "crie um agente dev",
      null,
      expect.anything(),
      expect.any(AbortSignal)
    );
  });

  it("propagates config_update to onConfigUpdate", async () => {
    sendMock.mockImplementation(
      (_p: string, _m: string, _d: string | null, cb: any) => {
        cb.onConfigUpdate({ name: "Dev" });
        cb.onDone("d-2");
        return Promise.resolve({ rateLimited: false, draftId: "d-2" });
      }
    );

    const onConfigUpdate = vi.fn();
    renderChat({ onConfigUpdate });

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "ajuste" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(onConfigUpdate).toHaveBeenCalledWith({ name: "Dev" });
    });
  });

  it("shows cancel button while streaming and aborts on click", async () => {
    let abortSignal: AbortSignal | null = null;
    sendMock.mockImplementation(
      (_p: string, _m: string, _d: string | null, _cb: any, signal: AbortSignal) => {
        abortSignal = signal;
        return new Promise(() => {
          // nunca resolve: simula stream em andamento.
        });
      }
    );

    renderChat();
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "oi" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /parar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /parar/i }));

    await waitFor(() => {
      expect(abortSignal?.aborted).toBe(true);
    });
  });

  it("disables sending and shows cooldown on 429", async () => {
    sendMock.mockResolvedValue({ rateLimited: true, retryAfter: 5 });

    renderChat();
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "oi" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("alert").textContent
      ).toMatch(/limite de mensagens atingido/i);
    });

    // Input desabilitado durante o cooldown.
    expect(input).toBeDisabled();
  });

  it("does not send empty message", async () => {
    renderChat();
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "   " } });
    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    expect(sendBtn).toBeDisabled();
    expect(sendMock).not.toHaveBeenCalled();
  });
});
