/**
 * Jornada 1 — Autenticação (registro, login, logout, redirect de rota protegida).
 *
 * O usuário da jornada 1 é registrado AQUI (via UI), porque o registro por UI é
 * o que está sendo testado. Por isso NÃO usamos o fixture `user` (que registra
 * via API): usamos um e-mail próprio e limpo no teardown.
 *
 * Fontes: contrato §5 (fluxo de auth), spec §3.14 (login/registro),
 * GUIA-API-FRONTEND (auth).
 */
import { test, expect } from "../fixtures";
import { Api, db, dbDeleteUser, uniqueEmail } from "../helpers";

const EMAIL = uniqueEmail("auth");
const PASSWORD = "AuthE2e123!";
const NAME = "QA Auth E2E";

test.describe("Jornada 1: autenticação", () => {
  test.beforeEach(async ({}, info) => {
    if (/credenciais válidas|senha errada|logout|duplicado/.test(info.title)) {
      const result = await new Api().post("/api/auth/register", {name: NAME, email: EMAIL, password: PASSWORD});
      expect([201, 409]).toContain(result.status);
    }
  });
  test.afterAll(async () => {
    // Limpeza do usuário registrado via UI (id descoberto via e-mail).
    try {
      const rows = await db(
        "query",
        "SELECT id FROM users WHERE email = %s",
        JSON.stringify([EMAIL])
      );
      for (const [id] of rows) {
        await dbDeleteUser(id as string);
      }
    } catch {
      // usuário já removido
    }
  });

  test("redirect de rota protegida leva ao login com callbackUrl", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
    // O middleware preserva a rota original em callbackUrl.
    const search = new URL(page.url()).searchParams.get("callbackUrl");
    expect(search, `callbackUrl ausente; URL atual: ${page.url()}`).toBeTruthy();
  });

  test("registro por UI cria a conta e entra direto", async ({ page }) => {
    await page.goto("/register");
    await page.locator("#name").fill(NAME);
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("#confirmPassword").fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    // Sucesso: chega no dashboard (shell com sidebar).
    await page
      .locator('nav[aria-label="Navegação principal"]')
      .waitFor({ state: "visible", timeout: 30_000 });
    await expect(page).not.toHaveURL(/\/login|\/register/);
  });

  test("login com credenciais válidas entra no dashboard", async ({ page }) => {
    // Sessão nova (sem cookies).
    await page.context().clearCookies();
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page
      .locator('nav[aria-label="Navegação principal"]')
      .waitFor({ state: "visible", timeout: 30_000 });
  });

  test("login com senha errada mostra erro genérico e não entra", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill("SenhaErrada999!");
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('[role="alert"]').filter({ hasText: "Credenciais inválidas" })).toContainText(
      "Credenciais inválidas"
    );
    await expect(page).toHaveURL(/\/login/);
    // Não pode ter entrado.
    await expect(
      page.locator('nav[aria-label="Navegação principal"]')
    ).toHaveCount(0);
  });

  test("login com validação client-side (campo vazio / senha curta)", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    // Campo vazio.
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("#email-error")).toContainText("obrigatório");
    await expect(page.locator("#password-error")).toContainText("obrigatória");

    // Senha curta.
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill("123");
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("#password-error")).toContainText("8 caracteres");
    await expect(page).toHaveURL(/\/login/);
  });

  test("logout derruba a sessão e protege as rotas de novo", async ({ page }) => {
    // Garante sessão logada.
    await page.context().clearCookies();
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page
      .locator('nav[aria-label="Navegação principal"]')
      .waitFor({ state: "visible", timeout: 30_000 });

    await page.locator('button[aria-label="Sair"]').click();
    await expect(page).toHaveURL(/\/login/, { timeout: 30_000 });

    // Rota protegida volta a redirecionar.
    await page.goto("/skills");
    await expect(page).toHaveURL(/\/login/);
  });

  test("registro com e-mail duplicado mostra erro e não cria conta", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/register");
    await page.locator("#name").fill(NAME);
    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("#confirmPassword").fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    // O backend devolve 409; a UI exibe o erro e permanece na tela de registro.
    await expect(page.locator('[role="alert"]').filter({ hasText: /email|e-mail|existe|registrad/i })).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/register/);
    await expect(
      page.locator('nav[aria-label="Navegação principal"]')
    ).toHaveCount(0);
  });
});
