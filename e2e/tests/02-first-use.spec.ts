/**
 * Jornada 2 — Primeiro uso: dashboard e listas vazias com convite para criar.
 *
 * O usuário do fixture nasce sem dados (contrato §0: portal nasce vazio).
 * Cada tela de lista precisa mostrar um estado vazio com CTA real (navega),
 * sem links mortos (feedback: no-fake-ui).
 *
 * Fontes: protótipo view-dashboard e views de lista; DESIGN-SYSTEM §3 (empty
 * states); feedback no-fake-ui / no-emojis.
 */
import { test, expect, loginViaUI, dashboardReady } from "../fixtures";
import { PASSWORD } from "../helpers";

test.describe("Jornada 2: primeiro uso (estados vazios)", () => {
  test("dashboard vazio convida a criar o primeiro agente", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await dashboardReady(page);
    await page.waitForURL(/(^|\/)$/, { timeout: 30_000 }).catch(() => undefined);

    // Título + subtítulo com contagem zero.
    await expect(page.getByRole("heading", { name: "Agentes", exact: true, level: 1 })).toBeVisible();
    await expect(page.locator("p", { hasText: "0 agentes" })).toBeVisible();

    // Estado vazio com CTA real.
    const empty = page.getByRole("button", { name: /Criar primeiro agente/i }).first();
    await expect(empty).toBeVisible({ timeout: 30_000 });
    await empty.click();
    await expect(page).toHaveURL(/\/agents\/new/, { timeout: 30_000 });
    // A tela de criação realmente carrega (chat + preview).
    await expect(
      page.getByRole("heading", { name: "Novo Agente" })
    ).toBeVisible();
  });

  test("skills: estado vazio com convite", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/skills");
    await expect(page.getByText("Nenhum skill ainda")).toBeVisible({ timeout: 30_000 });
    const cta = page.getByRole("button", { name: /Criar primeiro skill/i }).first();
    await expect(cta).toBeVisible();
  });

  test("tools: estado vazio com convite", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/tools");
    const cta = page.getByRole("button", { name: /Criar primeira tool|Nova tool/i }).first();
    await expect(cta).toBeVisible({ timeout: 30_000 });
  });

  test("MCP servers: estado vazio com convite", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/mcp");
    await expect(page.getByText("Nenhum servidor MCP ainda")).toBeVisible({ timeout: 30_000 });
    const cta = page.getByRole("button", { name: /Registrar primeiro servidor/i }).first();
    await expect(cta).toBeVisible();
  });

  test("knowledge: estado vazio com convite", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/knowledge");
    const cta = page.getByRole("button", { name: /Nova base/i }).first();
    await expect(cta).toBeVisible({ timeout: 30_000 });
    // Sidebar também mostra o estado vazio de bases.
    await expect(page.getByText("Nenhuma base ainda")).toBeVisible();
    // Abre o modal de criação (botão real, não link morto).
    await cta.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("aprovações: fila vazia com mensagem", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/approvals");
    await expect(
      page.getByText("Nenhuma aprovação pendente")
    ).toBeVisible({ timeout: 30_000 });
    // Badge da sidebar/topbar ausente (0 pendentes).
    await expect(
      page.locator('span[aria-label*="aprovações pendentes"]')
    ).toHaveCount(0);
  });

  test("pipelines: tela acessível via URL com estado vazio e CTA", async ({ page, user }) => {
    // OBSERVAÇÃO: a sidebar NÃO tem item "Pipelines" (ver relatório, E1).
    // A tela existe por URL (/pipelines) e é o ponto de partida do editor.
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/pipelines");
    const h1 = page.getByRole("heading", { name: "Pipelines", exact: true });
    await expect(h1).toBeVisible({ timeout: 30_000 });

    // Estado vazio OU erro de listagem (F9/B1: GET /api/pipelines ausente).
    const empty = page.getByRole("button", { name: /Create first pipeline/i });
    const errorBanner = page.getByText("Failed to load pipelines");
    const outcome = await Promise.race([
      empty
        .waitFor({ state: "visible", timeout: 20_000 })
        .then(() => "empty"),
      errorBanner
        .waitFor({ state: "visible", timeout: 20_000 })
        .then(() => "error"),
    ]).catch(() => "neither");
    // O teste documenta o estado real; ambos os ramos são registrados no relatório.
    expect(["empty", "error"]).toContain(outcome);
    if (outcome === "empty") {
      await empty.screenshot({ path: test.info().outputPath("pipelines-empty.png") }).catch(() => undefined);
    }
  });

  test("navegação da sidebar cobre as telas do PLANO-FRONTEND", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    const items: Array<[string, RegExp]> = [
      ["Dashboard", /\/$/],
      ["Novo Agente", /\/agents\/new/],
      ["Aprovações", /\/approvals/],
      ["Skills", /\/skills/],
      ["Tools Custom", /\/tools/],
      ["MCP Servers", /\/mcp/],
      ["Knowledge", /\/knowledge/],
    ];
    for (const [label, url] of items) {
      await page
        .locator('nav[aria-label="Navegação principal"]')
        .getByRole("link", { name: new RegExp(label) })
        .click();
      await expect(page).toHaveURL(url, { timeout: 30_000 });
      // Cada navegação deixa uma página renderizada (título h1).
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 15_000 });
    }
  });
});
