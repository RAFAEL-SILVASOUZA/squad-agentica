/**
 * Jornada 10: conexão Git -> repositório no pipeline -> execução -> arquivos e PR.
 *
 * Ambiente: stack em mock com o perfil "test" do compose (serviço git-test:
 * git daemon + GitHub fake) e o orchestrator apontado para ele
 * (GITHUB_API_BASE=http://git-test:8080, GIT_CLONE_BASE_OVERRIDE=git://git-test).
 * Sem esse ambiente a jornada é pulada (ver qa-projeto-git.md).
 *
 * Tudo pela UI: cadastrar a conexão (token de teste), testar, vincular o
 * repositório pelo RepositoryPicker do cabeçalho do editor, executar, abrir o
 * monitor na aba Arquivos (result.md gravado pelo agente mock) e ver o link
 * do PR no cabeçalho. Só os agentes e o pipeline vazio nascem pela API.
 */
import { test, expect, loginViaUI } from "../fixtures";
import { PASSWORD, Api, GitTest } from "../helpers";

async function createAgent(api: Api, name: string) {
  const response = await api.post("/api/agents", {
    name, type: "custom", prompt: "Responda no campo result.",
    inputs: [{ name: "spec", type: "document", required: false }],
    outputs: [{ name: "result", type: "document", required: true }],
    actions: ["follow", "finalize"],
  });
  expect(response.status, response.text).toBe(201);
  return response.body;
}

/** AgentSnapshot congelado (spec 4.2) a partir do Agent da API. */
function snapshotOf(agent: any) {
  return {
    agentId: agent.id, version: 1, name: agent.name, description: agent.description,
    prompt: agent.prompt, strategy: agent.strategy, skills: agent.skills, tools: agent.tools,
    mcpServers: agent.mcpServers, knowledge: agent.knowledge, integrations: agent.integrations,
    inputs: agent.inputs, outputs: agent.outputs, actions: agent.actions, model: agent.model,
    maxIterations: agent.maxIterations, timeout: agent.timeout, shellAccess: agent.shellAccess,
  };
}

test.describe("Jornada 10: integrações Git e projeto", () => {
  test("conexão, repositório no editor, execução, arquivos e PR", async ({ page, user, api }) => {
    const reason = await GitTest.unavailableReason();
    test.skip(reason !== null, reason ?? "");
    await GitTest.initRepo();

    const suffix = Date.now().toString(36);
    const connectionName = `Local ${suffix}`;
    const agent = await createAgent(api, `E2E Dev ${suffix}`);
    const nodeId = crypto.randomUUID();
    const created = await api.post("/api/pipelines", {
      name: `QA Projeto ${suffix}`,
      description: "e2e projeto git",
      entryNodeId: nodeId,
      nodes: [{ id: nodeId, agentId: agent.id, agentSnapshot: snapshotOf(agent), position: { x: 0, y: 0 } }],
      edges: [],
    });
    expect(created.status, created.text).toBe(201);
    const pipelineId = created.body.id as string;

    try {
      await loginViaUI(page, user.email, PASSWORD);

      // 1) Integrações > GitHub: nova conexão com o token de teste e "Testar".
      await page.goto("/integrations?tab=github");
      await expect(page.getByRole("heading", { name: "Integrações" })).toBeVisible({ timeout: 30_000 });
      await page.getByRole("button", { name: "Nova conexão" }).click();
      const form = page.getByRole("dialog");
      await form.getByLabel("Nome").fill(connectionName);
      await form.getByLabel("Token").fill(GitTest.token);
      await form.getByRole("button", { name: "Salvar conexão" }).click();
      await expect(page.getByRole("heading", { name: connectionName })).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: `Testar conexão ${connectionName}` }).click();
      await expect(page.getByText(/Conectado, 1 repositórios/)).toBeVisible({ timeout: 15_000 });

      // 2) Editor: vincula o repositório pelo RepositoryPicker do cabeçalho.
      await page.goto(`/pipelines/${pipelineId}`);
      await page.getByRole("button", { name: "Sem repositório" }).click();
      const picker = page.getByRole("dialog", { name: "Repositório do pipeline" });
      await picker.getByLabel("Conexão").selectOption({ label: connectionName });
      await picker.getByLabel("Repositório", { exact: true }).selectOption(GitTest.repo);
      await expect(picker.getByLabel("Branch")).toHaveValue("main");
      await expect(page.getByRole("button", { name: `Repositório: ${GitTest.repo} (main)` })).toBeVisible({
        timeout: 15_000,
      });
      await expect
        .poll(async () => (await api.get(`/api/pipelines/${pipelineId}`)).body.repository?.fullName)
        .toBe(GitTest.repo);
      await picker.getByRole("button", { name: "Fechar" }).click();

      // 3) Executar (o agente não tem entrada obrigatória).
      await page.getByRole("button", { name: "Executar pipeline" }).click();
      await page.getByRole("dialog", { name: "Executar pipeline" }).getByRole("button", { name: /^Executar$/ }).click();
      await expect(page).toHaveURL(new RegExp(`/pipelines/${pipelineId}/run`), { timeout: 30_000 });

      // 4) Fim do run: commit + push + PR no GitHub fake; link no cabeçalho.
      const prLink = page.getByRole("link", { name: /PR #\d+/ });
      await expect(prLink).toBeVisible({ timeout: 90_000 });
      await expect(prLink).toHaveAttribute("href", new RegExp(`${GitTest.repo}/pull/\\d+`));
      expect((await GitTest.branches()).some((b) => b.startsWith("agent-portal/"))).toBe(true);

      // 5) Aba Arquivos do projeto: result.md (agente mock) e o README clonado.
      await page.getByRole("tab", { name: "Arquivos do projeto" }).click();
      const files = page.getByRole("list", { name: "Arquivos do projeto" });
      await expect(files.getByRole("button", { name: /^result\.md/ })).toBeVisible({ timeout: 15_000 });
      await expect(files.getByRole("button", { name: /^README\.md/ })).toBeVisible();
      await files.getByRole("button", { name: /^result\.md/ }).click();
      await expect(page.getByText(/MOCK_LLM/).first()).toBeVisible({ timeout: 15_000 });
      await page.screenshot({ path: test.info().outputPath("projeto-git.png") });
    } finally {
      await api.delete(`/api/pipelines/${pipelineId}`).catch(() => undefined);
    }
  });
});
