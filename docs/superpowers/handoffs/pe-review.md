# Handoff: pe-review (FASE 5 - Pipeline engine)

**Veredito:** APROVADO. Merge commit: `0ae4e53` (pe-loader, último merge da fase).

## Inventário do que existe

### Arquivos criados/alterados nesta fase

| Arquivo | Dono | Descrição |
|---------|------|-----------|
| `agent-orchestrator/app/compiler/__init__.py` | pe-compiler | Pacote compiler |
| `agent-orchestrator/app/compiler/state.py` | pe-compiler | State schema fixo (ADR-002) + reducers |
| `agent-orchestrator/app/compiler/graph_builder.py` | pe-compiler | `compile_pipeline()` + dataclasses + WorkerClient Protocol |
| `agent-orchestrator/app/compiler/validator.py` | pe-validator | `validate_pipeline()` + 11 regras |
| `agent-orchestrator/app/skills/loader.py` | pe-loader | `SkillLoader` + `load()` + `SkillContentCache` |
| `agent-orchestrator/app/agents/base.py` | pe-loader (modificado) | `AgentSnapshot` expandido com campos de refs |
| `agent-orchestrator/tests/test_compiler_graph_builder.py` | pe-compiler | 10 testes |
| `agent-orchestrator/tests/test_compiler_validator.py` | pe-validator | 32 testes |
| `agent-orchestrator/tests/test_skills_loader.py` | pe-loader | 23 testes |
| `agent-orchestrator/tests/test_pe_review_integration.py` | pe-review | 7 testes de integração |

### Módulos e contratos públicos

**`app.compiler.state`:**
- `State` (TypedDict): keys fixas `data`, `actions`, `status`, `iterations`, `max_iter_exceeded`, `pipeline_status`.
- `initial_state() -> dict[str, Any]`: estado inicial para nova execução.
- Reducers: `_merge_dicts` (data/actions/status), `_sum_dicts` (iterations), `operator.or_` (max_iter_exceeded), `_pipeline_status_reducer` (precedência failed>running>completed).

**`app.compiler.graph_builder`:**
- `compile_pipeline(pipeline, *, worker_client, checkpointer=None) -> CompiledStateGraph`
- `pipeline_from_dict(d: dict) -> Pipeline`: parsing JSON camelCase.
- `WorkerClient` (Protocol): `async def execute(agent_id, node_id, inputs, *, timeout=60) -> WorkerResponse`
- `WorkerResponse` (dataclass): `status`, `outputs`, `action`, `iterations`, `logs`, `error`
- Dataclasses: `Pipeline`, `PipelineNode`, `PipelineEdge`, `AgentSnapshot`, `PortDef`, `DataMapping`, `EdgeCondition`

**`app.compiler.validator`:**
- `validate_pipeline(pipeline: Pipeline) -> ValidationResult`
- `ValidationResult`: `errors`, `warnings`, `injected_flow_edges`, `is_valid`, `to_dict()`
- `ValidationError`: `rule`, `message`, `node_id`, `edge_id`, `to_dict()`
- `ValidationWarning`: `rule`, `message`, `node_id`, `edge_id`, `to_dict()`

**`app.skills.loader`:**
- `SkillLoader(db, storage, rag=None, mcp_client_factory=None, cache=None)`
- `SkillLoader.load(snapshot: AgentSnapshot) -> LoadResult`
- `LoadResult`: `capabilities: AgentCapabilities`, `warnings: list[str]`
- `load(snapshot, db, storage, rag=None, mcp_client_factory=None, cache=None) -> LoadResult` (conveniência)
- `SkillContentCache` (TTL 300s, in-memory, por skill_id)

**`app.agents.base`:**
- `AgentSnapshot` (dataclass): `id`, `name`, `type`, `description`, `prompt`, `strategy`, `model`, `max_iterations`, `timeout`, `shell_access`, `skills`, `tools`, `mcp_servers`, `knowledge`, `integrations`, `inputs`, `outputs`, `actions`
- `AgentCapabilities` (dataclass): `system_prompt`, `tools`, `mcp_tools`, `knowledge_context`
- `Agent` (classe base): `async def run(inputs, capabilities) -> dict`
- `create_agent_from_snapshot(snapshot, llm=None) -> Agent`

## Comandos para subir e testar

```bash
# Testes do compiler
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_compiler_graph_builder.py -v

# Testes do validator
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_compiler_validator.py -v

# Testes do loader
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_skills_loader.py -v

# Testes de integração (pe-review)
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_pe_review_integration.py -v

# Lint
docker compose -p squad-agentica run --rm --no-deps --entrypoint ruff orchestrator check app/compiler/ app/skills/loader.py app/agents/base.py
```

## Ressalvas e pendências para FASE 6 (rt-executor)

1. **`app/api/pipelines.py`**: o rt-executor deve criar o CRUD de pipelines (POST/GET/PUT/DELETE `/api/pipelines`), endpoint de validação (`POST /api/pipelines/validate`), e consumir `validate_pipeline()` antes de persistir. Formato de 400: `{"error": "validation error", "code": "invalid_graph", "details": {"errors": [...]}}`.

2. **`app/runtime/worker_client.py`**: implementação HTTP do `WorkerClient` Protocol. O compiler define o Protocol; o rt-executor implementa a chamada HTTP ao worker (com retry, backoff, timeout, nunca raise).

3. **`app/runtime/executor.py`**: consome o `CompiledStateGraph` retornado por `compile_pipeline()`. Deve:
   - Chamar `validate_pipeline()` antes de compilar.
   - Usar `compile_pipeline(pipeline, worker_client=..., checkpointer=...)`.
   - Executar com `astream` (stream_mode="updates").
   - Detectar interrupção via `__interrupt__` no update (não há `stream.interrupted`).
   - Fazer upsert de `ApprovalRequest` pós-interrupção (ADR-009).
   - Recompor o grafo via `compile_pipeline()` em todo resume (ADR-004).

4. **`AgentSnapshot` duplicado**: `graph_builder.py` tem um `AgentSnapshot` (dataclass) e `app/agents/base.py` tem outro. O rt-executor deve unificar: importar de `app/agents/base.py` e converter para o formato do compiler quando necessário.

5. **Worker (rt-worker)**: precisa instanciar `SkillLoader` com `db`, `storage` (SkillStorage), `rag` (RagService) e chamar `load(snapshot)` antes de `Agent.run(inputs, capabilities)`. O worker baixa o `.yml` do agente do Garage e constrói o `AgentSnapshot` com os campos de refs.

6. **Nó de aprovação (hitl-approval, FASE 7)**: o compiler gera a topologia `approval_node_{edgeId}` com `interrupt()`. O hitl-approval implementa a função completa (upsert ApprovalRequest + notificação). O nó atual no compiler é um stub que apenas chama `interrupt()` e retorna `Command(goto=...)`.

## Decisões tomadas nesta fase

1. **`pipeline_status` com reducer de precedência** (não `last`): em fan-out, dois nós escrevem `pipeline_status` no mesmo superstep. O reducer escolhe o "pior" status (failed > running > completed). Desvio do ADR-002 que pede `last`, mas necessário para fan-out.

2. **`maxIterations` checado na node function**: a node function checa `iters >= max_iterations` no início; se excedido, retorna `actions={nodeId: "finalize"}` + `max_iter_exceeded=True` sem rodar o worker. A route_fn roteia `finalize` -> END.

3. **Nó de aprovação sem arestas saídas explícitas**: o `approval_node_{edgeId}` retorna `Command(goto=<id real>)` que define o roteamento. O compiler adiciona apenas `source -> approval_node` (incondicional).

4. **Regra 7 (data edge sem flow edge)**: o compiler injeta uma `PipelineEdge` sintética (`id="__injected_{edgeId}"`, `type="flow"`, `condition=None`). O validator também retorna essas edges em `ValidationResult.injected_flow_edges`.

5. **Loader roda no worker (ADR-008)**: o `SkillLoader` recebe `db`, `storage`, `rag`, `mcp_client_factory` por injeção. O worker instancia e chama `load()`.

6. **Falhas parciais não derrubam o load**: skill ausente, MCP fora do ar, KB sem chunks -> warning em `LoadResult.warnings`, load continua.
