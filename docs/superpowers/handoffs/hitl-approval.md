# Handoff: hitl-approval (FASE 7 - HITL Approval)

**Veredito:** Implementado e testado. Merge commit: `6256285`.

## Arquivos criados/alterados

**Criados:**
- `agent-orchestrator/app/approvals/__init__.py`
- `agent-orchestrator/app/approvals/node_function.py`
- `agent-orchestrator/app/approvals/service.py`
- `agent-orchestrator/app/api/approvals.py`
- `agent-orchestrator/tests/test_hitl_approval.py`

**Alterados:**
- `agent-orchestrator/app/runtime/executor.py` (injeta task id real no payload do interrupt)
- `agent-orchestrator/app/compiler/graph_builder.py` (delega `_make_approval_node` para hitl-approval)

## Contratos públicos expostos

### `app/approvals/node_function.py`
- `create_approval_node(edge: PipelineEdge, source_node_id: str) -> Callable`
  - Factory do nó de aprovação. O compiler importa e registra no StateGraph.
  - `approval_node_function` = alias de `create_approval_node`.
  - Semântica: monta payload (puro, sem side effects), chama `interrupt(payload)`,
    ao retomar retorna `Command(goto=...)`:
    - aprovar -> `Command(goto=target)`
    - rejeitar -> `Command(goto=reject_target)` (loop-back pro source ou END)
    - argumentar -> `Command(update={"data": {sourceNodeId: {"humanFeedback": feedback}}}, goto=target)`
  - Constantes: `DECISION_APPROVED`, `DECISION_REJECTED`, `DECISION_REVISED`, `HUMAN_FEEDBACK_KEY`.

### `app/approvals/service.py`
- `upsert_approval_request(session, *, owner_id, pipeline_id, run_id, node_id, interrupt_id, payload) -> tuple[ApprovalRequest, bool]`
  - Upsert idempotente por chave `(pipeline_id, node_id, checkpoint_id)` onde `checkpoint_id = interrupt_id`.
  - Retorna `(approval, created)`: `created=True` se criou agora, `False` se já existia.
- `build_approval_hook(session_factory) -> Callable`
  - Devolve o callback com a assinatura do hook do executor:
    `async def hook(run_id, pipeline_id, node_id, interrupt_payload, thread_id)`.
  - Fluxo: extrai `__interruptId__` do payload, upsert da ApprovalRequest,
    se `created=True` emite `approval:new` via WebSocket.

### `app/api/approvals.py`
- `GET /api/approvals` (query: `?status=pending|resolved|cancelled&pipelineId=&page=&limit=`)
- `GET /api/approvals/{id}` (detalhe)
- `POST /api/approvals/{id}/respond` (body: `{"decision": "approved"|"rejected"|"revised", "response"?: str}`)
  - 404 se não existe ou não é do owner.
  - 409 `already_responded` se já respondida ou run cancelado.
  - Emite `approval:resolved` via WebSocket.
  - Chama `compile_and_resume` do hitl-resume (import lazy; se não existe, adia).

## Decisões tomadas

1. **Chave de idempotência:** `(pipeline_id, node_id, checkpoint_id)` onde `checkpoint_id` guarda o `interrupt_id` (task id real do LangGraph, `PregelTask.id` == `CONFIG_KEY_TASK_ID`). O executor injeta o task id no payload sob `__interruptId__`.

2. **Nó de aprovação sem side effects antes do interrupt (ADR-009):** O nó só monta o payload (puro) e chama `interrupt()`. A persistência da ApprovalRequest e a notificação são feitas pelo executor (hook), não pelo nó.

3. **Argumentar (revised):** O feedback do humano é injetado no State via `Command(update={"data": {sourceNodeId: {"humanFeedback": feedback}}}, goto=target)`. O agente target lê `data[sourceNodeId].humanFeedback` e retoma com a informação.

4. **Compiler delega para hitl-approval:** O `_make_approval_node` do compiler agora chama `create_approval_node` do hitl-approval (import lazy para evitar circular import). O compiler não tem mais a implementação do nó de aprovação.

5. **Executor injeta task id:** O `_handle_interrupt_from_tasks` do executor agora injeta `task.id` (task id real) no payload sob `__interruptId__` para o hook consumir.

## Comandos de verificação

```bash
# Testes (16/16 passando)
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_hitl_approval.py -v

# Suíte completa (459/459 passando)
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/ -v

# Ruff (passando)
docker compose -p squad-agentica run --rm --no-deps --entrypoint ruff orchestrator check app/approvals/ app/api/approvals.py app/runtime/executor.py app/compiler/graph_builder.py tests/test_hitl_approval.py

# Mypy (só erros pré-existentes em models.py e graph_builder.py; nenhum erro novo nos arquivos do hitl-approval)
docker compose -p squad-agentica run --rm --no-deps --entrypoint mypy orchestrator app/approvals/ app/api/approvals.py
```

## Pendências

1. **`compile_and_resume` do hitl-resume:** O `app/api/approvals.py` importa `compile_and_resume` de `app/approvals/resume.py` (nó hitl-resume, em paralelo). Se o hitl-resume ainda não existe, o import falha e o resume é adiado (loga warning). A assinatura esperada é:
   ```python
   async def compile_and_resume(
       pipeline_id: str,
       run_id: str,
       checkpointer: Any,
       thread_id: str,
       resume_value: dict[str, Any],
   ) -> None
   ```
   O hitl-resume precisa implementar esta função.

2. **Registro do hook no startup:** O `build_approval_hook(session_factory)` precisa ser registrado no executor via `register_approval_hook()` no startup da aplicação. O nó hitl-approval fornece o hook, mas o registro no `main.py` (dono: infra-docker) ou no lifespan do executor precisa ser feito. Sugestão: no `main.py` ou no `pipeline_runs.py` (dono: rt-executor), chamar:
   ```python
   from app.approvals.service import build_approval_hook
   from app.db.session import async_session_factory
   from app.runtime.executor import register_approval_hook
   register_approval_hook(build_approval_hook(async_session_factory))
   ```

3. **`agent_id` na ApprovalRequest:** O hook não preenche `agent_id` (coluna nullable). O payload do interrupt não carrega o `agentId` diretamente. Se necessário, o nó de aprovação pode adicionar `agentId` ao payload.

## Skills usadas

- Nenhuma skill específica carregada. Segui o protocolo comum do flow Agent Portal Dev e as fontes de verdade (CONTRATO-TECNICO.md, D7, spec 4.5/5.3/9.6, spike).
