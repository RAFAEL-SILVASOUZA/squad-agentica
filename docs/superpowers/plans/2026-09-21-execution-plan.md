# Agent Portal — Plano de Execução por Domínio

> **Data:** 2026-09-21
> **Base:** Spec `2026-09-17-agent-portal-design.md` + protótipo `prototype/agent-portal.html`
> **Stack:** Next.js 14 (portal) · Python 3.11 / FastAPI (orquestrador + workers) · PostgreSQL 15 + pgvector · LangGraph · MinIO (object storage) · NGINX (reverse proxy + LB) · Docker Compose

---

## Visão Geral

O projeto é decomposto em **10 domínios** com dependências explícitas. A ordem de execução segue o grafo de dependências abaixo. Domínios independentes podem ser trabalhados em paralelo após suas dependências estarem prontas.

```
D1 ──→ D2 ──→ D3 ──→ D4 ──→ D5 ──→ D6
 │       │       │       │       │       ▲
 │       │       │       │       │       │
 │       │       │       └──→ D8 ────────┘
 │       │       └───────────────┤
 │       └───────────────────────┤
 └───────────────────────────────┘
```

| Domínio | Escopo | Dependências |
|---------|--------|--------------|
| D1 | Infraestrutura & Setup | — |
| D2 | Autenticação & Segurança | D1 |
| D3 | Modelo de Dados & API Base | D1, D2 |
| D4 | Agentes (CRUD + Contrato) | D3 |
| D5 | Pipeline (Grafo + Compiler) | D4 |
| D6 | Runtime & Orquestração | D5, D8 |
| D7 | Human-in-the-Loop & Notificações | D6 |
| D8 | Capacidades (Skills + Tools + MCP) | D4 |
| D9 | Knowledge & RAG | D3 |
| D10 | Portal Frontend (Next.js) | D3, D4, D5, D6, D7, D8, D9 |

---

## D1 — Infraestrutura & Setup

**Objetivo:** Ambiente local funcional com `docker-compose up` subindo os 6 serviços.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 1.1 | `docker-compose.yml` | 6 serviços: `nginx`, `portal` (Next.js), `orchestrator` (FastAPI), `agent-worker` (pool), `postgres` (Postgres 15 + pgvector), `minio` (object storage) |
| 1.2 | `Dockerfile` orchestrator | Python 3.11, uv/pip, alembic, healthcheck |
| 1.3 | `Dockerfile` portal | Node 20, Next.js build, healthcheck |
| 1.4 | Postgres init | Script de init: criar extensão `vector`, criar DB `agent_portal` |
| 1.5 | Configuração de ambiente | `.env.example` com todas as vars: `DATABASE_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `RIVVN_*`, `MINIO_*` |
| 1.6 | Estrutura de repositórios | `agent-portal/` (Next.js) + `agent-orchestrator/` (Python) + `docker-compose.yml` na raiz |
| 1.7 | CI básico (opcional) | Lint + type-check + test em PR |
| 1.8 | `nginx.conf` | Reverse proxy + load balancer. Rota: `/` → portal, `/api/*` → orchestrator, `/workers/*` → agent-worker pool (round-robin). WebSocket upgrade. |
| 1.9 | `Dockerfile` agent-worker | Python 3.11, FastAPI, MinIO S3 client, healthcheck. Stateless. |
| 1.10 | MinIO init | Script de init: cria buckets `agents` e `skills`. Volume persistente `minio-data`. |

### Critérios de aceite
- [ ] `docker-compose up` sobe os 6 serviços sem erro
- [ ] Postgres acessível com extensão `vector` ativa
- [ ] FastAPI responde em `/health`
- [ ] Next.js responde em `/`
- [ ] `.env.example` documenta todas as variáveis
- [ ] NGINX responde em :80 e roteia corretamente para portal, API e workers
- [ ] MinIO acessível em :9001 com buckets `agents` e `skills` criados
- [ ] Agent-worker responde em /health

---

## D2 — Autenticação & Segurança

**Objetivo:** Autenticação funcional entre portal e API.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 2.1 | NextAuth.js (portal) | Provider: credentials (V1). Route handler emite JWT |
| 2.2 | JWT middleware (FastAPI) | Dependência `get_current_user` que valida o JWT no header `Authorization` |
| 2.3 | Secrets manager (V1) | Leitura de env vars para credenciais. Interface para V2 (Key Vault) |
| 2.4 | CORS | Configuração de CORS no FastAPI para o domínio do portal |

### Critérios de aceite
- [ ] Login no portal gera sessão NextAuth
- [ ] Route handler emite JWT válido
- [ ] API Python rejeita request sem JWT (401)
- [ ] API Python aceita request com JWT válido
- [ ] Credenciais nunca aparecem em logs

---

## D3 — Modelo de Dados & API Base

**Objetivo:** Schema do banco + API REST base + tipos compartilhados.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 3.1 | SQLAlchemy models | `Agent`, `Pipeline`, `PipelineNode`, `PipelineEdge`, `PipelineRun`, `Checkpoint`, `Skill`, `CustomTool`, `MCPServer`, `KnowledgeBase`, `KnowledgeDocument`, `ApprovalRequest`, `RivvnConnection`, `Integration`, `Artifact` |
| 3.2 | Alembic migrations | Migration inicial com todo o schema |
| 3.3 | API base (FastAPI) | Routers vazios com endpoints stubs para todos os recursos da spec (seção 9) |
| 3.4 | Tipos TypeScript | `lib/types.ts` no portal com todas as interfaces da spec (Agent, Pipeline, PipelineNode, PipelineEdge, etc.) |
| 3.5 | API client | `lib/api.ts` no portal: wrapper fetch com JWT, error handling |
| 3.6 | WebSocket base | `lib/websocket.ts` no portal: conexão, reconnect, canais |

### Critérios de aceite
- [ ] Migrations rodam limpo (`alembic upgrade head`)
- [ ] Todos os endpoints da spec (seção 9) respondem (stub 200/501)
- [ ] Tipos TypeScript compilam sem erro
- [ ] API client faz request autenticado com sucesso

---

## D4 — Agentes (CRUD + Contrato)

**Objetivo:** CRUD completo de agentes com validação de contrato, com artefato (.yml) persistido no MinIO.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 4.1 | CRUD de agentes (API) | `POST/GET/PUT/DELETE /api/agents` com validação de contrato, com persistência do .yml no MinIO (S3 API) |
| 4.2 | Validação de contrato | `inputs`, `outputs`, `actions` validados: nomes únicos, tipos válidos, actions ∈ {follow, return, finalize} |
| 4.3 | Agent base (Python) | `agents/base.py`: classe base que recebe `AgentSnapshot`, monta prompt, chama LLM, retorna output |
| 4.4 | Agentes built-in | `planner.py`, `developer.py`, `reviewer.py`, `deployer.py` — subclasses com prompt default |
| 4.5 | Chat de construção (API) | `POST /api/agents/:id/chat` — streaming (SSE) com IA assistente que sugere skills, knowledge, integrações e contrato |
| 4.6 | Chat de construção (Portal) | `AgentChat.tsx` — UI de chat com streaming, sugestões estruturadas, preview do agente |
| 4.7 | Agent Storage | MinIO S3 client: save/get/delete do .yml do agente. Bucket `agents`. |

### Critérios de aceite
- [ ] CRUD de agentes funciona via API
- [ ] Contrato inválido é rejeitado com mensagem clara
- [ ] Chat de construção sugere configuração coerente
- [ ] Agente criado via chat aparece como card no portal
- [ ] Agent base executa e retorna output estruturado

---

## D5 — Pipeline (Grafo + Compiler)

**Objetivo:** Editor de grafo + compiler JSON → LangGraph StateGraph.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 5.1 | CRUD de pipelines (API) | `POST/GET/PUT /api/pipelines` com validação de grafo |
| 5.2 | Validador de grafo | Regras 1-11 da spec (seção 4.2): dataMapping válido, ports compatíveis, nós órfãos, ciclos, data edge implica flow, entryNodeId, actions warning, edges duplicadas |
| 5.3 | Compiler: JSON → StateGraph | `compiler/graph_builder.py`: converte `Pipeline` em `StateGraph` do LangGraph |
| 5.4 | Compiler: State | `compiler/state.py`: definição do `State` (TypedDict) com todos os ports de todos os agentes |
| 5.5 | Compiler: condições | `EdgeCondition` → função condicional do LangGraph (whitelist: field, operator, value) |
| 5.6 | Editor de fluxo (Portal) | `FlowEditor.tsx` com React Flow: drag-and-drop, conexões, painel de aresta (tipo, dataMapping, condition, requiresApproval) |
| 5.7 | Validação visual | Erros de contrato destacados no editor (arestas inválidas em vermelho, tooltip com motivo) |

### Critérios de aceite
- [ ] Grafo inválido é rejeitado pelo validador com mensagem específica
- [ ] Compiler gera StateGraph válido para grafo simples (A→B→C)
- [ ] Compiler trata data edge sem flow edge (regra 7: injeta flow edge implícita)
- [ ] Editor permite criar, conectar e configurar arestas
- [ ] Painel de aresta mostra tipo, dataMapping, condition, requiresApproval
- [ ] Validação visual destaca erros em tempo real

---

## D6 — Runtime & Orquestração

**Objetivo:** Execução de pipelines com checkpoints, delegando execução a workers via HTTP (NGINX LB).

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 6.1 | Executor | `runtime/executor.py`: inicia execução do StateGraph, delega execução de agentes ao worker pool via HTTP (NGINX), gerencia ciclo de vida |
| 6.2 | Checkpoint Manager | `runtime/checkpoint.py`: PostgresSaver do LangGraph, listagem, retomada |
| 6.3 | API de execução | `POST /pipelines/:id/execute`, `pause`, `resume`, `stop`, `GET /checkpoints` |
| 6.4 | maxIterations | Contador por agente, aborta ciclo se excedido |
| 6.5 | Timeout | Timeout por agente + timeout global da pipeline |
| 6.6 | Monitor de execução (Portal) | `PipelineMonitor.tsx`: status de nós em tempo real, logs, checkpoints, botão "Retomar" |
| 6.7 | WebSocket: pipeline:status | Server → Client: status de cada nó |
| 6.8 | WebSocket: pipeline:log | Server → Client: logs de execução |
| 6.9 | WebSocket: agent:output | Server → Client: output do agente (streaming) |
| 6.10 | Worker Client | HTTP client pro agent-worker via NGINX. Retry com backoff. Timeout por request. |
| 6.11 | Agent Worker | Container stateless: POST /execute. Baixa .yml/.md do MinIO, executa agente, retorna output. |
| 6.12 | MinIO Client (worker) | S3 client no worker: download de agent .yml e skills .md. |

### Critérios de aceite
- [ ] Pipeline simples (A→B→C) executa de ponta a ponta
- [ ] Checkpoint salvo a cada nó
- [ ] Retomada de checkpoint funciona
- [ ] maxIterations aborta loop infinito
- [ ] Timeout encerra agente que demora demais
- [ ] Monitor mostra status em tempo real via WebSocket
- [ ] Logs aparecem no monitor em tempo real
- [ ] Worker executa agente e retorna output ao orchestrator via HTTP
- [ ] Retry funciona: worker down → orchestrator tenta outro worker

---

## D7 — Human-in-the-Loop & Notificações

**Objetivo:** Aprovações humanas no fluxo + notificações multi-canal.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 7.1 | Approval node function | `runtime/approval_node.py`: função do nó de aprovação (gerado pelo D5) que chama `interrupt()` do LangGraph e, ao retomar, retorna `Command(goto=...)` |
| 7.2 | ApprovalRequest | Criação, persistência e listagem de `ApprovalRequest` |
| 7.3 | API de aprovações | `GET /api/approvals?status=pending`, `POST /api/approvals/:id/respond` |
| 7.4 | Notificação: in-app | WebSocket push → badge no portal + tela de aprovação |
| 7.5 | Notificação: email | Template com link para o portal (SMTP) |
| 7.6 | Retry + fallback | `retryCount`, `maxRetries`, `fallbackChannel` — se canal principal falha, tenta fallback |
| 7.7 | Painel de aprovações (Portal) | `ApprovalPanel.tsx`: lista de aprovações pendentes, aprovar/rejeitar/argumentar |
| 7.8 | WebSocket: approval:new | Server → Client: nova aprovação pendente |
| 7.9 | WebSocket: approval:resolved | Server → Client: aprovação respondida |

### Critérios de aceite
- [ ] Edge com `requiresApproval: true` pausa a execução
- [ ] Notificação in-app chega via WebSocket
- [ ] Notificação email é enviada
- [ ] Humano aprova → execução retoma
- [ ] Humano rejeita → execução devolve ou encerra
- [ ] Humano argumenta → feedback injetado no estado, agente retoma
- [ ] Retry funciona: canal principal falha → fallback é tentado
- [ ] Painel de aprovações mostra pendentes e permite responder

---

## D8 — Capacidades (Skills + Tools Custom + MCP)

**Objetivo:** Mochila completa do agente: skills, tools custom, servidores MCP, com skills (.md) persistidas no MinIO.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 8.1 | Skill Registry | `skills/registry.py`: CRUD de skills no PostgreSQL, com conteúdo (.md) no MinIO |
| 8.2 | Skill Loader | `skills/loader.py`: carrega skill por tipo, baixa .md do MinIO, injeta no agente |
| 8.3 | Skills built-in | `skills/builtins/`: code-gen, test-runner, security-scanner, doc-writer, api-client, deploy-runner |
| 8.4 | Ferramentas básicas | `tools/builtins/`: read_file, write_file, edit_file, shell, web_search, web_fetch, glob, grep, list_directory |
| 8.5 | Tool Registry | `tools/registry.py`: CRUD de tools custom |
| 8.6 | Tool Sandbox | `tools/sandbox.py`: subprocesso isolado, timeout, sem acesso ao filesystem do host |
| 8.7 | Tool Validator | `tools/validator.py`: valida script Python + contrato de I/O |
| 8.8 | API de tools custom | `GET/POST/PUT/DELETE /api/tools`, `POST /api/tools/:id/deploy`, `POST /api/tools/:id/test` |
| 8.9 | Editor de tools (Portal) | `ToolsEditor.tsx`: script Python + parâmetros de I/O + deploy + teste |
| 8.10 | MCP Registry | `mcp/registry.py`: CRUD de servidores MCP |
| 8.11 | MCP Client | `mcp/client.py`: conecta via stdio/sse/http, chama `tools/list`, invoca tools |
| 8.12 | MCP Validator | `mcp/validator.py`: valida config de conexão |
| 8.13 | API de MCP servers | `GET/POST/PUT/DELETE /api/mcp-servers`, `POST /api/mcp-servers/:id/test` |
| 8.14 | Biblioteca MCP (Portal) | `MCPServersLibrary.tsx`: registrar, testar conexão, listar tools descobertas |
| 8.15 | Biblioteca de Skills (Portal) | `SkillsLibrary.tsx`: listar, associar a agentes |
| 8.17 | Skill Storage | MinIO S3 client: save/get/delete do .md da skill. Bucket `skills`. |

### Critérios de aceite
- [ ] Skills built-in são carregadas e injetadas no prompt do agente
- [ ] Ferramentas básicas estão disponíveis em todo agente (read-only)
- [ ] Tool custom: criar → validar → deploy → testar → usar em agente
- [ ] Tool custom roda em sandbox (sem acesso ao host)
- [ ] MCP server: registrar → testar conexão → tools descobertas aparecem
- [ ] MCP server conectado a agente expõe tools na mochila
- [ ] Biblioteca de skills: listar e associar a agentes
- [ ] Editor de tools: script + I/O + deploy + teste

---

## D9 — Knowledge & RAG

**Objetivo:** Bases de conhecimento com RAG local (pgvector) + integração Rivvn.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 9.1 | Knowledge Base model | `KnowledgeBase` no PostgreSQL: nome, escopo (global/agent/pipeline), fonte |
| 9.2 | Upload + Chunking | `knowledge/chunker.py`: upload de PDFs/docs, chunking inteligente |
| 9.3 | Embedding | `knowledge/embedder.py`: geração de embeddings (OpenAI ou local) |
| 9.4 | RAG Query | `knowledge/rag.py`: similarity search no pgvector, top-K, injeção no prompt |
| 9.5 | API de knowledge | `POST /api/knowledge/upload`, `POST /api/knowledge/query` |
| 9.6 | Knowledge UI (Portal) | View Knowledge: sidebar de bases, upload, escopo, documentos |
| 9.7 | Rivvn: OAuth | `knowledge/rivvn/oauth.py`: authorization code flow (authorize/callback) |
| 9.8 | Rivvn: Client | `knowledge/rivvn/client.py`: wrapper do SDK do Rivvn (token + query) |
| 9.9 | Rivvn: Gate comercial | Validação de `contractStatus` antes de qualquer operação |
| 9.10 | Rivvn: API | `GET /api/integrations/rivvn/authorize`, `callback`, `status`, `DELETE` |
| 9.11 | Rivvn: UI (Portal) | Barra de conexão Rivvn, gate por contrato, escolha de collection |

### Critérios de aceite
- [ ] Upload de PDF → chunking → embedding → query retorna trechos relevantes
- [ ] Escopo (global/agent/pipeline) filtra quais agentes acessam a KB
- [ ] Rivvn: sem contrato → botão desabilitado, CTA de contato comercial
- [ ] Rivvn: com contrato → OAuth funciona, collection selecionada, query via SDK
- [ ] Rivvn: token expirado → erro tratável, agente decide como agir
- [ ] Rivvn: contrato expirado → conexão desativada, KB retorna erro

---

## D10 — Portal Frontend (Next.js)

**Objetivo:** Portal completo com todas as views do protótipo.

### Entregas

| # | Item | Detalhes |
|---|------|----------|
| 10.1 | Layout base | Topbar, sidebar, tema dark/light, navegação entre views |
| 10.2 | Dashboard (Agentes) | Grid de cards de agentes, stats strip, botão "Novo Agente" |
| 10.3 | Agent Detail | AgentChat.tsx + AgentPreview.tsx + config panel (identidade, ferramentas, integrações, skills, tools, MCP, contrato, execução) |
| 10.4 | Flow Editor | FlowEditor.tsx + EdgePanel.tsx: React Flow, drag-and-drop, conexões, painel de aresta, validação visual, zoom/pan/fit |
| 10.5 | Pipeline Monitor | Status de nós, logs em tempo real, checkpoints, botão "Retomar" |
| 10.6 | Approvals Panel | Lista de aprovações pendentes, aprovar/rejeitar/argumentar |
| 10.7 | Skills Library | Grid de skills, associar a agentes |
| 10.8 | Tools Custom | Grid de tools, editor (script + I/O + deploy + teste) |
| 10.9 | MCP Servers | Grid de servidores, detalhe (transporte, comando, env, tools descobertas) |
| 10.10 | Knowledge | KnowledgeView.tsx: sidebar de bases, upload, escopo, Rivvn bar |
| 10.11 | Integração WebSocket | Conexão persistente, reconnect, handlers para todos os canais |
| 10.12 | Integração GitHub | Leitura de PRs/issues (integração da mochila) |

### Critérios de aceite
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

---

## Ordem de Execução (Fases)

As fases agrupam domínios por dependência. Dentro de cada fase, os domínios podem ser paralelizados.

```
FASE 1 (Fundação)
├── D1: Infraestrutura & Setup
└── D2: Autenticação & Segurança

FASE 2 (Base de Dados & API)
└── D3: Modelo de Dados & API Base

FASE 3 (Núcleo)
├── D4: Agentes (CRUD + Contrato)
└── D9: Knowledge & RAG  ← independente de D4, depende de D3

FASE 4 (Orquestração)
├── D5: Pipeline (Grafo + Compiler)  ← depende de D4
└── D8: Capacidades (Skills + Tools + MCP)  ← depende de D4

FASE 5 (Execução)
└── D6: Runtime & Orquestração  ← depende de D5 e D8 (ambos devem estar concluídos)

FASE 6 (Humano no Loop)
└── D7: Human-in-the-Loop & Notificações  ← depende de D6

FASE 7 (Portal Completo)
└── D10: Portal Frontend (Next.js)  ← depende de tudo
```

> **Nota:** A FASE 1 agora inclui NGINX, MinIO e o scaffold do agent-worker. O worker é funcional a partir da FASE 5 (D6), mas o container sobe desde a FASE 1 com `/health`.

### Paralelismo possível

| Fase | Paralelo 1 | Paralelo 2 |
|------|-----------|-----------|
| FASE 1 | D1 (Infra) | D2 (Auth) |
| FASE 3 | D4 (Agentes) | D9 (Knowledge) |
| FASE 4 | D5 (Pipeline) | D8 (Capacidades) |

---

## Riscos por Domínio

| Domínio | Risco | Mitigação |
|---------|-------|-----------|
| D1 | MinIO single-instance: volume persistente, sem HA na V1 | Volume `minio-data`. Em V2, MinIO distributed ou S3 real. |
| D5 | Compiler: regra 7 (data edge implica flow) é sutil | Testes de unidade cobrindo todos os 11 casos de validação |
| D6 | LangGraph: checkpoint com State complexo (muitos ports) | State como TypedDict, testes de round-trip (save → load → resume) |
| D6 | Worker down durante execução: retry + checkpoint | 3 retries com backoff. Checkpoint anterior permite retomada. |
| D6 | Latência HTTP por nó do grafo | ~50-200ms overhead. Aceitável V1. Otimização: gRPC/queue. |
| D7 | Notificação: retry + fallback pode travar pipeline | Timeout global + fallback para in-app (sempre disponível) |
| D8 | Sandbox: subprocesso isolado pode ser frágil | Docker-in-Docker ou gVisor como fallback; timeout agressivo |
| D9 | Rivvn: SDK externo, contrato comercial | Mock do SDK para testes; gate de contrato antes de qualquer chamada |
| D10 | React Flow: performance com 44+ nós | Virtualização, lazy loading de nós distantes |
| D4 | Consistência Postgres+MinIO (agent sem artefato) | Transação compensatória: rollback Postgres se MinIO falhar. |

---

## Estimativa de Esforço (relativa)

| Domínio | Esforço | Justificativa |
|---------|---------|---------------|
| D1 | Médio | Docker Compose 6 serviços + NGINX config + MinIO init + worker scaffold |
| D2 | Baixo | NextAuth + JWT middleware, padrão conhecido |
| D3 | Médio | Schema completo + migrations + stubs |
| D4 | Médio | CRUD + validação + chat de construção (streaming) |
| D5 | Alto | Compiler JSON → StateGraph + validação de grafo + editor React Flow |
| D6 | Alto | Runtime LangGraph + worker client + worker container + checkpoints + WebSocket + monitor |
| D7 | Médio | Interrupt + notificações + painel de aprovações |
| D8 | Alto | 3 sub-sistemas (Skills, Tools, MCP) + sandbox + editor |
| D9 | Médio | RAG local + Rivvn OAuth + SDK |
| D10 | Alto | 10+ views, WebSocket, React Flow, integração com todas as APIs |

---

## Definição de Pronto (DoD) por Domínio

Cada domínio está "pronto" quando:
1. Todas as entregas da tabela estão implementadas
2. Todos os critérios de aceite estão verificados
3. Testes de unidade cobrem os casos principais
4. Não há dead code nem imports quebrados
5. O domínio integra com os domínios dependentes sem erro
