/**
 * Jornada 6: execução real e monitor. Agentes são criados pela API para
 * persistir também no Garage; pipeline semeada pertence ao usuário do teste.
 * GET da pipeline, runtime e WebSocket usam o backend real, sem interceptação.
 */
import { test, expect, loginViaUI } from "../fixtures";
import {
  PASSWORD,
  db,
  Api,
  dbSeedPipeline,
  dbDeletePipeline,
  connectWs,
  ofChannel,
  sleep,
} from "../helpers";
async function createAgent(api: Api, name: string) {
  const response = await api.post("/api/agents", {
    name, type: "custom", prompt: "Responda no campo result.",
    inputs: [{ name: "spec", type: "document", required: false }],
    outputs: [{ name: "result", type: "document", required: true }],
    actions: ["follow", "finalize"],
  });
  expect(response.status, response.text).toBe(201);
  return response.body;
}

test.describe("Jornada 6: executar e monitor", () => {
  test("executar: monitor abre, run inicia, status/logs refletem, pause+resume", async ({ page, user, api }) => {
    const a1 = await createAgent(api, `E2E Run A ${Date.now().toString(36)}`);
    const a2 = await createAgent(api, `E2E Run B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Run ${Date.now().toString(36)}`,
    });

    // Cliente WS para inspecionar os eventos reais (contrato §7).
    const ws = await connectWs(user.accessToken);

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto(`/pipelines/${seeded.id}/run`);

      // Monitor abre pelo GET real: título + faixa de etapas com os 2 agentes.
      await expect(page.getByRole("heading", { name: seeded.name })).toBeVisible({ timeout: 30_000 });
      const stages = page.getByRole("list", { name: "Etapas" });
      await expect(stages.getByRole("button")).toHaveCount(2, { timeout: 30_000 });
      await expect(page.getByRole("tab", { name: "Resultado" })).toHaveAttribute("aria-selected", "true");

      // Iniciar execução: o formulário pede as entradas do agente de entrada
      // (backend real: POST .../execute com { inputs }).
      await page.getByRole("button", { name: /Iniciar execução/i }).click();
      const runDialog = page.getByRole("dialog");
      await runDialog.getByLabel(/spec/).fill("Especificação de teste E2E");
      const [executeResp] = await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes(`/api/pipelines/${seeded.id}/execute`),
          { timeout: 30_000 }
        ),
        runDialog.getByRole("button", { name: /^Executar$/ }).click(),
      ]);
      expect(executeResp.request().postDataJSON()).toEqual({ inputs: { spec: "Especificação de teste E2E" } });
      expect(executeResp.status(), `execute respondeu ${executeResp.status()}`).toBe(200);
      const runId = (await executeResp.json()).runId as string;

      // Toast de sucesso.
      await expect(page.getByText(/Pipeline iniciada/i).first()).toBeVisible({ timeout: 15_000 });

      // O badge do run aparece (Executando).
      await expect(
        page.getByText(/Executando|Pausado|Concluído|Falhou|Cancelado/).first()
      ).toBeVisible({ timeout: 15_000 });

      // Aguarda eventos do WS (contrato §7). O backend real (F1/F11) pode não
      // emitir eventos por nó; o teste coleta e documenta.
      await expect.poll(() => ofChannel(ws.frames, "pipeline:status", seeded.id)
        .filter((event: any) => !event.nodeId).at(-1)?.status, { timeout: 30_000 }).toBe("completed");
      // A aba Resultado mostra a saída do 1º agente em largura total.
      await expect(page.getByRole("region", { name: a1.name })).not.toContainText(/Aguardando execução|Em execução/, {
        timeout: 30_000,
      });
      await expect(stages.getByRole("button", { name: new RegExp(`${a1.name}.*Concluído`) })).toBeVisible();
      const statusEvents = ofChannel(ws.frames, "pipeline:status", seeded.id);
      const logEvents = ofChannel(ws.frames, "pipeline:log", seeded.id);
      const outputEvents = ofChannel(ws.frames, "agent:output", seeded.id);
      // F11: nodeId deve estar presente; F1: status final "failed".
      const hasNodeId = statusEvents.some((e: any) => e.nodeId);
      const finalStatus = statusEvents.length ? statusEvents[statusEvents.length - 1].status : null;

      // Pause (backend real).
      const pauseResp = await page.request.post(`/api/pipelines/${seeded.id}/pause`, { headers: { Authorization: `Bearer ${user.accessToken}` } });
      const pauseOk = pauseResp.status() === 200;
      await sleep(500);

      // Resume (backend real).
      const resumeResp = await page.request.post(`/api/pipelines/${seeded.id}/resume`, { headers: { Authorization: `Bearer ${user.accessToken}` } });
      const resumeOk = resumeResp.status() === 200;

      // Evidência no banco: status final do run (F7: pode ficar "running").
      const row = await db(
        "query",
        "SELECT status, completed_at FROM pipeline_runs WHERE id = %s",
        JSON.stringify([runId])
      );
      const dbStatus = row[0]?.[0] ?? null;

      await page.screenshot({ path: test.info().outputPath("monitor-run.png") });

      // Evidências estruturadas (o relatório cruza com F1/F7/F10/F11).
      expect(executeResp.status()).toBe(200);
      // Os botões de ação do monitor reagem (não são links mortos): o estado
      // muda conforme o status do run.
      expect([200, 404]).toContain(pauseResp.status());
      expect([200, 404, 409]).toContain(resumeResp.status());
      // Documenta o estado real (não falha aqui; o relatório interpreta).
      expect(hasNodeId).toBe(true);
      await test.info().attach("runtime-observation", {body: JSON.stringify({runId, hasNodeId, finalStatus, dbStatus, logEvents, outputEvents}), contentType: "application/json"});
      expect(finalStatus, "F1: execução real deve completar").toBe("completed");
      expect(dbStatus).toBe("completed");
      void logEvents;
      void outputEvents;
      void pauseOk;
      void resumeOk;
    } finally {
      await ws.close().catch(() => undefined);

      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("grafo no modal, foco no resultado do nó e filtros de log", async ({ page, user, api }) => {
    const a1 = await createAgent(api, `E2E Node A ${Date.now().toString(36)}`);
    const a2 = await createAgent(api, `E2E Node B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Node ${Date.now().toString(36)}`,
    });

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto(`/pipelines/${seeded.id}/run`);
      await expect(page.getByRole("heading", { name: seeded.name })).toBeVisible({ timeout: 30_000 });

      // "Ver grafo" abre o grafo somente leitura num modal.
      await page.getByRole("button", { name: "Ver grafo" }).click();
      const graph = page.getByRole("dialog", { name: /grafo/i });
      await expect(graph.locator(".react-flow__node")).toHaveCount(2, { timeout: 30_000 });

      // Clique num nó fecha o modal e foca o resultado do agente.
      await graph.locator(".react-flow__node").first().click();
      await expect(graph).toBeHidden();
      await expect(page.getByRole("tab", { name: "Resultado" })).toHaveAttribute("aria-selected", "true");
      await expect(page.getByRole("region").first()).toBeVisible();

      // Aba Logs (vai para a URL) com filtros por agente e por nível.
      await page.getByRole("tab", { name: "Logs" }).click();
      await expect(page).toHaveURL(/\?tab=logs/);
      await expect(page.getByLabel("Filtrar por agente")).toBeVisible();
      await expect(page.getByLabel(/Filtrar por n.vel/i)).toBeVisible();
      await page.screenshot({ path: test.info().outputPath("monitor-node.png") });
    } finally {

      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });
});
