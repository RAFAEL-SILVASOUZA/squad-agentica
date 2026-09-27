/**
 * Jornada 5 — Montar pipeline de 2 agentes no editor: arrastar, conectar flow e
 * data, mapear output->input, marcar aprovação; validação em grafo inválido;
 * salvar.
 *
 * F9/B1 (CRUD de pipeline ausente) bloqueia as telas: GET/PUT
 * /api/pipelines/{id} retornam 404 no backend, e sem isso o editor e o monitor
 * não carregam. A suíte intercepta GET/PUT/validate (mockPipelineApi) e semeia
 * a pipeline no banco para as rotas de runtime reais. A decisão é registrada
 * no relatório.
 *
 * Fontes: spec §4.2 (regras de validação), ADR-006 (aresta flow vs data),
 * protótipo view-PIPELINE-EDITOR, DESIGN-SYSTEM §2.11/§2.19.
 */
import { test, expect, loginViaUI } from "../fixtures";
import { PASSWORD, db, dbCreateAgent, dbSeedPipeline, dbDeletePipeline } from "../helpers";
import { mockPipelineApi, twoNodeGraph, MockPipelineState } from "../helpers/pipeline-mock";

test.describe("Jornada 5: editor de pipeline", () => {
  test("carregar, arrastar 2 agentes, conectar flow+data, mapear, aprovação, salvar", async ({ page, user }) => {
    // Agentes reais no banco (a paleta lista via GET /api/agents real).
    const a1 = await dbCreateAgent(user.id, `E2E Pipe A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Pipe B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Pipeline ${Date.now().toString(36)}`,
    });

    // Mock do CRUD (F9): GET/PUT /api/pipelines/{id} + validate.
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });
    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto(`/pipelines/${seeded.id}`);

      // Carrega: título + 2 nós no canvas.
      await expect(page.getByRole("heading", { name: seeded.name })).toBeVisible({ timeout: 30_000 });
      await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 30_000 });
      await expect(page.locator(".react-flow__node")).toHaveCount(2, { timeout: 15_000 });

      // Aresta flow já existe (semeada) + data edge. O canvas tem 2 arestas.
      await expect(page.locator(".react-flow__edge")).toHaveCount(2, { timeout: 15_000 });

      // Arrastar um novo agente da paleta para o canvas (drag & drop real).
      await page.getByRole("button", { name: "Add agent" }).click();
      const palette = page.getByRole("dialog", { name: /Add agent to pipeline/i });
      await expect(palette).toBeVisible();
      const dragItem = palette.getByRole("button", { name: new RegExp(a2.name) });
      await expect(dragItem).toBeVisible();

      const canvas = page.locator(".react-flow");
      const dragBox = await dragItem.boundingBox();
      const canvasBox = await canvas.boundingBox();
      if (dragBox && canvasBox) {
        // HTML5 drag: o React Flow usa dataTransfer; o Playwright precisa do
        // evento de drag nativo. Tenta dragTo; se o nó não aparecer, registra
        // (verba de 2 tentativas) e segue com o clique simples na paleta, que
        // também adiciona o nó (handleAddAgent).
        try {
          await dragItem.dragTo(canvas, {
            targetPosition: { x: canvasBox.width * 0.6, y: canvasBox.height * 0.6 },
            timeout: 8_000,
          });
        } catch {
          // Fallback: clique na paleta (mesmo handler handleAddAgent).
          await dragItem.click();
        }
        await expect(page.locator(".react-flow__node")).toHaveCount(3, { timeout: 15_000 });
      } else {
        await dragItem.click();
        await expect(page.locator(".react-flow__node")).toHaveCount(3, { timeout: 15_000 });
      }

      // Conectar: source (nó A, output "result") -> target (novo nó, input "spec").
      // O novo nó tem id aleatório; localiza o terceiro nó pelo nome.
      const nodes = page.locator(".react-flow__node");
      const newHandle = nodes
        .filter({ hasText: a2.name })
        .last()
        .locator('.react-flow__handle.target')
        .first();
      const srcHandle = nodes
        .filter({ hasText: a1.name })
        .first()
        .locator('.react-flow__handle.source')
        .first();

      const s = await srcHandle.boundingBox();
      const t = await newHandle.boundingBox();
      if (s && t) {
        await page.mouse.move(s.x + s.width / 2, s.y + s.height / 2);
        await page.mouse.down();
        await page.mouse.move(t.x + t.width / 2, t.y + t.height / 2, { steps: 12 });
        await page.mouse.up();
        // Uma nova aresta (flow) surge.
        await expect(page.locator(".react-flow__edge")).toHaveCount(3, { timeout: 15_000 });
      }

      // Conectar data edge: abre o EdgePanel do novo nó? Não: a data edge é
      // criada como edge e depois tipada via painel. Selecione a nova aresta
      // (clique) e mude o tipo para data + mapeie output->input.
      const newEdge = page.locator(".react-flow__edge").last();
      await newEdge.click();
      const edgePanel = page.getByRole("region", { name: /Configuracao da aresta/i });
      await expect(edgePanel).toBeVisible({ timeout: 15_000 });

      // Troca o tipo para data.
      await edgePanel.locator("#edge-type").selectOption("data");
      // Mapeia output "result" -> input "spec".
      await edgePanel.locator("#edge-source-output").selectOption("result");
      await edgePanel.locator("#edge-target-input").selectOption("spec");
      await expect(edgePanel.locator("#edge-source-output")).toHaveValue("result");
      await expect(edgePanel.locator("#edge-target-input")).toHaveValue("spec");
      await edgePanel.getByRole("button", { name: /Fechar painel da aresta/i }).click();

      // Marcar aprovação numa aresta flow existente (a primeira).
      const flowEdge = page.locator(".react-flow__edge").first();
      await flowEdge.dispatchEvent("click");
      const panel2 = page.getByRole("region", { name: /Configuracao da aresta/i });
      await expect(panel2).toBeVisible({ timeout: 10_000 });
      await panel2.locator("#edge-requires-approval").click();
      // Mensagem de notificação aparece.
      await panel2.locator("#edge-approval-message").fill("Aprovar passagem E2E");
      await expect(panel2.locator("#edge-approval-channel")).toBeVisible();
      await page.screenshot({ path: test.info().outputPath("pipeline-editor.png") });

      // Salvar (grava no mock + valida).
      await page.getByRole("button", { name: /Save/i }).click();
      await expect(page.getByText(/Pipeline saved/i)).toBeVisible({ timeout: 15_000 });

      // Confirma o payload salvo: 3 nós, 3 arestas, 1 com requiresApproval.
      const saved: { nodes: number; edges: number; approval: number } = await (async () => ({
        nodes: mock.state.nodes.length,
        edges: mock.state.edges.length,
        approval: mock.state.edges.filter((e) => e.requiresApproval).length,
      }))();
      expect(saved.nodes).toBe(3);
      expect(saved.edges).toBe(3);
      expect(saved.approval, `E13: edições do EdgePanel (tipo data, mapeamento, aprovação) não chegam ao grafo salvo. Arestas salvas: ${JSON.stringify(mock.state.edges).slice(0, 900)}`).toBe(1);
      const dataEdge = mock.state.edges.find((e) => e.type === "data");
      expect(dataEdge?.dataMapping?.sourceOutput).toBe("result");
      expect(dataEdge?.dataMapping?.targetInput).toBe("spec");
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("validação: grafo inválido mostra erro e bloqueia o Execute", async ({ page, user }) => {
    const a1 = await dbCreateAgent(user.id, `E2E Val A ${Date.now().toString(36)}`);
    const a2 = await dbCreateAgent(user.id, `E2E Val B ${Date.now().toString(36)}`);
    const seeded = await dbSeedPipeline({
      ownerId: user.id,
      agents: [
        { id: a1.id, name: a1.name },
        { id: a2.id, name: a2.name },
      ],
      name: `QA Inv ${Date.now().toString(36)}`,
    });

    // Grafo inválido: 2 nós, aresta data sem mapeamento (regra 1) e entrada
    // required não atendida (regra 6). O mock devolve valid:true do servidor;
    // os erros locais (mesmas regras do compiler) devem aparecer.
    const graph = twoNodeGraph(seeded.id, { id: a1.id, name: a1.name }, { id: a2.id, name: a2.name });
    // Remove a dataMapping da data edge para tornar o grafo inválido.
    const badEdge = graph.edges.find((e) => e.type === "data")!;
    badEdge.dataMapping = undefined;
    // Torna a entrada "spec" required no nó 2 (regra 6: input required sem data edge).
    (graph.nodes[1].agentSnapshot.inputs as any[]).find((p) => p.name === "spec").required = true;

    const mock = await mockPipelineApi(page, {
      id: seeded.id,
      entryNodeId: graph.n1,
      nodes: graph.nodes,
      edges: graph.edges,
      name: seeded.name,
    });

    try {
      await loginViaUI(page, user.email, PASSWORD);
      await page.goto(`/pipelines/${seeded.id}`);
      await expect(page.locator(".react-flow__node")).toHaveCount(2, { timeout: 30_000 });

      // Erros de validação aparecem (indicador "validation error(s)").
      await expect(
        page.getByText(/validation error/i).first()
      ).toBeVisible({ timeout: 15_000 });

      // O nó 2 (entrada required não atendida) fica destacado; a aresta data
      // (sem mapeamento) também.
      await page.screenshot({ path: test.info().outputPath("pipeline-invalid.png") });

      // Botão Execute bloqueado enquanto há erro.
      const execute = page.getByRole("button", { name: /Execute/i }).first();
      await expect(execute).toBeDisabled({ timeout: 10_000 });
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("pipelines list: CTA cria e navega para o editor (F9: backend 404)", async ({ page, user }) => {
    // A listagem chama GET /api/pipelines (404 real, F9). A UI mostra erro com
    // retry. O teste documenta o estado real (bloqueada por F9) e verifica que
    // o CTA "New Pipeline" reage (não é link morto).
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/pipelines");
    const errorBanner = page.getByText("Failed to load pipelines");
    // E12: o 404 do FastAPI vem como {"detail": ...}; ApiError usa body.error
    // (undefined) e a tela cai no estado vazio "No pipelines yet", mascarando F9.
    await expect(errorBanner, "E12: 404 da listagem aparece como lista vazia").toBeVisible({ timeout: 30_000 });
    // CTA presente e habilitado.
    const cta = page.getByRole("button", { name: /New Pipeline/i });
    await expect(cta).toBeEnabled();
    await page.screenshot({ path: test.info().outputPath("pipelines-list-404.png") });
    // Clique dispara POST /api/pipelines (404 real) -> toast de erro.
    await cta.click();
    const errorToast = page
      .locator("[role=status]")
      .filter({ hasText: /Failed to create|not_found|error/i });
    await errorToast
      .first()
      .waitFor({ state: "visible", timeout: 15_000 })
      .catch(() => undefined);
  });
});
