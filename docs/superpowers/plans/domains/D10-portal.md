# D10 — Portal Frontend (Next.js)

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 7 · Portal Completo**. Dependência: **D3, D4, D5, D6, D7, D8, D9** (todos os back-ends + tipos + client).
> Base: spec (seções 1, 3, 9, 11, 12 ADR-006) + protótipo `prototype/agent-portal.html` + plano.

## Objetivo

Implementar o portal completo com todas as views do protótipo, integrando com todas as APIs e canais WebSocket. O portal é o designer da pipeline (editor de fluxo) e o painel de monitoramento/aprovações.

## Escopo (o que FAZ)

- Layout base: topbar, sidebar, tema dark/light, navegação entre views.
- Dashboard (Agentes): grid de cards, stats strip, botão "Novo Agente".
- Agent Detail: chat de construção + config panel (identidade, ferramentas, integrações, skills, tools, MCP, contrato, execução).
- Flow Editor: React Flow completo.
- Pipeline Monitor: status, logs, checkpoints, "Retomar".
- Approvals Panel: aprovar/rejeitar/argumentar.
- Skills Library, Tools Custom, MCP Servers, Knowledge.
- Integração WebSocket (todos os canais).
- Integração GitHub (leitura de PRs/issues — a única integração de plataforma na V1).

## Escopo (o que NÃO FAZ)

- NÃO implementa backend (consome as APIs dos D3–D9).
- NÃO implementa auth do zero (D2 entrega NextAuth + JWT; aqui só consome).
- NÃO implementa lógica de negócio (validação de contrato, compiler, runtime — tudo no backend).
- NÃO implementa Rivvn OAuth (D9) — só a UI de conexão.

## Dependências

- **D3:** `types.ts`, `api.ts`, `websocket.ts`, routers base.
- **D4:** `AgentChat.tsx` (D4 entrega; D10 integra no Agent Detail).
- **D5:** `FlowEditor.tsx`, `EdgePanel.tsx` (D5 entrega; D10 integra no route de pipeline).
- **D6:** `PipelineMonitor.tsx` (D6 entrega).
- **D7:** `ApprovalPanel.tsx` (D7 entrega).
- **D8:** `SkillsLibrary.tsx`, `ToolsEditor.tsx`, `MCPServersLibrary.tsx` (D8 entrega).
- **D9:** `KnowledgeView.tsx` (D9 entrega).

> Nota: D4–D9 entregam os componentes individuais. O D10 é o **orquestrador da UI**: monta o layout, a navegação, e integra cada componente no route certo. Se algum componente não estiver pronto, o D10 pode implementar a view mínima e delegar a complexidade, mas o ideal é consumir os entregáveis dos domínios anteriores.

## Arquivos que OWNS

```
agent-portal/
  app/layout.tsx                (topbar, sidebar, tema)
  app/(dashboard)/page.tsx      (Dashboard: grid de agentes)
  app/(dashboard)/pipelines/
    [id]/page.tsx               (Flow Editor)
    [id]/run/page.tsx           (Pipeline Monitor)
  app/(dashboard)/agents/
    new/page.tsx                (Chat de construção)
    [id]/page.tsx               (Agent Detail)
  app/(dashboard)/approvals/page.tsx
  app/(dashboard)/skills/page.tsx
  app/(dashboard)/tools/page.tsx
  app/(dashboard)/mcp/page.tsx
  app/(dashboard)/knowledge/page.tsx
  components/                   (integração dos componentes dos D4-D9)
  lib/websocket.ts              (D3 entrega; D10 consome todos os canais)
```

## Tarefas

### 10.1 Layout base
- Topbar (nome do projeto, tema toggle), sidebar (navegação entre views), tema dark/light persistido (localStorage/NextAuth session).
- Aceite: navegação entre views funciona; tema persiste.

### 10.2 Dashboard (Agentes)
- Grid de cards de agentes (via `api.get('/api/agents')`), stats strip (total, rodando, etc.), botão "Novo Agente" (vai pro chat de construção).
- Aceite: dashboard mostra agentes reais da API.

### 10.3 Agent Detail
- Chat de construção (consome `AgentChat.tsx` do D4) + config panel (identidade, ferramentas, integrações, skills, tools, MCP, contrato, execução). Editar agente via `PUT /api/agents/:id`.
- Aceite: ver/editar agente, conversar no chat, salvar alterações.

### 10.4 Flow Editor
- Integra `FlowEditor.tsx` + `EdgePanel.tsx` do D5 no route `[id]`. Carregar grafo (`GET /api/pipelines/:id`), salvar (`PUT`).
- Aceite: abrir pipeline mostra o grafo; editar e salvar persiste.

### 10.5 Pipeline Monitor
- Integra `PipelineMonitor.tsx` do D6 no route `[id]/run`. Consome `pipeline:status`, `pipeline:log`, `agent:output`.
- Aceite: execução mostra status em tempo real.

### 10.6 Approvals Panel
- Integra `ApprovalPanel.tsx` do D7. Consome `approval:new`/`approval:resolved`.
- Aceite: aprovar/rejeitar/argumentar atualiza o grafo.

### 10.7 Skills Library
- Integra `SkillsLibrary.tsx` do D8.
- Aceite: listar skills, associar a agentes.

### 10.8 Tools Custom
- Integra `ToolsEditor.tsx` do D8.
- Aceite: grid de tools, editar, deploy, testar.

### 10.9 MCP Servers
- Integra `MCPServersLibrary.tsx` do D8.
- Aceite: grid de servidores, detalhe, testar conexão.

### 10.10 Knowledge
- Integra `KnowledgeView.tsx` do D9.
- Aceite: sidebar de bases, upload, escopo, Rivvn bar.

### 10.11 Integração WebSocket
- `lib/websocket.ts` (D3): conexão WebSocket nativo via `new WebSocket(`ws://${host}/ws?token=${jwt}`)`. Handlers para todos os canais (`pipeline:status`, `pipeline:log`, `agent:output`, `approval:new`, `approval:resolved`).
- Formato de mensagem: frames JSON `{ channel: string, data: any }`.
- Reconnection: backoff exponencial (1s, 2s, 4s, máx 30s). Ao reconectar, reenviar o token JWT no query string.
- Aceite: portal conecta, recebe eventos de todos os canais, reconecta com backoff se cair.

### 10.12 Integração GitHub
- Leitura de PRs/issues (integração da mochila do agente, seção 8 da spec). UI: listar PRs/issues num painel do agente.
- Aceite: PRs/issues aparecem na mochila do agente.

## Critérios de aceite (DoD)

- [ ] Todas as views do protótipo estão implementadas e funcionais
- [ ] Navegação entre views funciona (sidebar)
- [ ] Tema dark/light persiste
- [ ] Dashboard mostra agentes reais (da API)
- [ ] Flow Editor cria e salva pipelines
- [ ] Monitor mostra execução em tempo real
- [ ] Approvals permite responder
- [ ] Skills/Tools/MCP/Knowledge: CRUD via UI
- [ ] WebSocket conecta e recebe eventos
- [ ] GitHub: PRs/issues aparecem na mochila do agente

## Contratos de interface (o que consome dos outros)

- **D3:** `types.ts` (todos os tipos), `api.ts` (client autenticado), `websocket.ts` (conexão + canais).
- **D4:** `AgentChat.tsx`, `AgentPreview.tsx`, tipo `Agent`.
- **D5:** `FlowEditor.tsx`, `EdgePanel.tsx`, tipo `Pipeline`/`PipelineEdge`.
- **D6:** `PipelineMonitor.tsx`, canais `pipeline:*`.
- **D7:** `ApprovalPanel.tsx`, canais `approval:*`.
- **D8:** `SkillsLibrary.tsx`, `ToolsEditor.tsx`, `MCPServersLibrary.tsx`.
- **D9:** `KnowledgeView.tsx`, tipo `KnowledgeBase`/`RivvnConnection`.

## Riscos

- **React Flow performance:** com muitos nós, virtualização/lazy loading (risco anotado no plano).
- **Integração de componentes distribuídos:** cada view consome um componente de outro domínio. Se um back-end não estiver pronto, a view fica incompleta. Coordenar com D4–D9.
- **WebSocket centralizado:** um ponto de falha — se a conexão cair, todas as views perdem tempo real. Reconnect robusto.

## Nota sobre o protótipo

- Basear a UI no protótipo `prototype/agent-portal.html` (estrutura, cores dark, layout). Seguir as regras do projeto: **sem emojis** (usar SVGs Lucide-style), **todos os menus/botões funcionam** (sem links mortos ou telas fake).
