# Handoff: be-review (FASE 4 aprovada)

**Data:** 2026-09-24
**Veredito:** APROVADO
**Merge commits da fase:** f2a74b6 (be-agents), 187bea6 (be-agent-chat), c6ff1b4 (be-skills), 12a2804 (be-knowledge), e097f01 (be-integrations)

## Inventário de módulos

### Agentes (be-agents)
- `app/api/agents.py` - Router CRUD
- `app/agents/__init__.py`
- `app/agents/service.py` - AgentService (CRUD + validação + persistência dupla)
- `app/agents/validator.py` - Validação de contrato (ports, actions)
- `app/agents/storage.py` - GarageAgentStorage (S3 via minio)
- `app/agents/base.py` - Agent, AgentSnapshot, AgentCapabilities, create_agent_from_snapshot

### Chat de construção (be-agent-chat)
- `app/api/agent_chat.py` - Router SSE (chat, edit, confirm)
- `app/agents/chat/__init__.py`
- `app/agents/chat/conversation.py` - DraftStore (in-memory, TTL 1h)
- `app/agents/chat/proposal.py` - System prompts, parse_llm_response, validate_config
- `app/agents/chat/preview.py` - build_preview

### Skills (be-skills)
- `app/api/skills.py` - Router CRUD + builtins
- `app/skills/__init__.py`
- `app/skills/registry.py` - CRUD com sync Postgres + Garage
- `app/skills/storage.py` - S3 client bucket skills
- `app/skills/builtins/__init__.py` - 6 skills built-in (in-memory)

### Tools (be-skills)
- `app/api/tools.py` - Router CRUD + deploy + test
- `app/tools/__init__.py`
- `app/tools/registry.py` - CRUD tools custom
- `app/tools/validator.py` - Valida script Python + contrato I/O
- `app/tools/sandbox.py` - Subprocesso isolado, timeout 30s/120s
- `app/tools/builtins/__init__.py` - 9 ferramentas + blocklist shell + executores

### MCP (be-skills)
- `app/api/mcp_servers.py` - Router CRUD + test
- `app/mcp/__init__.py`
- `app/mcp/registry.py` - CRUD servidores MCP
- `app/mcp/client.py` - stdio/sse/http, tools/list, tools/call
- `app/mcp/validator.py` - Valida config de conexão

### Knowledge (be-knowledge)
- `app/api/knowledge.py` - Router CRUD + upload + documents + query
- `app/knowledge/__init__.py`
- `app/knowledge/chunker.py` - chunk_text (512/64 default)
- `app/knowledge/embedder.py` - RagEmbedder wrapper
- `app/knowledge/rag.py` - RagService (ingest + query)
- `app/knowledge/storage.py` - GarageKnowledgeStorage (bucket knowledge)
- `app/knowledge/rivvn.py` - Stub (is_rivvn_available=False, rivvn_query=501)

### Integrações (be-integrations)
- `app/api/integrations.py` - Router CRUD + GitHub + Rivvn
- `app/integrations/__init__.py`
- `app/integrations/github.py` - GitHub client (repos, pulls, issues, pr_diff) + wrap_external_data
- `app/integrations/registry.py` - CRUD integrações

## Endpoints registrados (FASE 4)

| Método | Rota | Nó |
|--------|------|-----|
| POST | /api/agents | be-agents |
| GET | /api/agents | be-agents |
| GET | /api/agents/{id} | be-agents |
| PUT | /api/agents/{id} | be-agents |
| DELETE | /api/agents/{id} | be-agents |
| POST | /api/agents/chat | be-agent-chat |
| POST | /api/agents/{id}/chat | be-agent-chat |
| POST | /api/agents/chat/confirm | be-agent-chat |
| GET | /api/skills | be-skills |
| POST | /api/skills | be-skills |
| GET | /api/skills/{id} | be-skills |
| PUT | /api/skills/{id} | be-skills |
| DELETE | /api/skills/{id} | be-skills |
| GET | /api/skills/builtins | be-skills |
| GET | /api/tools | be-skills |
| POST | /api/tools | be-skills |
| GET | /api/tools/{id} | be-skills |
| PUT | /api/tools/{id} | be-skills |
| DELETE | /api/tools/{id} | be-skills |
| POST | /api/tools/{id}/deploy | be-skills |
| POST | /api/tools/{id}/test | be-skills |
| GET | /api/mcp-servers | be-skills |
| POST | /api/mcp-servers | be-skills |
| GET | /api/mcp-servers/{id} | be-skills |
| PUT | /api/mcp-servers/{id} | be-skills |
| DELETE | /api/mcp-servers/{id} | be-skills |
| POST | /api/mcp-servers/{id}/test | be-skills |
| POST | /api/knowledge | be-knowledge |
| GET | /api/knowledge | be-knowledge |
| GET | /api/knowledge/{id} | be-knowledge |
| PUT | /api/knowledge/{id} | be-knowledge |
| DELETE | /api/knowledge/{id} | be-knowledge |
| POST | /api/knowledge/{id}/upload | be-knowledge |
| GET | /api/knowledge/{id}/documents | be-knowledge |
| DELETE | /api/knowledge/{id}/documents/{docId} | be-knowledge |
| POST | /api/knowledge/query | be-knowledge |
| GET | /api/integrations | be-integrations |
| POST | /api/integrations | be-integrations |
| GET | /api/integrations/{id} | be-integrations |
| PUT | /api/integrations/{id} | be-integrations |
| DELETE | /api/integrations/{id} | be-integrations |
| GET | /api/integrations/github/repos | be-integrations |
| GET | /api/integrations/github/repos/{owner}/{repo}/pulls | be-integrations |
| GET | /api/integrations/github/repos/{owner}/{repo}/issues | be-integrations |
| GET | /api/integrations/rivvn/authorize | be-integrations |
| GET | /api/integrations/rivvn/callback | be-integrations |
| GET | /api/integrations/rivvn/status | be-integrations |
| DELETE | /api/integrations/rivvn | be-integrations |

## Contratos públicos (para FASE 5+)

### AgentService (para chat e runtime)
```python
from app.agents.service import AgentService, validate_contract
service = AgentService(storage=optional_storage)
await service.create_agent(db, owner_id, data_dict) -> Agent
await service.get_agent(db, owner_id, agent_id) -> Agent
await service.list_agents(db, owner_id, page, limit, type_filter) -> (list[Agent], int)
await service.update_agent(db, owner_id, agent_id, data_dict) -> Agent
await service.delete_agent(db, owner_id, agent_id) -> None
validate_contract(inputs, outputs, actions) -> ValidationResult
```

### Base agent (para worker/runtime)
```python
from app.agents.base import Agent, AgentSnapshot, AgentCapabilities, create_agent_from_snapshot
agent = create_agent_from_snapshot(snapshot, llm)
output = await agent.run(inputs: dict, capabilities: AgentCapabilities) -> dict
```

### Storage (protocolo para mock em testes)
```python
from app.agents.storage import AgentStorage, GarageAgentStorage, get_agent_storage
```

### Chat (para portal/frontend)
```python
from app.agents.chat.conversation import draft_store, AgentDraft
from app.agents.chat.proposal import parse_llm_response, validate_config, draft_to_agent_data
from app.agents.chat.preview import build_preview
```

### Knowledge RAG (para runtime D6)
```python
from app.knowledge.rag import RagService
await RagService.query(db, owner_id, text, knowledge_base_ids, top_k?, agent_id?, pipeline_id?) -> list[dict]
```

### GitHub tools (para be-loader, FASE 5)
```python
from app.integrations.github import wrap_external_data, list_repos, list_pulls, list_issues, get_pr_diff
```

### Shell blocklist (para worker)
```python
from app.tools.builtins import check_shell_command, list_builtin_tools, TOOL_EXECUTORS
```

### Tool sandbox (para worker)
```python
from app.tools.sandbox import ToolSandbox
sandbox = ToolSandbox(timeout=30)
result = await sandbox.execute(script, args, env=None, timeout=None)
```

## Config (app/core/config.py)

Novos campos adicionados pelo revisor:
- `minio_bucket_knowledge: str = "knowledge"`
- `github_token: str = ""`

## Comandos de verificação

```bash
# Lint
docker compose -p squad-agentica run --rm --no-deps --entrypoint ruff orchestrator check app/ tests/
# Resultado: All checks passed!

# Testes
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/ -q
# Resultado: 320 passed in 106.26s

# Rotas registradas
docker compose -p squad-agentica run --rm --no-deps --entrypoint python orchestrator -c "from app.main import app; [print(f'{m} {r.path}') for r in app.routes if hasattr(r,'methods') for m in r.methods if m!='HEAD']"
```

## Ressalvas (não bloqueantes)

1. **Sandbox V1:** subprocesso com restrições de ambiente, não é isolamento de kernel. Mitigação: roda dentro do container Docker com limits. Documentado em `tools/sandbox.py`.
2. **Shell blocklist:** substring match (lowercase). Falsos positivos aceitáveis na V1 (ex: "mountain" contém "mount").
3. **MCP stdio tests:** testes de subprocesso MCP via stdio não funcionam de forma confiável no container. Testes HTTP mock + test_failed_connection cobrem a lógica. Integração com servidor MCP real fica para FASE 6.
4. **409 graph_running:** não implementado em PUT/DELETE /api/agents/{id} (requer consulta a PipelineRun que é de FASE 5/6).
5. **Draft store in-memory:** V1 single-user. TTL 1h. Não persiste entre restarts.
6. **Skills builtins:** servidas em memória (não persistidas no Postgres/Garage). O loader (FASE 5) consulta via `list_builtin_skills()`.

## Mudanças aplicadas pelo revisor

1. `app/core/config.py`: +`minio_bucket_knowledge`, +`github_token`
2. `.env.example`: +`MINIO_BUCKET_KNOWLEDGE=knowledge`, +`GITHUB_TOKEN=`
3. `garage/init.py`: +bucket `knowledge` no bootstrap
4. `app/integrations/github.py`: usa `settings.github_token` em vez de `os.environ.get`
5. `tests/test_integrations_github_mock.py`: mocks atualizados para `settings.github_token`
