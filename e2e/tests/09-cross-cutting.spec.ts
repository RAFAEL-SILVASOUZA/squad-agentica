import { test, expect, loginViaUI } from "../fixtures";
import { PASSWORD } from "../helpers";

const ROUTES = ["/", "/agents/new", "/approvals", "/skills", "/tools", "/mcp", "/knowledge", "/pipelines"];
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u;

for (const width of [1280, 390]) {
  test(`telas em ${width}px: console, emoji, layout e ações principais`, async ({ page, user }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await loginViaUI(page, user.email, PASSWORD);
    if (width === 1280) {
      expect.soft(await page.locator('nav a[href="/pipelines"]').count(), "E14: navegação deve permitir abrir Pipelines").toBe(1);
    }
    const audit: unknown[] = [];
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", msg => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", error => pageErrors.push(error.message));
    for (const route of ROUTES) {
      await test.step(route, async () => {
        const start = consoleErrors.length;
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("h1").first()).toBeVisible();
        const geometry = await page.evaluate(() => ({
          documentOverflow: document.documentElement.scrollWidth - innerWidth,
          mainOverflow: Math.max(...Array.from(document.querySelectorAll("main")).map(el => el.scrollWidth-el.clientWidth)),
          emoji: document.body.innerText.match(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u)?.[0] ?? null,
        }));
        const buttons = await page.getByRole("button").allTextContents();
        const screenshot = info.outputPath(`${width}-${route.replaceAll("/", "_") || "dashboard"}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        audit.push({ route, width, ...geometry, buttons, console: consoleErrors.slice(start), screenshot });
        expect.soft(geometry.documentOverflow, `${route}: documento`).toBeLessThanOrEqual(1);
        expect.soft(geometry.mainOverflow, `${route}: conteúdo de main`).toBeLessThanOrEqual(1);
        expect.soft(geometry.emoji, `${route}: emoji`).toBeNull();
        if (route === "/skills" || route === "/tools" || route === "/mcp" || route === "/knowledge") {
          const create = page.getByRole("button", { name: /Criar primeiro skill|Criar primeira tool|Registrar primeiro servidor|Nova base/ }).first();
          await create.click();
          await expect(page.getByRole("dialog")).toBeVisible();
          await page.keyboard.press("Escape");
          await expect(page.getByRole("dialog")).not.toBeVisible();
        }
      });
    }
    if (width === 390) {
      // Mobile: a navegação é pela BottomNav (Task 17). "Mais" abre a sidebar
      // overlay (Navegação principal) com o resto dos links.
      await page.getByRole("button", { name: "Mais", exact: true }).click();
      const nav = page.getByRole("navigation", { name: "Navegação principal" });
      await expect(nav).toBeVisible();
      await nav.locator('a[href="/skills"]').click();
      await expect(page).toHaveURL(/\/skills$/);
    }
    await info.attach("screen-audit", {body: JSON.stringify(audit, null, 2), contentType: "application/json"});
    expect.soft(pageErrors, "exceções JS").toEqual([]);
    // F9 gera console 404 na lista de pipelines; audit preserva todos os erros.
    const otherErrors = consoleErrors.filter(s => !s.includes("404") && !s.includes("React DevTools"));
    expect.soft(otherErrors, "erros de console além do F9 conhecido").toEqual([]);
  });
}

test("login por teclado: Tab e Enter", async ({ page, user }) => {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("Tab");
  await expect(page.locator("#email")).toBeFocused();
  await page.locator("#email").fill(user.email);
  await page.keyboard.press("Tab");
  await expect(page.locator("#password")).toBeFocused();
  await page.locator("#password").fill(PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/login/, {timeout: 30000});
});
