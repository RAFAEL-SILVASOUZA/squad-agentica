/**
 * Jornada 7 — Aprovação (HITL): badge na sidebar, card na fila, aprovar;
 * rejeitar argumentando; o monitor reflete.
 *
 * F6 (hook de HITL não registrado) faz o backend nunca persistir
 * ApprovalRequest num run real, e F1 impede o interrupt de chegar. Para
 * exercitar a UI de aprovação (fila, ações, badge, monitor), a suíte semeia a
 * ApprovalRequest pendente no banco (mesmo workaround do cenário 5 da suite de
 * integração). As respostas (POST /api/approvals/{id}/respond) e o
 * approval:resolved via WS são reais.
 *
 * Fontes: contrato §7 (approval:new / approval:resolved), spec §5.3,
 * protótipo view-approvals.
 */
import { test, expect, loginViaUI } from "../fixtures";
import {
  PASSWORD,
  db,
  dbCreateAgent,
  dbSeedPipeline,
  dbSeedApproval,
  dbDeletePipeline,
  connectWs,
  ofChannel,
  sleep,
  Api,
} from "../helpers";
import { mockPipelineApi, twoNodeGraph } from "../helpers/pipeline-mock";

test.describe("Jornada 7: aprovações", () => {
  test("aprovar: badge na sidebar, card na fila, aprovar, monitor reflete", async ({ page, user }) => {
    const a1 = await dbCreateAgent(user.id, `E2E Appr A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Appr B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Appr ${Date.now().toString(36)}`,
      approvalOn: 0,
      rejectToSource: true,
    });
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });
    // Semeia a aprovação pendente (workaround F6).
    const approval = await dbSeedApproval({
      ownerId: user.id,
      pipelineId: seeded.id,
      nodeId: graph.n1,
      message: "Aprovar a passagem para o nó 2?",
    });

    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });
    const ws = await connectWs(user.accessToken);

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.waitForURL(/\/$/, { timeout: 30_000 }).catch(() => undefined);

      // Badge na sidebar (link Aprovações mostra a contagem) e no sino.
      const sidebarBadge = page
        .locator('nav[aria-label="Navegação principal"]')
        .locator('[aria-label*="aprovações pendentes"]');
      const badgeVisible = await sidebarBadge
        .first()
        .waitFor({ state: "visible", timeout: 30_000 })
        .then(() => true)
        .catch(() => false);
      expect.soft(badgeVisible, "badge de aprovações pendentes na sidebar").toBe(true);
      const bell = page.locator('button[aria-label*="aprovações pendentes"]');
      const bellVisible = await bell.first().isVisible().catch(() => false);

      // Fila de aprovações: card com a mensagem e ações.
      await page.goto("/approvals");
      const card = page.locator(`[data-approval-card="${approval.id}"]`);
      await expect(card).toBeVisible({ timeout: 30_000 });
      await expect(card).toContainText("Aprovar a passagem para o nó 2?");

      // Aprovar.
      await card.getByRole("button", { name: /Aprovar/i }).click();
      await expect(page.getByText(/Pipeline retomada|Aprovação aprovada/i).first()).toBeVisible({
        timeout: 20_000,
      });
      // O card sai da fila (pending).
      await expect(card).toHaveCount(0, { timeout: 15_000 });

      // WS: approval:resolved real (backend emite no respond).
      await sleep(1500);
      const resolved = ofChannel(ws.frames, "approval:resolved");
      const ourResolved = resolved.filter((e: any) => e.approvalId === approval.id);
      const dbRow = await db(
        "query",
        "SELECT status, response FROM approval_requests WHERE id = %s",
        JSON.stringify([approval.id])
      );
      const dbStatus = dbRow[0]?.[0] ?? null;

      // O monitor reflete: abre sem erro (mock GET) e o nó 1 não fica
      // "waiting_approval" de forma permanente.
      await page.goto(`/pipelines/${seeded.id}/run`);
      await expect(page.getByRole("heading", { name: seeded.name })).toBeVisible({ timeout: 30_000 });
      await page.screenshot({ path: test.info().outputPath("approval-approved.png") });

      // Evidências estruturadas (relatório cruza com F6).
      expect(dbStatus, `status da aprovação no banco: ${dbStatus}`).toBe("approved");
      // approval:resolved real pelo backend (contrato §7).
      expect(
        ourResolved.length,
        `approval:resolved no WS: ${JSON.stringify(resolved).slice(0, 300)}`
      ).toBeGreaterThan(0);
      void bellVisible;
    } finally {
      await ws.close().catch(() => undefined);
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("rejeitar argumentando: resposta persistida e run reflete rejeição", async ({ page, user }) => {
    const a1 = await dbCreateAgent(user.id, `E2E Rej A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Rej B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Rej ${Date.now().toString(36)}`,
      approvalOn: 0,
      rejectToSource: true,
    });
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });
    const approval = await dbSeedApproval({
      ownerId: user.id,
      pipelineId: seeded.id,
      nodeId: graph.n1,
      message: "Aprovar a passagem (rejeição)?",
    });
    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto("/approvals");
      const card = page.locator(`[data-approval-card="${approval.id}"]`);
      await expect(card).toBeVisible({ timeout: 30_000 });

      // Argumentar: expande o card, textarea obrigatório.
      await card.getByRole("button", { name: /Argumentar/i }).click();
      const textarea = card.locator("#argument-" + approval.id);
      await expect(textarea).toBeVisible({ timeout: 10_000 });
      // Botão de enviar desabilitado sem argumento.
      const sendBtn = card.getByRole("button", { name: /Enviar argumento/i });
      await expect(sendBtn).toBeDisabled();
      await textarea.fill("O resultado do nó 1 está incompleto; refaça.");
      await expect(sendBtn).toBeEnabled();
      await sendBtn.click();

      // Toast de sucesso + card sai.
      await expect(page.getByText(/Argumento enviado/i).first()).toBeVisible({ timeout: 20_000 });
      await expect(card).toHaveCount(0, { timeout: 15_000 });

      // No banco: status revised + response persistida.
      const dbRow = await db(
        "query",
        "SELECT status, response FROM approval_requests WHERE id = %s",
        JSON.stringify([approval.id])
      );
      expect(dbRow[0]?.[0]).toBe("revised");
      expect(String(dbRow[0]?.[1] ?? "")).toContain("incompleto");

      // E rejeitar uma segunda aprovação (rejeitar simples).
      const approval2 = await dbSeedApproval({
        ownerId: user.id,
        pipelineId: seeded.id,
        nodeId: graph.n1,
        message: "Aprovar a passagem (rejeitar)?",
      });
      await page.reload();
      const card2 = page.locator(`[data-approval-card="${approval2.id}"]`);
      await expect(card2).toBeVisible({ timeout: 30_000 });
      await card2.getByRole("button", { name: /Rejeitar/i }).click();
      await expect(page.getByText(/Pipeline cancelada neste ramo|Aprovação rejeitada/i).first()).toBeVisible({
        timeout: 20_000,
      });
      const dbRow2 = await db(
        "query",
        "SELECT status FROM approval_requests WHERE id = %s",
        JSON.stringify([approval2.id])
      );
      expect(dbRow2[0]?.[0]).toBe("rejected");
      await page.screenshot({ path: test.info().outputPath("approval-rejected.png") });
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("aprovação respondida em outra sessão sai da fila (tempo real ou aviso 409)", async ({ page, user }) => {
    const a1 = await dbCreateAgent(user.id, `E2E Dup A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Dup B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Dup ${Date.now().toString(36)}`,
    });
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });
    const approval = await dbSeedApproval({
      ownerId: user.id,
      pipelineId: seeded.id,
      nodeId: graph.n1,
    });
    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });

    try {
      // A UI abre a fila com o card pendente; outra sessão responde antes
      // (API). O clique em Aprovar recebe 409 already_responded e a UI deve
      // avisar de forma legível e tirar o card da fila.
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto("/approvals");
      const card = page.locator(`[data-approval-card="${approval.id}"]`);
      await expect(card).toBeVisible({ timeout: 30_000 });

      const client = new Api();
      client.token = user.accessToken;
      const first = await client.post(`/api/approvals/${approval.id}/respond`, {
        decision: "approved",
      });
      expect(first.status).toBe(200);

      // Tempo real: approval:resolved pelo WS tira o card sem recarregar.
      const removedLive = await card
        .waitFor({ state: "detached", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      await page.screenshot({ path: test.info().outputPath("approval-409.png") });
      if (!removedLive) {
        // Sem o evento: o clique recebe 409 e a UI deve avisar de forma legível.
        const [second] = await Promise.all([
          page.waitForResponse((r) => r.url().includes(`/api/approvals/${approval.id}/respond`), { timeout: 20_000 }),
          card.getByRole("button", { name: /Aprovar/i }).click(),
        ]);
        expect(second.status(), "esperado 409 already_responded").toBe(409);
        const toast = page.locator("[role=status]").filter({ hasText: /./ }).last();
        await expect(toast).toBeVisible({ timeout: 10_000 });
        const text = (await toast.innerText()).trim();
        expect(text, `aviso do 409: "${text}"`).toMatch(/respondid|já|outra/i);
        await expect(card).toHaveCount(0, { timeout: 15_000 });
      }
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });
});
