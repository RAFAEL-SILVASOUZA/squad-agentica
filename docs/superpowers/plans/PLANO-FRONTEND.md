# PLANO-FRONTEND — Portal Agent Portal

> **Nível:** plano que os nós de frontend deste flow seguem. Não escreve código de produto; descreve o que cada nó entrega, onde, com que endpoints/canais e com critérios de aceite testáveis.
> **Autor:** Tech Lead de Frontend.
> **Leiam antes:** `docs/superpowers/plans/CONTRATO-TECNICO.md` (precedência 1), spec `2026-09-17-agent-portal-design.md` (seções 1, 3, 4, 5, 6, 9, 10, 11, 12 ADR-006, 14), `docs/superpowers/plans/domains/D10-portal.md`, `docs/superpowers/plans/2026-09-21-execution-plan.md` (D10 + fases), `prototype/agent-portal.html` (referência de telas/fluxos/navegação).
> **Stack:** Next.js 14 App Router · React 18 · next-auth v4 · @xyflow/react 12 · lucide-react · vitest + testing-library · Playwright.

---

## Contratos que este plano consome (não recriar)

- **D3** entrega `lib/types.ts` (todas as interfaces da spec §4), `lib/api.ts` (client fetch com JWT + envelope de erro) e `lib/websocket.ts` (conexão única, canais, reconexão). O portal **só consome**; não reimplementa o client nem o WebSocket.
- **Design System** cuida de cores, tipografia e tokens. Este plano **não define** cores nem tipografia: consome `app/globals.css` do fe-shell e os `components/ui/*`.
- **Contrato** define o URL do token de delegação: `GET /api/session-token` (§5). **Desvio de precedência:** o D3 §3.5 cita `/api/jwt`; o contrato (§5) manda `session-token`. O plano usa `session-token`. O fe-shell/fe-review devem alinhar o D3 se ainda estiver em `/api/jwt`.

### Regras de precedência que o plano aplica

- **Portal nasce vazio** (contrato §0): todo `GET` de lista devolve `items: []` → a UI mostra empty state com CTA para o primeiro item. Nenhum "seed" de agente/pipeline ilustrativo na V1.
- **Sem emojis** (feedback explícito do usuário + nota D10): ícones via `lucide-react`, stroke-based, sempre com `aria-label`.
- **Nenhum botão sem ação** (feedback explícito): cada botão dispara action real (navegação, submit, abrir painel, etc.), nunca `#`/href vazio/`showToast` de tela fake.
- **camelCase** em toda comunicação (contrato §8): os tipos espelham `ownerId`, `sourceOutput`, `requiresApproval`, etc.

---

## 1. Mapa de rotas (App Router)

Estrutura obrigatória (contrato §1 + §9 fase 8). Cada rota aponta pra qual view do protótipo implementa.

```
agent-portal/app/
├── layout.tsx                        # (fe-shell) shell com sidebar + topbar; provedor de sessão + tema
├── globals.css                       # (fe-shell) tokens de design
├── page.tsx                          # (fe-shell) placeholder → fe-dashboard substitui
├── (auth)/
│   ├── login/page.tsx                # → protótipo: tela de login (fora do shell; NextAuth signIn)
│   └── register/page.tsx             # → (sem tela no protótipo; habilita-se se o backend expor register)
├── api/
│   ├── auth/[...nextauth]/route.ts   # (fe-shell/auth-frontend) NextAuth credentials
│   └── session-token/route.ts        # (fe-shell) GET → JWT de delegação para REST + WS
└── (dashboard)/
    ├── page.tsx                      # → protótipo: view-DASHBOARD (grid de Agentes + stats strip) [fe-dashboard]
    ├── agents/
    │   ├── new/page.tsx              # → protótipo: view-AGENT-DETAIL em modo "Criar novo agente" [fe-agents]
    │   └── [id]/page.tsx             # → protótipo: view-AGENT-DETAIL em modo edição [fe-agents]
    ├── pipelines/
    │   ├── [id]/page.tsx             # → protótipo: view-FLOW EDITOR [fe-flow-editor]
    │   └── [id]/run/page.tsx         # → protótipo: view-MONITOR [fe-monitor]
    ├── approvals/page.tsx            # → protótipo: view-APPROVALS [fe-approvals]
    ├── skills/page.tsx               # → protótipo: view-SKILLS [fe-library]
    ├── tools/page.tsx                # → protótipo: view-TOOLS-CUSTOM [fe-library]
    ├── mcp/page.tsx                  # → protótipo: view-MCP-SERVERS [fe-library]
    └── knowledge/page.tsx            # → protótipo: view-KNOWLEDGE [fe-library]
```

Observações de navegação (baseadas no protótipo):

- O **shell** (`(dashboard)/page.tsx` e sub-rotas) roda dentro do layout; a **sidebar** aponta para `/`, `/agents/new`, `/agents/[id]`, `/pipelines/[id]`, `/pipelines/[id]/run`, `/approvals`, `/skills`, `/tools`, `/mcp`, `/knowledge`.
- A navegação do protótipo é `data-view`/`onclick` (HTML único). No App Router, isso vira `<Link>` real entre as rotas acima. **Nenhum `data-view` e nenhum `onclick` de troca de view** — a navegação é de roteamento de página de verdade.
- O protótipo tem uma "view Flow" (lista de pipelines / editor de uma pipeline). Não há rota `/pipelines` de listagem no mapa do contrato; a pipeline entra por `/pipelines/[id]`. Para não deixar link morto: a stats strip do dashboard ("N pipelines em execução") leva a `/pipelines/[id]/run`; o botão "Executar" do flow editor leva a `/pipelines/[id]/run`. Se houver `/pipelines` de listagem, ela será implementada como tela de navegação; de contrário, não se cria rota inexistente no contrato.

> **Decisão (ponto cego):** o contrato não lista `/pipelines` (listagem). O portal deriva de agentes/pipelines reais; como o portal nasce vazio, a tela de listagem de pipelines só faria sentido com pelo menos uma pipeline criada. Enquanto não houver pipelines, o entry point é o dashboard + "Novo Agente". O dashboard mostra pipelines **em execução** (via `GET /api/pipelines?status=running`); ao clicar, vai para o monitor. Registrar na resposta final se um revisor quiser `/pipelines` explícito.

---

## 2. Árvore de componentes

Compartilhados (fe-shell) vs específicos de domínio (cada nó de tela). Não escrever cores/tipografia aqui; usar `components/ui/*`.

```
agent-portal/
├── components/
│   ├── ui/                         # (fe-shell) primitives: button, input, select, textarea, toggle,
│   │                               #   badge, card, table, modal, drawer, tabs, toast, empty-state, skeleton
│   ├── layout/                     # (fe-shell):
│   │   ├── app-shell.tsx           #   grid topbar + sidebar + main (estrutura do shell)
│   │   ├── app-sidebar.tsx         #   navegação entre views (Links reais)
│   │   ├── app-topbar.tsx          #   logo + toggle de tema + avatar
│   │   └── notifications-badge.tsx #   badge de aprovações pendentes (consumo WS approval:new)
│   └── <domínio>/                  # (nós de tela, um por nó):
│       ├── AgentCard.tsx           #   (fe-dashboard): card de agente (status, tags)
│       ├── stats-strip.tsx         #   (fe-dashboard): faixa de métricas
│       ├── AgentChat.tsx           #   (fe-agents): chat de construção com streaming
│       ├── AgentPreview.tsx        #   (fe-agents): preview/resumo do agente no chat
│       ├── FlowEditor.tsx          #   (fe-flow-editor): React Flow wrapper
│       ├── EdgePanel.tsx           #   (fe-flow-editor): config de aresta (tipo/dataMapping/condition/requiresApproval)
│       ├── PipelineMonitor.tsx     #   (fe-monitor): nós em tempo real + logs + checkpoints
│       ├── ApprovalPanel.tsx       #   (fe-approvals): lista + aprobar/rejeitar/argumentar
│       ├── SkillsLibrary.tsx       #   (fe-library): grid de skills
│       ├── ToolsEditor.tsx         #   (fe-library): grid + editor de tools custom
│       ├── MCPServersLibrary.tsx   #   (fe-library): grid + detalhe de servidores MCP
│       └── KnowledgeView.tsx       #   (fe-library): sidebar de bases + upload + rivvn bar
├── lib/
│   ├── api.ts                      # (fe-shell) client fetch com JWT
│   ├── websocket.ts                # (fe-shell) conexão única + canais + reconexão
│   └── types.ts                    # (D3) espelha schemas da API
└── app/
    ├── (auth)/login, register      # (fe-shell/auth-frontend)
    ├── (dashboard)/                # cada view
```

> **Handoff de DOM:** os `components/<domínio>/*` (fe-agents/fe-flow-editor/fe-monitor/fe-approvals/fe-library) vivem em `components/` por convenção do contrato (§9 fase 8), não dentro das rotas. O fe-shell entrega `components/ui/*` e `components/layout/*`; os nós de tela consomem esses primitives e criam seus próprios `components/<domínio>/*`.

---

## 3. Camada de dados

Consumida; o fe-shell entrega `lib/api.ts`, `lib/websocket.ts`, `lib/types.ts`. Este plano só consome e define o **estado de servidor vs local** de cada view.

### `lib/api.ts` (consome)
- `api.get/post/put/delete<,T>(path, opts?)`: busca token em `GET /api/session-token` (cache em memória, `let` no escopo do módulo; não `localStorage`), injeta `Authorization: Bearer <token>`, devolve `{ status, data }` ou lança `ApiError`.
- **Envelope de erro** (contrato §8): em 4xx/5xx, `ApiError` carrega `{ error, code, details }`. Tratar `401` → redirecionar a `/login` (NextAuth). `409` (pipeline_already_running / graph_running / already_responded) → exibir no toast e atualizar UI. `429` (rate_limited) → usar `retryAfter` para desabilitar ação por N segundos.
- Paginação: `api.list<T>(path)` devolve `{ items, total, page, limit }` (contrato §8).

### `lib/websocket.ts` (consome)
- Conexão única em `wss(s)://<host>/api/ws?token=<JWT>` (contrato §7; correção da spec §9.7: rota `/api/ws`, não `/ws`).
- Frames: `JSON.stringify({ channel, data })`. Cliente escuta todos os canais; **filtra por `pipelineId`** do payload (contrato §7).
- Reconexão: backoff exponencial (1s,2s,4s…30s); token reenviado na query string; ao reconectar, **state de servidor refetchado por REST** (`GET /api/pipelines/{id}` + `/api/pipelines/{id}/runs`) para sincronizar.
- Registro de handlers por canal; interface `onEvent(channel, data)`.

> **Nota para o fe-review:** o D3 §3.6 cita `ws://host/ws?token=JWT`; o contrato (§7) corrige para `/api/ws`. Consumir `/api/ws`.

### `lib/types.ts` (D3) — interfaces que as views espelham
`Agent, PortDef, SkillRef, ToolRef, MCPServerRef, KnowledgeRef, IntegrationRef, Pipeline, PipelineNode, AgentSnapshot, PipelineEdge, DataMapping, EdgeCondition, PipelineRun, Checkpoint, Skill, CustomTool, MCPToolInfo, KnowledgeBase, KnowledgeDocument, ApprovalRequest, RivvnConnection, Integration, Artifact, NotificationChannel`.

### Estado de servidor vs local (por view)
- **Servidor** (via `api.*`, refetchado ou via WS): lista de agentes, status de nós/pipeline, logs, aprovações, skills/tools/mcp/knowledge, estado de execução.
- **Local** (`useState`/`useReducer`): estado temporário do chat de construção (mensagens em buffer, `draftId` de sessão efêmera), estado de expansão de cartão de aprovação, `zoom`/`pan`/nós temporários do editor até salvar, valor de input de upload.

---

## 4. Bloco por nó

---

### `fe-shell` — shell, `lib/*`, `components/ui/*`, `components/layout/*`, placeholders
**Objetivo:** entregar o chão do portal que os nós de tela substituem. Não consome endpoints de negócio; só o shell, a camada de dados e os primitives.
**Arquivos:** `app/layout.tsx`, `app/globals.css`, `app/page.tsx` (placeholder), `components/layout/{app-shell,app-sidebar,app-topbar,notifications-badge}.tsx`, `components/ui/{button,input,select,textarea,toggle,badge,card,table,modal,drawer,tabs,toast,empty-state,skeleton}.tsx`, `lib/api.ts`, `lib/websocket.ts`, `types/next-auth.d.ts`, `agent-portal/README.md`.
**Páginas placeholder:** uma página por rota do mapa de rotas (§1), com `empty-state` ("Em construção" sem CTA de produto, ou vazio) — os nós de tela substituem. Nenhuma página placeholder cria agente/pipeline ilustrativo (portal nasce vazio, contrato §0).
**Componentes de layout:**
- `app-shell`: grid topbar + sidebar + main (estrutura do shell do protótipo; consome `components/ui/*`).
- `app-sidebar`: navegação entre views via `<Link>` real (contrato §1, não `data-view`/`onclick`). Itens: Dashboard (`/`), Pipelines (`/pipelines/[id]` via stats strip), Monitor (`/pipelines/[id]/run` via stats strip), Aprovações (`/approvals`), Skills (`/skills`), Tools Custom (`/tools`), MCP Servers (`/mcp`), Knowledge (`/knowledge`).
- `app-topbar`: logo + toggle de tema (`data-theme` no `html`, persistido em `localStorage`) + avatar.
- `notifications-badge`: badge de aprovações pendentes (consumo WS `approval:new`, ver §3).
**Camada de dados (entrega, não consome):** `lib/api.ts`, `lib/websocket.ts`, `lib/types.ts` (tipos espelham os schemas da API). Ver §3 para a especificação completa.
**Estado:** nenhum estado de produto próprio; só estado de shell (tema, estado de sessão via NextAuth, badge de notificação).
**Critérios de aceite testáveis:**
- `app/layout.tsx` renderiza shell com sidebar + topbar; navegação entre views funciona via `<Link>`.
- Tema persiste em `localStorage` (`agent-portal-theme`) e restaura no load.
- Toda rota do mapa de rotas existe como página (placeholder com empty state); nenhum link morto.
- `lib/api.ts` obtém token de `GET /api/session-token` (não `localStorage`), injeta `Authorization: Bearer`, e lança `ApiError` com `{ error, code, details }` em 4xx/5xx.
- `lib/websocket.ts` conecta em `wss(s)://<host>/api/ws?token=<JWT>` (não `/ws`), frame `{ channel, data }`, filtra por `pipelineId`, reconecta com backoff exponencial.
- `components/ui/*` são primitives sem emojis; ícones via `lucide-react` com `aria-label`.
- Nenhum `npm install`/`npm ci`/`npm run build` (dependências ficam com infra-docker).

---

### `auth-frontend` (login/register) — parte do fe-shell/fe-frontend
**Telas:** `(auth)/login`, `(auth)/register` (fora do shell; NextAuth redirect em 401).
**Endpoints:** consumo do NextAuth (`POST /api/auth/[...nextauth]`); `GET /api/session-token`.
**Eventos WS:** nenhum.
**Estados:** loading (submetendo), erro de credencial (mensagem genérica — contrato §5, não revela se o e-mail existe), redirecionamento pós-login.
**Critérios de aceite testáveis:**
- Sem credenciais válidas → `401` do NextAuth → redirect a `/login`.
- Login com sucesso obtém session e o avatar do topbar aparece.
- Formulário valida email/senha client-side antes de submeter (acessibilidade: labels + `aria-describedby` para erro).
- Nenhum token em `localStorage`/`sessionStorage`.

---

### `fe-dashboard` — substitui `app/(dashboard)/page.tsx`
**Tela:** protótipo view-DASHBOARD. Grid de cards de agentes + stats strip + botão "Novo Agente".
**Componentes:** `components/layout/app-shell`, `app-sidebar`, `app-topbar`; `components/ui/{card,badge,skeleton,empty-state,toast,button}`; `components/AgentCard.tsx`; `components/stats-strip.tsx`.
**Endpoints:** `GET /api/agents?type=&page=&limit=` (lista), `GET /api/pipelines?status=running&page=&limit=` (pipes em execução para a stats strip).
**Eventos WS:** `approval:new` (para atualizar o badge do header — consumo mínimo, componente `notifications-badge`).
**Estados:**
- **Loading:** skeleton cards + skeleton stats.
- **Vazio (portal nasce vazio):** `empty-state` com texto "Nenhum agente ainda" e CTA "Criar primeiro agente" → `/agents/new`. Sem dados ilustrativos.
- **Erro:** toast de erro + botão "Tentar novamente".
**Ação do botão "Novo Agente":** `router.push('/agents/new')` (real).
**Critérios de aceite testáveis:**
- `GET /api/agents` vazio → renderiza empty-state com CTA clicável que navega.
- Carto de agente real mostra nome, tipo, status, tags; clicar → `/agents/{id}` (real).
- Stats strip exibe contagem de pipelines rodando; clicar numa leva a `/pipelines/{id}/run` (real).
- Badge de aprovações atualiza ao receber `approval:new` do canal apropriado (filtrado por pipelineId do owner).

---

### `fe-agents` — `app/(dashboard)/agents/new` e `app/(dashboard)/agents/[id]`
**Telas:** protótipo view-AGENT-DETAIL (dois modos: construção de novo + edição).
**Componentes:** `components/layout/app-shell`; `components/AgentChat.tsx`; `components/AgentPreview.tsx`; `components/ui/{button,input,select,textarea,toast,skeleton,empty-state,card}`.
**Endpoints:**
- Construção (sem id): `POST /api/agents/chat` (SSE streaming; `message` + `draftId?`).
- Edição (com id): `GET /api/agents/{id}`, `POST /api/agents/{id}/chat` (SSE), `PUT /api/agents/{id}`, `DELETE /api/agents/{id}`.
**Eventos WS:** nenhum (construção via SSE).
**Estados:**
- **Chat loading:** mensagem inicial do assistente; buffer de mensagens em estado local.
- **Streaming:** mensagem do usuário fixa; resposta IA appending tokens via SSE (`text`), `config_update` aplicando ao draft, `done` com `draftId`.
- **Preview:** mostra resumo do draft (identidade, mochila, contrato, execução) atualizado por `config_update`.
- **Salvando:** state de loading no botão "Salvar".
- **Vazio/erro:** se `GET /api/agents/{id}` 404 → toast + voltar ao dashboard; chat sem `draftId` ainda não gerou agente.
**Critérios de aceite testáveis:**
- Envia mensagem → SSE appenda texto e `config_update` atualiza o preview; "Salvar" cria agente via `POST /api/agents` e navega.
- `PUT /api/agents/{id}` persiste alterações; `DELETE` remove e navega.
- Campo "Canal de aprovação" (select) reflete o `approvalChannel` do agente (conforme types); sem `showToast` de "em desenvolvimento" — é control field real.

---

### `fe-flow-editor` — `app/(dashboard)/pipelines/[id]/page.tsx`
**Tela:** protótipo view-FLOW EDITOR. React Flow com nós, arestas flow (sólida) e data (tracejada azul), legend, toolbar (zoom in/out, fit, adicionar nó, conectar), painel de aresta.
**Componentes:** `components/layout/app-shell`; `components/FlowEditor.tsx` (wrapper `@xyflow/react`); `components/EdgePanel.tsx`; `components/ui/{button,badge,skeleton,toast}`.
**Endpoints:** `GET /api/pipelines/{id}` (grafo + estado), `PUT /api/pipelines/{id}` (salvar grafo), `POST /api/pipelines/{id}/execute`, `POST /api/pipelines/{id}/pause`, `POST /api/pipelines/{id}/stop`.
**Eventos WS:** `pipeline:status` (para refletir status dos nós após executar), `pipeline:log`.
**Estados:**
- **Loading grafo:** skeleton / node de carregamento do grafo.
- **Vazio:** portal nasce vazio; se não há nós → empty state "Nenhum nó ainda. Adicione um agente ao grafo" + botão "Adicionar agente" (real: abre node paleta).
- **Erro:** `PUT`/`GET` 4xx → toast de erro de validação de grafo (conforme envelope 400 `details.errors`).
**Painel de aresta (`EdgePanel`):** ao clicar numa aresta, mostra tipo (Flow/Data), condition (só se flow edge explícita), data mapping (sourceOutput/targetInput, só se data edge), requiresApproval, approvalChannel. Ação de "Conectar": modo de selection de two nós (real, sem `showToast`). Botões zoom/fit reagem ao React Flow (real).
**Critérios de aceite testáveis:**
- `GET` carifica grafo; `PUT` persiste alterações; grafo inválido → erros de validação exibidos (cores de erro por aresta, tooltip com motivo — cores via design system).
- Clicar em arestas abre `EdgePanel` com dados reais da `PipelineEdge`; salvar grafo com data edge sem flow edge implícita respeita ADR-006 (conforme types, o compiler decide a injestão).
- Botão "Executar" navega a `/pipelines/{id}/run` (real); "Pausar"/"Parar" disparam os endpoints correspondentes.
- Nenhum estado de demonstração fixo (os 44 nós do protótipo NÃO são seed); grafo só aparece após o usuário criá-lo.

---

### `fe-monitor` — `app/(dashboard)/pipelines/[id]/run/page.tsx`
**Tela:** protótipo view-MONITOR. Layout duas colunas: lista de nós (status por dot), painel principal com logs em tempo real e checkpoints recentes com "Retomar".
**Componentes:** `components/layout/app-shell`; `components/PipelineMonitor.tsx`; `components/ui/{badge,skeleton,toast,button,empty-state,table}`.
**Endpoints:** `GET /api/pipelines/{id}`, `GET /api/pipelines/{id}/runs`, `GET /api/pipelines/{id}/checkpoints`, `POST /api/pipelines/{id}/resume`, `POST /api/pipelines/{id}/checkpoints/{cpId}/resume`, `POST /api/pipelines/{id}/pause`, `POST /api/pipelines/{id}/stop`.
**Eventos WS:** `pipeline:status` (status de nó em tempo real), `pipeline:log` (logs), `agent:output` (streaming de output de nó), `approval:new`/`approval:resolved` (se houver nodes de aprovação no run).
**Estados:**
- **Loading:** skeleton da lista de nós e dos logs.
- **Vazio:** run sem eventos ainda → "Aguardando início da execução" + CTA "Iniciar execução" (`POST execute`).
- **Erro:** `409 pipeline_already_running` ao tentar executar → toast informando.
**Ações:** "Pausar"/"Parar" reais; "Ver pipeline" navega a `/pipelines/{id}` (real); "Retomar" em checkpoint → `POST checkpoints/{cpId}/resume` (real); botão "Retomar pipeline" resume pelo run atual.
**Critérios de aceite testáveis:**
- `pipeline:status` do canal correto (filtrado por `pipelineId`) atualiza o dot de status de cada nó em tempo real.
- `pipeline:log` appenda linhas na ordem recebida; checkpoint com status "interrupted"/"failed" mostra "Retomar".
- Reconexão WS → refetch REST (`{id}`, `runs`, `checkpoints`) sincroniza estado.

---

### `fe-approvals` — `app/(dashboard)/approvals/page.tsx`
**Tela:** protótipo view-APPROVALS. Lista de cartões de aprovação (urgente em destaque) com aprovar/rejeitar/argumentar.
**Componentes:** `components/layout/app-shell`; `components/ApprovalPanel.tsx`; `components/ui/{button,badge,toast,skeleton,empty-state}`.
**Endpoints:** `GET /api/approvals?status=pending|resolved|cancelled&pipelineId=&page=`, `POST /api/approvals/{id}/respond` (approved/rejected/revised + response), `DELETE /api/approvals/{id}` (cancelar pendente).
**Eventos WS:** `approval:new` (nova aprovação entra na lista), `approval:resolved` (card sai/ muda de status).
**Estados:**
- **Loading:** skeleton cards.
- **Vazio:** "Nenhuma aprovação pendente" + CTA secundário "Ver pipelines".
- **Erro:** `404 already_responded` ao responder → toast "Já respondida".
**Ações:** "Aprovar" → `respond(approved)`; "Rejeitar" → `respond(rejected)`; "Argumentar" abre textarea (estado local) e submete `respond(revised, response)`; "Cancelar" → `DELETE`. Expansão do card em estado local.
**Consumo mínimo do shell:** o `notifications-badge` (componente do fe-shell) escuta `approval:new` e incrementa o badge; a view não duplica isso — ela lista via REST + WS no próprio `ApprovalPanel`.
**Critérios de aceite testáveis:**
- Lista refetcha após responder/cancelar; `approval:new` do canal correto adiciona novo cartão.
- "Argumentar" injeta `response` como feedback via `respond(revised)`.
- Nenhum `showToast` de "em desenvolvimento" — respostas são reais e atualizam a lista.

---

### `fe-library` — `app/(dashboard)/{skills,tools,mcp,knowledge}/page.tsx`
Quatro telas, cada uma consome um componente do D8/D9 (`components/*.{tsx}`) e um router do backend.

**`skills/page.tsx` — view-SKILLS**
- **Componente:** `components/SkillsLibrary.tsx`.
- **Endpoints:** `GET /api/skills`, `POST /api/skills`, `GET /api/skills/{id}`, `PUT /api/skills/{id}`, `DELETE /api/skills/{id}`.
- **Estados:** loading (skeleton grid), vazio ("Nenhum skill ainda" + CTA), erro.
- **Ação:** "Nova Skill" abre modal/form de criação (real).

**`tools/page.tsx` — view-TOOLS-CUSTOM**
- **Componente:** `components/ToolsEditor.tsx`.
- **Endpoints:** `GET /api/tools`, `POST /api/tools`, `GET/PUT/DELETE /api/tools/{id}`, `POST /api/tools/{id}/deploy`, `POST /api/tools/{id}/test`.
- **Estados:** loading, vazio ("Nenhuma tool ainda" + CTA), erro de validação de script (400), deploy/update via toast de resultado real.
- **Ações:** "Nova Tool" (form), "Testar" (`POST test`), "Deploy" (`POST deploy`), editar script/parâmetros (PUT).

**`mcp/page.tsx` — view-MCP-SERVERS**
- **Componente:** `components/MCPServersLibrary.tsx`.
- **Endpoints:** `GET /api/mcp-servers`, `POST /api/mcp-servers`, `GET/PUT/DELETE /api/mcp-servers/{id}`, `POST /api/mcp-servers/{id}/test`.
- **Estados:** loading, vazio, erro de conexão (exibe `status` disconnected/error).
- **Ações:** "Novo Servidor" (form de transporte/comando/URL/env), "Testar conexão" (`POST test`, popula `discoveredTools`).

**`knowledge/page.tsx` — view-KNOWLEDGE**
- **Componente:** `components/KnowledgeView.tsx`.
- **Endpoints:** `GET /api/knowledge?scope=&source=`, `POST /api/knowledge`, `GET/PUT/DELETE /api/knowledge/{id}`, `POST /api/knowledge/{id}/upload` (multipart), `GET /api/knowledge/{id}/documents`, `DELETE /api/knowledge/{id}/documents/{docId}`, `POST /api/knowledge/query`, + Rivvn (`GET/DELETE /api/integrations/rivvn`, `authorize`/`callback`).
- **Rivvn (fora da V1 / gateado):** UI desabilitada sem contrato ativo; botão "Conectar Rivvn" aparece com CTA de contato comercial; conforme contrato §10 e spec §7.4, `GET /api/integrations/rivvn/authorize` responde 403 sem contrato. **Nenhuma UI Rivvn ativa sem contrato.**
- **Estados:** loading, vazio, processamento de upload (`status: processing/ready/failed` por documento).
- **Ações:** Upload (form multipart), seleção de base na sidebar (estado local), escopo (select real), disconnect Rivvn (`DELETE`).

**Critérios de aceite testáveis (geral da library):**
- Cada view refetcha após criar/deletar/ atualizar; `GET` vazio → empty-state com CTA real.
- Nenhum `showToast` de "em desenvolvimento"; todas as ações chamam endpoints reais.
- Rivvn só ativa quando o backend confirma `contractStatus === active`.

---

## 5. Regras transversais

### Sem emojis, ícones lucide-react
- Nenhum caractere emoji em texto, botões ou ícones. Ícones via `lucide-react`, sempre `aria-label` e `role="img"`.
- Os ícones do protótipo (SVG inline) são substituídos por componentes `lucide-react` equivalentes (ex.: `LayoutGrid` dashboard, `GitBranch` pipelines, `Monitor` monitor, `CheckCircle2` aprovações, `BookOpen` skills, `Wrench` tools, `Server` mcp, `FileText` knowledge).

### Nenhum botão sem ação
- Todo `<button>` tem `onClick` que executa action real (navegação via `router.push`, submit, abre painel, dispara API). Nada de `href="#"`, `onclick="showToast(...)"` de tela fake, ou "em desenvolvimento". Botões desabilitados (`disabled`) enquanto loading, com `aria-disabled`.

### Acessibilidade
- Foco visível em todos os interativos (`:focus-visible`). Labels em todos os inputs (`<label htmlFor>` + `id`), erro com `aria-describedby`. Botões com `aria-label` quando o ícone é a única marcação. Contraste conforme design system. Navegação por teclado no editor (React Flow nativo + atalhos documentados).

### Responsividade
- Grids fluidos (como o protótipo: `repeat(auto-fill, minmax(...))`). Em `< 900px`, sidebar recolhível (não somida de vez — menu hamburger) mantendo navegação. Agent detail empilha chat + config verticalmente.

### Testes
- **Componentes (vitest + @testing-library/react):** 1 suíte por componente de UI com estado de loading, vazio, cheio e erro. Mock de `lib/api.ts` (respostas) e de `lib/websocket.ts` (eventos). Ex.: `AgentCard` render vazio/cheio; `ApprovalPanel` submete resposta; `PipelineMonitor` refetch após `approval:resolved`; `FlowEditor` abre `EdgePanel` com dados da aresta.
- **Jornadas (Playwright):** 1) login → dashboard vazio → criar agente → ver card; 2) criar pipeline → abrir editor → conectar nós → executar → monitor em tempo real via WS; 3) aprovação pendente → responder → card sai da lista. Mock do backend via route handlers/intercepts (não tocar no banco de dev).

### Verificação (regra do protocolo comum §7)
- `npx tsc --noEmit` sem erro por arquivo novo; `eslint` limpo por arquivo tocado. Testes do nó rodam no host (`npx vitest run <path>`), não no container. Nenhum `npm install`/`npm ci`/`npm run build` (fe-shell/infra-docker/revisor de frontend).
- Nenhum `showToast` de "em desenvolvimento" como terminal de ação: toast só para resultado real de operação (sucesso/erro), nunca para encobrir funcionalidade não implementada.

---

## 6. Pendências / mudanças a outros donos (para o revisor da fase aplicar)

1. **D3 `/api/jwt` vs contrato `session-token`:** o D3 §3.5 cita `/api/jwt`; o contrato (§5) manda `GET /api/session-token`. **O fe-shell consome `session-token`** — se o router do D3 ainda estiver em `/api/jwt`, o fe-review/alinhar. Arquivo do outro dono (D3): não tocado.
2. **WS `ws://host/ws` vs `/api/ws`:** D3 §3.6 cita `/ws`; contrato (§7) corrige para `/api/ws`. **O fe-shell consome `/api/ws`** — alinhar no D3. Arquivo do outro dono (D3): não tocado.
3. **`next.config.ts` / `package.json`:** dependências `@xyflow/react`, `lucide-react`, dev (vitest, testing-library, playwright) ficam com o **fe-shell** (instala), não com nós de tela (contrato §9 fase 8). Nenhum nó de tela instala dependência. Dono: infra-docker.
4. **Rotas placeholder:** o fe-shell entrega **páginas placeholder com empty state** para todas as rotas do PLANO-FRONTEND (§9 fase 8). Os nós de tela (fe-dashboard, fe-agents, etc.) substituem os placeholders. Confirmar no handoff do fe-shell que `app/(dashboard)/page.tsx` e sub-rotas estão como placeholder vazio, não como seed.
5. **Rota `/pipelines` (listagem):** não consta no mapa do contrato. Se a fase quiser listagem de pipelines, é decisão do revisor de frontend; de imediato, o dashboard deriva pipelines por status via API. Registrar se houver solicitação.
6. **Rivvn UI desabilitada:** a view Knowledge consome a API Rivvn; sem `contractStatus === active`, a UI mostra CTA comercial e botão desabilitado. Confirmar no D9 que `/api/integrations/rivvn/authorize` responde 403 sem contrato.

---

## 7. Riscos de frontend

- **React Flow com muitos nós:** portabilidade do grafo grande (protótipo: 44 nós); lazy render / virtualização de nós distantes, `nodes`/`edges` imutáveis, key estável por `nodeId`/`edgeId`.
- **Integração de componentes distribuídos:** `AgentChat`/`FlowEditor`/etc. são entregues por D4–D9; o fe-shell/orquestrador só os monta na rota certa. Se um componente não estiver pronto, a view mostra loading/erro tratado (nunca tela fake).
- **WebSocket centralizado:** um ponto de falha. Reconexão robusta + refetch REST garante que, se a conexão cair, a view recupera estado. Badge de notificação consome o componente do fe-shell (não reimplanta).
- **Portal nasce vazio:** cuidar de empty states com CTA real em toda lista (dashboard, editor, approvals, skills, tools, mcp, knowledge) e no chat (mensagem inicial do assistente).
- **Streaming SSE (chat de construção):** buffering local + append token-a-token; `draftId` em estado local (sessão efêmera); "Salvar" só habilitado após geração de draft coerente.
```