# D5 — Pipeline (Grafo + Compiler)

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 4 · Orquestração**. Dependência: **D4** (contrato do agente).
> Base: spec (seção 4.2 "Pipeline", ADR-006, seção 12) + plano.

## Objetivo

Editor de grafo (portal) + compiler que converte o grafo JSON da pipeline num `StateGraph` do LangGraph, com validador que aplica as 11 regras da seção 4.2 (especialmente a regra 7: data edge sem flow edge explícita injeta flow edge incondicional).

## Escopo (o que FAZ)

- CRUD de pipelines: `POST/GET/PUT /api/pipelines` com validação de grafo.
- Validador de grafo: regras 1-11 da spec (dataMapping válido, ports compatíveis, nós órfãos, ciclos, data edge implica flow, entryNodeId válido, actions warning, edges duplicadas).
- Compiler: `compiler/graph_builder.py` — `Pipeline` → `StateGraph` do LangGraph.
- Compiler: `compiler/state.py` — definição do `State` (TypedDict) com todos os ports.
- Compiler: `compiler/conditions.py` — `EdgeCondition` → função condicional do LangGraph.
- Editor de fluxo (Portal): `FlowEditor.tsx` com React Flow.
- Validação visual no editor.

## Escopo (o que NÃO FAZ)

- NÃO executa o grafo (D6), NÃO implementa a função do nó de aprovação (D7 fornece a implementação; o compiler apenas gera a topologia), NÃO integra skills/tools/MCP (D8).
- NÃO implementa o chat de construção (D4).
- NÃO define o estado de execução em tempo real (isso é D6 no runtime — o compiler só constrói o grafo estático).
- NÃO lida com checkpoints.

## Dependências

- **D4:** contrato do agente (`inputs`/`outputs`/`actions`) + model `Agent` no banco. O compiler lê os agentes da pipeline e valida ports contra o contrato.
- **D3:** model `Pipeline`/`PipelineNode`/`PipelineEdge` + router `/api/pipelines` + tipos em `types.ts`.

## Arquivos que OWNS

```
agent-orchestrator/
  app/compiler/
    validator.py          (regras 1-11 da spec)
    state.py              (State TypedDict)
    graph_builder.py      (Pipeline -> StateGraph)
    conditions.py         (EdgeCondition -> LangGraph condition)
agent-portal/
  components/FlowEditor.tsx
  components/EdgePanel.tsx   (painel de configuração da aresta)
```

## Comportamento do Compiler (contrato de comportamento)

Esta seção define **como** o compiler transforma o grafo JSON em um `StateGraph` do LangGraph. É o contrato que o worker deve seguir.

### Mapeamento de FlowAction → Topologia do Grafo

Cada agente, ao executar, retorna um `action` (follow | return | finalize). O compiler gera **uma conditional edge por nó** que roteia com base no `action` no State:

| Action | Roteamento | Como o compiler implementa |
|--------|-----------|---------------------------|
| `follow` | Próximo nó (flow edge incondicional ou a primeira condicional que casar) | `add_conditional_edges(node, route_fn, {"follow": next_node, ...})` |
| `return` | Nó de loop (target da flow edge com `condition: {field: "action", operator: "eq", value: "return"}`) | `route_fn` retorna o target dessa edge |
| `finalize` | `END` (encerra a pipeline) | `route_fn` retorna `END` |

**Regra (aviso, não erro):** se um agente declara uma action mas nenhuma flow edge com essa condition sai dele, o compiler emite um **aviso** (não rejeita o grafo). O grafo é válido: actions é o que o agente PODE produzir, não o que o grafo DEVE rotear (regra 10, ver 5.2).

**Regra:** se um agente declara `actions: ["finalize"]`, o compiler **sempre** adiciona a rota `finalize → END` na conditional edge, independentemente de haver flow edge explícita.

### Fan-out (múltiplas flow edges do mesmo source)

Múltiplas flow edges incondicionais saindo do mesmo nó = **execução em paralelo** no LangGraph. O compiler faz:
- `add_conditional_edges(source, route_fn, {"follow": [nodeA, nodeB]})` — LangGraph executa ambos em paralelo.
- Se as edges têm conditions diferentes, cada condition roteia pro seu target.
- **Conflito de State:** se dois nós em paralelo escrevem na mesma key do State, o reducer `last` (padrão LangGraph) aplica. O compiler **não** resolve conflitos de escrita — é responsabilidade do design do grafo evitar (ou o D6 trata no runtime).

### State: Naming Convention e dataMapping

O `State` é um `TypedDict` com keys **namespaced por nodeId**:

```
State = {
  # Ports de entrada (inputs) de cada nó
  "{nodeId}.inputs.{portName}": Any,   # ex: "node-2.inputs.code_para_review"
  
  # Ports de saída (outputs) de cada nó
  "{nodeId}.outputs.{portName}": Any,  # ex: "node-1.outputs.code_pronto"
  
  # Action do agente (para roteamento condicional)
  "{nodeId}.action": str,              # "follow" | "return" | "finalize"
  
  # Status do agente (V2: para condition field: "status")
  "{nodeId}.status": str,              # "completed" | "failed" | "interrupted"
  
  # Contador de iterações (maxIterations)
  "{nodeId}.iterations": int,
  
  # Metadata global
  "pipeline.status": str,               # "running" | "completed" | "failed"
}
```

> **Nota:** as keys são namespaced por `nodeId` (PipelineNode.id), não por `agentId`. Isso permite que o mesmo agente apareça múltiplas vezes no grafo (loop A→B→A) sem colisão de keys.

**Como dataMapping funciona no State:**
- A data edge diz: `sourceOutput: "code_pronto"` (do nó A) → `targetInput: "code_para_review"` (do nó B).
- O **nó A**, ao terminar, escreve em `"{nodeId_A}.outputs.code_pronto"`.
- O **nó B**, ao iniciar, lê de `"{nodeId_A}.outputs.code_pronto"` e usa como input `code_para_review`.
- O dataMapping é resolvido **no node function** (não no State): o node function do nó B sabe que seu input `code_para_review` vem da key `"{nodeId_A}.outputs.code_pronto"` no State.
- **Colisão de nomes:** como as keys são namespaced por `nodeId`, o mesmo agente pode aparecer em múltiplos nós sem conflito.

### Node Function Contract

Cada nó do StateGraph é uma função assíncrona com este contrato:

```python
async def node_function(state: State) -> dict:
    """
    1. LER inputs: para cada input do agente, buscar a key no State
       (via dataMapping: qual output de qual nó alimenta este input).
    2. EXECUTAR: chamar Agent.run(inputs, capabilities) com o snapshot do agente.
       capabilities é obtido via loader.load(agent_snapshot) (contrato D8).
    3. ESCREVER outputs: para cada output produzido, escrever em
       "{nodeId}.outputs.{portName}" no State.
    4. SET action: escrever "{nodeId}.action" = action retornada pelo agente.
    5. SET status: escrever "{nodeId}.status" = "completed" (ou "failed").
    6. INCREMENT iterations: "{nodeId}.iterations" += 1.
    7. RETORNAR dict com as keys escritas (LangGraph merge no State).
    """
```

O node function **não** decide para onde ir — isso é papel da conditional edge (route_fn). O node function só executa e atualiza o State.

### EdgeCondition: o que cada field avalia

| field | Avalia contra | Exemplo |
|-------|-------------|--------|
| `"action"` | `"{nodeId}.action"` no State (o action retornado pelo agente) | `{field: "action", operator: "eq", value: "return"}` |

> **V2:** suportar field `"status"` e `"output"` (semântica a definir). Na V1, apenas `"action"` é aceito.

**Nunca `eval`.** Sempre lookup no State com a key namespaced.

### requiresApproval no compiler: geração de nó de aprovação

O compiler **gera um nó de aprovação dedicado** para cada edge com `requiresApproval: true`. O nó de aprovação é um nó real do `StateGraph`, não uma anotação na aresta. O que o compiler faz:

1. **Cria a função do nó de aprovação:** `approval_node_{edgeId}`. A função é fornecida pelo D7 (o D7 OWNS a implementação). O compiler importa e registra a função no grafo.
2. **Adiciona o nó ao StateGraph:** `graph.add_node(f"approval_node_{edgeId}", approval_fn)`.
3. **Fia as arestas:**
   - `source → approval_node_{edgeId}` (aresta incondicional, substitui a edge original)
   - `approval_node_{edgeId} → target` (aresta "proceed", quando o humano aprova)
   - `approval_node_{edgeId} → reject_handler` (aresta "reject", quando o humano rejeita; o reject_handler pode ser o source ou END, conforme configuração)
4. **Roteamento pós-aprovação:** o nó de aprovação retorna `Command(goto="proceed")` ou `Command(goto="reject_handler")`. O roteamento é decidido **dentro do nó**, não por uma conditional edge pré-definida.

**Importante:** o `interrupt()` é chamado **dentro** da função do nó de aprovação (primitivo de nó do LangGraph). O compiler não chama `interrupt()` em lugar nenhum; ele apenas estrutura o grafo para que o nó de aprovação exista na topologia correta.

### maxIterations no State

O State inclui `"{nodeId}.iterations": int` (inicializado em 0). O node function incrementa a cada execução. A verificação do limite é feita **exclusivamente pelo runtime (D6)**, não pelo compiler. O compiler não verifica maxIterations na route_fn: a route_fn trata apenas topologia e condições. Se o runtime detecta que o limite foi excedido, aborta a pipeline com status "failed".

### position (layout) é UI-only

O campo `position: {x, y}` no `PipelineNode` é **exclusivamente** para o editor visual (React Flow). O compiler **ignora** completamente. Não entra no State, não afeta topologia.

### AgentSnapshot (não o agente vivo)

O compiler usa o `agentSnapshot` do `PipelineNode` (cópia imutável congelada no momento da execução), **não** o agente vivo do banco. Se o usuário editar o agente durante a execução, a pipeline em andamento não é afetada.

---

## Tarefas

### 5.1 CRUD de pipelines (API)
- Preencher o router stub: `POST /api/pipelines` (criar grafo), `GET /api/pipelines` (listar, query: `?status=`, `?page=`, `?limit=`), `GET /api/pipelines/:id`, `PUT /api/pipelines/:id`, `GET /api/pipelines/:id/runs` (listar runs da pipeline).
- Antes de persistir, rodar o validador (5.2). Grafo inválido → 400 com lista de erros estruturada: `{"errors": [{"rule": 6, "message": "...", "nodeId": "...", "edgeId": "..."}]}`.
- `entryNodeId` é explícito (compiler não infere).
- **Nota:** `POST /api/pipelines/:id/execute` cria um `PipelineRun` (model D3) e inicia a execução com `thread_id` derivado (`f"{pipelineId}:{runId}"`). Retorna 409 se já há run com status "running".
- Aceite: criar pipeline com grafo válido persiste; grafo inválido é rejeitado com lista de erros; listar runs retorna PipelineRuns ordenados por `startedAt` desc.

### 5.2 Validador de grafo
- Implementar as 8 regras da seção 4.2 da spec **+ 3 regras adicionais**:
  1. Toda data edge exige dataMapping com sourceOutput e targetInput válidos.
  2. sourceOutput existe em `outputs` do agente source.
  3. targetInput existe em `inputs` do agente target.
  4. Tipo do port compatível entre sourceOutput e targetInput (match exato de string: `"code"` == `"code"`, sem hierarquia).
  5. Agente pode ter data edge pra B e flow edge pra C (alvos diferentes) — **não é erro**.
  6. Target com inputs required sem data edge correspondente → rejeitar.
  7. Data edge sem flow edge explícita entre o mesmo par → injeta flow edge incondicional (transformação, não erro).
  8. Todo nó (exceto entry) tem flow edge OU data edge de entrada (nó órfão → rejeitar).
  9. **(nova)** `entryNodeId` deve referenciar um nó existente em `nodes`. Se não existe → rejeitar.
  10. **(nova)** Se um agente declara uma action mas nenhuma flow edge com essa condition sai dele → **aviso** (não erro). O grafo é válido: actions é capacidade, não obrigação de roteamento.
  11. **(nova)** Múltiplas flow edges entre o mesmo par (source, target) com conditions diferentes são **permitidas** (branching). Duas flow edges **idênticas** (mesma condition) entre o mesmo par → rejeitar (redundante).
- Aceite: cada regra testada individualmente (ver seção de testes).

### 5.3 Compiler: JSON → StateGraph
- `graph_builder.py`: dado um `Pipeline` (com `agentSnapshot` nos nós), construir um `StateGraph` do LangGraph:
  - **State:** gerar o `TypedDict` dinamicamente com todas as keys namespaced (ver seção "State: Naming Convention").
  - **Nós:** um node function por agente (contrato na seção "Node Function Contract"). Usa `agentSnapshot`, não o agente vivo.
  - **Entry:** `add_edge(START, entryNodeId)`.
  - **Flow edges incondicionais:** `add_conditional_edges(source, route_fn, {"follow": target})`.
  - **Flow edges condicionais:** `add_conditional_edges(source, route_fn, {"follow": target1, "return": target2, "finalize": END})`.
  - **Fan-out:** múltiplos targets para `"follow"` → lista no mapping (LangGraph executa em paralelo).
  - **Data edges:** não criam arestas separadas. O dataMapping é resolvido no node function (o target lê a key do source no State). Se a regra 7 injeta uma flow edge, ela é tratada como flow edge incondicional.
  - **requiresApproval:** gerar nó de aprovação dedicado (ver seção "requiresApproval no compiler"). O compiler importa a função do D7 e registra no grafo com as arestas source → approval_node → target/reject_handler.
  - **maxIterations:** NÃO é verificado na route_fn. A enforcement é exclusiva do runtime (D6). A route_fn trata apenas topologia e condições.
- Aceite: grafo A→B→C (data edges simples) gera um StateGraph com 3 nós e arestas corretas.

### 5.4 Compiler: State
- `state.py`: função `build_state(pipeline: Pipeline) -> type[TypedDict]` que gera o TypedDict dinamicamente com:
  - `{nodeId}.inputs.{portName}` para cada input de cada nó
  - `{nodeId}.outputs.{portName}` para cada output de cada nó
  - `{nodeId}.action` (str)
  - `{nodeId}.status` (str)
  - `{nodeId}.iterations` (int, default 0)
  - `pipeline.status` (str)
- Reducer: `last` (padrão LangGraph) para todas as keys. Sem merge custom na V1.
- Aceite: State contém todas as keys namespaced por nodeId; round-trip (save → load) preserva o estado.

### 5.5 Compiler: condições
- `conditions.py`: converter `EdgeCondition` numa função `route_fn(state) -> str` (retorna o nome do target ou `END`).
  - `field: "action"` → lê `state["{nodeId}.action"]`
  - `operator`: `eq` (==), `neq` (!=), `in` (in list), `not_in` (not in list)
  - **Nunca `eval`.** Sempre lookup no State.
  - **V1:** apenas `field: "action"` é suportado. V2: `"status"` e `"output"` (semântica a definir).
- A `route_fn` principal de cada nó combina: conditions das edges + fallback `follow`. NÃO inclui maxIterations (isso é D6).
- Aceite: condition `{action, eq, "return"}` direciona pro nó de loop; `{action, eq, "finalize"}` direciona pro END.

### 5.6 Editor de fluxo (Portal)
- `FlowEditor.tsx` com React Flow: nós arrastáveis (agentes), arestas, painel lateral ao clicar na aresta (tipo flow/data, dataMapping, condition, requiresApproval). Zoom/pan/fit.
- `position` é salvo no grafo (UI-only, compiler ignora).
- Aceite: criar nós, conectar, configurar aresta, salvar persiste no backend.

### 5.7 Validação visual
- Ao salvar ou editar aresta, chamar validação (backend ou local) e destacar arestas inválidas em vermelho com tooltip.
- Aceite: aresta com dataMapping inválido aparece vermelha com motivo.

## Critérios de aceite (DoD)

- [ ] Grafo inválido é rejeitado pelo validador com mensagem específica
- [ ] Compiler gera StateGraph válido para grafo simples (A→B→C)
- [ ] Compiler trata data edge sem flow edge (regra 7: injeta flow edge implícita)
- [ ] Editor permite criar, conectar e configurar arestas
- [ ] Painel de aresta mostra tipo, dataMapping, condition, requiresApproval
- [ ] Validação visual destaca erros em tempo real

## Contratos de interface (o que entrega aos outros)

- **Para D6:**
  - `compile_pipeline(pipeline: Pipeline) -> StateGraph` — o runtime recebe o grafo compilado (já com os nós de aprovação inseridos).
  - O `State` é um `TypedDict` com keys namespaced (schema documentado na seção "State: Naming Convention").
  - O runtime invoca o StateGraph com `ainvoke`/`astream` passando o State inicial (todos os inputs do entry node preenchidos, `iterations` em 0, `pipeline.status` = "running").
  - **Interrupt/resume:** o nó de aprovação (gerado pelo compiler, função fornecida pelo D7) chama `interrupt()` internamente. O D6 precisa saber que o grafo pode pausar nesses nós e retomar com `Command(resume=response)` + `thread_id`.
  - **Checkpoint round-trip:** o State (TypedDict) precisa serializar/deserializar no PostgresSaver sem perda. Testar.
- **Para D10:** `FlowEditor.tsx` + `EdgePanel.tsx` são a UI do editor.

## Riscos

- **Regra 7 é sutil:** data edge implica flow, mas flow edge explícita com condition prevalece. Testar os 11 casos de validação explicitamente.
- **State com muitos ports:** o State TypedDict cresce com o número de agentes. LangGraph lida bem, mas o D6 precisa saber round-trip no checkpoint (serialização JSONB).
- **Condições:** whitelist rigorosa, nunca string livre (`eval` proibido).
- **Fan-out + State conflicts:** dois nós em paralelo escrevendo na mesma key → reducer `last` aplica. Não é bug, mas o design do grafo deve evitar. Documentar.
- **maxIterations:** enforcement exclusiva do runtime (D6). O compiler NÃO verifica maxIterations na route_fn. Se o runtime detecta limite excedido, aborta a pipeline com status "failed".

## Testes obrigatórios

- Unit tests para o validador (todas as 11 regras, incluindo as 3 novas).
- Unit test para compiler:
  - Grafo simples A→B→C (data edges, sem condition)
  - Grafo com data edge sem flow edge (regra 7: injeta flow edge implícita)
  - Grafo com condition (branch: follow vs return)
  - Grafo com fan-out (A → B e A → C em paralelo)
  - Grafo com `finalize` (rota para END)
  - Grafo com `requiresApproval` (nó de aprovação gerado, arestas source → approval_node → target/reject_handler)
  - Grafo com mesmo agente em dois nós (loop A→B→A): State keys namespaced por nodeId sem colisão
- Teste de round-trip: State → JSON → State (simula checkpoint save/load)
