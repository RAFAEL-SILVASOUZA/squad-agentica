# Agent Portal — Especificação de Arquitetura

> **Data:** 2026-09-17
> **Status:** Draft para revisão
> **Autor:** Rafael (com apoio de IA)

---

## 1. Visão

Portal visual para **design, execução e monitoramento de pipelines de agentes de IA**. O usuário monta um "squad agêntico" conectando agentes em um grafo de fluxo, define suas capacidades (skills, knowledge, integrações) e acompanha a execução em tempo real. Humanos entram no fluxo onde necessário (aprovação, revisão, argumentação).

### Princípios

- **O portal é o designer.** A UI é a fonte de verdade da pipeline.
- **Agentes têm contrato.** Entrada, saída e ações são declarados, validados no wiring.
- **Falha não é perda.** Checkpoints no PostgreSQL permitem retomar de onde parou.
- **Humano é parte do grafo.** Não é exceção, é um nó com canal de notificação configurável.
- **Flexibilidade com guarda-corpos.** Agentes custom via chat, mas o contrato impede wiring inválido.

---

## 2. Arquitetura de Alto Nível

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PORTAL (Next.js)                            │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Cards de │  │ Editor de    │  │ Chat de   │  │ Monitor de   │  │
│  │ Agentes  │  │ Fluxo (grafo)│  │ Construção│  │ Execução     │  │
│  └──────────┘  └──────────────┘  └───────────┘  └──────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Human-in-the-Loop: aprovações, notificações, argumentação   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ REST + WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ORQUESTRADOR (Python + FastAPI)                  │
│                                                                     │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │ Compiler   │  │ Runtime      │  │ Notification Service       │  │
│  │ JSON →     │  │ LangGraph    │  │ (Email, Teams, Slack,      │  │
│  │ StateGraph │  │ Execution    │  │  In-App)                   │  │
│  └────────────┘  └──────────────┘  └────────────────────────────┘  │
│                                                                     │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │ Skill      │  │ Knowledge    │  │ Checkpoint Manager         │  │
│  │ Registry   │  │ (RAG +       │  │ (PostgresSaver)            │  │
│  │            │  │  Vector DB)  │  │                            │  │
│  └────────────┘  └──────────────┘  └────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                                  │
│  • Checkpoints de execução (LangGraph)                              │
│  • Estado dos agentes                                               │
│  • Definições de pipelines (grafo JSON)                             │
│  • Histórico de conversas                                           │
│  • Skills e knowledge bases                                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Vector DB (RAG)                                │
│  • pgvector (PostgreSQL) ou Qdrant                                  │
│  • Embeddings de artefatos, docs, knowledge bases                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Frontend | Next.js 14+ (App Router) + React | SSR, DX, ecossistema de componentes |
| Editor de fluxo | React Flow (ou XYFlow) | Grafo interativo, drag-and-drop, linhas conectoras |
| Backend | Python 3.11+ / FastAPI | Assíncrono, compatível com ecossistema AI |
| Orquestração | LangGraph | Checkpoints, human-in-the-loop, loops nativos |
| Banco | PostgreSQL 15+ | Transacional, pgvector para RAG |
| Vector DB | pgvector (inicial) → Qdrant (escala) | Começa simples, escala quando necessário |
| WebSocket | FastAPI WebSocket + Socket.IO (frontend) | Tempo real: status de agentes, notificações |
| Auth | NextAuth.js (portal) + JWT (API) | NextAuth.js (portal) emite JWT via route handler. O frontend envia o JWT no header Authorization para chamar a API Python. O Python valida o JWT com a mesma secret. Sessão do NextAuth é o source of truth; o JWT é um token de delegação para a API. |
| Deploy (V1) | Docker Compose local | Portal + Python + Postgres em containers |

---

## 4. Modelo de Dados

### 4.1 Agente (contrato)

```typescript
interface Agent {
  id: string;
  ownerId: string;           // V1: single-user, ownerId é fixo. V2: multi-tenant.
  name: string;
  type: AgentType;           // "planner" | "developer" | "reviewer" | "deployer" | "custom"
  description: string;
  
  // Definição via chat (prompt + estratégia)
  prompt: string;
  strategy: string;          // passo a passo, abordagem
  
  // Capacidades
  skills: SkillRef[];        // skills da biblioteca
  knowledge: KnowledgeRef[]; // bases de conhecimento
  integrations: IntegrationRef[]; // "mochila": Azure, GitHub, GitLab, etc.
  
  // Contrato de fluxo
  inputs: PortDef[];         // o que PRECISA receber
  outputs: PortDef[];        // o que PODE produzir
  actions: FlowAction[];     // "follow" | "return" | "finalize"
  
  // Configuração de execução
  model: string;             // modelo de IA (gpt-4, claude, etc.)
  maxIterations: number;     // limite de execuções deste agente POR CICLO (A→B→A conta como 1 ciclo)
  timeout: number;           // timeout em segundos
  
  // Human-in-the-loop
  requiresApproval: boolean;
  approvalChannel: NotificationChannel; // "in-app" | "email" | "teams" | "slack"
  approvalMessage: string;   // template da notificação
}

type AgentType = "planner" | "developer" | "reviewer" | "deployer" | "custom";

interface PortDef {
  name: string;              // "plano_aprovado", "code_pronto"
  type: string;              // "document" | "code" | "artifact" | "signal"
  required: boolean;
}

type FlowAction = "follow" | "return" | "finalize";

interface SkillRef {
  skillId: string;
  config: Record<string, any>;
}

interface KnowledgeRef {
  source: "upload" | "vector-db" | "url";
  reference: string;         // path, collection name, ou URL
}

interface IntegrationRef {
  platform: "azure" | "github" | "gitlab" | "azure-devops" | "email" | "custom";
  config: Record<string, any>; // credentials ref, scopes, etc.
}
```

### 4.2 Pipeline (grafo)

```typescript
interface Pipeline {
  id: string;
  ownerId: string;           // V1: single-user, ownerId é fixo. V2: multi-tenant.
  name: string;
  description: string;
  status: "draft" | "running" | "paused" | "completed" | "failed";
  entryNodeId: string;       // O nó de entrada é explícito. O compiler não infere.
  
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  
  // Execução
  currentCheckpoint: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

interface PipelineNode {
  agentId: string;           // referência ao agente
  position: { x: number; y: number }; // layout no portal
  label?: string;            // override de nome no grafo
  agentSnapshot: AgentSnapshot; // cópia imutável do agente no momento da execução
}

interface AgentSnapshot {
  agentId: string;
  version: number;
  prompt: string;
  skills: SkillRef[];
  knowledge: KnowledgeRef[];
  integrations: IntegrationRef[];
  inputs: PortDef[];
  outputs: PortDef[];
  actions: FlowAction[];
  model: string;
  maxIterations: number;
  timeout: number;
  requiresApproval: boolean;
  approvalChannel: NotificationChannel;
}

// O snapshot é congelado quando a pipeline inicia. Edições no agente não afetam execuções em andamento.

interface PipelineEdge {
  id: string;
  source: string;            // agentId de origem
  target: string;            // agentId de destino
  condition?: EdgeCondition; // structured, not free string
  label?: string;            // "aprovado" | "reprovado" | "seguir"
  requiresApproval: boolean; // se true, a transição por esta aresta passa por humano (default: false)
}

interface EdgeCondition {
  field: "action" | "status" | "output";  // whitelist de campos
  operator: "eq" | "neq" | "in" | "not_in";
  value: string | string[];  // quando field === "action", value deve ser FlowAction | FlowAction[]
}

// String livre é proibida. O compiler valida field contra a whitelist acima, operador contra a union,
// e value contra FlowAction quando field === "action". Nunca eval.
```

### 4.3 Checkpoint

```typescript
interface Checkpoint {
  id: string;
  pipelineId: string;
  nodeId: string;            // agente que gerou
  state: Record<string, any>; // estado completo do grafo nesse ponto
  timestamp: string;
  status: "completed" | "interrupted" | "failed";
  metadata: Record<string, any>;
}
```

### 4.4 Skill

```typescript
interface Skill {
  id: string;
  name: string;
  description: string;
  category: "code" | "docs" | "infra" | "communication" | "analysis";
  
  // Implementação
  type: "prompt" | "tool" | "function";
  definition: SkillDefinition; // discriminated union por tipo
  
  // Metadados
  inputs: PortDef[];
  outputs: PortDef[];
  requiredIntegrations: string[]; // plataformas que precisa ter
}

type SkillDefinition =
  | { type: "prompt"; template: string; variables: string[] }
  | { type: "tool"; schema: Record<string, any>; endpoint: string }
  | { type: "function"; module: string; functionName: string; args: string[] };
```

### 4.5 Notificação / Aprovação

```typescript
interface ApprovalRequest {
  id: string;
  pipelineId: string;
  agentId: string;
  checkpointId: string;
  
  // Conteúdo
  message: string;
  context: Record<string, any>; // o que o agente produziu até aqui
  artifacts?: string[];         // links para artefatos (print, doc, code)
  
  // Resposta
  status: "pending" | "approved" | "rejected" | "revised";
  response?: string;            // argumento do humano
  respondedBy?: string;
  respondedAt?: string;
  
  // Canal
  channel: NotificationChannel;
  sentAt: string;
  
  // Retry / Fallback
  retryCount: number;
  maxRetries: number;
  attemptedChannels: NotificationChannel[];
  fallbackChannel: NotificationChannel | null;
  timeoutSeconds: number;
}
```

---

## 5. Fluxo de Execução

### 5.1 Ciclo de vida de uma pipeline

```
[Portal: salvar grafo]
        │
        ▼
[API: POST /pipelines/:id/execute]
        │
        ▼
[Compiler: JSON → LangGraph StateGraph]
        │
        ▼
[Runtime: iniciar execução]
        │
        ├──→ Agente 1 executa
        │       │
        │       ├──→ Salva checkpoint
        │       │
        │       ├──→ Decide ação: follow / return / finalize
        │       │
        │       ├──→ Se "follow": próximo nó
        │       ├──→ Se "return": nó anterior (loop)
        │       └──→ Se "finalize": encerra pipeline
        │
        ├──→ Se requiresApproval:
        │       │
        │       ├──→ interrupt() (pausa o grafo)
        │       ├──→ Envia notificação (canal configurado)
        │       ├──→ Aguarda resposta humana
        │       │       ├──→ approved: retoma
        │       │       ├──→ rejected: encerra ou devolve
        │       │       └──→ revised: retoma com feedback
        │       └──→ Salva checkpoint da decisão
        │
        └──→ Pipeline completa / falhou
                │
                ▼
[Portal: notificação via WebSocket]
```

### 5.2 Loops entre agentes

```
Agente A (Developer) ──[code_pronto]──→ Agente B (Reviewer)
                                              │
                          ┌───────────────────┤
                          │                   │
                     [aprovado]          [reprovado]
                          │                   │
                          ▼                   ▼
                     Agente C (Deploy)    Agente A (Developer)
                                         (com feedback do Reviewer)
```

O loop é controlado por:
- **Aresta condicional:** `condition: "action == 'return'"`
- **Limite de iterações:** `maxIterations` no agente (anti-loop-infinito)
- **Checkpoint:** cada volta salva estado, não perde contexto

maxIterations conta execuções do agente isoladamente dentro de um ciclo. Se o agente A executa 5 vezes seguidas (mesmo que alternando com B), o ciclo é abortado. O limite é por agente, não por ciclo global.

### 5.3 Human-in-the-loop

O humano é um **nó especial** no grafo. Quando o agente atinge um ponto de aprovação:

1. LangGraph `interrupt()` pausa a execução
2. O orquestrador cria um `ApprovalRequest`
3. Notificação é enviada via canal configurado:
   - **In-app:** WebSocket → badge no portal + tela de aprovação
   - **Email:** template com link para o portal
   - **Teams/Slack:** mensagem com botões (aprovar/rejeitar/revise)
4. Humano responde (aprova, rejeita, ou argumenta)
5. Resposta é injetada no estado do grafo
6. LangGraph retoma a execução

O humano pode:
- **Aprovar:** fluxo segue
- **Rejeitar:** fluxo devolve ao agente anterior ou encerra
- **Argumentar/Revisar:** feedback é adicionado ao contexto, agente retoma com a informação

---

## 6. Sistema de Skills

### 6.1 Conceito

Skills são **capacidades reutilizáveis** que um agente pode ter. Pense como "ferramentas" que o agente pode usar durante sua execução.

### 6.2 Tipos de skill

| Tipo | Descrição | Exemplo |
|------|-----------|---------|
| `prompt` | Template de prompt especializado | "Revisar código com foco em segurança" |
| `tool` | Ferramenta que o agente pode chamar (function calling) | "Criar PR no GitHub", "Deploy no Azure" |
| `function` | Função Python custom | "Calcular complexidade ciclomática" |

### 6.3 Biblioteca

A biblioteca de skills é um **registro central** no PostgreSQL. Skills podem ser:
- **Sistema:** vêm com a plataforma (code-gen, test-runner, doc-writer)
- **Custom:** criadas pelo usuário via chat

### 6.4 Associação

Um agente referencia skills por ID. A configuração é por agente (ex: mesma skill "deploy" com configs diferentes para staging vs produção).

---

## 7. Knowledge Base / RAG

### 7.1 Fontes

| Fonte | Descrição |
|-------|-----------|
| Upload | Usuário faz upload de PDFs, docs, código |
| Vector DB pré-existente | Collection já indexada (Qdrant, pgvector) |
| URL | Documento público indexado |

### 7.2 Fluxo

```
[Upload/URL] → [Chunking] → [Embedding] → [Vector DB]
                                              │
[Agente executa] → [Query] → [Similarity Search] → [Top-K chunks]
                                              │
                                              ▼
                                    [Injetado no prompt do agente]
```

### 7.3 Escopo

Knowledge base pode ser:
- **Global:** disponível para todos os agentes da pipeline
- **Por agente:** específico de um agente
- **Por pipeline:** compartilhado entre agentes de uma pipeline

---

## 8. Integrações ("Mochila" do Agente)

Cada agente pode ter conexões com plataformas externas:

| Plataforma | O que faz |
|-----------|-----------|
| Azure | Deploy, monitoramento, recursos |
| GitHub | PRs, issues, code review, CI/CD |
| GitLab | MRs, issues, pipelines |
| Azure DevOps | Repos, builds, releases |
| Email | Enviar/receber emails |
| Custom | Webhook, API REST |

As integrações são **referenciadas** pelo agente, não embutidas. As credenciais ficam em um secrets manager (env vars na V1, Azure Key Vault na V2).

---

## 9. API (Visão Geral)

### 9.1 Portal → Orquestrador

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/pipelines` | Criar pipeline (grafo JSON) |
| GET | `/api/pipelines/:id` | Obter pipeline + estado |
| PUT | `/api/pipelines/:id` | Atualizar grafo |
| POST | `/api/pipelines/:id/execute` | Iniciar execução |
| POST | `/api/pipelines/:id/pause` | Pausar execução |
| POST | `/api/pipelines/:id/resume` | Retomar (de checkpoint) |
| POST | `/api/pipelines/:id/stop` | Encerrar |
| GET | `/api/pipelines/:id/checkpoints` | Listar checkpoints |
| POST | `/api/pipelines/:id/checkpoints/:cpId/resume` | Retomar de checkpoint específico |

### 9.2 Agentes

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/agents` | Criar agente |
| GET | `/api/agents/:id` | Obter agente |
| PUT | `/api/agents/:id` | Atualizar agente |
| DELETE | `/api/agents/:id` | Remover agente |
| POST | `/api/agents/:id/chat` | Chat de construção (streaming) |

### 9.3 Skills & Knowledge

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/skills` | Listar skills da biblioteca |
| POST | `/api/skills` | Criar skill custom |
| POST | `/api/knowledge/upload` | Upload de artefato |
| POST | `/api/knowledge/query` | Query na knowledge base |

### 9.4 Aprovações

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/approvals?status=pending` | Listar aprovações pendentes |
| POST | `/api/approvals/:id/respond` | Responder (aprovar/rejeitar/revisar) |

### 9.5 WebSocket

| Canal | Direção | Payload |
|-------|---------|---------|
| `pipeline:status` | Server → Client | Status de cada nó em tempo real |
| `pipeline:log` | Server → Client | Logs de execução |
| `approval:new` | Server → Client | Nova aprovação pendente |
| `approval:resolved` | Server → Client | Aprovação respondida |
| `agent:output` | Server → Client | Output do agente (streaming) |

---

## 10. Chat de Construção de Agentes

### 10.1 Fluxo

```
[Usuário clica "Criar Agente" no portal]
        │
        ▼
[Chat abre com IA assistente]
        │
        ├── Usuário: "Quero um agente que faz code review de Python"
        │
        ├── IA: "Entendi. Vou te ajudar a montar. Qual o foco da review?"
        │       "Segurança, performance, estilo, ou tudo?"
        │
        ├── Usuário: "Tudo, mas com foco em segurança"
        │
        ├── IA: "Perfeito. Sugiro:
        │       • Skills: code-analyzer, security-scanner
        │       • Knowledge: docs de segurança do projeto
        │       • Integração: GitHub (para ler PRs)
        │       • Contrato: recebe 'code_pronto', produz 'review_aprovada' ou 'review_reprovada'
        │       Quer ajustar algo?"
        │
        ├── Usuário: "Pode adicionar integração com GitLab também"
        │
        ├── IA: "Feito. Aqui está o agente configurado: [resumo]
        │       Quer salvar?"
        │
        └── [Salvar] → Agente criado, aparece como card no portal
```

### 10.2 O que a IA faz no chat

- Entende a intenção do usuário
- Sugere skills, knowledge e integrações apropriadas
- Define o contrato (inputs/outputs/actions)
- Gera o prompt do agente
- Valida que o contrato é coerente
- Permite iteração (ajustes)

---

## 11. Estrutura de Repositórios

```
agent-portal/                    # Frontend (Next.js)
├── app/
│   ├── (dashboard)/
│   │   ├── page.tsx            # Grid de agentes (cards)
│   │   ├── pipelines/
│   │   │   ├── [id]/page.tsx   # Editor de fluxo
│   │   │   └── [id]/run/page.tsx  # Monitor de execução
│   │   └── agents/
│   │       ├── new/page.tsx    # Chat de construção
│   │       └── [id]/page.tsx   # Detalhe/editar agente
│   ├── (auth)/
│   └── api/                    # Route handlers (proxy p/ backend)
├── components/
│   ├── AgentCard.tsx
│   ├── FlowEditor.tsx          # React Flow wrapper
│   ├── AgentChat.tsx           # Chat de construção
│   ├── ApprovalPanel.tsx       # Human-in-the-loop
│   ├── SkillsLibrary.tsx
│   └── PipelineMonitor.tsx
├── lib/
│   ├── api.ts                  # Client da API
│   ├── websocket.ts            # Conexão WebSocket
│   └── types.ts                # Tipos compartilhados
└── package.json

agent-orchestrator/              # Backend (Python)
├── app/
│   ├── main.py                 # FastAPI app
│   ├── api/
│   │   ├── pipelines.py
│   │   ├── agents.py
│   │   ├── skills.py
│   │   ├── knowledge.py
│   │   └── approvals.py
│   ├── compiler/
│   │   ├── graph_builder.py    # JSON → LangGraph StateGraph
│   │   ├── validator.py        # Valida grafo (ciclos, ports)
│   │   └── state.py            # Definição do State
│   ├── runtime/
│   │   ├── executor.py         # Executa o grafo
│   │   ├── checkpoint.py       # Gerencia checkpoints
│   │   └── interrupt.py        # Human-in-the-loop
│   ├── agents/
│   │   ├── base.py             # Classe base do agente
│   │   ├── planner.py
│   │   ├── developer.py
│   │   ├── reviewer.py
│   │   └── deployer.py
│   ├── skills/
│   │   ├── registry.py
│   │   ├── loader.py
│   │   └── builtins/           # Skills de sistema
│   ├── knowledge/
│   │   ├── rag.py
│   │   ├── chunker.py
│   │   └── embedder.py
│   ├── notifications/
│   │   ├── base.py
│   │   ├── email.py
│   │   ├── teams.py
│   │   ├── slack.py
│   │   └── inapp.py            # WebSocket push
│   ├── db/
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── migrations/         # Alembic
│   │   └── session.py
│   └── config.py
├── tests/
├── alembic.ini
├── pyproject.toml
└── Dockerfile

docker-compose.yml               # Portal + Orchestrator + Postgres
```

---

## 12. Decisões de Arquitetura (ADR)

### ADR-001: LangGraph como orquestrador

**Decisão:** Usar LangGraph para orquestração de agentes.

**Alternativas consideradas:**
- CrewAI: menos controle fino de loops e checkpoints
- Orquestração custom: muito trabalho, reinventa a roda
- AutoGen: foco em multi-agent conversation, não em pipeline com checkpoints

**Razão:** LangGraph oferece checkpoints nativos (PostgresSaver), human-in-the-loop (interrupt), e grafo com arestas condicionais. É o framework que mais se alinha com o modelo de pipeline com loops e aprovação humana.

### ADR-002: Contrato de entrada/saída nos agentes

**Decisão:** Cada agente declara inputs, outputs e actions. O portal valida o wiring.

**Alternativas consideradas:**
- Grafo livre (sem contrato): flexível mas propenso a erros
- Tipos fixos (sem custom): controlado mas rígido

**Razão:** O contrato é barato de implementar e elimina a maior classe de erros (wiring inválido). Mantém flexibilidade porque o conteúdo do port é livre, só o nome/tipo é validado.

### ADR-003: pgvector antes de Qdrant

**Decisão:** Começar com pgvector (extensão do PostgreSQL), migrar para Qdrant se necessário.

**Alternativas consideradas:**
- Qdrant desde o início: mais performático, mas mais infra
- Weaviate: bom, mas mais uma dependência

**Razão:** Na V1 local, menos containers é melhor. pgvector resolve para volumes de knowledge base de projeto. Se a escala exigir (milhões de chunks), Qdrant é o upgrade natural.

### ADR-004: Separação de repositórios

**Decisão:** Portal (Next.js) e Orquestrador (Python) em repositórios separados.

**Alternativas consideradas:**
- Monorepo: versionamento conjunto, mas stacks muito diferentes
- Monolito: inviável, linguagens diferentes

**Razão:** Ciclos de deploy diferentes, stacks diferentes, times diferentes (frontend vs backend/AI). A comunicação é via API bem definida.

### ADR-005: Docker Compose para V1

**Decisão:** Docker Compose com 3 serviços (portal, orchestrator, postgres).

**Alternativas consideradas:**
- Kubernetes: overkill para V1 local
- Sem Docker: dependências de Python + Node + Postgres são pesadas

**Razão:** Um `docker-compose up` sobe tudo. Simples, reproduzível, e a migração para Azure AKS na V2 é direta.

---

## 13. Escopo V1

### Incluído

- [ ] Portal: grid de agentes (cards), CRUD
- [ ] Portal: editor de fluxo (React Flow) com validação de contrato
- [ ] Portal: chat de construção de agentes (streaming)
- [ ] Portal: monitor de execução em tempo real (WebSocket)
- [ ] Portal: painel de aprovações (human-in-the-loop)
- [ ] Portal: biblioteca de skills (listar, associar)
- [ ] Backend: API REST completa
- [ ] Backend: compiler JSON → LangGraph
- [ ] Backend: runtime com checkpoints (PostgresSaver)
- [ ] Backend: human-in-the-loop (interrupt + notificação)
- [ ] Backend: sistema de skills (registry + loader)
- [ ] Backend: RAG básico (upload → chunk → embed → query)
- [ ] Backend: notificações (in-app via WebSocket, email)
- [ ] Tipos base de agentes: planner, developer, reviewer, deployer
- [ ] Docker Compose (portal + orchestrator + postgres)
- [ ] Integração: GitHub (leitura de PRs/issues)

### Fora de escopo V1 (V2+)

- [ ] Integração: Azure, GitLab, Azure DevOps, Slack, Teams
- [ ] Multi-tenant
- [ ] Auth avançada (RBAC, SSO)
- [ ] Versionamento de pipelines
- [ ] Templates de pipeline
- [ ] Métricas e analytics
- [ ] Deploy em nuvem (Azure AKS)
- [ ] Skills custom via code (function calling com código)
- [ ] Agente "meta" que sugere melhorias no pipeline

---

## 14. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Loop infinito entre agentes | Pipeline nunca termina | `maxIterations` por agente + timeout global |
| Grafo inválido (ciclo sem saída) | Pipeline trava | Validador no compiler (detecção de ciclos, nós órfãos) |
| Checkpoint corrompido | Não consegue retomar | Checkpoint imutável + snapshot periódico |
| LLM alucina no chat de construção | Agente mal configurado | Validação de contrato + preview antes de salvar |
| Knowledge base muito grande | RAG lento | Chunking inteligente + limit de top-K + cache |
| Notificação não chega | Humano não aprova, pipeline trava | Retry + timeout + fallback para outro canal |

---

## 15. Próximos Passos

1. **Revisar esta especificação** (você + gestor)
2. **Definir o protótipo visual** (design do portal)
3. **Escrever o implementation plan** (fases, sprints, entregas)
4. **Scaffold dos repositórios** (estrutura base, Docker, CI)
5. **Implementar em fases:**
   - Fase 1: Backend (API + compiler + runtime básico)
   - Fase 2: Portal (cards + editor de fluxo)
   - Fase 3: Chat de construção + Skills
   - Fase 4: Human-in-the-loop + Notificações
   - Fase 5: RAG + Knowledge
   - Fase 6: Integrações (GitHub)
   - Fase 7: Polish + Docker Compose + Docs

---

## 16. Decisões de Design

- **Return policy:** configurável por edge. Cada `PipelineEdge` tem `requiresApproval: boolean` (campo presente na interface, seção 4.2). Se `true`, a transição por aquela aresta passa por aprovação humana. Se `false` (default), é autônoma. Isso vale para qualquer aresta, incluindo as de `return`.
