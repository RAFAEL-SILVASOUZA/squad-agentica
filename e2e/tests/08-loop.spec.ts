/**
 * Jornada 8 — Pipeline com loop por rejeição até maxIterations.
 *
 * Aresta com requiresApproval + rejectTarget=source (ADR-006 do contrato):
 * aprovar -> avança; rejeitar -> volta ao source (loop). O limite de loop
 * (maxIterations) é imposto pela node function no backend (ADR-005/ADR-007),
 * que hoje está quebrado por F1 (run sempre falha) e F6 (hook de HITL não
 * registrado): o interrupt nunca é detectado, então o backend NUNCA cria a
 * ApprovalRequest da próxima iteração.
 *
 * Para exercitar a UI do loop (o que a interface revela), a suíte semeia uma
 * ApprovalRequest pendente por iteração (workaround F6, mesmo padrão da
 * jornada 7 e do cenário 5 da suite de integração) e percorre
 * aprovar -> rejeitar (com argumento) via UI. O teste documenta o estado real:
 * após a rejeição da última iteração, o loop continuaria no backend se o
 * interrupt funcionasse; aqui ele para porque o interrupt está morto (F1/F6).
 *
 * Fontes: ADR-005/006/007 do contrato, spec §5.3, protótipo view-approvals.
 */
import { test, expect, loginViaUI } from "../fixtures";
import { PASSWORD, db, dbCreateAgent, dbSeedPipeline, dbSeedApproval, dbDeletePipeline } from "../helpers";
import { mockPipelineApi, twoNodeGraph } from "../helpers/pipeline-mock";

test.describe("Jornada 8: loop por rejeição até maxIterations", () => {
  test.skip("aprovar, rejeitar argumentando, e o loop até o limite (documentado)", async ({ page, user }) => {
    test.skip(true, "Bloqueada por F1/F6/F7: aprovações semeadas não comprovam loop nem maxIterations.");
    const a1 = await dbCreateAgent(user.id, `E2E Loop A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Loop B ${Date.now().toString(36)}`);
    // maxIterations=3 no agente 1 (ADR-005: guarda de segurança no loop).
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name, maxIterations: 3 },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Loop ${Date.now().toString(36)}`,
      approvalOn: 0,
      rejectToSource: true,
    });
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });

    // Verifica o grafo semeado: aresta flow com requires_approval + reject_target=source.
    const edgeRow = await db(
      "query",
      "SELECT requires_approval, reject_target FROM pipeline_edges WHERE pipeline_id = %s AND type = 'flow'",
      JSON.stringify([seeded.id])
    );
    expect(edgeRow[0]?.[0]).toBe(true);
    expect(String(edgeRow[0]?.[1])).toBe(seeded.nodes[0]);

    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });

    try {
      await loginViaUI(page, user.email, PASSWORD);

      // Iteração 1: aprovar (avança para o nó 2).
      const appr1 = await dbSeedApproval({
        ownerId: user.id,
        pipelineId: seeded.id,
        nodeId: graph.n1,
        message: "Loop iteração 1: aprovar?",
      });
      await page.goto("/approvals");
      const card1 = page.locator(`[data-approval-card="${appr1.id}"]`);
      await expect(card1).toBeVisible({ timeout: 30_000 });
      await card1.getByRole("button", { name: /Aprovar/i }).click();
      await expect(page.getByText(/Pipeline retomada|Aprovação aprovada/i).first()).toBeVisible({ timeout: 20_000 });
      const db1 = await db("query", "SELECT status FROM approval_requests WHERE id = %s", JSON.stringify([appr1.id]));
      expect(db1[0]?.[0]).toBe("approved");

      // Iteração 2: rejeitar argumentando (volta ao nó 1; seria loop 2).
      const appr2 = await dbSeedApproval({
        ownerId: user.id,
        pipelineId: seeded.id,
        nodeId: graph.n1,
        message: "Loop iteração 2: aprovar?",
      });
      await page.reload();
      const card2 = page.locator(`[data-approval-card="${appr2.id}"]`);
      await expect(card2).toBeVisible({ timeout: 30_000 });
      await card2.getByRole("button", { name: /Argumentar/i }).click();
      const ta = card2.locator("#argument-" + appr2.id);
      await expect(ta).toBeVisible();
      await ta.fill("Resultado incompleto; refaça com mais contexto.");
      await card2.getByRole("button", { name: /Enviar argumento/i }).click();
      await expect(page.getByText(/Argumento enviado/i).first()).toBeVisible({ timeout: 20_000 });
      const db2 = await db(
        "query",
        "SELECT status, response FROM approval_requests WHERE id = %s",
        JSON.stringify([appr2.id])
      );
      expect(db2[0]?.[0]).toBe("revised");
      expect(String(db2[0]?.[1] ?? "")).toContain("incompleto");

      // Iteração 3 (última, maxIterations=3): rejeitar simples.
      const appr3 = await dbSeedApproval({
        ownerId: user.id,
        pipelineId: seeded.id,
        nodeId: graph.n1,
        message: "Loop iteração 3 (limite): aprovar?",
      });
      await page.reload();
      const card3 = page.locator(`[data-approval-card="${appr3.id}"]`);
      await expect(card3).toBeVisible({ timeout: 30_000 });
      await card3.getByRole("button", { name: /Rejeitar/i }).click();
      await expect(page.getByText(/Pipeline cancelada neste ramo|Aprovação rejeitada/i).first()).toBeVisible({
        timeout: 20_000,
      });
      const db3 = await db("query", "SELECT status FROM approval_requests WHERE id = %s", JSON.stringify([appr3.id]));
      expect(db3[0]?.[0]).toBe("rejected");

      // Estado real: sem interrupt (F1/F6) não há run ativo nem iteração 4.
      // O monitor abre (mock GET) e reflete o fim do loop.
      await page.goto(`/pipelines/${seeded.id}/run`);
      await expect(page.getByRole("heading", { name: seeded.name })).toBeVisible({ timeout: 30_000 });
      await page.screenshot({ path: test.info().outputPath("loop-final.png") });
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });
});
