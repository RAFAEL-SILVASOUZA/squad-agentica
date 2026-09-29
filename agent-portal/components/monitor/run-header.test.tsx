import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RunHeader } from "./run-header";
import { makePipeline, makeRun } from "./test-fixtures";

describe("RunHeader", () => {
  it("shows the PR link or the publish failure with retry", () => {
    const onPublish = vi.fn();
    const { rerender } = render(
      <RunHeader
        pipeline={makePipeline({ name: "P" })}
        run={makeRun({ status: "completed", publishStatus: "published", prUrl: "https://x/pull/3", prNumber: 3 })}
        onPublish={onPublish}
        actions={null}
      />
    );
    const link = screen.getByRole("link", { name: "PR #3" });
    expect(link).toHaveAttribute("href", "https://x/pull/3");
    expect(link).toHaveAttribute("target", "_blank");
    rerender(
      <RunHeader
        pipeline={makePipeline({ name: "P" })}
        run={makeRun({ status: "completed", publishStatus: "failed", publishError: "token inválido ou sem acesso" })}
        onPublish={onPublish}
        actions={null}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("token inválido");
    fireEvent.click(screen.getByRole("button", { name: /Tentar publicar de novo/ }));
    expect(onPublish).toHaveBeenCalled();
  });

  it("says no file changed, shows the repository or its absence, and the run failure", () => {
    const { rerender } = render(
      <RunHeader
        pipeline={makePipeline({
          name: "P",
          repository: { integrationId: "i1", fullName: "acme/app", baseBranch: "main" },
        })}
        run={makeRun({ status: "completed", publishStatus: "no_changes" })}
        onPublish={vi.fn()}
        actions={<button>Ação</button>}
      />
    );
    expect(screen.getByRole("heading", { name: "P" })).toBeInTheDocument();
    expect(screen.getByText("Nenhum arquivo alterado")).toBeInTheDocument();
    expect(screen.getByText("acme/app")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ação" })).toBeInTheDocument();

    rerender(
      <RunHeader
        pipeline={makePipeline({ name: "P" })}
        run={makeRun({ status: "failed", error: "Missing tool call type", publishStatus: "none" })}
        onPublish={vi.fn()}
        actions={null}
      />
    );
    expect(screen.getByText("Sem repositório")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Missing tool call type");
    expect(screen.queryByRole("link", { name: /PR #/ })).not.toBeInTheDocument();
  });

  it("offers Publicar for a completed run with repository that was never published", () => {
    const onPublish = vi.fn();
    const repo = { integrationId: "i1", fullName: "acme/app", baseBranch: "main" };
    const { rerender } = render(
      <RunHeader
        pipeline={makePipeline({ name: "P", repository: repo })}
        run={makeRun({ status: "completed", publishStatus: "none" })}
        onPublish={onPublish}
        actions={null}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Publicar" }));
    expect(onPublish).toHaveBeenCalled();
    // Sem repositório, ou ainda em execução: nada de "Publicar".
    rerender(
      <RunHeader
        pipeline={makePipeline({ name: "P" })}
        run={makeRun({ status: "completed", publishStatus: "none" })}
        onPublish={onPublish}
        actions={null}
      />
    );
    expect(screen.queryByRole("button", { name: "Publicar" })).not.toBeInTheDocument();
    rerender(
      <RunHeader
        pipeline={makePipeline({ name: "P", repository: repo })}
        run={makeRun({ status: "running", publishStatus: "none" })}
        onPublish={onPublish}
        actions={null}
      />
    );
    expect(screen.queryByRole("button", { name: "Publicar" })).not.toBeInTheDocument();
  });
});
