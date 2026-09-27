/**
 * Fixtures da suíte E2E (nó qa-e2e).
 *
 * - `user`: usuário de teste (registro via API + login na UI), criado por
 *   módulo e removido no fim (usuário do banco + cascata).
 * - `consoleErrors`/`pageErrors`: coleta erros de console e de página para a
 *   verificação transversal (jornada 9). Whitelist de ruído benigno.
 * - `loginPage`: helper para logar via UI (form NextAuth).
 *
 * O usuário é criado via API (registro) e logado na UI para que a sessão
 * NextAuth (cookie) exista; o token de API para chamadas diretas vem do
 * `Api` do helper.
 */
import { test as base, expect, type Page } from "@playwright/test";
import {
  Api,
  TestUser,
  dbDeleteUser,
  purgeAgentsViaApi,
  uniqueEmail,
  sleep,
} from "./helpers";

/** Ruído benigno que não indica bug de produto. */
const CONSOLE_NOISE = [
  "Download the React DevTools",
  "favicon.ico",
  "ResizeObserver loop",
  "THREE",
  "WebSocket connection to", // reconexão de WS derrubada no teardown
];

export interface E2eWorkerFixtures {
  user: TestUser;
}

export interface E2eFixtures {
  api: Api;
  consoleErrors: string[];
  pageErrors: string[];
  assertNoFatalConsole: () => Promise<void>;
}

export const test = base.extend<E2eFixtures, E2eWorkerFixtures>({
  // Escopo de worker: um usuário por worker (um worker novo por arquivo e após
  // cada falha). Reduz o consumo do rate limit de login (5/min por IP).
  user: [
    async ({}, use, workerInfo) => {
      const api = new Api();
      const email = uniqueEmail(`w${workerInfo.workerIndex}`);
      const user = await api.register("QA E2E", email);
      await use(user);
      // Teardown: remove agentes (Garage) pela API e o usuário pelo banco.
      await purgeAgentsViaApi(api, user.accessToken).catch(() => undefined);
      await dbDeleteUser(user.id).catch(() => undefined);
    },
    { scope: "worker" },
  ],

  api: async ({ user }, use) => {
    const api = new Api();
    api.token = user.accessToken;
    await use(api);
  },

  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await use(errors);
  },

  pageErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));
    await use(errors);
  },

  assertNoFatalConsole: async ({ consoleErrors, pageErrors }, use) => {
    await use(async () => {
      const fatalConsole = consoleErrors.filter(
        (t) => !CONSOLE_NOISE.some((n) => t.includes(n))
      );
      expect(
        pageErrors,
        `pageerror (exceção de JS): ${pageErrors.join(" | ").slice(0, 800)}`
      ).toHaveLength(0);
      expect(
        fatalConsole,
        `erros de console: ${fatalConsole.join(" | ").slice(0, 800)}`
      ).toHaveLength(0);
    });
  },
});

export { expect };

/** Senha padrão dos usuários criados pela suíte (re-export para os testes). */
export { PASSWORD } from "./helpers";

/**
 * Loga via UI (form NextAuth) e espera o shell do dashboard.
 * O rate limit do login é 5/min por IP e é compartilhado por toda a suíte
 * (o registro também consome). Em 429 o backend devolve retryAfter no
 * envelope; a espera abaixo cobre a janela deslizante.
 */
export async function loginViaUI(
  page: Page,
  email: string,
  password: string,
  maxAttempts = 2
): Promise<void> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(password);
    const [res] = await Promise.all([
      page
        .waitForResponse((r) => r.url().includes("/api/auth/callback/credentials"), { timeout: 30_000 })
        .catch(() => null),
      page.locator('button[type="submit"]').click(),
    ]);
    const status = res?.status() ?? 0;
    if (status === 401 && attempt + 1 < maxAttempts) {
      // NextAuth masks the upstream login 429 as CredentialsSignin (401).
      // One bounded cooldown prevents rate-limit noise between UI scenarios.
      await sleep(60_000);
      continue;
    }
    if (status === 429) {
      let wait = 12;
      try {
        wait = ((await res!.json()).details?.retryAfter as number) ?? 12;
      } catch {
        // envelope inesperado; usa o default
      }
      await sleep(Math.min(wait + 3, 70) * 1000);
      continue;
    }
    // O shell (dashboard) tem a sidebar de navegação.
    await page.waitForURL((url) => !/\/login|\/register/.test(url.pathname), { timeout: 30_000 });
    return;
  }
  throw new Error("loginViaUI: esgotou tentativas (429/timeout)");
}

/** Aguarda um toast (components/ui/toast renderiza com role=status). */
export async function waitForToast(page: Page, text?: string, timeout = 15_000) {
  const toast = page.locator("[role=status]");
  await toast
    .filter({ hasText: text ?? "" })
    .first()
    .waitFor({ state: "visible", timeout });
  return toast;
}

/** Aguarda o loading do dashboard sumir (skeleton -> conteúdo). */
export async function dashboardReady(page: Page) {
  await page
    .locator('nav[aria-label="Navegação principal"]')
    .waitFor({ state: "visible" });
  // Espera o "Carregando…" sair do subtítulo (dados carregados ou erro).
  await page
    .locator("p")
    .filter({ hasText: "Carregando…" })
    .waitFor({ state: "detached", timeout: 30_000 })
    .catch(() => undefined);
  await sleep(300);
}

/**
 * Mocka o chat de construção para devolver um draft determinístico.
 * O mock real (LLM_PROVIDER=mock) devolve `MOCK_LLM: echo of: <msg>`, que o
 * parser trata como texto puro (sem config) — por isso, para exercitar o fluxo
 * completo (streaming + preview + confirmação), a suíte injeta uma resposta
 * JSON válida conforme o contrato do be-agent-chat.
 */
export async function mockAgentChat(
  page: Page,
  draft: Record<string, unknown>,
  name: string
): Promise<void> {
  await page.route(/\/api\/agents\/chat(?:\/|\?|$)/, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const config = {
      name,
      type: "custom",
      description: "Agente criado pela suíte E2E.",
      prompt: "Você é um agente de teste que responde no campo result.",
      strategy: "react",
      inputs: [{ name: "spec", type: "document", required: false }],
      outputs: [{ name: "result", type: "document", required: true }],
      actions: ["follow", "finalize"],
      model: "gpt-4o",
      maxIterations: 5,
      timeout: 60,
      shellAccess: false,
      ...draft,
    };
    if (new URL(route.request().url()).pathname.endsWith("/confirm")) {
      // Isolated UI continuation: persist through real CRUD; this does not
      // validate the backend draft store or the real chat-confirm endpoint.
      const response = await route.fetch({
        url: new URL("/api/agents", route.request().url()).toString(),
        method: "POST",
        postData: config,
      });
      return route.fulfill({ response });
    }
    const draftId = "e2e-" + crypto.randomUUID();
    const events = [
      `data: ${JSON.stringify({ type: "text", data: "Entendido. Vou montar o rascunho do agente." })}\n\n`,
      `data: ${JSON.stringify({ type: "config_update", data: config })}\n\n`,
      `data: ${JSON.stringify({ type: "done", data: { draftId } })}\n\n`,
    ].join("");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache", "X-Accel-Buffering": "no" },
      body: events,
    });
  });
}
