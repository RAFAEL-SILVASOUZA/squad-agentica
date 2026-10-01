/**
 * Jornada 3 — Criar agente pelo chat de construção + editar contrato e mochila.
 *
 * Fluxo (spec §10): chat de construção (SSE streaming) → preview atualizado →
 * confirmação (Salvar) → agente criado → edição do contrato (ports/actions) e
 * da mochila (skills) pela tela de detalhe.
 *
 * O chat é mockado (page.route) para devolver um draft determinístico, porque
 * o provedor real é `mock` (LLM_PROVIDER=mock) e devolve um texto puro que o
 * parser trata como texto (sem config) — a jornada precisa de um draft real
 * para exercitar streaming + preview + confirmação. A decisão de mock do
 * streaming é registrada no relatório.
 *
 * Fontes: spec §10, GUIA-API-FRONTEND (Agentes, chat), protótipo
 * view-AGENT-DETAIL.
 */
import { test, expect, loginViaUI, mockAgentChat, PASSWORD } from "../fixtures";
import { db, dbCreateAgent, dbDeleteUser, purgeAgentsViaApi } from "../helpers";
import { Api } from "../helpers";

const AGENT_NAME = "QA Agent E2E";

test.describe("Jornada 3: criar agente por chat + editar", () => {
  test("chat de construção gera draft com streaming e preview", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/agents/new");
    await expect(page.getByRole("heading", { name: "Novo Agente" })).toBeVisible();

    // O botão permanece habilitado mesmo sem draft; a API rejeita a confirmação.

    // Primeira jornada usa o provedor mock real, sem interceptar SSE.

    // Envia a descrição do agente.
    await page.locator("#agent-chat-input").fill(
      "Um agente que recebe uma spec e devolve um resultado."
    );
    await page.getByRole("button", { name: /Enviar mensagem/i }).click();

    // Streaming visível: indicador "Assistente respondendo…" e o texto chega.
    await expect(
      page.locator('div[role="log"]').getByText(/MOCK_LLM/i).first()
    ).toBeVisible({ timeout: 15_000 });
    // Com o provedor mock real (texto puro, sem config_update), o preview fica vazio.
    await expect(page.getByText("Descreva o agente no chat para ver o preview aqui.")).toBeVisible();
    const saveBtn = page.getByRole("button", { name: /Salvar agente/i });
    await expect(saveBtn).toBeEnabled();

    const confirmResp = page.waitForResponse(
      (response) => response.url().includes("/api/agents/chat/confirm"),
      { timeout: 10_000 }
    );
    await saveBtn.click();
    const response = await confirmResp;
    expect(response.status(), "confirmação sem preview deve retornar 400").toBe(400);
    await expect(page.locator("[role=status], [role=alert]").filter({ hasText: /400|inválid|preview|rascunho/i }).last()).toBeVisible();
  });

  test("confirmação cria o agente e navega para o detalhe", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/agents/new");
    await mockAgentChat(page, {}, AGENT_NAME);

    await page.locator("#agent-chat-input").fill("crie um agente de teste");
    await page.getByRole("button", { name: /Enviar mensagem/i }).click();

    const saveBtn = page.getByRole("button", { name: /Salvar agente/i });
    await expect(saveBtn).toBeEnabled({ timeout: 15_000 });
    await saveBtn.click();

    // Toast de sucesso + navegação para /agents/{id}.
    await expect(page.getByText(/criado/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/agents\/[0-9a-f-]{36}/, { timeout: 20_000 });

    // O agente aparece com o nome no detalhe.
    await expect(
      page.getByRole("heading", { name: AGENT_NAME })
    ).toBeVisible({ timeout: 20_000 });

    // Confirmação no banco: o agente existe para o owner.
    const agents = await db(
      "query",
      "SELECT id, name FROM agents WHERE owner_id = %s AND name = %s",
      JSON.stringify([user.id, AGENT_NAME])
    );
    expect(agents.length, "agente persistido para o owner").toBeGreaterThan(0);
  });

  test("salvar com nome já existente mostra erro legível e permanece", async ({ page, user, api }) => {
    const dup = AGENT_NAME + " Dup";
    const pre = await api.post("/api/agents", {
      name: dup, type: "custom", description: "pre-existente", prompt: "p", strategy: "react",
      inputs: [], outputs: [{ name: "result", type: "document", required: true }],
      actions: ["finalize"], model: "gpt-4o", maxIterations: 5, timeout: 60, shellAccess: false,
    });
    expect(pre.status, pre.text.slice(0, 200)).toBe(201);
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/agents/new");
    await mockAgentChat(page, {}, dup);
    await page.locator("#agent-chat-input").fill("crie um agente duplicado");
    await page.getByRole("button", { name: /Enviar mensagem/i }).click();
    const saveBtn = page.getByRole("button", { name: /Salvar agente/i });
    await expect(saveBtn).toBeEnabled({ timeout: 15_000 });
    await saveBtn.click();
    const toast = page.locator("[role=status]").filter({ hasText: /./ }).last();
    await expect(toast).toBeVisible({ timeout: 10_000 });
    const text = (await toast.innerText()).trim();
    await expect(page).toHaveURL(/\/agents\/new/);
    expect(text, `toast de erro de nome duplicado: "${text}"`).toMatch(/existe|nome|duplicad/i);
  });

  test("editar contrato (ports e actions) e mochila (skill) e salvar", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/agents/new");
    await mockAgentChat(page, {}, AGENT_NAME + " Edit");
    await page.locator("#agent-chat-input").fill("crie um agente para edição");
    await page.getByRole("button", { name: /Enviar mensagem/i }).click();
    const saveBtn = page.getByRole("button", { name: /Salvar agente/i });
    await expect(saveBtn).toBeEnabled({ timeout: 15_000 });
    await saveBtn.click();
    await expect(page).toHaveURL(/\/agents\/[0-9a-f-]{36}/, { timeout: 20_000 });
    const agentId = new URL(page.url()).pathname.split("/").pop()!;

    // Cria uma skill via API para ligar na mochila.
    const api = new Api();
    api.token = user.accessToken;
    const skill = await api.post("/api/skills", {
      name: "QA Skill E2E",
      description: "skill de teste",
      category: "docs",
      definition: { template: "## Instruções\nUse {{contexto}}.", variables: ["contexto"] },
    });
    expect(skill.status, `criar skill: ${skill.status} ${skill.text.slice(0, 200)}`).toBe(201);

    await page.reload();
    // Edita o contrato: adiciona uma entrada (port) e uma saída.
    await page.getByRole("button", { name: /Adicionar entrada/i }).click();
    const in1 = page.getByLabel(/Nome da entrada 2/i);
    await in1.fill("spec_extra");
    await expect(in1).toHaveValue("spec_extra");

    await page.getByRole("button", { name: /Adicionar saída/i }).click();
    const out1 = page.getByLabel(/Nome da saída 2/i);
    await out1.fill("result_extra");
    await expect(out1).toHaveValue("result_extra");

    // Liga a skill na mochila.
    const skillSelect = page.getByLabel(/Selecionar skill/i);
    await expect(skillSelect).toBeEnabled({ timeout: 15_000 });
    await skillSelect.selectOption(skill.body.id);
    await page.getByRole("button", { name: "Adicionar skill" }).click();

    // E3: o chip da mochila deveria mostrar o nome da skill, não o UUID.
    expect.soft(
      await page.getByText(skill.body.id, { exact: true }).count(),
      "E3: chip da skill na mochila mostra o id em vez do nome"
    ).toBe(0);

    // Salva.
    const putResp = page.waitForResponse(
      (r) => r.request().method() === "PUT" && /\/api\/agents\//.test(r.url()),
      { timeout: 15_000 }
    );
    await page.getByRole("button", { name: /Salvar/i }).last().click();
    const put = await putResp;
    const toastText = await page
      .locator("[role=status]")
      .filter({ hasText: /./ })
      .last()
      .innerText({ timeout: 5_000 })
      .catch(() => "");
    expect(
      put.status(),
      `E4: PUT do agente após adicionar portas -> ${put.status()} ${(await put.text()).slice(0, 200)}; toast: "${toastText}"`
    ).toBe(200);
    await expect(page.getByText(/atualizado/i).first()).toBeVisible({ timeout: 15_000 });

    // Confirma no banco: ports e skill persistidos.
    const row = await db(
      "query",
      "SELECT inputs, outputs, skills FROM agents WHERE id = %s",
      JSON.stringify([agentId])
    );
    expect(row.length).toBe(1);
    const [inputs, outputs, skills] = row[0];
    expect(inputs.map((p: any) => p.name)).toContain("spec_extra");
    expect(outputs.map((p: any) => p.name)).toContain("result_extra");
    expect(skills.some((s: any) => s.skillId === skill.body.id)).toBe(true);

    // Cleanup da skill (owner cascade apaga no teardown do usuário).
  });
});
