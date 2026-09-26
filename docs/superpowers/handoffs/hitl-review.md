# Handoff: HITL Review (FASE 7)

**Veredito:** APROVADO (com ressalvas não bloqueantes)

## Inventário do que existe

### Arquivos criados/alterados

**HITL Approval:**
- `agent-orchestrator/app/approvals/__init__.py`
- `agent-orchestrator/app/approvals/node_function.py` (função do nó de aprovação)
- `agent-orchestrator/app/approvals/service.py` (upsert idempotente + hook do executor)
- `agent-orchestrator/app/api/approvals.py` (endpoints REST)
- `agent-orchestrator/tests/test_hitl_approval.py` (16 testes)

**HITL Notification:**
- `agent-orchestrator/app/notifications/__init__.py`
- `agent-orchestrator/app/notifications/interface.py` (protocolo de canais)
- `agent-orchestrator/app/notifications/inapp.py` (canal WebSocket)
- `agent-orchestrator/app/notifications/email.py` (canal SMTP, desligado por padrão)
- `agent-orchestrator/app/notifications/teams.py` (stub V2)
- `agent-orchestrator/app/notifications/slack.py` (stub V2)
- `agent-orchestrator/app/notifications/service.py` (retry + fallback)
- `agent-orchestrator/tests/test_notify_inapp.py` (5 testes)
- `agent-orchestrator/tests/test_notify_email_disabled.py` (5 testes)
- `agent-orchestrator/tests/test_notify_fallback.py` (12 testes)

**HITL Resume:**
- `agent-orchestrator/app/approvals/resume.py` (recompilação + retomada)
- `agent-orchestrator/tests/test_hitl_resume.py` (16 testes)

**Integração:**
- `agent-orchestrator/app/runtime/executor.py` (injeta task id no payload do interrupt)
- `agent-orchestrator/app/compiler/graph_builder.py` (delega `_make_approval_node` para hitl-approval)

### Contratos públicos

**`node_function.py`:**
```python
def create_approval_node(edge, source_node_id) -> Callable
# alias: approval_node_function
# Sem side effects antes do interrupt()
# Ao retomar: Command(goto=target) (aprovar), Command(goto=reject_target) (rejeitar),
# ou Command(update={"data": {sourceNodeId: {"humanFeedback": feedback}}}, goto=target) (argumentar)
```

**`service.py`:**
```python
def upsert_approval_request(session, *, owner_id, pipeline_id, run_id, node_id, interrupt_id, payload) -> (ApprovalRequest, bool)
# idempotente por chave (pipeline_id, node_id, checkpoint_id)

def build_approval_hook(session_factory) -> Callable
# callback do executor: upsert + notificação approval:new
```

**`resume.py`:**
```python
async def compile_and_resume(pipeline_id, run_id, checkpointer, thread_id, resume_value, *, worker_client=None, owner_id=None, session=None) -> dict
# resume_value: str ("approved"|"rejected"|"revised"), dict ({"decision":..., "response":...}),
# ou mapa {interrupt_id: response} (fan-out)
# Returns: {"status": "completed"|"interrupted"|"paused"|"failed"|"no_pending_interrupt", "state": dict, "interrupted": bool}
# Raises: PipelineNotFoundError (404), RunCancelledError (409), NoPendingInterruptError (409)

async def compile_and_resume_with_pipeline(pipeline, checkpointer, thread_id, resume_value, *, worker_client, owner_id=None, run_id=None) -> dict
# variante que recebe a Pipeline dataclass já carregada
```

**`api/approvals.py`:**
```python
GET /api/approvals (filtros status/pipelineId, paginação)
GET /api/approvals/{id}
POST /api/approvals/{id}/respond (aprovar/rejeitar/argumentar, 409 already_responded, owner isolation, emite approval:resolved)
DELETE /api/approvals/{id}
```

**`notifications/service.py`:**
```python
async def notify(session, approval, channel, response_url=None) -> bool
async def notify_with_fallback(session, approval, primary, response_url=None) -> bool
def get_channel(name: NotificationChannel) -> ChannelNotifier
# NotificationChannel = Literal["in-app", "email", "teams", "slack"]
```

### Eventos WebSocket

- `approval:new`: quando uma ApprovalRequest é criada
- `approval:resolved`: quando uma ApprovalRequest é respondida
- `run:started`, `run:completed`, `run:failed`: ciclo de vida do run
- `node:started`, `node:completed`: ciclo de vida do nó

## Comandos para subir e testar

```bash
# Subir o stack
docker compose up -d

# Rodar testes HITL
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_hitl_approval.py tests/test_hitl_resume.py tests/test_notify_inapp.py tests/test_notify_fallback.py -v

# Rodar suíte completa
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/ -x -q

# Lint
cd agent-orchestrator && ruff check app/ tests/

# Type check
cd agent-orchestrator && mypy app/
```

## Ressalvas

1. **Hook não registrado no startup**: `register_approval_hook` não é chamado no `main.py`. Em produção, o HITL não funciona. **Ação necessária**: adicionar `register_approval_hook(build_approval_hook(async_session_factory))` no startup.
2. **Run_id mismatch**: a API `pipeline_runs.py` cria o `PipelineRun` com um `run_id`, mas o executor gera outro `run_id` interno. O `thread_id` diverge. **Ação necessária**: alinhar o `run_id` entre API e executor.
3. **E2E bloqueado pelo bug de auth**: `POST /api/auth/login` retorna 500 (bug de serialização JSON no handler de erro). **Ação necessária**: corrigir `app/core/errors.py`.

## Guia de API para o frontend

Ver `docs/superpowers/plans/GUIA-API-FRONTEND.md` para todos os endpoints REST e eventos WebSocket.

## Skills usadas

Nenhuma skill específica se aplicou além do protocolo comum do flow.
