/**
 * Suíte E2E do Agent Portal (nó qa-e2e).
 *
 * Rode a partir da raiz do repositório:
 *   npx playwright test --config e2e/playwright.config.ts
 *
 * O stack `docker compose -p squad-agentica` deve estar de pé (NGINX :80),
 * com LLM_PROVIDER=mock / EMBEDDING_PROVIDER=mock (contrato §4).
 * Navegador: Chromium (instalar com `npx playwright install chromium`).
 *
 * workerCount=1: o rate limit do backend é por IP (login 5/min, execute
 * 5/min), e todo o tráfego do host chega pelo mesmo IP via NGINX.
 * Paralelismo aqui quebraria os próprios testes com 429.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["tests/**/*.spec.ts"],
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "test-results/html", open: "never" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  outputDir: "test-results/artifacts",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost",
    browserName: "chromium",
    headless: true,
    viewport: { width: 1280, height: 800 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 45_000,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
});
