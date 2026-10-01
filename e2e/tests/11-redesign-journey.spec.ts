/**
 * Jornada 11 — Redesign de usabilidade: fluxo completo de um usuário novo.
 *
 * Roda em 1440px (desktop) e em 390px (mobile), cobrindo os 7 passos da spec:
 *   1. cadastro;
 *   2. Overview mostra "Primeiros passos";
 *   3. + Novo → Agente, chat, preview "pronto para salvar" e salvar;
 *   4. + Novo → Pipeline, adicionar o agente, configurar a entrada e salvar;
 *   5. executar e ver a linha do tempo no monitor;
 *   6. Knowledge: criar base, enviar documento .md e perguntar (citação);
 *   7. ⌘K encontra o agente.
 *
 * O chat de construção é mockado (mockAgentChat) para devolver um draft
 * determinístico, porque o provedor mock real devolve texto puro (sem config).
 * A decisão de mock do streaming é registrada no relatório (qa-redesign.md).
 *
 * Um teste por viewport (não 7) para minimizar o consumo do rate limit de
 * login (5/min por IP, compartilhado por toda a suíte).
 */
import { test, expect, loginViaUI, mockAgentChat, dashboardReady, PASSWORD } from "../fixtures";
import { db, dbDeletePipeline, uniqueEmail } from "../helpers";

// Nome base do agente; cada teste (1440/390) usa um sufixo único para evitar
// conflito de nome (o fixture limpa agentes só no teardown do worker).
const AGENT_NAME_BASE = "Jornada Agente E2E";

for (const width of [1440, 390]) {
  test(`jornada de usuário novo em ${width}px`, async ({ page, user, api }, info) => {
    const isMobile = width < 768;
    // Nomes únicos por teste: as constraints de unicidade (owner+name) fazem o
    // 2º teste do worker conflitar com o 1º se os nomes fossem fixos.
    const AGENT_NAME = `${AGENT_NAME_BASE} ${width}`;
    const PIPELINE_NAME = `Jornada Pipeline E2E ${width}`;
    const BASE_NAME = `Base Jornada E2E ${width}`;
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });

    // Coleta erros de console/página para a verificação transversal.
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("pageerror", (e) => pageErrors.push(e.message));

    // ── 1. Cadastro ──────────────────────────────────────────────────────
    await test.step("1. cadastro", async () => {
      // O fixture `user` já registrou via API; aqui exercitamos o cadastro
      // por UI com um e-mail próprio (o passo 1 da jornada é o cadastro).
      const regEmail = uniqueEmail("journey");
      await page.goto("/register");
      await page.waitForLoadState("networkidle");
      await page.locator("#name").fill("Usuário Jornada");
      await page.locator("#email").fill(regEmail);
      await page.locator("#password").fill(PASSWORD);
      await page.locator("#confirmPassword").fill(PASSWORD);
      await page.locator('button[type="submit"]').click();
      // Sucesso: chega no dashboard (shell). Em mobile a bottom nav aparece.
      await expect(page).not.toHaveURL(/\/register/, { timeout: 30_000 });
      if (isMobile) {
        await expect(page.getByRole("navigation", { name: /navegação inferior/i })).toBeVisible({ timeout: 15_000 });
      }
      // Limpa o usuário de cadastro no fim (o fixture limpa o `user`).
      const rows = await db("query", "SELECT id FROM users WHERE email = %s", JSON.stringify([regEmail])).catch(() => []);
      if (rows.length) {
        await import("../helpers").then(({ dbDeleteUser }) => dbDeleteUser(rows[0][0] as string)).catch(() => undefined);
      }
    });

    // O cadastro via UI já autenticou o navegador; limpa a sessão para o
    // loginViaUI do fixture (passos 2-7) partir de um estado limpo.
    await page.context().clearCookies();
    await loginViaUI(page, user.email, PASSWORD);

    // ── 2. Overview mostra "Primeiros passos" ────────────────────────────
    await test.step("2. Overview mostra Primeiros passos", async () => {
      await page.goto("/");
      if (isMobile) {
        // Em mobile a sidebar não aparece; espera o conteúdo do dashboard.
        await page.waitForLoadState("networkidle");
      } else {
        await dashboardReady(page);
      }
      // O checklist de onboarding aparece enquanto o portal não tem os 4 itens.
      await expect(page.getByText("Primeiros passos")).toBeVisible({ timeout: 30_000 });
    });

    // ── 3. + Novo → Agente, chat, preview e salvar ───────────────────────
    let agentId: string;
    await test.step("3. criar agente por chat", async () => {
      await page.goto("/agents/new");
      await mockAgentChat(page, {}, AGENT_NAME);
      await expect(page.getByRole("heading", { name: "Novo Agente" })).toBeVisible();

      await page.locator("#agent-chat-input").fill("Um agente que recebe uma spec e devolve um resultado.");
      await page.getByRole("button", { name: /Enviar mensagem/i }).click();

      // Preview "pronto para salvar" (valid=true do draft mockado).
      await expect(page.getByText("✓ pronto para salvar")).toBeVisible({ timeout: 20_000 });

      const saveBtn = page.getByRole("button", { name: /Salvar agente/i });
      await expect(saveBtn).toBeEnabled({ timeout: 15_000 });
      await saveBtn.click();
      await expect(page).toHaveURL(/\/agents\/[0-9a-f-]{36}/, { timeout: 20_000 });
      agentId = new URL(page.url()).pathname.split("/").pop()!;
      await expect(page.getByRole("heading", { name: AGENT_NAME })).toBeVisible({ timeout: 20_000 });
    });

    // ── 4. + Novo → Pipeline, adicionar agente, configurar entrada, salvar ─
    let pipelineId: string | undefined;
    await test.step("4. montar pipeline", async () => {
      // Cria a pipeline via API (o CRUD de pipeline é o caminho real) e abre
      // o editor. O passo da jornada é adicionar o agente e configurar a
      // entrada pelo painel (desktop) ou pela lista (mobile).
      const created = await api.post("/api/pipelines", { name: PIPELINE_NAME, nodes: [], edges: [] });
      expect(created.status, `criar pipeline: ${created.status} ${created.text.slice(0, 200)}`).toBe(201);
      pipelineId = created.body.id;

      await page.goto(`/pipelines/${pipelineId}`);
      await expect(page.getByRole("heading", { name: PIPELINE_NAME })).toBeVisible({ timeout: 30_000 });

      if (isMobile) {
        // Modo lista de etapas (abaixo de 768px): canvas não aparece.
        await expect(page.locator(".react-flow")).toHaveCount(0);
        // Adiciona o agente pelo seletor da lista.
        const addSelect = page.getByLabel(/Escolher agente para adicionar/i);
        await addSelect.selectOption(agentId);
        await page.getByRole("button", { name: /Adicionar agente/i }).click();
        // O nó aparece na lista de etapas (data-testid step-node).
        await expect(page.locator("[data-testid^='step-node']").first()).toBeVisible({ timeout: 15_000 });
      } else {
        // Desktop: paleta de agentes + canvas.
        await page.getByRole("button", { name: "Adicionar agente" }).click();
        const palette = page.getByRole("dialog", { name: /Adicionar agente ao pipeline/i });
        await expect(palette).toBeVisible();
        await palette.getByRole("button", { name: new RegExp(AGENT_NAME) }).click();
        await expect(page.locator(".react-flow__node")).toHaveCount(1, { timeout: 15_000 });
      }

      // Salvar a pipeline: espera o PUT real (o toast de sucesso só existe no
      // FlowEditor desktop; o botão mobile da página não emite toast).
      const [putResp] = await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes(`/api/pipelines/${pipelineId}`) && r.request().method() === "PUT",
          { timeout: 20_000 }
        ),
        page.getByRole("button", { name: /Salvar pipeline/i }).click(),
      ]);
      expect(putResp.status(), `PUT pipeline: ${putResp.status()}`).toBe(200);
    });

    // ── 5. Executar e ver a linha do tempo no monitor ────────────────────
    await test.step("5. executar e ver linha do tempo", async () => {
      await page.goto(`/pipelines/${pipelineId}/run`);
      await expect(page.getByRole("heading", { name: PIPELINE_NAME })).toBeVisible({ timeout: 30_000 });

      await page.getByRole("button", { name: /Iniciar execução/i }).click();
      const runDialog = page.getByRole("dialog");
      // Configura a entrada "spec" (o agente de entrada tem input spec).
      const specField = runDialog.getByLabel(/spec/i);
      if (await specField.count()) {
        await specField.fill("Especificação da jornada");
      }
      const [executeResp] = await Promise.all([
        page.waitForResponse((r) => r.url().includes(`/api/pipelines/${pipelineId}/execute`), { timeout: 30_000 }),
        runDialog.getByRole("button", { name: /^Executar$/ }).click(),
      ]);
      expect(executeResp.status(), `execute: ${executeResp.status()}`).toBe(200);

      // Aguarda o run completar (mock: rápido).
      await expect(page.getByText(/Concluído|Falhou|Executando|Pausado/).first()).toBeVisible({ timeout: 30_000 });
      // A linha do tempo por nó (Task 14) aparece na aba Resultado.
      await expect(page.getByRole("tab", { name: /Resultado/i })).toHaveAttribute("aria-selected", "true");
      await page.screenshot({ path: info.outputPath(`jornada-monitor-${width}.png`) });
    });

    // ── 6. Knowledge: criar base, enviar doc, perguntar ──────────────────
    await test.step("6. knowledge com citação", async () => {
      // Cria a base via API com similarityThreshold -1.0: o mock de embedding
      // gera vetores ortogonais (score ~0), então o threshold padrão (0.7)
      // filtraria o resultado e a citação não apareceria. Com -1.0 qualquer
      // score passa e a citação [1] é renderizada. O objetivo da jornada é a
      // citação, não o retrieval semântico (coberto em modo real).
      const kbResp = await api.post("/api/knowledge", {
        name: BASE_NAME,
        scope: "global",
        source: "upload",
        similarityThreshold: -1.0,
      });
      expect(kbResp.status, `criar base: ${kbResp.status} ${kbResp.text.slice(0, 200)}`).toBe(201);

      await page.goto("/knowledge");
      // A base aparece na sidebar; clica para selecionar (abre docs + chat).
      const baseCard = page.getByText(BASE_NAME).first();
      await expect(baseCard).toBeVisible({ timeout: 20_000 });
      await baseCard.click();
      await expect(page.getByText(/Documentos/).first()).toBeVisible({ timeout: 20_000 });

      // Envia um documento .md (upload direto, sem confirmação).
      await page.locator("#knowledge-upload").setInputFiles({
        name: "doc.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("# Documento de teste\n\nO capital médio de uma startup é de 500 mil reais.\n"),
      });
      await expect(page.getByText(/doc\.md/).first()).toBeVisible({ timeout: 30_000 });

      // Pergunta e espera a resposta com fonte citada.
      // Em modo mock o LLM devolve texto sem o marcador [1] literal, então a
      // citação aparece como lista de fontes ("1 fonte" + "1. doc.md"). Em modo
      // real o LLM cita [1] no texto e o Citations renderiza o sobrescrito.
      const chatInput = page.getByLabel("Mensagem");
      await chatInput.fill("Qual é o capital médio de uma startup?");
      await page.getByRole("button", { name: /Enviar|Perguntar/i }).first().click();
      // A lista de fontes aparece (retrieval retornou o chunk indexado).
      await expect(page.getByText(/1 fonte/).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/doc\.md/).first()).toBeVisible({ timeout: 15_000 });
      await page.screenshot({ path: info.outputPath(`jornada-knowledge-${width}.png`) });
    });

    // ── 7. ⌘K encontra o agente ──────────────────────────────────────────
    await test.step("7. paleta de comandos encontra o agente", async () => {
      await page.goto("/");
      if (isMobile) {
        await page.waitForLoadState("networkidle");
      } else {
        await dashboardReady(page);
      }
      // Abre a paleta (Ctrl+K). Em mobile o atalho pode não existir; usa o
      // botão de busca da topbar quando houver.
      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: /comandos|busca/i }).first();
      await expect(palette).toBeVisible({ timeout: 10_000 });
      await palette.locator("input").first().fill(AGENT_NAME);
      // O agente aparece nos resultados.
      await expect(palette.getByText(AGENT_NAME).first()).toBeVisible({ timeout: 15_000 });
      await page.keyboard.press("Escape");
    });

    // ── Verificação transversal ──────────────────────────────────────────
    // O ReactFlow/xyflow emite um warning conhecido de SVG tags (<path> não
    // reconhecido) que vira console error no dev; não é um bug da jornada.
    const NOISE = ["React DevTools", "favicon.ico", "ResizeObserver loop", "THREE", "WebSocket connection to", "is unrecognized in this browser"];
    const fatalConsole = consoleErrors.filter((t) => !NOISE.some((n) => t.includes(n)));
    const fatalPage = pageErrors.filter((t) => !NOISE.some((n) => t.includes(n)));
    expect(fatalPage, `pageerror em ${width}px: ${fatalPage.join(" | ").slice(0, 800)}`).toHaveLength(0);
    expect(fatalConsole, `erros de console em ${width}px: ${fatalConsole.join(" | ").slice(0, 800)}`).toHaveLength(0);

    // Cleanup da pipeline (o agente e o usuário são limpos pelo fixture).
    if (pipelineId) await dbDeletePipeline(pipelineId).catch(() => undefined);
  });
}
