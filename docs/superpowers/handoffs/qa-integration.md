# QA Integration: relatório (2026-09-26)

Nó `qa-integration`, depois do `fe-review` aprovado (rodada 4, `b5239d6`). Stack `docker compose -p squad-agentica` de pé (7 containers healthy, 2 réplicas do worker), `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=mock`. Nenhum código de produto foi alterado.

## Como rodar (QA Final)

```bash
cd tests/integration
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt   # Windows; em Linux: .venv/bin/...
.venv/Scripts/python -m pytest -v          # ~10 min (o sleep de 61s do teste de rate limit do login está incluído)
```

- Roda no host contra `http://localhost` (NGINX). Use `localhost`, não `127.0.0.1`: neste host o IPv4 :80 responde outro serviço (`404 page not found`), e o NGINX está no `::1`.
- Postgres em `localhost:15432`, usado só para semear pipelines (B1) e para limpar os dados no fim.
- Cada cenário (módulo) tem os próprios usuários `qa-int-*@example.com`. No teardown, os agentes são removidos pela API (Garage) e o usuário pelo `DELETE FROM users`, que apaga o resto em cascata. Uma varredura de sessão remove sobras.
- Resiliência e ciclo de vida param e religam as réplicas do worker (`docker compose stop/start agent-worker`, `docker stop <réplica>`). O teardown sempre religa.
- O servidor MCP fake (`fake_mcp_server.py`) sobe como container sidecar na rede `squad-agentica_default`, usando a imagem do orchestrator.

## Resultado final

`29 failed, 59 passed, 1 skipped in 595s`. Execução final completa, com saída em `pytest -v`.

| # | Cenário | Status | Evidência (testes) |
|---|---|---|---|
| 1 | Auth | **Parcial** (12/14) | Passam: registro, 409 de duplicado, login, `/me`, refresh com rotação (o refresh antigo leva 401), access token recusado no refresh, 401 genérico, 401 sem token em 11 rotas, **rota nova desconhecida leva 401** (opt-out), openapi/docs protegidos. Falham: 422 de validação vira **500** (F13) e `admin@local` leva 500 (B2). |
| 2 | Agente, skill, tool, MCP, GitHub | **Passa** (17/17 + 1 skip) | CRUD de agente com ports, 400 estruturado (`action_whitelist`, `port_type_whitelist`, `port_name_unique`), 409 de nome, chat mock. Skill CRUD e vínculo. Tool: draft, deploy (versão +1), teste no sandbox, 422 no script inválido, erro e timeout estruturados, sandbox sem env de segredos. MCP fake: `connected` + `discoveredTools=[qa_echo]`, `error` se inalcançável. GitHub: CRUD, 400 `invalid_config`, 404/502 estruturados. **Skip:** API GitHub mockada (F17). |
| 3 | Knowledge | **Falha** (1/5) | Todo upload leva `500 storage_error` (F5). Diagnóstico com o bucket criado à mão: 4/5 passam, e o PDF é indexado cru (F15). |
| 4 | Pipeline | **Falha** (2/11) | CRUD e validate ausentes (B1). Execução: todo run termina `failed` (F1 e F3). runId divergente (F7). Sem eventos por nó nem `agent:output` (F11). Sem checkpoints nem artefatos (F10). Passam: formato da resposta do execute e 404 de pipeline inexistente. |
| 5 | HITL | **Falha** (2/6) | `approval:new` nunca é emitido (F1) e a ApprovalRequest nunca é persistida (F6). Passam: 400 `invalid_decision`, 404 de aprovação inexistente e o formato da listagem. |
| 6 | Pause, resume, stop, 409 | **Falha** (1/6) | 409 `pipeline_already_running` sai, mas com o runId do executor (F7). Pause e stop respondem 200 com runId ≠ execute (F7). PUT durante o run leva 404 (B1). Passa: 404 de pause/resume/stop sem run. |
| 7 | Segurança | **Parcial** (18/21) | Passam: isolamento de CRUD em agents, skills, tools, mcp-servers, knowledge e integrations (GET/PUT/DELETE levam 404, fora da lista); deploy, test e query cruzados; isolamento de aprovações e do WebSocket; WS recusa token inválido e refresh token; worker fora da :80 (`/execute` leva 307 para `/login` do portal); portas 8081/9000/8000/3000 fechadas; **rate limits com 429 no envelope e `retryAfter`**: execute 5/min, chat 30/min, upload 10/min, login 5/min. Falham: isolamento do runtime de pipeline (F4), segredos devolvidos (F12), token nos logs (F16). |
| 8 | Resiliência | **Falha** (0/2) | Com uma réplica parada o run termina `failed`. Sem réplicas termina `failed`, e não `paused` retomável (F14, mascarado por F1 e F3). |

## Falhas por severidade

Formato de cada item: passo, esperado, obtido, logs, hipótese e arquivo provável.

### Críticas

**F1: todo run termina `failed`, porque `graph.get_state` é síncrono sobre o `AsyncPostgresSaver`.**
- Passo: `POST /api/pipelines/{id}/execute` numa pipeline de 2 nós.
- Esperado: `completed`, ou `waiting_approval` quando há HITL.
- Obtido: WS `pipeline:status {status:"failed", nodeId:""}`. Isso aconteceu em 23 de 23 runs.
- Log (`docker compose logs orchestrator`): `Pipeline execution error ... File "/app/app/runtime/executor.py", line 425, in _run_stream ... InvalidStateError: Synchronous calls to AsyncPostgresSaver are only allowed from a different thread ... use await checkpointer.aget_tuple(...)`.
- Hipótese: `snap = graph.get_state(config)` precisa ser `await graph.aget_state(config)`. Por isso nenhum interrupt é tratado (HITL morto) e nenhum run completa.
- Arquivo: `agent-orchestrator/app/runtime/executor.py:425` (rt-executor).

**F2: o primeiro execute com o banco sem as tabelas de checkpoint trava para sempre (deadlock).**
- Passo: primeiro `POST .../execute` depois de subir o stack.
- Obtido: ReadTimeout. No `pg_stat_activity`, o `CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoint_blobs_thread_id_idx` aparece em `Lock/virtualxid`, esperando a própria sessão SQLAlchemy do request (`idle in transaction`, `SELECT pipeline_edges...`).
- Hipótese: `_get_executor()` → `create_checkpointer()` → `saver.setup()` é chamado depois de `_load_pipeline()` já ter aberto uma transação, e o `CONCURRENTLY` espera todas as transações abertas, inclusive essa.
- Correção provável: inicializar o checkpointer no startup (lifespan) ou antes de qualquer query do request.
- **Ação de QA:** para seguir com os testes, destravei com `pg_terminate_backend` da sessão ociosa. As migrações do checkpointer 6 e 7 completaram. No banco de dev atual o bug não reproduz mais. Num banco novo, reproduz.
- Arquivos: `agent-orchestrator/app/api/pipeline_runs.py:55-70,203-211` e `app/runtime/checkpoint.py` (rt-executor).

**F3: o worker nunca executa um agente (endpoint S3 com esquema).**
- Log do worker: `minio_client.py:111 ... ValueError: path in endpoint is not allowed`, e o `/execute` devolve `{"status":"failed","error":"Execution error: ValueError: path in endpoint is not allowed"}`.
- Prova: `docker compose run --rm --no-deps -e MINIO_ENDPOINT=garage:3900 --entrypoint python agent-worker -c "...execute_agent(...)"` devolve `status: completed`, `outputs: {"output": "MOCK_LLM: echo of: ## spec\nx"}`. Com `http://garage:3900` (o valor do `.env`) devolve failed.
- Hipótese: o worker passa `MINIO_ENDPOINT` cru para `Minio()`. O orchestrator normaliza com `settings.minio_endpoint_host`, o worker não.
- Arquivo: `agent-worker/app/minio_client.py:30,111` (dono do worker / infra-garage).

**F4: o runtime de pipeline não filtra por owner.**
- Passo: B chama os endpoints de runtime da pipeline de A.
- Obtido: `POST /api/pipelines/{A}/execute` leva **200**, com o run criado com `owner_id = B` e executando o grafo de A. `GET .../runs` e `GET .../checkpoints` levam 200 (vazio), e o esperado é 404. `pause` e `stop` indexam `_active_runs` só pelo `pipeline_id`, então B consegue pausar ou parar o run ativo de A.
- Arquivos: `agent-orchestrator/app/api/pipeline_runs.py` (`_load_pipeline` sem `Pipeline.owner_id == user.id`, `list_runs`, `list_checkpoints`, `pause/resume/stop`, `resume_from_checkpoint`) (rt-executor).

**F5: o upload de knowledge sempre dá 500 `storage_error`.**
- Reprodução no container: `S3Error AccessDenied: Access key adminkey01 is not allowed to create buckets, resource: /knowledge`. `garage bucket list` mostra só `agents` e `skills`.
- Arquivo: `garage/init.sh:105-118` não cria nem autoriza o bucket `knowledge` (infra-garage).
- **Diagnóstico de QA (temporário, desfeito):** criei `knowledge` com `allow RWO` para `adminkey01` e o cenário 3 passou 4/5. Depois esvaziei e apaguei o bucket, e o Garage voltou ao estado original.

**F6: a ApprovalRequest nunca é persistida (hook de HITL não registrado).**
- `grep` confirma que `register_approval_hook` / `build_approval_hook` não são chamados em lugar nenhum do app (nem `main.py` nem lifespan). Com isso o `_approval_hook` é `None`, o executor só loga `Interrupt detected but no approval hook registered`, e `GET /api/approvals` fica sempre vazio.
- Além disso, o `approval:new.approvalId` é o task id do LangGraph, e não o `ApprovalRequest.id`.
- Hoje o F1 mascara isso: o interrupt nem chega a ser detectado.
- Arquivos: `app/approvals/service.py:190` (`build_approval_hook`) e o registro no startup (`app/main.py`, infra-docker, ou um módulo do hitl-approval). Também `executor.py:541-551`.

### Altas

- **F7: dois runIds.** O endpoint cria `PipelineRun` X e responde X. O `executor.execute` gera outro `run_id` Y e usa Y no WS, no `pause/stop` (a resposta foi `{"runId": Y}`) e em `409.details.runId`. O `pipeline_runs.status` de X nunca sai de `running` (sem `completedAt`), porque o executor não atualiza o banco. Arquivos: `pipeline_runs.py:203-238`, `executor.py:204`.
- **F8: o 409 e o 429 deixam run órfão.** `execute` faz `db.commit()` do run e `pipeline.status="running"` antes de chamar o executor, e o `db.rollback()` do except não desfaz nada. Identificado na leitura do código; o teste `test_concurrent_execute_409_without_orphan_run` cobre, mas hoje para antes no assert do F7. Arquivo: `pipeline_runs.py:217-237`.
- **F9 (= B1): CRUD e validate de pipeline ausentes.** `POST/GET/PUT /api/pipelines[/{id}]` e `POST /api/pipelines/validate` levam 404/405, e `PUT` durante o run leva 404 em vez de 409 `graph_running`. Dono: rt-executor.
- **F10: sem checkpoints nem artefatos.** Nada escreve em `run_checkpoints` nem em `artifacts` (grep), e `GET /api/artifacts/:id` (spec 9.1) não existe. `GET /checkpoints` sempre vazio. Arquivos: `app/runtime/executor.py`, novo router de artefatos (rt-executor).
- **F11: o WebSocket só publica status agregado.** Nenhum `pipeline:status` por nó (`nodeId` sempre `""`), nenhum `agent:output` e nenhum `pipeline:log` (contrato §7). Arquivo: `executor.py` / `graph_builder.py`.
- **F12: segredos devolvidos pela API.** `mcp-servers.env` (`API_KEY`) e `integrations.config.token` voltam em claro em POST, GET e LIST. Arquivos: `app/api/mcp_servers.py:_to_response`, `app/api/integrations.py:_to_response` (mascarar valores).
- **F13 (= B2): qualquer 422 de `field_validator` vira 500.** Exemplos: `register` com e-mail inválido, e `login admin@local`. Log: `TypeError: Object of type ValueError is not JSON serializable` em `app/core/errors.py:44`. Soma-se ao regex que exige TLD em `app/auth/schemas.py:12`.
- **F14: sem worker o run falha em vez de pausar.** Com as 2 réplicas paradas o worker_client esgota o retry (logs `Worker HTTP error (attempt 3/3) ... HTTP 502`) e o run termina `failed`. Com 1 réplica parada também termina `failed`, mas aí por causa de F1 e F3. A node function marca `pipeline_status="failed"` e o executor não pausa, e o `resume` exige `PipelineRun.status=="paused"` no banco, que o executor nunca grava. Arquivos: `compiler/graph_builder.py:340-350`, `executor.py:430-444`, `pipeline_runs.py:resume`.

### Médias

- **F15: PDF indexado como bytes crus.** O chunk começa com `%PDF-1.4\n1 0 obj...`. O upload faz `data.decode("utf-8", errors="replace")` sem extrair texto. Arquivo: `app/api/knowledge.py:424-427` (be-knowledge).
- **F16: JWT nos logs.** O access log do uvicorn e do NGINX grava `GET /api/ws?token=eyJ...` (contrato §8: nunca logar token). Arquivos: `nginx/nginx.conf` (log_format com `$request`), flags do uvicorn / filtro de log (infra-nginx, infra-docker).
- **F17: API GitHub não mockável.** `GITHUB_API_BASE = "https://api.github.com"` fixo em `app/integrations/github.py:26`, sem variável de ambiente. O cenário "GitHub com API mockada" ficou `skip` até existir um override.
- **F18: saída mock do worker ignora o contrato de ports.** O output vem `{"output": ...}` e não `{"result": ...}` (a porta declarada do agente), então a data edge `result -> spec` não carrega nada. Arquivo: `agent-worker/app/worker.py:~873/1011`.

### Baixas

- **F19:** `_trigger_resume` cria um checkpointer (conexão psycopg nova) a cada resposta de aprovação e nunca fecha. Arquivo: `app/api/approvals.py:_trigger_resume`.
- **F20:** o worker carrega `GARAGE_RPC_SECRET` e `GARAGE_ADMIN_TOKEN` no ambiente sem precisar deles (privilégio mínimo). Arquivo: `docker-compose.yml` e `.env` via `env_file` (infra-docker).

## Pendências conhecidas (PENDENCIAS.md)

- **B1:** confirmado (F9). Afeta os cenários 4 e 6. A suite semeia as pipelines direto no banco para testar o resto.
- **B2:** confirmado e ampliado (F13). Não é só o login: todo 422 de `field_validator` vira 500.
- **C4:** é de frontend (grid do dashboard), fora do escopo desta suite de API. Nada a acrescentar.

## Intervenções de QA no ambiente (transparência)

1. `pg_terminate_backend` na sessão ociosa que travava o F2 (uma vez). Efeito colateral: as migrações 6 e 7 do checkpointer foram aplicadas no banco de dev.
2. Bucket `knowledge` criado para diagnóstico e depois removido (F5). O estado final é igual ao inicial.
3. Réplicas do worker paradas e religadas pelos testes. Ao final estão `Up (healthy)`.
4. Usuários de teste removidos. `SELECT count(*) FROM users WHERE email LIKE 'qa-%'` = 0.
