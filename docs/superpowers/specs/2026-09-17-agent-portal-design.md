# Agent Portal , Especificação de Arquitetura

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
  type: string;              // tipo livre definido pelo usuário (ex: "planner", "developer", "épico", "task")
  description: string;
  
  // Definição via chat (prompt + estratégia)
  prompt: string;
  strategy: string;          // passo a passo, abordagem
  
  // Capacidades (mochila)
  skills: SkillRef[];        // skills da biblioteca (prompt templates)
  tools: ToolRef[];          // tools custom (scripts Python do usuário)
  mcpServers: MCPServerRef[]; // servidores MCP conectados (seção 6.7)
  knowledge: KnowledgeRef[]; // bases de conhecimento
  integrations: IntegrationRef[]; // integrações: Azure, GitHub, GitLab, etc.
  
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

// AgentType não é enum fixa , o usuário cria o tipo de agente que quiser.
// Os tipos "planner", "developer", "reviewer", "deployer" são templates/sugestões,
// não restrições. O portal pode oferecer templates pré-definidos, mas o usuário
// pode criar qualquer tipo (ex: "épico", "história", "task", "qa").

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

interface ToolRef {
  toolId: string;
  config: Record<string, any>; // overrides de parâmetros default
}

interface MCPServerRef {
  serverId: string;
  toolFilter?: string[];     // opcional: subconjunto de tools do servidor a expor (default: todas)
}

interface KnowledgeRef {
  source: "upload" | "vector-db" | "url" | "rivvn";
  reference: string;         // path, collection name, URL, ou collectionId do Rivvn
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
  tools: ToolRef[];
  mcpServers: MCPServerRef[];
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
  type: EdgeType;            // "flow" | "data"
  source: string;            // agentId de origem
  target: string;            // agentId de destino
  condition?: EdgeCondition; // structured, not free string (apenas em edges de flow)
  label?: string;            // "aprovado" | "reprovado" | "seguir"
  requiresApproval: boolean; // se true, a transição por esta aresta passa por humano (default: false)
  dataMapping?: DataMapping; // obrigatório quando type === "data"
}

type EdgeType = "flow" | "data";

// Edge de FLOW: define a ordem de execução (quem roda depois de quem).
// Múltiplas flow edges do mesmo source = fan-out (execução em paralelo ou sequencial, conforme o grafo).
// A condition é opcional: sem condition, a transição é incondicional.
// Data edges nunca têm condition — condição sempre exige uma flow edge explícita (ver regra 7 abaixo).

// Edge de DATA: define que um output específico do agente source é enviado para um input específico do agente target.
// Um agente pode ter múltiplas data edges saindo dele (mesmo output para vários agentes, ou outputs diferentes para agentes diferentes).
// O compiler valida que sourceOutput existe em outputs do agente source e targetInput existe em inputs do agente target.
//
// IMPORTANTE: uma data edge entre (source, target) que NÃO tenha uma flow edge explícita entre o mesmo par
// implica automaticamente uma flow edge incondicional entre eles. Ou seja, o usuário não precisa desenhar
// as duas linhas para o caso comum de "mandar dado e seguir em frente": uma data edge sozinha já basta —
// ela carrega tanto o wiring (dataMapping) quanto a ordem de execução implícita.
// Uma flow edge explícita entre o mesmo par só é necessária quando a transição precisa ser CONDICIONAL
// (branches, loops com condition) — nesse caso ela coexiste com a data edge: a condition da flow edge
// decide se a transição (e a propagação do dado) acontece.

interface DataMapping {
  sourceOutput: string;      // nome do port em Agent.outputs do agente source
  targetInput: string;       // nome do port em Agent.inputs do agente target
}

interface EdgeCondition {
  field: "action" | "status" | "output";  // whitelist de campos
  operator: "eq" | "neq" | "in" | "not_in";
  value: string | string[];  // quando field === "action", value deve ser FlowAction | FlowAction[]
}

// String livre é proibida. O compiler valida field contra a whitelist acima, operador contra a union,
// e value contra FlowAction quando field === "action". Nunca eval.

// Regras de validação no compiler:
// 1. Toda edge de data exige dataMapping com sourceOutput e targetInput válidos.
// 2. sourceOutput deve existir em Agent.outputs do agente source.
// 3. targetInput deve existir em Agent.inputs do agente target.
// 4. O tipo do port (PortDef.type) deve ser compatível entre sourceOutput e targetInput.
// 5. Um agente pode ter uma data edge para B e uma flow edge para C (alvos diferentes) — nesse caso
//    ambos rodam em fan-out a partir do source, mas só B recebe o dado.
// 6. Se um agente target tem inputs required e não recebe data edge correspondente, o compiler rejeita o grafo.
// 7. Data edge implica flow: se (source, target) tem uma data edge e NENHUMA flow edge explícita entre
//    o mesmo par, o compiler injeta uma flow edge incondicional equivalente na hora de montar o StateGraph.
//    Se já existir uma flow edge explícita entre o mesmo par (ex: com condition), ela prevalece — a data
//    edge não cria uma segunda transição, só adiciona o dataMapping à transição existente.
// 8. Todo nó (exceto o entryNodeId) precisa ter pelo menos uma flow edge OU data edge de entrada —
//    sem isso é nó órfão e o compiler rejeita o grafo (a regra de "nó órfão" da seção 14 agora considera
//    data edges como incoming válido, já que elas também agendam execução).
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
[Flow edges - ordem de execução]
Agente A (Developer) ──flow──→ Agente B (Reviewer)
                                    │
                        ┌───────────┤
                        │           │
                   [aprovado]  [reprovado]
                        │           │
                        ▼           ▼
                   Agente C     Agente A (loop)

[Data edges - propagação de outputs]
Agente A ──data: code_pronto → code_para_review──→ Agente B
Agente B ──data: review_feedback → feedback──→ Agente A
```

O loop é controlado por:
- **Flow edge condicional:** `condition: { field: "action", operator: "eq", value: "return" }`
- **Data edge:** propaga o output específico (ex: `review_feedback`) para o input do agente de destino
- **Limite de iterações:** `maxIterations` no agente (anti-loop-infinito)
- **Checkpoint:** cada volta salva estado, não perde contexto

Neste exemplo, tanto A→B quanto B→A já têm uma flow edge explícita (a segunda é condicional, controlando o loop), então as data edges apenas acrescentam o `dataMapping` a uma transição que já existe — a flow edge explícita prevalece (regra 7 da seção 4.2). Se não houvesse necessidade de condição (ex: um simples "A produz, B consome, sempre segue em frente"), a data edge sozinha já seria suficiente — não seria preciso desenhar as duas linhas.

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

### 6.3 Ferramentas Básicas (Built-in Tools)

Todo agente possui um conjunto de **ferramentas básicas** sempre disponíveis, independentemente de configuração. São as operações fundamentais que qualquer agente precisa para interagir com o ambiente:

| Ferramenta | Descrição | Exemplo de uso |
|-----------|-----------|----------------|
| `read_file` | Ler conteúdo de um arquivo | Ler um arquivo de config, código-fonte, doc |
| `write_file` | Criar ou sobrescrever um arquivo | Gerar um novo arquivo de código, config |
| `edit_file` | Editar seções de um arquivo existente | Patch em código existente |
| `shell` | Executar comando no terminal | `pip install`, `git status`, `npm test` |
| `web_search` | Buscar na web (DuckDuckGo/Google) | Pesquisar documentação, API reference |
| `web_fetch` | Buscar e extrair texto de uma URL | Ler uma página de docs, artigo |
| `glob` | Listar arquivos por padrão | Encontrar todos os `.py` em um diretório |
| `grep` | Buscar texto em arquivos (regex) | Encontrar usagem de um símbolo no código |
| `list_directory` | Listar estrutura de diretório | Explorar estrutura de um projeto |

Essas ferramentas são **injetadas automaticamente** no contexto do agente. O usuário não precisa configurá-las, não podem ser removidas, e não aparecem na UI como itens configuráveis. Elas fazem parte do "sistema operacional" do agente.

### 6.4 Tools Custom (Scripts Python)

O usuário pode criar **ferramentas custom** escrevendo scripts Python com contrato de entrada/saída definido. O fluxo é:

```
[Usuário cria tool no portal]
        │
        ├── 1. Nome + descrição
        ├── 2. Script Python (função `execute`)
        ├── 3. Parâmetros de entrada (nome, tipo, descrição, obrigatório?)
        ├── 4. Parâmetros de saída (nome, tipo, descrição)
        │
        ▼
[Deploy da tool]
        │
        ├── Validação: script compila, tipos são coerentes
        ├── Teste opcional: usuário roda com parâmetros de exemplo
        ├── Registro no Tool Registry (PostgreSQL)
        │
        ▼
[Tool disponível na biblioteca]
        │
        ▼
[Usuário adiciona à mochila de um agente]
```

#### Contrato de uma Tool Custom

```typescript
interface CustomTool {
  id: string;
  ownerId: string;
  name: string;              // "calcular_custo_deploy", "consultar_jira"
  description: string;       // descrição para o LLM entender quando usar
  category: string;          // "infra" | "data" | "communication" | "custom"
  
  // Implementação
  script: string;            // código Python (função `execute`)
  
  // Contrato de I/O
  inputs: ToolParam[];       // parâmetros de entrada
  outputs: ToolParam[];      // parâmetros de saída
  
  // Metadados
  version: number;
  status: "draft" | "deployed" | "archived";
  createdAt: string;
  updatedAt: string;
}

interface ToolParam {
  name: string;              // "resource_group", "environment"
  type: "string" | "number" | "boolean" | "object" | "array";
  description: string;       // descrição para o LLM
  required: boolean;
  defaultValue?: any;
}
```

#### Exemplo de script Python

```python
# Tool: "consultar_jira"
# Descrição: Busca issues no Jira por projeto e status

def execute(project_key: str, status: str, max_results: int = 10) -> dict:
    """
    Busca issues no Jira.
    
    Args:
        project_key: Chave do projeto (ex: "PROJ")
        status: Status das issues ("To Do", "In Progress", "Done")
        max_results: Máximo de resultados (default 10)
    
    Returns:
        dict com "issues" (lista) e "total" (int)
    """
    import requests
    
    url = f"{JIRA_BASE}/rest/api/2/search"
    params = {
        "jql": f"project = {project_key} AND status = '{status}'",
        "maxResults": max_results
    }
    resp = requests.get(url, auth=(JIRA_USER, JIRA_TOKEN), params=params)
    resp.raise_for_status()
    data = resp.json()
    
    return {
        "issues": data["issues"],
        "total": data["total"]
    }
```

#### Regras de execução

- O script roda em **sandbox** (subprocesso isolado, sem acesso ao filesystem do host, timeout configurável)
- Variáveis de ambiente (credenciais) são injetadas pelo secrets manager, nunca hardcoded no script
- O retorno deve ser JSON-serializável
- Timeout padrão: 30s (configurável por tool, máx 120s)
- Erros são capturados e retornados como `{"error": "..."}` para o agente decidir como agir

### 6.5 Biblioteca e Associação

A biblioteca de skills/tools é um **registro central** no PostgreSQL. Itens podem ser:
- **Sistema (built-in):** ferramentas básicas (seção 6.3), sempre disponíveis, não configuráveis
- **Skills de sistema:** capacidades prontas da plataforma (code-gen, test-runner, doc-writer)
- **Tools custom:** criadas pelo usuário via portal (seção 6.4)

Um agente referencia skills e tools custom por ID. A configuração é por agente (ex: mesma tool "deploy" com configs diferentes para staging vs produção).

### 6.6 Mochila do Agente (capacidades totais)

A **mochila** de um agente é a união de:

```
Mochila = Ferramentas Básicas (sempre) + Skills associadas + Tools Custom associadas
        + Servidores MCP conectados + Integrações
```

| Camada | O que é | Exemplo |
|--------|---------|--------|
| Ferramentas Básicas | Sempre presentes, não configuráveis | `read_file`, `shell`, `web_search` |
| Skills | Capacidades de prompt/template | "Revisar código com foco em segurança" |
| Tools Custom | Scripts Python do usuário | `consultar_jira`, `calcular_custo_deploy` |
| Servidores MCP | Processos externos que expõem tools via protocolo MCP | Servidor Jira, Postgres, Slack |
| Integrações | Conexões com plataformas externas (comportamento fixo na plataforma) | GitHub, Azure, GitLab |

No portal, a UI de configuração do agente mostra as 5 camadas separadamente. As ferramentas básicas aparecem como referência (read-only), as demais são configuráveis.

### 6.7 Servidores MCP

**Decisão:** Servidores MCP (Model Context Protocol) são uma camada própria da mochila, distinta de Tools Custom e de Integrações.

**Por que não é Tools Custom:** o usuário não escreve código — o servidor é um processo externo já pronto que, ao ser conectado, expõe N tools de uma vez (descobertas via `tools/list` do protocolo), sem precisar declarar contrato de I/O manualmente.

**Por que não é Integração:** a spec trata Integração (seção 8) como uma plataforma fixa com comportamento embutido na plataforma (`platform: "azure" | "github" | ...`). Um servidor MCP é genérico e plugável — o usuário pode conectar qualquer servidor (interno ou de terceiros) sem o portal precisar conhecer a plataforma de antemão.

#### Contrato de um Servidor MCP

```typescript
interface MCPServer {
  id: string;
  ownerId: string;
  name: string;               // "jira-mcp", "postgres-readonly"
  description: string;
  transport: "stdio" | "sse" | "http";
  command?: string;           // obrigatório quando transport === "stdio" (ex: "npx -y @acme/mcp-jira")
  url?: string;                // obrigatório quando transport === "sse" | "http"
  env: Record<string, string>; // variáveis de ambiente (secrets ref, nunca valor em claro)

  // Estado da conexão
  status: "connected" | "disconnected" | "error";
  lastConnectedAt: string | null;
  discoveredTools: MCPToolInfo[]; // populado ao conectar, via tools/list

  createdAt: string;
  updatedAt: string;
}

interface MCPToolInfo {
  name: string;
  description: string;
  inputSchema: Record<string, any>; // JSON Schema, como retornado pelo servidor
}
```

#### Fluxo

```
[Usuário registra servidor MCP no portal]
        │
        ├── 1. Nome + descrição
        ├── 2. Transporte: stdio (comando local) | sse | http (URL remota)
        ├── 3. Variáveis de ambiente (secrets ref)
        │
        ▼
[Testar conexão]
        │
        ├── Orquestrador inicia/conecta o servidor e chama tools/list
        ├── Tools descobertas aparecem na tela para revisão
        │
        ▼
[Servidor disponível na biblioteca]
        │
        ▼
[Usuário conecta o servidor a um agente]
        │
        └── Todas as tools descobertas (ou um subconjunto via toolFilter) entram na mochila do agente
```

**Regras:**
- A conexão é testada sob demanda (`POST /api/mcp-servers/:id/test`); o resultado atualiza `status` e `discoveredTools`.
- Se o servidor cair durante a execução de um agente, a chamada de tool falha e retorna erro ao agente (mesmo tratamento de erro de Tools Custom — seção 6.4).
- Credenciais em `env` seguem o mesmo secrets manager das demais camadas (env vars na V1, Azure Key Vault na V2).

---

## 7. Knowledge Base / RAG

### 7.1 Fontes

| Fonte | Descrição |
|-------|-----------|
| Upload | Usuário faz upload de PDFs, docs, código |
| Vector DB pré-existente | Collection já indexada (Qdrant, pgvector) |
| URL | Documento público indexado |
| Rivvn (externo, opcional) | Consulta somente-leitura a uma collection já existente no Rivvn (rivvn.ai), via SDK + OAuth — seção 7.4 |

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

### 7.4 Integração externa: Rivvn (opcional, sob contrato)

**Decisão:** O Rivvn (rivvn.ai) já resolve bem o trabalho de knowledge/documentação no time. Em vez de duplicar esse conteúdo no pgvector local, uma Knowledge Base pode ser configurada como **fonte externa somente-leitura**, consultando o Rivvn diretamente via SDK.

**⚠️ Pré-requisito comercial:** o Rivvn é um sistema à parte, com tratamento comercial próprio (não é um serviço interno do Agent Portal nem incluído por padrão). Essa integração **só pode ser habilitada mediante contrato comercial ativo** entre o Grupo Supero e o Rivvn — não é uma feature que liga sozinha por configuração técnica. Implicações:
- A UI de "Conectar Rivvn" (view Knowledge) só fica disponível/habilitada para owners cujo contrato esteja ativo; sem contrato, o botão aparece desabilitado com um CTA para contato comercial.
- O backend valida `contractStatus` antes de permitir o início do fluxo OAuth (`/api/integrations/rivvn/authorize` retorna 403 se não houver contrato ativo).
- É tratado como um **add-on**, fora do escopo padrão de licenciamento do portal — não confundir com as demais integrações da seção 8 (essas são técnicas/gratuitas, sem gate comercial).

**Modelo de conexão:**
- Autenticação via **OAuth**: o usuário autoriza o portal a acessar sua conta/workspace do Rivvn (fluxo padrão de authorization code).
- O **SDK do Rivvn** troca o `code` do OAuth por um token e é responsável por gerar/renovar o token usado nas consultas — o orquestrador não implementa a chamada HTTP crua, delega ao SDK.
- O token (access + refresh) fica no secrets manager (mesma política das demais camadas — env vars na V1, Key Vault na V2), nunca em claro no banco.
- Conexão é por `ownerId` (uma autorização OAuth vale para todas as Knowledge Bases do usuário que apontarem para `source: "rivvn"`).

**Modelo de uso (somente leitura):**
- Não há upload nem sync de volta para o Rivvn nesta fase — o portal só consulta.
- O fluxo de RAG da seção 7.2 (chunking → embedding → vector DB) **não se aplica** a essa fonte: a query do agente é repassada para o SDK do Rivvn, que já faz a busca semântica do lado dele e devolve os trechos relevantes.

```typescript
interface RivvnConnection {
  ownerId: string;
  contractStatus: "active" | "inactive" | "expired"; // gate comercial — verificado antes de qualquer OAuth
  status: "connected" | "disconnected" | "expired";  // estado técnico da conexão OAuth
  connectedAt: string | null;
  scope: string[];            // escopos OAuth concedidos
}
```

```
[Usuário clica "Conectar Rivvn" na view Knowledge]
        │
        ▼
[Backend valida contractStatus === "active"]
        │
        ├── inativo/sem contrato → bloqueia, exibe CTA de contato comercial
        │
        ▼ (contrato ativo)
[Redirect OAuth para rivvn.ai] → [Usuário autoriza] → [Callback com code]
        │
        ▼
[SDK do Rivvn troca code por token] → [Token salvo no secrets manager]
        │
        ▼
[Usuário escolhe a collection do Rivvn a usar como Knowledge Base]
        │
        ▼
[Agente executa] → [Query] → [SDK do Rivvn faz a busca] → [Trechos injetados no prompt]
```

**Regras:**
- Se o token expirar ou a autorização for revogada do lado do Rivvn, `status` vira `expired`/`disconnected` e a query retorna erro tratável (mesmo padrão de falha de Tools Custom / MCP — o agente decide como agir).
- Se o **contrato comercial** expirar ou for cancelado (`contractStatus !== "active"`), o backend desativa a conexão independentemente do estado técnico do token, e Knowledge Bases com `source: "rivvn"` passam a retornar erro até o contrato ser renovado — não é um caso de falha técnica, é um bloqueio deliberado.
- Uma Knowledge Base com `source: "rivvn"` não tem `chunker`/`embedder` associados — o campo `reference` guarda o id da collection no Rivvn.

---

## 8. Integrações (camada da Mochila)

A mochila completa do agente é definida na seção 6.6. Esta seção detalha a camada de **integrações**: conexões com plataformas externas:

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
| GET | `/api/integrations/rivvn/authorize` | Inicia o fluxo OAuth (retorna URL de redirect) — **403 se `contractStatus !== "active"`** |
| GET | `/api/integrations/rivvn/callback` | Callback OAuth — troca `code` por token via SDK |
| GET | `/api/integrations/rivvn/status` | Status da conexão e do contrato (`connected`\|`disconnected`\|`expired`, `contractStatus`) |
| DELETE | `/api/integrations/rivvn` | Revoga a conexão (desconecta) |

### 9.4 Tools Custom

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/tools` | Listar tools custom do usuário |
| POST | `/api/tools` | Criar tool (script + I/O) |
| GET | `/api/tools/:id` | Obter tool |
| PUT | `/api/tools/:id` | Atualizar tool |
| DELETE | `/api/tools/:id` | Arquivar tool |
| POST | `/api/tools/:id/deploy` | Deploy (valida + registra) |
| POST | `/api/tools/:id/test` | Testar com parâmetros de exemplo |

### 9.5 Servidores MCP

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/mcp-servers` | Listar servidores MCP do usuário |
| POST | `/api/mcp-servers` | Registrar servidor (transporte + comando/URL + env) |
| GET | `/api/mcp-servers/:id` | Obter servidor |
| PUT | `/api/mcp-servers/:id` | Atualizar servidor |
| DELETE | `/api/mcp-servers/:id` | Remover servidor |
| POST | `/api/mcp-servers/:id/test` | Testar conexão (chama `tools/list`, atualiza `discoveredTools`) |

### 9.6 Aprovações

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/approvals?status=pending` | Listar aprovações pendentes |
| POST | `/api/approvals/:id/respond` | Responder (aprovar/rejeitar/revisar) |

### 9.7 WebSocket

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
│   ├── ToolsEditor.tsx         # Editor de tools custom (script + I/O + deploy)
│   ├── MCPServersLibrary.tsx   # Registro + teste de conexão de servidores MCP
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
│   │   ├── mcp_servers.py
│   │   ├── integrations.py     # Rivvn OAuth (authorize/callback/status)
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
│   ├── tools/
│   │   ├── registry.py         # Tool Registry (CRUD + deploy)
│   │   ├── sandbox.py          # Sandbox de execução (subprocesso isolado)
│   │   ├── validator.py        # Valida script + I/O
│   │   └── builtins/           # Ferramentas básicas (read_file, shell, etc.)
│   │       ├── read_file.py
│   │       ├── write_file.py
│   │       ├── edit_file.py
│   │       ├── shell.py
│   │       ├── web_search.py
│   │       ├── web_fetch.py
│   │       ├── glob.py
│   │       ├── grep.py
│   │       └── list_directory.py
│   ├── mcp/
│   │   ├── registry.py         # MCP Server Registry (CRUD)
│   │   ├── client.py           # Conecta via stdio/sse/http, chama tools/list e invoca tools
│   │   └── validator.py        # Valida config de conexão
│   ├── knowledge/
│   │   ├── rag.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── rivvn/
│   │       ├── oauth.py        # Authorization code flow (authorize/callback)
│   │       └── client.py       # Wrapper do SDK do Rivvn (token + query)
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

### ADR-006: Separação de edges de flow e data

**Decisão:** O grafo da pipeline usa dois tipos de aresta: `flow` (ordem de execução, pode ser condicional) e `data` (propagação de outputs). Não são totalmente independentes: **uma data edge sem flow edge explícita entre o mesmo par implica uma flow edge incondicional** — ela sozinha já basta para "manda dado e segue em frente". Uma flow edge explícita só é necessária quando a transição precisa de `condition` (branch, loop) ou quando não há dado nenhum sendo propagado.

**Alternativas consideradas:**
- Edge única (flow + data sempre combinados, sem distinção de tipo): mais simples ainda, mas perde a capacidade de expressar transição condicional junto com dado (o loop de reprovação da seção 5.2 precisa de `condition`, que só existe em flow edges) e a de mandar dado pra um nó que não é o próximo imediato no fluxo (fan-out assimétrico).
- Totalmente independentes, sem implicação nenhuma (versão anterior desta ADR): exigia o usuário desenhar duas linhas pro caso mais comum (mandar dado e seguir), o que gerava confusão visual (ver histórico de discussão) sem ganho real, já que causalmente um output só existe depois que o source roda.
- Shared state puro (LangGraph StateGraph sem mapeamento): todos leem/escrevem no mesmo estado. Funciona, mas o usuário não controla explicitamente qual output vai para qual agente. O contrato de ports fica decorativo.

**Razão:** Fisicamente, uma data edge já implica ordem — B não pode consumir o output de A antes de A rodar. Fazer o compiler reconhecer isso automaticamente (regra 7 da seção 4.2) elimina a necessidade de desenhar duas arestas pro caso comum, sem abrir mão de expressividade: quando o usuário precisa de uma transição condicional (loop, branch) junto com dado, ele ainda desenha a flow edge explícita ao lado da data edge, e a condition dela passa a governar se a transição (e a propagação) acontece.

**Representação visual (decisão de design):**
- Flow edges: linha sólida cinza (ordem de execução, pode ter condition)
- Data edges: linha tracejada azul (propagação de dados; sempre incondicional, a menos que combinada com uma flow edge explícita entre o mesmo par)
- Painel lateral ao clicar na aresta para configurar: tipo, data mapping, requiresApproval — o campo `condição` só aparece quando a aresta é (ou tem ao lado) uma flow edge explícita, já que data edges puras não carregam condition
- Padrão alinhado com ferramentas BPMN/workflow (Camunda, n8n)

---

### ADR-007: Servidores MCP como camada própria da mochila

**Decisão:** Servidores MCP (Model Context Protocol) são uma 5ª camada da mochila do agente (seção 6.7), com registro, contrato e API próprios — não são modelados como Tools Custom nem como Integração.

**Alternativas consideradas:**
- Tratar como Tools Custom: exigiria o usuário "empacotar" cada tool do servidor manualmente, perdendo a vantagem central do MCP (descoberta automática via `tools/list`).
- Tratar como subtipo de `IntegrationRef.platform`: reaproveita a estrutura existente, mas Integração pressupõe comportamento fixo conhecido pela plataforma; um servidor MCP é genérico e o portal não precisa conhecer sua plataforma de antemão.

**Razão:** MCP é hoje o mecanismo padrão de mercado para conectar agentes a ferramentas externas sem escrever código por integração. Modelá-lo como camada própria mantém a distinção conceitual que a spec já faz (plataforma vs. usuário vs. protocolo aberto) e permite que um único servidor registrado alimente múltiplos agentes com todas as suas tools de uma vez.

---

### ADR-008: Rivvn como fonte externa de Knowledge Base (somente leitura)

**Decisão:** O Rivvn (rivvn.ai) é modelado como um novo valor de `KnowledgeRef.source` ("rivvn"), não como uma camada nova da mochila nem como Integração da seção 8. A conexão é por OAuth + SDK do próprio Rivvn, e o uso é **somente consulta** — sem upload nem sincronização de volta.

**Alternativas consideradas:**
- Nova camada da mochila (como MCP Servers): rejeitada porque Rivvn não expõe "tools" genéricas — expõe busca semântica sobre documentação, que é exatamente o que Knowledge Base já representa. Tratá-lo como fonte de Knowledge evita duplicar conceito.
- Sincronização bidirecional (upload/push para o Rivvn): fora de escopo por decisão do usuário — o Rivvn já é a fonte de verdade da documentação do time; o portal só consome.

**Razão:** O time já usa o Rivvn para o trabalho de documentação/knowledge. Duplicar esse conteúdo via chunking/embedding local (seção 7.2) seria retrabalho e criaria duas fontes de verdade divergentes. Consultar o Rivvn diretamente via SDK, com autenticação OAuth padrão, mantém uma única fonte de verdade e é opcional por Knowledge Base (o pgvector local continua disponível para as demais).

**Nota comercial:** diferente das demais fontes/camadas da spec (que são técnicas e sempre disponíveis), o Rivvn é um **sistema de terceiros com tratamento comercial próprio**. A integração é gateada por `contractStatus` (seção 7.4) — habilitada apenas para owners com contrato ativo com o Rivvn, não é uma feature que qualquer usuário do portal liga por conta própria.

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
- [ ] Backend: ferramentas básicas (read_file, write_file, shell, web_search, web_fetch, glob, grep, list_directory)
- [ ] Backend: tools custom (sandbox Python, deploy, registry)
- [ ] Portal: editor de tools custom (script + I/O + deploy)
- [ ] Backend: servidores MCP (registry, client stdio/sse/http, test-connection)
- [ ] Portal: biblioteca de servidores MCP (registrar, testar conexão, listar tools descobertas)
- [ ] Backend: RAG básico (upload → chunk → embed → query)
- [ ] Backend: integração opcional com Rivvn, sob contrato comercial (OAuth + SDK, somente leitura)
- [ ] Portal: Knowledge — conectar Rivvn (gateado por contrato) e escolher collection como fonte externa
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
- [ ] Tools custom com acesso a filesystem do host (V1: sandbox isolado)
- [ ] Marketplace de tools (compartilhar entre usuários)
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
