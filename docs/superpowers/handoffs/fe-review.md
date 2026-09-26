# fe-review — review da fase frontend (dashboard, agents, approvals, library)

Veredito: **REJEITADO** (rodada 1). Registros: `docs/superpowers/validacoes/fe-review.md`.
Escopo revisado: os 4 nós de tela + a navegação/integração do portal inteiro. Editor e monitor
já aprovados pelo fe-review-editor (`docs/superpowers/handoffs/fe-review-editor.md`) — **não revisados de novo**;
confirmado que continuam no build e na navegação (rotas presentes no build, sem endpoint novo).

## Evidência de verificação (saída real)
- `npx tsc --noEmit` → exit 0.
- `npm run lint` → "No ESLint warnings or errors".
- `npx vitest run` → **43 files, 355 tests passed**.
- `npm run build` → exit 0, 14 rotas (há warning não-fatal de copy de arquivo standalone; não quebra o build).
- Stack de pé (6 serviços healthy); probes vivos: `GET /api/health`→200; `/`, `/dashboard`, `/skills` → 307 `/login` (middleware ok).
- Login real: `POST /api/auth/login` com seed `admin@local`/`change-me-in-prod` → **500** (ver PENDENCIAS B2, backend).
- Screenshot autenticado: NÃO executável agora (browser headless sem cache + login backend 500). Evidência de rota vem do build manifest (autoritativo) + leitura de fonte.

## Git
- `git worktree list` → só o checkout principal (`main`). Nenhum `wt/*` pendente.
- Merges no main presentes: dashboard `ca0e063`, agents `68021d0`, approvals `4bcacee`, library `af56344` (+ editor `7865f77`, monitor `12b6a42`, flow-edges `f925aa1`).
- Todos os 4 nós deram merge → critério de merge OK.

## A) PROBLEMAS BLOQUEANTES (estado atual)

### A1 [fe-dashboard + fe-shell] Dashboard inacessível — conflito de rota `/` (CRITÉRIO 2) — **CORRIGIDO pelo revisor (commit `6058ea9`)**
Sintoma (rodada 1): `GET /` → 307 → `/dashboard` → **404**. A sidebar "Dashboard" (`href="/dashboard"`) era **link morto**.
Causa (evidência do build manifest `agent-portal/.next/app-build-manifest.json`): `app/page.tsx` (fe-shell, `redirect("/dashboard")`) e `app/(dashboard)/page.tsx` (fe-dashboard) disputam `/` (route group transparente); o redirect da raiz sombreou o dashboard (`/(dashboard)/page` ausente do manifest).
**O revisor APLICOU a correção** (arquivos compartilhados fe-shell, fora do escopo dos 4 nós de retry; protocolo permite ao revisor unblocking de arquivo compartilhado) e COMMITOU no `main` (`6058ea9`):
1. Removido `agent-portal/app/page.tsx` + `app/page.test.tsx` → `app/(dashboard)/page.tsx` agora é a rota `/` (dentro do grupo `(dashboard)`, herda o `AppShell` + guarda de sessão de `(dashboard)/layout.tsx`).
2. `agent-portal/components/layout/app-sidebar.tsx`: item Dashboard `href` e `isActive` de `/dashboard` → `/`.
3. `app/(auth)/login/page.test.tsx` + `register/page.test.tsx`: `callbackUrl`/assert de `/dashboard` → `/` (o default do código já era `/`).
Verificação pós-fix (saída real): `npx tsc --noEmit` exit 0; `npm run lint` limpo; `npx vitest run` 42 files/354 tests; `npm run build` exit 0 — rota `/` = 5.21 kB (dashboard), **sem rota `/dashboard`**; manifest agora tem `/(dashboard)/page`. Nenhum nó precisa re-fazer A1.

### A2 [fe-library] Endpoints inventados + botão morto no Knowledge (CRITÉRIOS 3 e 6) — **ABERTO, corrigir no re-run**

### A2 [fe-library] Endpoints inventados + botão morto no Knowledge (CRITÉRIOS 3 e 6)
Sintoma: `components/library/github-integration.tsx` chama 4 endpoints que **não existem** nem no backend nem em nenhum plano/contrato:
- `GET /api/integrations/github/status` (linha 43)
- `POST /api/integrations/github/connect` (linha 66)
- `POST /api/integrations/github/test` (linha 93)
- `DELETE /api/integrations/github` (linha 83)
Backend tem só `/api/integrations/github/repos|pulls|issues` + CRUD genérico (`integrations.py`).
Consequência: o botão "Conectar GitHub" nunca funciona (sempre 404) ⇒ **botão morto**, violação do feedback do usuário (sem botão morto) e da Seção 7 do DESIGN-SYSTEM (item: "Todo `<button>` tem ação real").
Além disso o PLANO-FRONTEND (§fe-library, knowledge) manda a view-KNOWLEDGE exibir **Rivvn** (gateado/desabilitado), **não** integração GitHub — o card Rivvn desabilitado já existe em `knowledge-view.tsx` (correto).
Correção:
1. **Remover** `agent-portal/components/library/github-integration.tsx` (+ `github-integration.test.tsx`) e o import/uso em `app/(dashboard)/knowledge/page.tsx` (linha 2 e 27).
2. Manter o card Rivvn desabilitado (já ok) — isso satisfaz o plano §284-285.
3. Se a equipe quiser integração GitHub de verdade, é item de BACKEND (endpoint + contrato), fora do escopo FE desta fase — registrar em pendência, não implementar aqui.
4. Revalidar: `npm run build`/`lint`/`tsc`/`vitest` limpos; knowledge sem referência a `/api/integrations/github/*`.

## B) PROBLEMAS DE OUTROS DONOS / BACKEND (NÃO bloqueantes para os 4 nós FE — NÃO refazer)
- **B1 [rt-executor / FASE 6]** — Pipeline CRUD ausente: `GET /api/pipelines`, `POST /api/pipelines`, `GET/PUT /api/pipelines/{id}`, `POST /api/pipelines/validate` → 404. Mandado pelo contrato (linhas 443 + 503 + resolução 16). Impacta editor/monitor (já aprovado, tratam com fallback/404) e o **dashboard** (deriva runs por aprovações pendentes + `GET /api/pipelines/{id}/runs`, que EXISTE — então o dashboard NÃO quebra). Detalhe em `docs/superpowers/validacoes/PENDENCIAS.md`.
- **B2 [auth-backend + infra-docker]** — `POST /api/auth/login` → **500** com credenciais válidas. Causa dupla: (a) `_EMAIL_RE` em `app/auth/schemas.py:12` exige TLD (`.local` falha) → rejeita o seed `admin@local`; (b) `app/core/errors.py:44` passa `exc.errors()` (com `ValueError` em `ctx`) para `json.dumps` → TypeError → 500. Impede e2e autenticado no browser. **Não é código FE.** Ver PENDENCIAS.md.
- **C1 [fe-shell / design]** — tokens: conferir que `app/globals.css` contém todos os tokens da Seção 1 do DESIGN-SYSTEM (o fe-shell aplica; não revisado aqui a fundo, mas o build/lint passa e os componentes usam `var(--...)`).

## C) O QUE PASSOU (os 4 nós)
1. **CRITÉRIO 1** (build/lint/tsc/testes): todos os 4 nós — OK.
2. **CRITÉRIO 3** (sem endpoint inventado):
   - dashboard — OK (`/api/agents`, `/api/approvals?status=pending`, `/api/pipelines/{id}/runs`, `/api/session-token`).
   - agents — OK (`/api/agents`, `/api/agents/{id}`, `/api/agents/chat`, `/api/agents/{id}/chat`, `/api/agents/chat/confirm`, seletores skills/tools/mcp-servers/knowledge).
   - approvals — OK (`/api/approvals?status=pending`, `/api/approvals/{id}/respond`, `DELETE /api/approvals/{id}`).
   - library — **FAIL** (github, ver A2); skills/tools/mcp/knowledge OK.
3. **CRITÉRIO 4** (auth): NextAuth credentials; token no cookie JWT (nunca localStorage); `/api/session-token` delega via `getServerSession`; `lib/api.ts` cache em memória; layout `(dashboard)/layout.tsx` redireciona p/ `/login` se não autenticado; middleware protege todas as rotas exceto login/register/api/auth/api/session-token/_next. **OK.**
4. **CRITÉRIO 5** (estados): loading (skeleton), vazio (EmptyState + CTA real), erro (toast + retry) presentes em dashboard/agents/approvals/library. Portal nasce vazio sem quebrar (dashboard tem empty-state "Comece criando seu primeiro agente" + CTA). Coberto por 355 testes. **OK.**
5. **CRITÉRIO 6** (design): zero emojis (só `→` tipográfico em comentários/labels, aceito); ícones `lucide-react` com `aria-label`; sem `href="#"`; botões reais **exceto** o "Conectar GitHub" (A2). **FAIL parcial (A2).**
6. **CRITÉRIO 7** (sem duplicar shell): os 4 nós usam `components/ui/*` e `components/layout/*` do shell e criam só `components/{dashboard,agents,approvals,library}/*`; nenhum sobrescreve o shell. **OK.**
7. Editor/monitor (já aprovados): rotas presentes no build; consumo de `/api/pipelines/*` tratado com fallback; sem regressão. **OK.**

## D) Inventário (handoff para QA e nós seguintes)
Rotas do portal (build): `/` (dashboard), `/agents/new`, `/agents/[id]`, `/pipelines`, `/pipelines/[id]`, `/pipelines/[id]/run`, `/approvals`, `/skills`, `/tools`, `/mcp`, `/knowledge`, `/login`, `/register`, `/_not-found`, `/api/auth/[...nextauth]`, `/api/session-token`.
- **fe-dashboard**: `app/(dashboard)/page.tsx`, `components/dashboard/{agent-card,stats-strip,recent-runs,pending-approvals,index}`. Consome `api.list`, `getWebSocketClient` (canal `pipeline:status`). WS: status em tempo real, `onReconnect` refetch REST.
- **fe-agents**: `app/(dashboard)/agents/{new,[id]}/page.tsx`, `lib/agent-chat.ts` (SSE `sendAgentChat`/`confirmAgentDraft`), `lib/agents.ts` (CRUD), `components/agents/{agent-chat,agent-preview,agent-detail,delete-agent-modal,index}`. SSE eventos `text|config_update|validation_error|done`; 429 com cooldown.
- **fe-approvals**: `app/(dashboard)/approvals/page.tsx`, `components/approvals/approval-panel.tsx`. Ações aprovar/rejeitar/argumentar/cancelar; 409 tratado; link p/ monitor. Badge via `CustomEvent approvals:pending-count` + fetch inicial.
- **fe-library**: `app/(dashboard)/{skills,tools,mcp,knowledge}/page.tsx`, `components/library/{skills-library,tools-editor,mcp-servers-library,knowledge-view,markdown-preview,github-integration}`. GitHub (A2) a remover; skills/tools/mcp/knowledge completos com estados.
- **Shell (fe-shell)**: `components/ui/*` (15 primitives), `components/layout/{app-shell,app-sidebar,app-topbar,notifications-badge}`, `lib/{api,websocket,types}.ts`, `auth-options.ts`, `app/(dashboard)/layout.tsx`, `app/page.tsx` (A1 a remover).

## E) Comandos
- Subir (revisor só, já feito): `docker compose up -d --build`; stack de pé ao final.
- Testar FE: `cd agent-portal && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`.
- Health: `curl http://localhost/api/health`.

## F) Decisões deste nó
- Não apliquei correção nos 2 problemas bloqueantes porque os arquivos afetados são de donos diferentes (fe-dashboard, fe-library) e o protocolo manda rejeitar com feedback acionável; as arestas de retry levam ao dono certo.
- Login 500 e pipeline CRUD são backend: não bloqueio os nós FE (não tenho retry para eles e não é código FE).
- Screenshot autenticado não executável (browser sem cache + backend 500); uso build manifest + fonte + probes como evidência.
