# Spike LangGraph — Prova de Arquitetura

Prova funcional do padrão de orquestração do contrato técnico (ADR-001..ADR-011),
sem LLM, sem MinIO, sem auth. Autocontido: **não importa nada de `agent-orchestrator/`**.

Pipeline: `A -> [aprovação] -> B` com loop-back por rejeição e `maxIterations`.

## Como rodar

```bash
# 1. Subir o Postgres isolado do spike (projeto próprio, nunca toca o stack principal).
docker compose -p spike -f spike/docker-compose.yml up -d

# 2. Rodar os testes (Python 3.13 do host, venv do spike).
cd spike
.venv/Scripts/python.exe -m pytest test_spike.py -v

# 3. (Opcional) Rodar o worker simulado + o demo manual.
.venv/Scripts/python.exe -m uvicorn worker:app --port 9100   # em outro terminal
.venv/Scripts/python.exe main.py                              # demo A -> [aprovação] -> B
```

O Postgres do spike usa a porta **15433** (não colide com o stack principal em 15432).
A imagem é `pgvector/pgvector:pg15` (a do contrato).

## Versões pinadas (confirmadas por execução)

| Pacote | Versão | Status |
|---|---|---|
| `langgraph` | 0.2.61 | OK — API de `interrupt()`/`Command`/`astream` confirmada |
| `langgraph-checkpoint-postgres` | 2.0.10 | OK — `PostgresSaver(conn)` + `setup()` funcionam |
| `psycopg[binary]` | 3.2.10 | OK — conexão `connect(url, autocommit=True)` |
| `httpx` | 0.28.1 | OK — `AsyncClient` com timeout |
| `fastapi` | 0.115.6 | OK — worker simulado |
| `pydantic` | 2.11.7 | OK — models |
| `pytest` / `pytest-asyncio` | 8.3.4 / 0.24.0 | OK |

## Padrões provados (trecho canônico de cada ADR)

### ADR-001 — Node function nunca levanta exceção do worker

`main.py` → `worker_execute()`: retry com backoff, timeout, e **nunca** propaga
exceção. Qualquer falha de rede/timeout vira `WorkerResponse(status="failed")`.
O node function (`make_agent_node`) consome isso e escreve
`{"status": {nodeId: "failed"}}` no State; o grafo **não** aborta.

```python
# worker_execute: nunca raise
async def worker_execute(agent_id, inputs, *, timeout, max_retries, ...) -> WorkerResponse:
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{WORKER_URL}/execute", json=payload)
            resp.raise_for_status()
            return WorkerResponse(**resp.json())
        except (httpx.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))
    return WorkerResponse(status="failed", ..., error=f"worker unreachable: {last_err}")
```

**Teste:** `test_worker_down_node_failed_graph_survives` — worker falha, nó A fica
`failed`, pipeline `failed`, mas o grafo **segue** para o nó de aprovação (não aborta).

### ADR-002 — State schema FIXO

`main.py` → `State = TypedDict("State", {...})` com keys fixas e reducers explícitos.
Nunca TypedDict dinâmico (quebra no checkpoint round-trip).

```python
State = TypedDict("State", {
    "data": Annotated[dict, _merge_dicts],          # merge por chave (nodeId)
    "actions": Annotated[dict, _merge_dicts],
    "status": Annotated[dict, _merge_dicts],
    "iterations": Annotated[dict, _sum_dicts],      # SOMA por chave (ADR-005)
    "max_iter_exceeded": Annotated[bool, operator.or_],
    "pipeline_status": str,
})
```

**Divergência do contrato:** o contrato pede `iterations: Annotated[int, operator.add]`
(int simples). O schema fixo (ADR-002) tem `iterations` como **dict por nodeId**
(`{nodeId: int}`), então o reducer de soma é `_sum_dicts` (soma por chave), não
`operator.add` direto. Equivalente em comportamento, e JSON-serializável.

### ADR-003 — Namespace por nodeId é convenção de valor

`state["data"][nodeId]`, `state["actions"][nodeId]`, etc. O namespacing é **dentro**
dos valores do dict, nunca no schema. O reducer `_merge_dicts` (overwrite por chave)
garante que cada nó escreve só a sua chave sem perder as dos outros.

### ADR-004 — Resume sempre recompila o grafo

`main.py` → `compile_and_resume()`: recompila o `StateGraph` do JSON
(`compile_pipeline(PipelineJSON(**json))`) e chama `ainvoke(Command(resume=...))`.
O checkpoint sobrevive por `thread_id` (PostgresSaver).

```python
async def compile_and_resume(pipeline_json, saver, config, resume_value):
    graph = compile_pipeline(PipelineJSON(**pipeline_json)).compile(checkpointer=saver)
    snap = graph.get_state(config)
    resume_config = snap.config if snap is not None else config
    await graph.ainvoke(Command(resume=resume_value), config=resume_config)
    final_snap = graph.get_state(config)
    return dict(final_snap.values)
```

**Teste:** `test_resume_after_process_restart` — novo saver, novo grafo compilado,
retoma do checkpoint salvo (mesmo `thread_id`).

### ADR-005/007 — maxIterations checado no início; iterations = soma

`main.py` → `make_agent_node()`: no **início** da node function, lê
`state["iterations"][nodeId]` e compara com `maxIterations`. Se excedido, **não**
roda o agente, escreve `status="failed"` + `max_iter_exceeded=True`. O reducer
`_sum_dicts` (soma por chave) garante que o contador acumula entre execuções.

```python
async def agent_node(state):
    iters = state.get("iterations", {}).get(node_id, 0)
    if iters >= max_iterations:
        return {"status": {node_id: "failed"}, "max_iter_exceeded": True, ...}
    # ... roda o worker, incrementa iterations (soma)
    return {"iterations": {node_id: 1}, ...}
```

**Teste:** `test_max_iterations_cuts_loop` — `max_iterations=2`, loop-back por
rejeição, após 2 execuções o nó A não roda mais e a pipeline vai para `failed`.

### ADR-006 — Command(goto=<id real>); rejectTarget configurável

`main.py` → `make_approval_node()`: aprovar → `Command(goto=approve_target)`,
rejeitar → `Command(goto=reject_target)`. `reject_target` vem da configuração da
aresta (`edge.rejectTarget`); default: loop-back para o source.

```python
async def approval_node(state, config):
    decision = interrupt({"message": message, ...})
    if decision == "approved":
        return Command(goto=approve_target)
    return Command(goto=reject_target)
```

**Testes:** `test_approve_completes_pipeline` (aprovar → B roda),
`test_reject_loops_back` (rejeitar → loop-back pro A).

### ADR-009 — ApprovalRequest upsert pós-interrupt

`main.py` → `ApprovalStore.upsert()`: chave `(runId, nodeId, interruptId)`.
O `interrupt_id` é o **task id real** do LangGraph (`CONFIG_KEY_TASK_ID`), estável
entre execuções/resumes da mesma pausa. Upsert idempotente: re-execuções não duplicam.

```python
async def approval_node(state, config):
    from langgraph.constants import CONFIG_KEY_TASK_ID
    interrupt_id = config.get("configurable", {}).get(CONFIG_KEY_TASK_ID, "int-0")
    decision = interrupt({"message": message, ...})
    approval_store.upsert(run_id, node_id, interrupt_id, message)  # pós-interrupt
    ...
```

## Divergências da API real (langgraph 0.2.61)

### 1. `stream.interrupted` / `stream.interrupts` NÃO existem

O contrato (§3) menciona `stream.interrupted` / `stream.interrupts` como forma de
detectar interrupção. **Não existem** na API real. A forma correta:

- **`astream(stream_mode="updates")`**: o interrupt aparece como update
  `{"__interrupt__": (Interrupt(...),)}`. Detectar: `if "__interrupt__" in update`.
- **`get_state(config)`**: retorna `StateSnapshot` com `tasks` (tupla de `PregelTask`),
  cada um com `interrupts` (tupla de `Interrupt`). Detectar:
  `any(t.interrupts for t in snap.tasks)`.

**Trecho canônico (streaming + detecção):**
```python
async for update in graph.astream(initial_state, config=config, stream_mode="updates"):
    if "__interrupt__" in update:
        interrupted = True
        break
# Estado completo:
snap = graph.get_state(config)
final_state = dict(snap.values)
```

### 2. `ainvoke`/`invoke` devolve só o delta do último superstep

**Surpresa:** `graph.ainvoke(...)` retorna o update do **último** nó executado,
**não** o estado completo. Para o estado completo, usar `get_state(config).values`
após o invoke. Isso afeta `compile_and_resume` e `run_pipeline`.

### 3. `interrupt()` re-executa o nó do zero (confirmado)

O docstring do `interrupt()` diz explicitamente: *"The graph resumes from the start
of the node, **re-executing** all logic."* Isso confirma o risco V-02 da análise:
efeitos colaterais **antes** do `interrupt()` duplicam. A solução (ADR-009) é
colocar efeitos colaterais **após** o `interrupt()` com upsert idempotente.

### 4. `PostgresSaver` (síncrono) não tem métodos async nativos

`langgraph-checkpoint-postgres` 2.0.10: a classe `PostgresSaver` implementa **só**
os métodos síncronos (`get_tuple`, `put`, `list`, `put_writes`). Os métodos async
(`aget_tuple`, `aput`, ...) herdam stubs de `BaseCheckpointSaver` que levantam
`NotImplementedError`. Como os nós do grafo são assíncronos (httpx), o `astream`
precisa de um bridge. **Solução:** subclasse `PostgresSaver` com métodos async que
delegam para os síncronos via `asyncio.to_thread`.

```python
class PostgresSaver(SyncPostgresSaver):
    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)
    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)
    # ... etc
```

### 5. `Command(resume=X)` + `Command(goto=Y)` no mesmo nó

O nó de aprovação usa `interrupt()` (que recebe o valor de `Command(resume=X)`) e
retorna `Command(goto=Y)`. Isso funciona: o `resume` é consumido pelo `interrupt()`,
e o `goto` é retornado pelo node function. **Não** há conflito.

### 6. `iterations` como dict (não int)

O contrato pede `iterations: Annotated[int, operator.add]`. O schema fixo (ADR-002)
tem `iterations` como **dict por nodeId** (`{nodeId: int}`), então o reducer é
`_sum_dicts` (soma por chave). Equivalente em comportamento.

## Resultado dos testes

```
7 passed in 3.66s

test_compile_pipeline_builds_graph PASSED
test_approve_completes_pipeline PASSED
test_reject_loops_back PASSED
test_worker_down_node_failed_graph_survives PASSED
test_max_iterations_cuts_loop PASSED
test_resume_after_process_restart PASSED
test_streaming_detects_interrupt PASSED
```

## Arquivos

| Arquivo | Descrição |
|---|---|
| `spike/docker-compose.yml` | Postgres isolado (porta 15433, projeto `spike`) |
| `spike/worker.py` | FastAPI mínimo com `POST /execute` (simula agente) |
| `spike/main.py` | Pipeline A → [aprovação] → B com todos os ADRs |
| `spike/test_spike.py` | 7 testes cobrindo todos os padrões |
| `spike/README.md` | Este arquivo |
