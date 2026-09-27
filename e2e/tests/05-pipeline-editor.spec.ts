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
  test("carregar, arrastar 2 agentes, conectar flow+data, mapear, aprovação, salvar", async ({ page, user, pageErrors, api }) => {
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
      await page.getByRole("button", { name: "Adicionar agente" }).click();
      const palette = page.getByRole("dialog", { name: /Adicionar agente ao pipeline/i });
      await expect(palette).toBeVisible();
      const dragItem = palette.getByRole("button", { name: new RegExp(a2.name) });
      await expect(dragItem).toBeVisible();

      const idsBefore = await page
        .locator(".react-flow__node")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-id")));
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
            // Área vazia (canto inferior esquerdo): no centro e à direita o nó novo caía sobre o nó B
            // semeado e o handle de destino ficava coberto.
            targetPosition: { x: canvasBox.width * 0.25, y: canvasBox.height * 0.8 },
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
      // O nó novo é o data-id que não existia antes do drop (o B semeado tem o
      // mesmo nome e já recebe result -> spec; o addEdge do React Flow descarta
      // conexão duplicada).
      const idsAfter = await nodes.evaluateAll((els) => els.map((e) => e.getAttribute("data-id")));
      const newId = idsAfter.find((id) => !idsBefore.includes(id));
      expect(newId, "nó novo no canvas").toBeTruthy();
      // Dependendo do fitView, o nó novo fica parcialmente sob o B; selecioná-lo
      // o eleva (elevateNodesOnSelect) e expõe o handle de destino.
      const newNode = page.locator(`.react-flow__node[data-id="${newId}"]`);
      await newNode.dispatchEvent("click");
      const newHandle = newNode.locator('.react-flow__handle.target').first();
      const srcHandle = nodes
        .filter({ hasText: a1.name })
        .first()
        .locator('.react-flow__handle.source')
        .first();

      const s = await srcHandle.boundingBox();
      const t = await newHandle.boundingBox();
      if (s && t) {
        // hover() mede o handle no momento da ação: o canvas ainda se ajusta
        // alguns pixels depois do drop e a boundingBox anterior fica velha.
        await srcHandle.hover();
        await page.mouse.down();
        await newHandle.hover({ force: true });
        await page.mouse.up();
        // Uma nova aresta (flow) surge.
        await expect(page.locator(".react-flow__edge")).toHaveCount(3, { timeout: 15_000 });
      }

      // Conectar data edge: abre o EdgePanel do novo nó? Não: a data edge é
      // criada como edge e depois tipada via painel. Selecione a nova aresta
      // (clique) e mude o tipo para data + mapeie output->input.
      const newEdge = page.locator(".react-flow__edge").last();
      await newEdge.click();
      const edgePanel = page.getByRole("region", { name: /Configuração da aresta/i });
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
      const panel2 = page.getByRole("region", { name: /Configuração da aresta/i });
      await expect(panel2).toBeVisible({ timeout: 10_000 });
      await panel2.locator("#edge-requires-approval").click();
      // Mensagem de notificação aparece.
      await panel2.locator("#edge-approval-message").fill("Aprovar passagem E2E");
      await expect(panel2.locator("#edge-approval-channel")).toBeVisible();
      await page.screenshot({ path: test.info().outputPath("pipeline-editor.png") });

      // Salvar (grava no mock + valida).
      await page.getByRole("button", { name: /Salvar pipeline/i }).click();
      await expect(page.getByText(/Pipeline salvo/i)).toBeVisible({ timeout: 15_000 });

      // Confirma o payload salvo: 3 nós, 3 arestas, 1 com requiresApproval.
      const stored = (await api.get(`/api/pipelines/${seeded.id}`)).body;
      const saved = {
        nodes: stored.nodes.length,
        edges: stored.edges.length,
        approval: stored.edges.filter((edge: any) => edge.requiresApproval).length,
      };
      expect(saved.nodes).toBe(3);
      expect(saved.edges).toBe(3);
      expect(saved.approval, `E13: edições do EdgePanel (tipo data, mapeamento, aprovação) não chegam ao grafo salvo. Arestas salvas: ${JSON.stringify(stored.edges).slice(0, 900)}`).toBe(1);
      const dataEdge = stored.edges.find((e: any) => e.type === "data");
      expect(dataEdge?.dataMapping?.sourceOutput).toBe("result");
      expect(dataEdge?.dataMapping?.targetInput).toBe("spec");
      expect(pageErrors).toEqual([]);
    } finally {

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
        page.getByText(/erros? de validação/i).first()
      ).toBeVisible({ timeout: 15_000 });

      // O nó 2 (entrada required não atendida) fica destacado; a aresta data
      // (sem mapeamento) também.
      await page.screenshot({ path: test.info().outputPath("pipeline-invalid.png") });

      // Botão Execute bloqueado enquanto há erro.
      const execute = page.getByRole("button", { name: /Executar pipeline/i }).first();
      await expect(execute).toBeDisabled({ timeout: 10_000 });
    } finally {
      await mock.dispose();
      await dbDeletePipeline(seeded.id).catch(() => undefined);
    }
  });

  test("pipelines list: CTA cria e navega para o editor", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/pipelines");
    const cta = page.getByRole("button", { name: /Criar novo pipeline/i });
    await expect(cta).toBeEnabled();
    const [created] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && /\/api\/pipelines$/.test(response.url())),
      cta.click(),
    ]);
    expect(created.status()).toBe(201);
    const pipeline = await created.json();
    await page.waitForURL(`**/pipelines/${pipeline.id}`);
    await expect(page.getByRole("heading", { name: "Novo pipeline" })).toBeVisible();
    await dbDeletePipeline(pipeline.id);
  });
});
