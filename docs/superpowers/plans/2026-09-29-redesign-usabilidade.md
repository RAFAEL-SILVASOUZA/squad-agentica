# Redesign de usabilidade — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar as melhorias da revisão de design (20 itens), mais três correções verificadas depois dela: rascunho do agente persistente, descrição das entradas do agente e revalidação do monitor. Ao final, um usuário novo deve criar um agente, montar e executar uma pipeline, aprovar e consultar o Knowledge sem ajuda, tanto no desktop quanto em 390px.

**Architecture:** O trabalho começa por uma base compartilhada no portal: tokens de contraste, `ErrorPanel`, `Button loading`, skeletons, plural, breadcrumb, `PortsEditor` e a paleta de comandos. As telas são refeitas em cima dessa base. O backend recebe só o que as telas pedem: drafts em banco, validação de agente, `usageCount`, `runStats`, detalhe de documento, feedback de fonte e teste de integração sem salvar. Nenhuma API existente muda de forma incompatível; os campos novos são aditivos.

**Tech Stack:** Next.js 14 (App Router), React 18, vitest com Testing Library e Playwright; FastAPI, SQLAlchemy 2 e Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-redesign-usabilidade-design.md`. Referência visual: `docs/superpowers/design/2026-09-29-revisao-de-design.md`, com screenshots em `docs/superpowers/design/screenshots/`.

## Global Constraints

- **Idioma e termos:** UI em pt-BR com acentos. Os termos de domínio ficam em inglês (Skills, Tools, MCP, Knowledge), e "Tools Custom" vira "Tools".
- **Erros:**
  - dizem o que o usuário não conseguiu fazer e oferecem uma ação de recuperação;
  - detalhes técnicos ficam recolhidos;
  - erro que bloqueia uma ação principal aparece inline;
  - o toast de erro usa `aria-live="assertive"` e fica 8 s na tela.
- **Contraste:** `--text-secondary` e `--text-muted` com razão ≥ 4.5:1 sobre `--bg` e `--bg-card`, nos temas claro e escuro.
- **Acessibilidade:** alvos de toque ≥ 44px abaixo de 768px; `:focus-visible` em todo elemento interativo.
- **Valores técnicos:** modelo, timeout, IDs e logs em monospace 12–13px.
- **Breakpoints:** mobile abaixo de 768px e painel lateral do editor a partir de 1024px.
- **API:** nenhuma mudança incompatível; campos novos são opcionais ou aditivos.
- **Migrações:** novas migrações Alembic encadeadas na head atual `3b91c0d4a6e7`, com `alembic check` limpo (`tests/test_migration.py`).
- **Portal sem hot reload:** reiniciar o container `portal` antes de qualquer verificação no navegador.
- **Git:** commits em Conventional Commits terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nunca fazer push. `git add` só com caminhos explícitos. Não tocar em `.codex/`.
- **Comandos de teste:** ver `.superpowers/sdd/2026-09-28-projeto-git-e-usabilidade/conventions.md`, que tem os mesmos comandos deste projeto.

## Review Focus

1. **Draft restaurado de outro usuário.** O `restore` e o `get` precisam isolar por dono: um `draftId` alheio responde 404, nunca a config de outro usuário. O teste fica na Task 3.
2. **Plural e contagens com zero ou números grandes.** "0 agentes", "1 agente", "1.234 agentes", no formato pt-BR. O teste fica na Task 1.
3. **Paleta de comandos com a página sem foco ou com um input focado.** `/` não pode abrir a paleta enquanto o usuário digita num campo; ⌘K abre sempre. O teste fica na Task 6.
4. **Modo lista do editor com grafo inválido ou com ciclo.** A ordem topológica não pode travar num ciclo: os nós que sobram vão para o fim, com um aviso. O teste fica na Task 13.
5. **Teste de integração antes de salvar.** O token digitado nunca volta na resposta nem aparece em log, e nada é gravado. O teste fica na Task 15.

---

## Estrutura de arquivos

- `agent-portal/lib/plural.ts` (novo): `plural(n, singular, pluralForm)`, `formatCount(n)`.
- `agent-portal/lib/relative-time.ts` (novo): `relativeTime(iso, now?)` → "há 12 min".
- `agent-portal/components/ui/`:
  - `error-panel.tsx`, `breadcrumb.tsx` e `bottom-nav.tsx` (novos);
  - `button.tsx`, que ganha a prop `loading`;
  - `skeleton.tsx`, que ganha `SkeletonRows`/`SkeletonShell`;
  - `toast.tsx`, com erro assertivo, 8 s e "Ver detalhes";
  - `data-table.tsx` (novo): busca, filtro, ordenação e menu ⋮ por linha.
- `agent-portal/components/command-palette/` (novo): `command-palette.tsx`, `use-shortcuts.ts`, `shortcuts-help.tsx`.
- `agent-portal/components/ports/ports-editor.tsx` (novo), compartilhado por skills e pelo contrato do agente.
- `agent-portal/components/flow/properties-panel.tsx` e `flow/steps-list.tsx` (novos).
- `agent-portal/components/monitor/timeline.tsx` (novo).
- `agent-portal/components/knowledge/citations.tsx` e `knowledge/document-drawer.tsx` (novos).
- `agent-portal/components/approvals/approval-queue.tsx` (novo).
- `agent-portal/app/(auth)/forgot-password/page.tsx` (novo).
- `agent-orchestrator`:
  - `app/agents/chat/conversation.py`: `DraftStore` passa a ser persistido em banco;
  - `app/db/models.py` com migração `agent_drafts`, `knowledge_messages.feedback` e `knowledge_documents` (sem colunas novas);
  - `app/api/agent_chat.py`: `restore` e `validate`;
  - `app/api/pipelines.py`: `runStats` e filtros;
  - `app/api/knowledge.py`: detalhe do documento e feedback;
  - `app/api/integrations.py`: `POST /test` sem salvar, `token_hint` e `last_test_status`;
  - `app/api/skills.py`, `tools.py`, `mcp_servers.py`: `usageCount`.

---

### Task 1: Fundamentos do portal (tokens, plural, tempo relativo, Button loading, skeletons, ErrorPanel, toast)

**Files:**
- Modify: `agent-portal/app/globals.css`, `agent-portal/components/ui/button.tsx`, `ui/skeleton.tsx`, `ui/toast.tsx`, `ui/index.ts`
- Create: `agent-portal/lib/plural.ts`, `lib/relative-time.ts`, `components/ui/error-panel.tsx`
- Test: `agent-portal/lib/plural.test.ts`, `lib/relative-time.test.ts`, `app/contrast.test.ts`, `components/ui/error-panel.test.tsx`, casos novos em `button.test.tsx`, `skeleton.test.tsx`, `toast.test.tsx`

**Interfaces:**
- Produces:
  - `plural(n: number, singular: string, pluralForm: string): string` e `formatCount(n: number): string`.
  - `relativeTime(iso: string, now?: Date): string`.
  - `<Button loading>`, com `aria-busy`, spinner e `disabled`.
  - `<SkeletonRows rows={n} />` e `<SkeletonShell />`.
  - `<ErrorPanel title detail? onRetry? retryLabel? actions? />`, com `role="alert"`, "Ver detalhes" e "Copiar detalhes".
  - `toast.error(message, {detail?, onRetry?})`: fica 8 s e usa `aria-live="assertive"`.

- [ ] **Step 1: Testes que falham**

```ts
// agent-portal/lib/plural.test.ts
import { describe, it, expect } from "vitest";
import { plural, formatCount } from "./plural";
describe("plural", () => {
  it("usa singular só para 1", () => {
    expect(plural(0, "agente", "agentes")).toBe("0 agentes");
    expect(plural(1, "agente", "agentes")).toBe("1 agente");
    expect(plural(2, "agente", "agentes")).toBe("2 agentes");
    expect(plural(1234, "agente", "agentes")).toBe("1.234 agentes");
  });
  it("formatCount usa separador pt-BR", () => { expect(formatCount(1234567)).toBe("1.234.567"); });
});
```

```ts
// agent-portal/lib/relative-time.test.ts
import { relativeTime } from "./relative-time";
const now = new Date("2026-09-29T12:00:00Z");
it.each([
  ["2026-09-29T11:59:40Z", "agora"],
  ["2026-09-29T11:48:00Z", "há 12 min"],
  ["2026-09-29T09:00:00Z", "há 3 h"],
  ["2026-09-27T12:00:00Z", "há 2 dias"],
])("%s → %s", (iso, out) => expect(relativeTime(iso, now)).toBe(out));
```

```ts
// agent-portal/app/contrast.test.ts — lê globals.css e calcula a razão WCAG
import { readFileSync } from "node:fs";
import { join } from "node:path";
function hex(css: string, block: string, name: string) {
  const m = css.slice(css.indexOf(block)).match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`));
  if (!m) throw new Error(`${name} não encontrado em ${block}`); return m[1];
}
function lum(h: string) {
  const c = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const css = readFileSync(join(__dirname, "globals.css"), "utf8");
for (const block of [":root", "[data-theme=\"light\"]"]) {
  for (const fg of ["text-secondary", "text-muted"]) for (const bg of ["bg", "bg-card"]) {
    it(`${block} ${fg} sobre ${bg} ≥ 4.5`, () => expect(ratio(hex(css, block, fg), hex(css, block, bg))).toBeGreaterThanOrEqual(4.5));
  }
}
```

Antes de escrever o teste, conferir como o tema claro está declarado em `globals.css` (seletor exato) e usar esse seletor no lugar de `[data-theme="light"]`.

```tsx
// agent-portal/components/ui/error-panel.test.tsx
it("mostra impacto, detalhes recolhidos e tentar de novo", async () => {
  const onRetry = vi.fn();
  render(<ErrorPanel title="Não foi possível salvar o agente" detail="HTTP 404 · POST /api/agents/chat/confirm" onRetry={onRetry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível salvar o agente");
  expect(screen.queryByText(/HTTP 404/)).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Ver detalhes" }));
  expect(screen.getByText(/HTTP 404/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  expect(onRetry).toHaveBeenCalled();
});
```

`button.test.tsx`: com `loading`, o botão tem `aria-busy="true"`, fica desabilitado e não chama `onClick`. `toast.test.tsx`: o erro fica em `aria-live="assertive"`, some depois de 8000 ms (usar fake timers) e "Ver detalhes" mostra o detalhe.

- [ ] **Step 2: Rodar os testes e ver falhar.**

- [ ] **Step 3: Implementar**
  - `plural`: `` `${formatCount(n)} ${n === 1 ? singular : pluralForm}` ``. `formatCount`: `n.toLocaleString("pt-BR")`.
  - `relativeTime`: menos de 60 s → "agora"; menos de 60 min → "há N min"; menos de 24 h → "há N h"; senão "há N dias".
  - Tokens: ajustar `--text-secondary`/`--text-muted` dos dois temas até o teste passar. Sugestão para o tema escuro: `--text-secondary: #A8A8AE` e `--text-muted: #8E8E96`; no claro: `--text-muted: #5B6270`. Validar com o teste, não confiar na sugestão.
  - Adicionar `--font-mono`, `.mono` e `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }`. Abaixo de 768px, `.touch-target { min-width: 44px; min-height: 44px }`.
  - `Button loading`, `SkeletonRows`, `SkeletonShell`, `ErrorPanel` e ajuste do `toast`, conforme as Interfaces.

- [ ] **Step 4:** rodar `npx vitest run lib app/contrast.test.ts components/ui`, `npx tsc --noEmit` e `npm run lint`.
- [ ] **Step 5: Commit** — `feat(portal): fundamentos de UX (contraste, plural, erro com recuperacao, loading, skeletons)`

---

### Task 2: API errors com contexto, e padrão de erro aplicado

**Files:**
- Modify:
  - `agent-portal/lib/api.ts`: `ApiError` ganha `method`, `path` e `status`, e ganha `describe(): string`, que devolve "HTTP 404 · POST /api/…".
  - Os pontos que hoje só fazem `toast` num erro que bloqueia a ação: salvar agente, executar pipeline, salvar pipeline, salvar conexão e enviar documento.
- Test: `agent-portal/lib/api.test.ts` e testes existentes das telas afetadas.

**Interfaces:**
- Consumes: `ErrorPanel` e `toast.error` (Task 1).
- Produces: `ApiError.method`, `ApiError.path` e `ApiError.describe()`.

- [ ] **Step 1: Testes que falham.**
  - `api.test.ts`: uma requisição com 404 lança um `ApiError` com `method === "POST"`, `path === "/api/agents/chat/confirm"` e `describe()` contendo `HTTP 404 · POST /api/agents/chat/confirm`.
  - Teste da tela de execução da pipeline: falha ao executar → aparece um `role="alert"` inline com "Tentar de novo", que chama o execute de novo.
- [ ] **Step 2:** rodar e ver falhar.
- [ ] **Step 3:** implementar. Em `send()`, preencher `method` e `path` no `ApiError`. Trocar os toasts dos fluxos principais por `ErrorPanel` inline, com o título de impacto ("Não foi possível executar a pipeline") e `detail={err.describe()}`.
- [ ] **Step 4:** rodar a suíte completa do portal, `tsc` e lint.
- [ ] **Step 5: Commit** — `feat(portal): erros com contexto e recuperacao nos fluxos principais`

---

### Task 3: Rascunho do agente persistente, restaurar, validar e salvar com recuperação

**Files:**
- Modify:
  - `agent-orchestrator/app/agents/chat/conversation.py`: `DraftStore` apoiado no banco.
  - `agent-orchestrator/app/db/models.py`: `AgentDraft` ORM.
  - `agent-orchestrator/app/api/agent_chat.py`: novas rotas `restore` e `validate`.
  - `agent-orchestrator/app/main.py`: limpeza de drafts expirados no mesmo loop periódico do purge.
- Create: migração `agent_drafts`.
- Modify portal: `app/(dashboard)/agents/new/page.tsx`, `components/agents/agent-preview.tsx`.
- Test: `agent-orchestrator/tests/test_agent_drafts.py`, `agent-portal/app/(dashboard)/agents/new/page.test.tsx`, `components/agents/agent-preview.test.tsx`.

**Interfaces:**
- Produces:
  - Tabela `agent_drafts`: `id` UUID PK, `owner_id` FK users, `messages` JSONB, `config` JSONB, `created_at`, `updated_at`.
  - `DraftStore` passa a ser assíncrona: `await draft_store.create(db, owner_id)`, `get(db, draft_id, owner_id)`, `save(db, draft)` e `delete(db, draft_id)`. Atualizar todos os usos em `agent_chat.py`.
  - `POST /api/agents/chat/restore`, com body `{config: {...}, messages?: [...]}` → `201 {draftId}`.
  - `POST /api/agents/validate`, com body = config do agente → `200 {valid: bool, missing: string[], errors: string[]}`. Reusa `app/agents/validator.py`.
  - Ciclo de vida do draft: `purge_expired_drafts(db, ttl_hours=24) -> int` roda no loop periódico existente em `main.py`.

- [ ] **Step 1: Testes que falham (orchestrator)**

```python
# agent-orchestrator/tests/test_agent_drafts.py
async def test_draft_survives_store_recreation(session, test_user):
    from app.agents.chat.conversation import DraftStore
    d = await DraftStore().create(session, str(test_user.id))
    d.config["name"] = "Resumidor"; await DraftStore().save(session, d)
    again = await DraftStore().get(session, d.draft_id, str(test_user.id))   # nova instância = "reinício"
    assert again is not None and again.config["name"] == "Resumidor"

async def test_draft_of_other_owner_is_invisible(session, test_user, other_user):
    from app.agents.chat.conversation import DraftStore
    d = await DraftStore().create(session, str(test_user.id))
    assert await DraftStore().get(session, d.draft_id, str(other_user.id)) is None

async def test_restore_creates_draft_from_config(full_client):
    r = await full_client.post("/api/agents/chat/restore", json={"config": {"name": "X", "prompt": "p"}})
    assert r.status_code == 201 and r.json()["draftId"]

async def test_validate_lists_missing(full_client):
    r = await full_client.post("/api/agents/validate", json={"name": "", "outputs": []})
    body = r.json()
    assert body["valid"] is False and "name" in body["missing"]

async def test_expired_drafts_are_purged(session, test_user):
    # draft com updated_at 25h atrás → purge_expired_drafts remove 1
    ...
```

Escrever o último teste por completo: criar o draft, fazer `UPDATE agent_drafts SET updated_at = now() - interval '25 hours'`, chamar `purge_expired_drafts(session)` e verificar que o retorno é 1. Se não existir fixture `other_user`, criar uma com o mesmo padrão de `test_user` em `tests/integration_api_fixtures.py`.

- [ ] **Step 2:** rodar e ver falhar.
- [ ] **Step 3:** implementar no orchestrator: modelo, migração, `DraftStore` assíncrono, rotas e purge. Os rate limits do chat continuam como estão.
- [ ] **Step 4: Testes que falham (portal).**
  - `/agents/new` guarda o `draftId` em `sessionStorage` (`agent-draft-id`). Ao montar, se houver um id guardado, retoma o draft.
  - Salvar com 404 `draft_not_found` mostra o `ErrorPanel` "O rascunho expirou no servidor", com o botão "Recriar a partir do que está na tela". O botão chama `restore` com a config atual e depois o confirm, e o fluxo tem sucesso.
  - Qualquer outro erro mostra `ErrorPanel` com "Tentar de novo" e mantém o preview preenchido.
  - O preview chama `/api/agents/validate` com debounce de 500 ms. Mostra "✓ pronto para salvar" ou "Falta: nome, saídas". O botão Salvar fica desabilitado enquanto `valid=false`.
  - O chat de construção (`components/agents/agent-chat.tsx`) mostra "digitando…" com 3 pontos animados (`aria-live="polite"`) entre o envio e o primeiro token do SSE.
- [ ] **Step 5:** implementar, rodar a suíte do portal, `tsc` e lint.
- [ ] **Step 6: Commit** — `feat(agentes): rascunho persistente, restaurar, validar e salvar com recuperacao`

---

### Task 4: Login, cadastro e esqueci a senha

**Files:**
- Modify: `agent-portal/app/(auth)/login/page.tsx`, `app/(auth)/register/page.tsx`
- Create: `app/(auth)/forgot-password/page.tsx`
- Test: testes existentes das páginas, mais `forgot-password/page.test.tsx`

**Interfaces:**
- Consumes: `Button loading` (Task 1).

- [ ] **Step 1: Testes que falham.**
  - O placeholder do e-mail é `voce@empresa.com`.
  - O link "Esqueci?" aponta para `/forgot-password`.
  - O cadastro mostra "Mínimo 8 caracteres". Com uma senha de 5 caracteres, ao sair do campo aparece "A senha precisa ter pelo menos 8 caracteres", e o botão fica desabilitado.
  - Durante o login o botão fica com `aria-busy`.
  - A página `forgot-password` mostra "Peça ao administrador…" e tem o link "Voltar para o login".
- [ ] **Step 2–4:** implementar, rodar e verificar tsc e lint.
- [ ] **Step 5: Commit** — `feat(auth): placeholder neutro, esqueci a senha e requisitos de senha`

---

### Task 5: Navegação (topbar "+ Novo", sidebar, breadcrumb e nomes)

**Files:**
- Modify: `components/layout/app-sidebar.tsx`, `app-topbar.tsx`, `app-shell.tsx`
- Create: `components/ui/breadcrumb.tsx`
- Modify: páginas de detalhe `agents/[id]`, `pipelines/[id]`, `pipelines/[id]/run` e `knowledge` (base selecionada)
- Test: `app-sidebar.test.tsx` (criar se não existir), `app-topbar.test.tsx`, `breadcrumb.test.tsx`

**Interfaces:**
- Produces: `<Breadcrumb items={[{label, href?}]} />`, um `nav` com `aria-label="Você está em"`. O último item é a página atual (`aria-current="page"`).

- [ ] **Step 1: Testes que falham.**
  - Sidebar:
    - não tem "Novo Agente";
    - tem o grupo CONFIGURAÇÃO com "Integrações" (`/integrations`);
    - mostra "Tools" em vez de "Tools Custom".
  - Topbar:
    - o botão "+ Novo" abre um menu com "Agente" (`/agents/new`), "Pipeline" (cria e navega, reusando o `handleCreate` da lista de pipelines extraído para `lib/create-pipeline.ts`) e "Base de conhecimento" (`/knowledge?new=1`);
    - a engrenagem de Integrações sai da topbar.
  - Breadcrumb: renderiza "Pipelines / Nome", e o item atual não é link.
- [ ] **Step 2–4:** implementar e rodar. `/knowledge?new=1` abre o modal "Nova base". Atualizar os seletores das e2e 02 e 05 que usavam "Novo Agente" na sidebar.
- [ ] **Step 5: Commit** — `feat(portal): navegacao com + Novo, grupo Configuracao e breadcrumb`

---

### Task 6: Paleta de comandos (⌘K e /) e ajuda de atalhos (?)

**Files:**
- Create: `components/command-palette/command-palette.tsx`, `use-shortcuts.ts`, `shortcuts-help.tsx`, com testes
- Modify: `components/layout/app-shell.tsx`, que monta os dois componentes. O "?" da topbar abre a ajuda.

**Interfaces:**
- Produces: `useShortcuts({ onPalette, onHelp })`.
  - Ctrl+K ou ⌘K abre a paleta sempre.
  - `/` só abre quando o alvo do evento não for `input`, `textarea` ou `[contenteditable]`.
  - `?` segue a mesma regra do `/`.
- Resultados da paleta: busca, com debounce de 200 ms, em `GET /api/agents?limit=50`, `/api/pipelines?limit=50`, `/api/knowledge?limit=50`, `/api/skills?limit=50`, `/api/tools?limit=50` e `/api/mcp-servers?limit=50`. A lista é carregada ao abrir e filtrada no cliente por nome, sem distinguir maiúsculas e acentos (normalização NFD). O resultado vem agrupado por tipo e navega com Enter ou clique. As ações fixas são "Novo agente", "Nova pipeline" e "Nova base". Setas navegam, Esc fecha.

- [ ] **Step 1: Testes que falham.**
  - Ctrl+K abre a paleta (`role="dialog"`, nome "Buscar").
  - `/` com foco num input não abre a paleta; com foco no body, abre.
  - Digitar "especif" encontra "Redator de Especificações", porque o acento é ignorado. Enter navega para `/agents/<id>`.
  - Sem resultados, mostra "Nada encontrado para 'xyz'" e as ações de criar.
  - `?` abre a lista de atalhos.
- [ ] **Step 2–4:** implementar e rodar.
- [ ] **Step 5: Commit** — `feat(portal): paleta de comandos e ajuda de atalhos`

---

### Task 7: Overview (dashboard)

**Files:**
- Modify: `app/(dashboard)/page.tsx`, `components/dashboard/stats-strip.tsx`, `agent-card.tsx`, `recent-runs.tsx`, `pending-approvals.tsx`
- Create: `components/dashboard/onboarding-checklist.tsx`
- Test: testes existentes e `onboarding-checklist.test.tsx`

**Interfaces:**
- Consumes: `plural`, `SkeletonRows` (Task 1); os filtros da lista de pipelines por querystring (Task 12). Os links usam `?run=running`, `?since=24h` e `?run=completed`.

- [ ] **Step 1: Testes que falham.**
  - O H1 é "Overview".
  - Os `href` das métricas são `/pipelines?run=running`, `/pipelines?since=24h`, `/pipelines?run=completed` e `/approvals`.
  - Com um agente, o subtítulo mostra "1 agente".
  - O campo de busca tem label "Buscar por nome, descrição ou tipo", e buscar "planner" encontra o agente cujo `type` é "planner".
  - Com 0 agentes e 0 pipelines, aparece o checklist "Primeiros passos" com 4 itens e as métricas não aparecem.
  - Com um agente, o item "Crie um agente" aparece marcado.
  - Enquanto carrega, aparecem os skeletons.
  - O layout do dashboard (`app/(dashboard)/layout.tsx`) troca o spinner central por `<SkeletonShell />` enquanto a sessão carrega.
- [ ] **Step 2–4:** implementar e rodar.
- [ ] **Step 5: Commit** — `feat(portal): overview com metricas certas, onboarding e skeletons`

---

### Task 8: PortsEditor e descrição de entradas e saídas

**Files:**
- Create: `components/ports/ports-editor.tsx`, com teste
- Modify: `components/library/skills-library.tsx` (modal de skill), `components/agents/agent-detail.tsx` (seção Contrato)
- Backend: conferir se `app/agents/validator.py` aceita `description` em `PortDef`. Se o validador rejeitar chaves extras, permitir `description: str` com até 500 caracteres, com teste em `tests/test_agents_validator.py`.

**Interfaces:**
- Produces: `<PortsEditor label value={Port[]} onChange types={string[]} />`, com `Port = { name, type, required, description? }`.
  - Cada linha tem nome, tipo (select), obrigatório (toggle) e descrição.
  - "+ Adicionar", remover por linha e "Ver JSON" (bloco somente leitura).
  - Valida nome vazio e nome duplicado (erro inline).

- [ ] **Step 1: Testes que falham.**
  - Adicionar duas linhas chama `onChange` com dois ports.
  - Com nome duplicado, aparece "Nome repetido" e `onChange` não é chamado.
  - "Ver JSON" mostra o JSON com `description`.
  - O modal de skill não tem mais o textarea "Inputs (JSON)".
  - No Contrato do agente, a descrição de uma entrada é salva no `PUT` do agente.
- [ ] **Step 2–4:** implementar e rodar. Se o validador mudar, rodar também o orchestrator.
- [ ] **Step 5: Commit** — `feat(portal): editor estruturado de entradas e saidas com descricao`

---

### Task 9: Detalhe do agente em abas

**Files:**
- Modify: `components/agents/agent-detail.tsx`, `agent-preview.tsx`, `app/(dashboard)/agents/[id]/page.tsx`
- Test: `agent-detail.test.tsx`, `agent-preview.test.tsx`

**Interfaces:**
- Consumes: `PortsEditor` (Task 8), `Breadcrumb` (Task 5) e `Agent.effectiveModel`, que já existe.

- [ ] **Step 1: Testes que falham.**
  - Abas:
    - existem as abas Visão geral, Conversar, Contrato, Mochila e Execução;
    - `?tab=mochila` abre a Mochila.
  - Modelo:
    - o modelo aparece uma única vez, em destaque, com o efetivo;
    - quando o modelo configurado difere, aparece o texto "Configurado: gpt-4o · o servidor usa Qwen…";
    - não existe outro campo mostrando "gpt-4o" como se fosse o valor efetivo. O campo editável fica na aba Execução, rotulado "Modelo configurado".
  - Mochila sem skills: aparece o link "Criar skill →" para `/skills?new=1`, com `target=_blank`. O mesmo vale para tools e bases.
  - Mobile (mock de `matchMedia` abaixo de 768px): na aba Conversar, o campo de mensagem é `position: sticky; bottom: 0`.
- [ ] **Step 2–4:** implementar e rodar. `/skills?new=1`, `/tools?new=1` e `/knowledge?new=1` abrem o modal de criação.
- [ ] **Step 5: Commit** — `feat(portal): detalhe do agente em abas, modelo unico e atalhos de criacao`

---

### Task 10: Biblioteca em tabela com busca e usos

**Files:**
- Create: `components/ui/data-table.tsx`, com teste
- Modify: `components/library/skills-library.tsx`, `tools-editor.tsx` (lista), `mcp-servers-library.tsx`
- Backend: `app/api/skills.py`, `tools.py` e `mcp_servers.py` passam a devolver `usageCount`. É calculado numa só consulta sobre `Agent.skills`, `Agent.tools` e `Agent.mcp_servers` do dono, que são JSONB com refs `{skillId|toolId|serverId}`. Conferir os nomes reais das chaves.
- Test: `agent-orchestrator/tests/test_library_usage.py`; testes de portal das três telas.

**Interfaces:**
- Produces:
  - `<DataTable columns rows searchPlaceholder filters? onRowMenu />`, com busca no cliente (sem acento), filtros por select e ordenação por coluna (`aria-sort`).
  - Menu ⋮ por linha (`role="menu"`). Abaixo de 768px, cada linha vira um card de duas linhas.
  - Nas respostas de lista, cada item ganha `usageCount: int`.

- [ ] **Step 1: Testes que falham.**
  - Backend: um agente referencia a skill A duas vezes e outro agente a referencia uma vez → `usageCount` de A é 2, porque conta agentes distintos. A skill B tem 0. Um agente de outro dono não conta.
  - Portal:
    - buscar "revis" filtra a tabela;
    - o filtro de categoria funciona;
    - a coluna "Usos" mostra "2 agentes";
    - o menu ⋮ tem Editar, Duplicar e Excluir, e Excluir pede confirmação;
    - a tabela de MCP mostra "Conectado · 6 tools".
- [ ] **Step 2–4:** implementar e rodar as duas suítes.
- [ ] **Step 5: Commit** — `feat(biblioteca): tabelas com busca, filtros, usos e menu de acoes`

---

### Task 11: Knowledge (auto-seleção, drawer do documento, citações e feedback, etapas de espera, menus)

**Files:**
- Backend:
  - `app/api/knowledge.py`: `GET /api/knowledge/{kb}/documents/{doc}` e `PATCH .../conversations/{cid}/messages/{mid}/sources/{index}`.
  - `app/db/models.py` e migração: `knowledge_messages.feedback` JSONB, nullable.
- Portal: `components/library/knowledge-view.tsx`, `components/knowledge/kb-header.tsx`, `documents-panel.tsx` e `kb-chat.tsx`.
- Create: `components/knowledge/citations.tsx` e `document-drawer.tsx`.
- Test: `agent-orchestrator/tests/test_knowledge_detail_feedback.py`; testes de portal.

**Interfaces:**
- Produces:
  - `GET .../documents/{doc}` → `{id, name, size, status, chunkCount, createdAt, preview: string[≤3]}`. Os três primeiros chunks vêm em ordem, cada um truncado em 600 caracteres. 404 para outro dono.
  - `PATCH .../sources/{index}`, com body `{wrong: bool}` → `200 {feedback}`, gravado em `feedback.sources[index] = {wrong, at}`. `index` fora do intervalo → 422. Só aceita mensagens `assistant`.
  - Portal: `<Citations text sources onOpen(index) />` troca `[n]` por `<sup><button aria-label="Fonte n">n</button></sup>` fora de blocos de código. `<DocumentDrawer>` usa `components/ui/drawer.tsx`.

- [ ] **Step 1: Testes que falham.**
  - Backend:
    - o detalhe devolve `chunkCount` e até 3 `preview`;
    - o feedback grava;
    - um índice inválido dá 422;
    - outro dono recebe 404.
  - Portal:
    - criar uma base a seleciona;
    - "Excluir base" fica no menu ⋮ e pede confirmação;
    - "Ver" num documento abre o drawer com "3 trechos";
    - a resposta "Custa R$ 10 [1]" mostra o sobrescrito "1", que abre o drawer da fonte com o trecho;
    - acima das fontes aparece "2 fontes";
    - "Fonte errada" chama o PATCH e o botão fica marcado;
    - durante o envio aparecem, em sequência, "Buscando trechos", "Lendo" e "Respondendo" (fake timers, uma etapa a cada 1,5 s, a última permanece);
    - excluir conversa fica no menu ⋮ e pede confirmação.
- [ ] **Step 2–4:** implementar e rodar as duas suítes, incluindo `test_migration.py`.
- [ ] **Step 5: Commit** — `feat(knowledge): citacoes clicaveis, feedback de fonte, drawer de documento e etapas de espera`

---

### Task 12: Lista de pipelines (tabela, runStats e filtros)

**Files:**
- Backend: `app/api/pipelines.py`, `list_pipelines`: incluir `runStats` e aceitar `run` e `since`.
- Portal: `app/(dashboard)/pipelines/page.tsx`, usando o `DataTable` da Task 10.
- Test: `agent-orchestrator/tests/test_pipelines_run_stats.py`; `pipelines/page.test.tsx`.

**Interfaces:**
- Produces:
  - Cada item da lista ganha `runStats: {recentSucceeded, recentFailed, lastRunStatus, lastRunAt}`, calculado sobre os últimos 10 runs de cada pipeline, numa única consulta com janela (`row_number() over (partition by pipeline_id order by created_at desc)`).
  - Filtros opcionais:
    - `run` em `running|completed|failed|never`, pelo último run;
    - `since=24h`: pipelines com algum run nas últimas 24 h.

- [ ] **Step 1: Testes que falham.**
  - Backend:
    - uma pipeline com 12 runs (8 concluídos, 3 falhos e o último em execução) → `recentSucceeded=7`, `recentFailed=2`, `lastRunStatus=running`, considerando só os 10 últimos. Os números exatos dependem da ordem montada no teste: fixar a ordem;
    - `run=never` devolve só pipelines sem runs;
    - `since=24h` exclui uma pipeline cujo último run tem 2 dias.
  - Portal:
    - as colunas são Nome, Repositório, Últimos 10 runs, Último run e Atualizado;
    - "✓ 7 · ✗ 2" aparece;
    - o status do run não aparece como status da pipeline;
    - `?run=running` na URL pré-seleciona o filtro;
    - a busca funciona;
    - enquanto carrega, aparecem skeletons.
- [ ] **Step 2–4:** implementar e rodar as duas suítes.
- [ ] **Step 5: Commit** — `feat(pipelines): lista em tabela com historico de runs, filtros e busca`

---

### Task 13: Editor — painel de propriedades e modo lista (menos de 768px)

**Files:**
- Create: `components/flow/properties-panel.tsx`, `flow/steps-list.tsx`, com testes
- Modify:
  - `app/(dashboard)/pipelines/[id]/page.tsx`;
  - `components/FlowEditor.tsx`, para expor a seleção atual via callback `onSelectionChange({nodeId?, edgeId?})`;
  - `components/EdgePanel.tsx`, cujo conteúdo é reusado dentro do painel;
  - `components/flow/agent-palette.tsx`, que ganha busca.
- Test: `properties-panel.test.tsx`, `steps-list.test.tsx`, `pipelines/[id]/page.test.tsx`.

**Interfaces:**
- Consumes: `PipelineHeader` (plano anterior), `validation.ts` e o `EdgePanel` existente.
- Produces:
  - `<PropertiesPanel pipeline selection onChangeNode onChangeEdge onDeleteNode onDeleteEdge />`, com os três modos definidos na spec §3.6.
  - `<StepsList pipeline agents onChange />`:
    - usa `topoOrder(nodes, edges) → {order, cyclic: string[]}`, exportado de `steps-list.tsx`;
    - os nós que ficam num ciclo vão para o fim da ordem, com o aviso "Há um ciclo envolvendo: A, B".

- [ ] **Step 1: Testes que falham.**
  - Sem seleção, o painel mostra "Pipeline" com nome, descrição e o erro de validação clicável.
  - Com um nó selecionado:
    - aparece "Entradas" com um select por entrada do agente;
    - escolher "Saída 'result' de Redator" cria a aresta de dados correspondente (`onChangeEdge`, com o `dataMapping` correto);
    - "Excluir nó" pede confirmação.
  - Com uma aresta selecionada, aparecem o tipo, a condição (se o tipo for condição) e a aprovação com canal e mensagem.
  - `topoOrder` com A→B→A e C→D → a ordem começa por C, D e `cyclic=[A,B]`.
  - Em 390px (mock `matchMedia`):
    - o canvas não renderiza e aparece "Etapas";
    - "Adicionar agente" funciona;
    - "Conectar a…" cria a aresta de fluxo.
  - A paleta de agentes filtra por nome.
- [ ] **Step 2–4:** implementar e rodar. Rodar também a e2e `05-pipeline-editor.spec.ts` (ajustar seletores quando mudarem, sem apagar cobertura).
- [ ] **Step 5: Commit** — `feat(editor): painel de propriedades e modo lista no celular`

---

### Task 14: Monitor (contagens, linha do tempo, stage strip e logs)

**Files:**
- Create: `components/monitor/timeline.tsx`, com teste
- Modify: `components/monitor/pipeline-monitor.tsx`, `results-tab.tsx`, `stage-strip.tsx`, `logs-tab.tsx`
- Test: testes existentes do monitor e `timeline.test.tsx`

**Interfaces:**
- Produces: `buildTimeline(events: {nodeId, status, at}[], checkpoints: {nodeId, timestamp, status}[]) → {nodeId, startedAt?, endedAt?, durationMs?, status}[]`.
  - O início é o primeiro `running`, e o fim é o primeiro `completed` ou `failed` depois dele.
  - Na ausência de eventos, os dados vêm dos checkpoints.

- [ ] **Step 1: Testes que falham.**
  - `buildTimeline` com um evento running às 10:00:00 e completed às 10:00:12 → `durationMs = 12000`. Nó sem eventos, com checkpoint completed → aparece sem duração.
  - As abas mostram "Logs (3)"; com um log de erro, aparece um ponto de erro (`aria-label="há erros"`); "Histórico (2)" e "Arquivos (2 alterados)".
  - A aba Resultado mostra a linha do tempo com "12 s" para o nó.
  - O stage strip com rolagem (overflow simulado) mostra o botão "Mais etapas →". O card de resultado não repete o nome do chip como título extra: o card traz o nome, e o chip fica compacto.
  - Os logs têm numeração (`<ol>`) e fonte monospace.
- [ ] **Step 2–4:** implementar e rodar. Rodar também a e2e `06-run-monitor.spec.ts`.
- [ ] **Step 5: Commit** — `feat(monitor): contagens nas abas, linha do tempo por no e logs numerados`

---

### Task 15: Integrações (tabela, testar antes de salvar, status e usos)

**Files:**
- Backend: `app/api/integrations.py`:
  - `POST /api/integrations/test`, que recebe `{type, config}`, não grava nada e devolve `{ok, repositories?, error?}`;
  - `token_hint` (últimos 4 caracteres) gravado ao criar ou atualizar o token;
  - `last_test_status` e `last_tested_at`, gravados em `config` pelo `POST /{id}/test` existente;
  - `usageCount`, com o número de pipelines que usam a conexão.
- Portal: `components/integrations/git-connections.tsx`, `git-connection-form.tsx`, `integrations-view.tsx`.
- Test: `agent-orchestrator/tests/test_integrations_test_unsaved.py`; testes de portal existentes.

**Interfaces:**
- Produces:
  - `POST /api/integrations/test`, com body `{type: "github"|"azure", config: {token, organization?}}` → `200 {ok: true, repositories: n}` ou `{ok: false, error}`. Não faz nenhuma escrita no banco.
  - A resposta da conexão ganha `tokenHint` ("…a1b2"), `lastTestStatus` (`ok|failed|null`), `lastTestedAt` e `usageCount`. O token continua saindo como `***`.
- Consumes: `provider_for` e `GitProviderError`, que já existem. Para montar um provider sem registro salvo, criar `provider_from_config(type, config)` em `git_providers.py`, reaproveitando a lógica de `provider_for`, e fazer `provider_for` chamar essa função.

- [ ] **Step 1: Testes que falham (backend)**

```python
async def test_test_unsaved_does_not_persist_or_echo(full_client, session, monkeypatch):
    from app.integrations import git_providers
    class Fake:
        async def list_repos(self): return [git_providers.Repo("o/r", "main")]
    monkeypatch.setattr("app.api.integrations.provider_from_config", lambda t, c: Fake())
    before = (await session.execute(text("select count(*) from integrations"))).scalar()
    r = await full_client.post("/api/integrations/test", json={"type": "github", "config": {"token": "ghp_SEGREDO"}})
    assert r.json() == {"ok": True, "repositories": 1}
    assert "SEGREDO" not in r.text
    assert (await session.execute(text("select count(*) from integrations"))).scalar() == before
```

Casos adicionais:
- `token_hint` é "…REDO" depois de criar com `ghp_SEGREDO`;
- um teste por `/{id}/test` grava `last_test_status`;
- `usageCount` conta 2 pipelines;
- um tipo não git dá 400.

- [ ] **Step 2:** rodar e ver falhar. **Step 3:** implementar.
- [ ] **Step 4: Portal.**
  - A lista vira tabela com Nome, Token "…a1b2", Status "● válido · hoje 14:10", Usos "2 pipelines" e ⋮ (Testar, Editar, Excluir).
  - O modal tem "Testar", que chama `/api/integrations/test` com os valores digitados e mostra o resultado inline.
  - O modal mostra o texto de escopo mínimo e a frase "o token fica criptografado e nunca é mostrado de novo".
  - A aba Outras explica o Rivvn e o que vem a seguir.
  - Testes, depois implementar.
- [ ] **Step 5: Commit** — `feat(integracoes): testar antes de salvar, status, uso e dica do token`

---

### Task 16: Aprovações (fila com contexto e ações inline)

**Files:**
- Create: `components/approvals/approval-queue.tsx`, com teste
- Modify: `app/(dashboard)/approvals/page.tsx`, `components/approvals/approval-panel.tsx` (reusar as ações), `components/dashboard/pending-approvals.tsx`
- Test: `approval-queue.test.tsx`, `pending-approvals.test.tsx`

**Interfaces:**
- Consumes: `relativeTime` (Task 1); `GET /api/approvals?status=&pipelineId=`, que já existe e devolve `pipelineId`, `runId`, `nodeId`, `context`, `createdAt` e `message`; `POST /api/approvals/{id}/respond` com `{decision, feedback?}`.
- Produces: `<ApprovalQueue status pipelineId? />`.
  - Cada card mostra:
    - a mensagem (título), o nome da pipeline, o nó e o agente, resolvidos via `/api/pipelines/{id}`;
    - "há N min";
    - o resumo do `context` em 3 linhas, expansível.
  - Ações: Aprovar, Argumentar (textarea inline e Enviar) e Rejeitar, que pede confirmação.
  - "Ver contexto" leva a `/pipelines/{pid}/run?tab=resultado&node={nodeId}`.

- [ ] **Step 1: Testes que falham.**
  - O card mostra "Pipeline: X · Nó: Revisor · há 12 min".
  - Aprovar chama `respond` com `approved` e remove o card.
  - Argumentar sem texto deixa o Enviar desabilitado; com texto, envia `argued` junto com o `feedback`.
  - Rejeitar pede confirmação.
  - O filtro de status "Respondidas" chama a API com `status=responded` (conferir o nome real do status no backend).
  - "Ver contexto" tem o href correto.
  - O card de aprovações do Overview tem Aprovar e Rejeitar inline.
  - Com a fila vazia, aparece o link "Como funcionam as aprovações?", que abre um modal curto explicando Aprovar, Argumentar e Rejeitar.
- [ ] **Step 2–4:** implementar e rodar. Rodar também a e2e `07-approvals.spec.ts`.
- [ ] **Step 5: Commit** — `feat(aprovacoes): fila com contexto e acoes inline`

---

### Task 17: Mobile (barra inferior, topbar mínima e métricas compactas)

**Files:**
- Create: `components/ui/bottom-nav.tsx`, com teste
- Modify: `components/layout/app-shell.tsx`, `app-topbar.tsx`, `components/dashboard/stats-strip.tsx`, `app/globals.css`
- Test: `bottom-nav.test.tsx`, `app-shell.test.tsx` (criar se não existir)

**Interfaces:**
- Produces: `<BottomNav />`, visível só abaixo de 768px. Tem 4 itens: Início (`/`), Pipelines, Aprovações (com o badge de pendentes) e Mais (abre a sidebar em overlay). Cada item tem pelo menos 44px, e o item ativo leva `aria-current="page"`.

- [ ] **Step 1: Testes que falham.** Com `matchMedia` abaixo de 768px:
  - a `BottomNav` renderiza e o hamburger antigo não;
  - a topbar mostra o logo, o título e ⋯, e o ⋯ reúne notificações, tema, ajuda e sair;
  - as métricas viram uma linha de chips;
  - o conteúdo ganha `padding-bottom` para a barra inferior não cobrir nada.

  Acima de 768px, nada disso muda.
- [ ] **Step 2–4:** implementar e rodar. Rodar também a e2e `09-cross-cutting.spec.ts`, que tem a verificação em 390px.
- [ ] **Step 5: Commit** — `feat(mobile): barra inferior, topbar minima e metricas compactas`

---

### Task 18: E2E de ponta a ponta, QA visual e registro

**Files:**
- Create: `e2e/tests/11-redesign-journey.spec.ts`, `docs/superpowers/validacoes/qa-redesign.md`
- Modify: specs e2e quebradas pelas mudanças (sem apagar cobertura), `docs/superpowers/validacoes/PENDENCIAS.md`

- [ ] **Step 1: e2e da jornada de um usuário novo.** Rodar em 1440px e em 390px (`test.describe` com dois `viewport`):
  1. cadastro;
  2. o Overview mostra "Primeiros passos";
  3. "+ Novo → Agente", chat, preview "pronto para salvar" e salvar;
  4. "+ Novo → Pipeline", adicionar o agente, configurar a entrada pelo painel no desktop ou pela lista no celular, e salvar;
  5. executar e ver a linha do tempo no monitor;
  6. na Knowledge, criar uma base (que já fica selecionada), enviar um documento `.md` e perguntar; a resposta tem sobrescrito e drawer. Em modo mock, garantir que o mock produz `[1]` e fontes; se não produzir, ajustar o mock de chat para devolver uma citação quando houver trecho;
  7. ⌘K encontra o agente.
- [ ] **Step 2: Regressão completa em mock:** orchestrator, worker, portal (vitest, tsc e lint), integração e todas as specs e2e, uma por vez, mais `npm run build`. Registrar as contagens em `qa-redesign.md`.
- [ ] **Step 3: QA visual no modo real (Qwen).**
  - Capturar, em 1440px e em 390px:
    - cada tela;
    - **cada aba do monitor separadamente** (Resultado, Arquivos, Logs e Histórico), conferindo que os arquivos são diferentes por hash;
    - o drawer de fonte e o painel de propriedades nos três modos;
    - a fila de aprovações com um item pendente.
  - Guardar os arquivos em `docs/superpowers/validacoes/redesign-screenshots/`.
  - Para cada item de 1 a 20 da seção 11 da revisão de design, anotar em `qa-redesign.md` "atendido", "parcial" (com o motivo) ou "não atendido".
- [ ] **Step 4:** deixar o stack no modo real e com `/api/health` 200. Levar as pendências para `PENDENCIAS.md`.
- [ ] **Step 5: Commit** — `test(redesign): jornada e2e, QA visual e registro`
