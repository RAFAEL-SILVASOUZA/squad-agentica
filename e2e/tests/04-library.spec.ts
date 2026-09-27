/**
 * Jornada 4 — Biblioteca: criar skill, tool custom (testar no sandbox),
 * servidor MCP (testar conexão com o fake da suíte de integração) e
 * knowledge base com upload.
 *
 * Cada tela usa os próprios modais (components/ui/modal, role="dialog").
 * O MCP usa o mesmo servidor fake da suite de integração
 * (tests/integration/fake_mcp_server.py) subindo como container na rede do
 * compose, para que o orchestrator o alcance por nome.
 *
 * Fontes: GUIA-API-FRONTEND (Skills/Tools/MCP/Knowledge), spec §6, contrato §4.
 * Falhas conhecidas: F5 (upload de knowledge = 500 storage_error), F17.
 */
import { test, expect, loginViaUI } from "../fixtures";
import { PASSWORD, McpFake, Api } from "../helpers";

test.describe("Jornada 4a: skill", () => {
  test("criar skill com template e preview, editar, excluir", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/skills");

    await page.getByRole("button", { name: /Criar primeiro skill/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const name = `QA Skill ${Date.now().toString(36)}`;
    await page.locator("#skill-name").fill(name);
    await page.locator("#skill-description").fill("skill criada pela E2E");
    await page.locator("#skill-template").fill("## Instruções\nResponda {{objetivo}}.");
    await page.locator("#skill-variables").fill("objetivo");
    const createBtn = dialog.getByRole("button", { name: /Criar skill/i });
    // E5: o modal não tem altura máxima nem rolagem; em 1280x800 o rodapé
    // fica fora da viewport e o botão é inalcançável.
    const box = await createBtn.boundingBox();
    const vh = page.viewportSize()!.height;
    expect.soft(
      !!box && box.y >= 0 && box.y + box.height <= vh,
      `E5: botão "Criar skill" fora da viewport (y=${box?.y}, altura da viewport=${vh})`
    ).toBe(true);
    // Contorno para seguir a jornada: viewport alta.
    await page.setViewportSize({ width: 1280, height: 1600 });
    await createBtn.click();

    // Card aparece com o nome.
    await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });
    await expect(dialog).toHaveCount(0);

    // Abre o editor via card e edita a descrição.
    await page.getByText(name).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#skill-description").fill("desc editada pela E2E");
    await page.getByRole("dialog").getByRole("button", { name: /Salvar/i }).click();
    await expect(page.getByText(/atualizada/i).first()).toBeVisible({ timeout: 15_000 });

    // Exclusão com modal de confirmação (sem window.confirm).
    await page.getByRole("button", { name: new RegExp(`Excluir skill ${name}`) }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: /Excluir|Confirmar/i }).click();
    await expect(page.getByText(name)).toHaveCount(0, { timeout: 20_000 });
  });
});

test.describe("Jornada 4b: tool custom (sandbox)", () => {
  test("criar tool python, testar no sandbox, deploy", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/tools");

    await page.getByRole("button", { name: /Criar primeira tool/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const name = `QA Tool ${Date.now().toString(36)}`;
    // E7: o placeholder do script ensina `def main(inputs)`, mas o sandbox
    // chama `execute(**args)` (spec, tools custom). Registrado como soft.
    const placeholder = (await page.locator("#tool-script").getAttribute("placeholder")) ?? "";
    expect.soft(placeholder, "E7: placeholder do script deve usar execute(...)").toMatch(/def execute/);
    await page.locator("#tool-name").fill(name);
    await page.locator("#tool-description").fill("echo tool da E2E");
    await page.locator("#tool-script").fill(
      "def execute(data=''):\n    return {'result': 'ok:' + str(data)}"
    );
    await page.locator("#tool-inputs").fill('[{"name": "data", "type": "string", "required": false}]');
    await page.locator("#tool-outputs").fill('[{"name": "result", "type": "string", "required": false}]');
    await dialog.getByRole("button", { name: /Criar tool/i }).click();

    await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });

    // Testar no sandbox.
    await page.getByRole("button", { name: new RegExp(`Testar tool ${name}`) }).click();
    const testDialog = page.getByRole("dialog");
    await expect(testDialog).toBeVisible();
    await page.locator("#tool-test-input").fill('{"data": "e2e"}');
    await testDialog.getByRole("button", { name: /Executar teste/i }).click();

    // O sandbox executa e devolve o resultado (sucesso ou erro estruturado).
    const resultVisible = await testDialog
      .getByText("ok:e2e", { exact: false })
      .first()
      .waitFor({ state: "visible", timeout: 30_000 })
      .then(() => true)
      .catch(() => false);
    // E8: a UI envia { input } e o backend espera { args }: o input é ignorado.
    expect.soft(resultVisible, "E8: resultado do sandbox deve refletir o input (ok:e2e)").toBe(true);
    await page.screenshot({ path: test.info().outputPath("tool-sandbox.png") });
    await testDialog.getByRole("button", { name: /Fechar/i }).last().click();

    // Deploy (versão +1, status deployed).
    await page.getByRole("button", { name: new RegExp(`Deploy tool ${name}`) }).click();
    await expect(page.getByText(/deployed/i).first()).toBeVisible({ timeout: 20_000 });
  });
});

test.describe("Jornada 4c: MCP server (fake)", () => {
  let fake: McpFake | null = null;
  test.beforeAll(async () => {
    fake = await McpFake.start();
  });
  test.afterAll(async () => {
    await fake?.stop();
  });

  test("registrar MCP e testar conexão com o fake da suíte de integração", async ({ page, user }) => {
    if (!fake) throw new Error("MCP fake não subiu");
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/mcp");

    await page.getByRole("button", { name: /Registrar primeiro servidor/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const name = `QA MCP ${Date.now().toString(36)}`;
    await page.locator("#mcp-name").fill(name);
    await page.locator("#mcp-description").fill("fake MCP da suíte");
    await page.locator("#mcp-transport").selectOption("http");
    await page.locator("#mcp-url").fill(fake.url);
    await dialog.getByRole("button", { name: /Registrar servidor|Salvar/i }).click();
    await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });

    // Testar conexão: esperado status connected + discoveredTools [qa_echo]
    // (mesma expectativa da suite de integração).
    await page.getByRole("button", { name: new RegExp(`Testar servidor|Testar MCP|Testar .*${name}|Testar`) }).first().click();
    const testDialog = page.getByRole("dialog");
    await expect(testDialog).toBeVisible({ timeout: 10_000 });
    const testBtn = testDialog.getByRole("button", { name: /Testar conexão|Testar|Executar/i }).first();
    await testBtn.click();
    await page
      .getByText(/connected|qa_echo|error|Erro/i)
      .first()
      .waitFor({ state: "visible", timeout: 30_000 })
      .catch(() => undefined);
    await page.screenshot({ path: test.info().outputPath("mcp-test.png") });

    // Evidência via API (a UI pode não mostrar a lista de tools): esperado
    // connected + qa_echo.
    const api = new Api();
    api.token = user.accessToken;
    const list = await api.get("/api/mcp-servers?limit=50");
    const srv = (list.body?.items ?? []).find((s: any) => s.name === name);
    expect(srv, "servidor MCP listado").toBeTruthy();
    const r = await api.post(`/api/mcp-servers/${srv.id}/test`);
    expect(r.status).toBe(200);
    expect(r.body.status, `esperado connected: ${JSON.stringify(r.body).slice(0, 200)}`).toBe("connected");
    expect(r.body.discoveredTools?.map((t: any) => t.name)).toContain("qa_echo");
  });
});

test.describe("Jornada 4d: knowledge base (upload)", () => {
  test("criar base e enviar documento (F5: bucket knowledge ausente)", async ({ page, user }) => {
    await loginViaUI(page, user.email, PASSWORD);
    await page.goto("/knowledge");

    await page.getByRole("button", { name: /Nova base/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const kbName = `QA KB ${Date.now().toString(36)}`;
    await page.locator("#kb-name").fill(kbName);
    await page.locator("#kb-description").fill("base da E2E");
    const [createResp] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === "POST" && /\/api\/knowledge(\?|$)/.test(r.url()), { timeout: 20_000 }),
      dialog.getByRole("button", { name: /Criar base/i }).click(),
    ]);
    // E6: o formulário não envia `source` (obrigatório no backend) -> 422 e o
    // modal mostra o JSON cru do pydantic.
    expect.soft(createResp.status(), `E6: criar base pela UI -> ${createResp.status()} ${(await createResp.text()).slice(0, 160)}`).toBe(201);
    if (createResp.status() !== 201) {
      // Contorno: cria a base pela API (source=upload) para seguir ao upload.
      const api = new Api();
      api.token = user.accessToken;
      const kb = await api.post("/api/knowledge", { name: kbName, description: "base da E2E", scope: "global", source: "upload" });
      expect(kb.status, kb.text.slice(0, 200)).toBe(201);
      await page.reload();
    }
    await expect(page.getByText(kbName).first()).toBeVisible({ timeout: 20_000 });

    // Seleciona a base na sidebar.
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(String(e)));
    await page.getByText(kbName).first().click();
    await page.waitForTimeout(2_000);
    // E9: GET /documents é paginado ({ items }) e a UI espera array ->
    // "documents.map is not a function" derruba a tela.
    expect.soft(pageErrors, `E9: selecionar a base gera exceção: ${pageErrors.join(" | ").slice(0, 200)}`).toHaveLength(0);
    if (pageErrors.length) {
      // Contorno: desembrulha a página para a UI seguir até o upload.
      await page.route(/\/api\/knowledge\/[^/]+\/documents(\?|$)/, async (route) => {
        if (route.request().method() !== "GET") return route.continue();
        const res = await route.fetch();
        const body = await res.json().catch(() => null);
        return route.fulfill({ response: res, json: Array.isArray(body) ? body : body?.items ?? [] });
      });
      await page.goto("/knowledge");
      await page.getByText(kbName).first().click();
    }

    // Upload: F5 — o bucket 'knowledge' não existe no Garage (garage/init.sh),
    // o backend devolve 500 storage_error. A UI precisa exibir o erro.
    const [resp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/knowledge/") && r.url().includes("/upload"), { timeout: 30_000 }),
      page.setInputFiles("#knowledge-upload", {
        name: "doc.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Documento de teste E2E. Conteúdo para indexação."),
      }),
    ]);
    // Com F5 ativo: 500 storage_error. Corrigido: 201/200 + documento listado.
    // E10: a UI força Content-Type multipart/form-data sem boundary -> 400
    // "Missing boundary in multipart" antes de chegar ao storage (F5).
    expect(resp.status(), `E10: upload respondeu ${resp.status()}: ${(await resp.text()).slice(0, 160)}`).not.toBe(400);
    await page.screenshot({ path: test.info().outputPath("knowledge-upload.png") });

    // Evidência: com F5, um toast/badge de erro aparece; sem F5, o documento.
    const hasError = await page
      .locator("[role=status]")
      .filter({ hasText: /storage|Falha|erro/i })
      .first()
      .isVisible()
      .catch(() => false);
    const hasDoc = await page
      .getByText("doc.txt")
      .first()
      .isVisible()
      .catch(() => false);
    // O teste documenta o estado real; o relatório cruza com F5.
    expect(resp.status() === 500 ? hasError : hasDoc, "upload: erro visível (F5) ou documento listado").toBe(true);
  });
});
