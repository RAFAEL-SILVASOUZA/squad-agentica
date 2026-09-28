import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FilesTab } from "./files-tab";

const mockGet = vi.fn();
const mockDownload = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    download: (...args: unknown[]) => mockDownload(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
    }
  },
}));

describe("FilesTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists files with status, opens text, marks binary and offers zip", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? {
            items: [
              { path: "src/a.py", size: 9, binary: false, status: "added" },
              { path: "logo.png", size: 5, binary: true, status: "added" },
            ],
          }
        : { path: "src/a.py", content: "print(1)", binary: false, tooLarge: false, size: 9 }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /src\/a\.py/ }));
    expect(await screen.findByText("print(1)")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/runs/r1/files/content", { query: { path: "src/a.py" } });
    fireEvent.click(screen.getByRole("button", { name: /logo\.png/ }));
    expect(screen.getByText(/Arquivo binário/)).toBeInTheDocument();
    // Binário não é buscado nem renderizado.
    expect(mockGet).not.toHaveBeenCalledWith("/api/runs/r1/files/content", { query: { path: "logo.png" } });
    expect(screen.getByRole("button", { name: /Baixar \.zip/ })).toBeInTheDocument();
  });

  it("shows the size of a file too large to preview", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? { items: [{ path: "dump.sql", size: 3 * 1024 * 1024, binary: false, status: "modified" }] }
        : { path: "dump.sql", content: null, binary: false, tooLarge: true, size: 3 * 1024 * 1024 }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /dump\.sql/ }));
    expect(await screen.findByText(/Arquivo grande \(3(,0)? MB\) — baixe o \.zip/)).toBeInTheDocument();
  });

  it("downloads the zip with the session token and saves it with the server filename", async () => {
    mockGet.mockResolvedValue({ items: [] });
    const blob = new Blob(["PK"]);
    mockDownload.mockResolvedValue({ blob, filename: "pipe-abc.zip" });
    const createObjectURL = vi.fn(() => "blob:zip");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clicked: HTMLAnchorElement[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this);
      });

    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Baixar \.zip/ }));

    await waitFor(() => expect(mockDownload).toHaveBeenCalledWith("/api/runs/r1/archive"));
    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked[0].download).toBe("pipe-abc.zip");
    expect(clicked[0].getAttribute("href")).toBe("blob:zip");
    clickSpy.mockRestore();
  });

  it("shows the API error when the workspace was purged", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockResolvedValue({ items: [] });
    mockDownload.mockRejectedValue(new ApiError(404, { error: "Arquivos removidos", code: "workspace_not_found" }));
    render(<FilesTab runId="r1" />);
    expect(await screen.findByText(/Nenhum arquivo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Baixar \.zip/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Arquivos removidos");
  });

  it("shows the diff and warns when it was truncated", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? { items: [{ path: "a.txt", size: 1, binary: false, status: "modified" }] }
        : { diff: "diff --git a/a.txt b/a.txt\n+novo", truncated: true }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Ver diff/ }));
    expect(await screen.findByText(/\+novo/)).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/runs/r1/diff");
    expect(screen.getByText("Diff truncado — baixe o .zip para ver tudo")).toBeInTheDocument();
  });
});
