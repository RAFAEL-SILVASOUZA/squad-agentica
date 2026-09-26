import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { SkillsLibrary } from "./skills-library";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockList = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    get: vi.fn(),
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

function makeSkill(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "skill-1",
    name: "Revisar código",
    description: "Revisa diffs de código",
    category: "code",
    type: "prompt",
    definition: { template: "Revise {{arquivo}}", variables: ["arquivo"] },
    inputs: [{ name: "arquivo", type: "string", required: true }],
    outputs: [{ name: "resultado", type: "string", required: false }],
    required_integrations: [],
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

function renderLibrary() {
  return render(
    <ToastProvider>
      <SkillsLibrary />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("SkillsLibrary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
  });

  it("renders loading skeletons on initial load", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderLibrary();
    expect(screen.queryByText("Nenhum skill ainda")).not.toBeInTheDocument();
  });

  it("renders empty state with CTA when no skills", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("Nenhum skill ainda")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
  });

  it("renders skill cards with name, category and description", async () => {
    mockList.mockResolvedValue({
      items: [makeSkill()],
      total: 1,
      page: 1,
      limit: 100,
    });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("Revisar código")).toBeInTheDocument();
    });
    expect(screen.getByText("Revisa diffs de código")).toBeInTheDocument();
    expect(screen.getByText("Código")).toBeInTheDocument();
  });

  it("opens create modal when CTA is clicked", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    const btn = screen.getByRole("button", { name: /criar primeiro skill/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
  });

  it("submits create with template and variables", async () => {
    mockPost.mockResolvedValue(makeSkill({ id: "skill-new" }));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeiro skill/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Skill nova" } });
    fireEvent.change(screen.getByLabelText("Template (markdown)"), {
      target: { value: "Faça {{coisa}}" },
    });
    fireEvent.change(screen.getByLabelText("Variáveis"), { target: { value: "coisa, outra" } });

    fireEvent.click(screen.getByRole("button", { name: /criar skill/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/skills", {
        name: "Skill nova",
        description: "",
        category: "code",
        definition: { template: "Faça {{coisa}}", variables: ["coisa", "outra"] },
        inputs: [],
        outputs: [],
        required_integrations: [],
      });
    });
  });

  it("shows form error when template is empty", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeiro skill/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Sem template" } });
    fireEvent.click(screen.getByRole("button", { name: /criar skill/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/template é obrigatório/i);
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("shows form error for invalid inputs JSON", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeiro skill/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "JSON ruim" } });
    fireEvent.change(screen.getByLabelText("Template (markdown)"), { target: { value: "ok" } });
    fireEvent.change(screen.getByLabelText("Inputs (JSON)"), { target: { value: "{\"name\": \"x\"}" } });
    fireEvent.click(screen.getByRole("button", { name: /criar skill/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/deve ser uma lista/i);
    });
  });

  it("switches to preview tab and renders markdown", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeiro skill/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Template (markdown)"), {
      target: { value: "# Título\n\n**negrito**" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Pré-visualizar" }));

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Pré-visualizar" })).toHaveAttribute("aria-selected", "true");
    });
    const preview = screen.getByLabelText("Pré-visualização markdown");
    expect(preview.querySelector("h1")?.textContent).toContain("Título");
    expect(preview.querySelector("strong")?.textContent).toBe("negrito");
  });

  it("opens edit modal prefilled when Editar is clicked", async () => {
    mockList.mockResolvedValue({ items: [makeSkill()], total: 1, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar skill revisar código/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar skill revisar código/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Revisar código");
    expect((screen.getByLabelText("Template (markdown)") as HTMLTextAreaElement).value).toBe(
      "Revise {{arquivo}}"
    );
  });

  it("submits update via PUT when saving an edit", async () => {
    mockList.mockResolvedValue({ items: [makeSkill()], total: 1, page: 1, limit: 100 });
    mockPut.mockResolvedValue(makeSkill({ name: "Renomeada" }));
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar skill revisar código/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar skill revisar código/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Renomeada" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar alterações/i }));

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith("/api/skills/skill-1", expect.objectContaining({
        name: "Renomeada",
      }));
    });
  });

  it("asks confirmation and deletes a skill", async () => {
    mockList.mockResolvedValue({ items: [makeSkill()], total: 1, page: 1, limit: 100 });
    mockDelete.mockResolvedValue(undefined);
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /excluir skill revisar código/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /excluir skill revisar código/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Excluir skill" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^excluir$/i }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/skills/skill-1");
    });
  });

  it("shows error state with retry on fetch failure", async () => {
    mockList.mockRejectedValue(new Error("network down"));
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("refetches on retry", async () => {
    mockList.mockRejectedValueOnce(new Error("boom"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2);
    });
  });

  it("shows API error details on save failure", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeiro skill/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeiro skill/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Template (markdown)"), { target: { value: "y" } });

    mockPost.mockRejectedValue(
      new ApiError(400, { error: "validation", code: "invalid", details: { errors: ["nome curto"] } })
    );
    fireEvent.click(screen.getByRole("button", { name: /criar skill/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/nome curto/);
    });
  });
});
