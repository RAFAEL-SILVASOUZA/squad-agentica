# Handoff: rt-review (FASE 6 - Runtime)

**Veredito:** APROVADO. Merge commit: ver `git log --oneline --merges -1`.

## Inventário do que existe

### agent-orchestrator/app/runtime/

| Arquivo | Conteúdo |
|---------|----------|
| `__init__.py` | Package marker |
| `checkpoint.py` | `create_checkpointer(db_url) -> AsyncPostgresSaver`, `close_checkpointer(cp)`, `checkpointer_context(db_url)`, `make_thread_id(pipeline_id, run_id) -> "pid:rid"` |
| `worker_client.py` | `HttpWorkerClient` (implementa Protocol `WorkerClient` do compiler). POST `http://nginx:8081/execute`, header `X-Worker-Token`, retry 3x backoff 2/4/8s, timeout por request. **Nunca levanta exceção** (ADR-001). |
| `executor.py` | `PipelineExecutor(worker_client, checkpointer, global_timeout=3600)`. Métodos: `execute(pipeline, owner_id, initial_inputs) -> run_id`, `pause(pipeline_id) -> run_id`, `resume(pipeline, owner_id, run_id) -> run_id`, `stop(pipeline_id) -> run_id`. Hook: `register_approval_hook(callback)`. Exceções: `PipelineAlreadyRunningError` (409), `NoActiveRunError` (404), `RateLimitError` (429). Rate limit: 5/min por pipeline (in-memory). |
| `websocket.py` | `ConnectionManager` (singleton `manager`), `publish(owner_id, channel, data)`. Canais válidos: `pipeline:status`, `pipeline:log`, `approval:new`, `approval:resolved`, `agent:output`. Heartbeat 30s. Filtro por owner. |

### agent-orchestrator/app/api/

| Arquivo | Rotas |
|---------|-------|
| `pipeline_runs.py` | `POST /api/pipelines/{id}/execute`, `POST /api/pipelines/{id}/pause`, `POST /api/pipelines/{id}/resume`, `POST /api/pipelines/{id}/stop`, `GET /api/pipelines/{id}/runs`, `GET /api/pipelines/{id}/checkpoints`, `POST /api/pipelines/{id}/checkpoints/{cpId}/resume` |
| `ws.py` | `WS /api/ws?token=<JWT>` (handshake: JWT validado, close 4000 se inválido) |

### agent-worker/app/

| Arquivo | Conteúdo |
|---------|----------|
| `main.py` | FastAPI app. `GET /health`, `POST /execute` (auth `X-Worker-Token`, 401 se ausente/errado). |
| `worker.py` | `execute_agent(agent_id, node_id, inputs, timeout, *, llm, artifact_client) -> ExecutionResult`. LLM loop com tool calls (max 10 iterações). Shell blocklist. `EXTERNAL_DATA` markers. |
| `minio_client.py` | `GarageClient` (S3 via minio lib), `AgentArtifactClient` Protocol, `LocalCache` (TTL 300s). |
| `core/llm.py` | `LLMClient` Protocol, `MockLLMClient`, `OpenAILLMClient`, `get_llm_client()` (factory por `LLM_PROVIDER`). |

### Testes

| Arquivo | Testes |
|---------|--------|
| `agent-orchestrator/tests/test_rt_checkpoint.py` | 9 (banco de teste isolado) |
| `agent-orchestrator/tests/test_rt_worker_client.py` | 14 (httpx MockTransport) |
| `agent-orchestrator/tests/test_rt_executor.py` | 13 (MemorySaver + FakeWorker) |
| `agent-orchestrator/tests/test_rt_websocket.py` | 15 (TestClient) |
| `agent-worker/tests/test_worker_execute.py` | 15 (TestClient + mocks) |
| `agent-worker/tests/test_health.py` | 1 |

**Total: 67 testes de runtime, todos passando.**

## Contratos públicos

### Worker HTTP (contrato §2.3)
- `POST http://nginx:8081/execute`
- Header: `X-Worker-Token: <WORKER_TOKEN>`
- Body: `{"agentId": "uuid", "nodeId": "node-1", "inputs": {...}, "timeout": 60}`
- Response 200: `{"status": "completed"|"failed", "outputs": {...}, "action": "follow"|"return"|"finalize", "iterations": int, "logs": [str], "error"?: str}`
- Response 401: `{"error": "unauthorized", "code": "worker_token_invalid"}`
- Response 404: `{"error": "agent_not_found", "code": "agent_not_found"}`

### WebSocket (contrato §7, spec 9.7)
- `wss(s)://<host>/api/ws?token=<JWT>`
- Frame: `{"channel": "<string>", "data": <any>}`
- Canais: `pipeline:status`, `pipeline:log`, `approval:new`, `approval:resolved`, `agent:output`
- Filtro por ownerId; cliente não manda subscribe.

### Executor API (spec 9.1)
- `POST /api/pipelines/{id}/execute` -> `{runId, status, threadId}` (409 se running, 429 se rate limited)
- `POST /api/pipelines/{id}/pause` -> `{runId, status}`
- `POST /api/pipelines/{id}/resume` -> `{runId, status}`
- `POST /api/pipelines/{id}/stop` -> `{runId, status}` (cancela aprovações pendentes)
- `GET /api/pipelines/{id}/runs` -> paginado
- `GET /api/pipelines/{id}/checkpoints` -> paginado
- `POST /api/pipelines/{id}/checkpoints/{cpId}/resume` -> `{runId, status, resumedFromCheckpoint}`

### Approval hook (ponto de extensão para hitl-approval)
- `register_approval_hook(callback)` no `app.runtime.executor`
- Callback: `async def hook(run_id, pipeline_id, node_id, interrupt_payload, thread_id) -> None`
- Chamado pelo executor ao detectar interrupt no stream.

## Comandos para subir e testar

```bash
# Stack completo
docker compose up -d --build

# Testes orchestrator (443 testes)
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/ -v

# Testes worker (16 testes)
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest agent-worker tests/ -v

# Lint
docker compose -p squad-agentica run --rm --no-deps --entrypoint ruff orchestrator check app/runtime/ app/api/pipeline_runs.py app/api/ws.py
docker compose -p squad-agentica run --rm --no-deps --entrypoint ruff agent-worker check app/ tests/
```

## Ressalvas

1. **E2E via API bloqueado por bug pré-existente:** o client Minio 7.2.13 rejeita `http://garage:3900` com "path in endpoint is not allowed". Isso afeta a criação de agentes (500) e impede o teste E2E completo via API. Não é um problema do runtime; é um problema do `app/agents/storage.py` (dono: be-agents) ou do pin de versão do Minio. Os testes unitários de runtime cobrem todos os cenários com mocks.

2. **Executor singleton lazy:** a inicialização do executor (checkpointer) é lazy no primeiro request (`_get_executor()` em `pipeline_runs.py`). Em produção, idealmente no `lifespan` do FastAPI app. Pendência para infra-docker ou hitl-approval.

3. **`_active_runs` in-memory:** V1 single-process. Em multi-process, precisaria de Redis ou DB lock.

4. **MCP tool execution:** V1 não executa MCP tools no worker (retorna error "not executable"). Fica para V2.

5. **Orchestrator deve enriquecer snapshot:** antes de dispatchar ao worker, o orchestrator deve serializar CustomTools (com `definition`) e MCP tools (com `tools` list) nos refs do YAML. Sem isso, o worker não tem acesso a essas tools.

## Skills usadas

Nenhuma skill externa aplicável. Revisão baseada em contrato técnico, spec, code review e execução de testes.
