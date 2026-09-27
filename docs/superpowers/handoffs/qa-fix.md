# QA Fix — handoff (nó qa-fix)

## Resumo

Correções de causa raiz das falhas críticas/altas (F1–F14, E2, E4, E5, E6, E8, E9, E10, E12, E13) + lacunas de contrato (CRUD/validate de pipeline, GET /api/artifacts/:id, evento approval:new, checkpoints/artefatos por nó, owner filtering do runtime, envelope 422, masking de segredos, worker-down pausa).

## Estado (retomável)

### Fechamento em 2026-09-27 (retomada final)

- Correção adicional: `PUT /api/pipelines/{id}` com o `entryNodeId` nulo que a própria API devolve para pipeline vazia dava 400 (`_build_pipeline_from_body` validava o UUID nulo antes de tratá-lo). Agora o UUID nulo equivale a "não definido" e a entrada vira o primeiro nó. `test_empty_pipeline_accepts_first_graph` passa (test_04: 13 passed).
- `test_ws_rejects_invalid_token_with_policy_violation` passou na suíte completa: a falha residual de WS no-token não se reproduziu.
- Ambiente recriado com `docker compose down -v` + `up -d --build` (banco e Garage vazios): `garage-init` criou agents/skills/knowledge; migrations e seed rodaram; stack saudável.
- Suítes finais e commits: ver `docs/superpowers/handoffs/qa-fix-rest.md` (os dois nós foram fechados na mesma sessão; as verificações completas foram feitas depois das correções de ambos).

### Retomada em 2026-09-27

- Portal completo: **367 passed**, TypeScript e ESLint sem erros.
- Orchestrator completo: **498 passed**, 10 avisos preexistentes.
- Integração completa: **85 passed, 3 failed, 1 skipped**. Falhas: F15 (PDF cru), F16 (JWT nos logs), e limite de execução retornando 500. Esta última foi corrigida e o teste focal passou (1 passed); F15/F16 continuam atribuídas ao qa-fix-rest no flow.
- Aprovação, rejeição com loop, cancelamento e validação de entrada inválida: **8 passed** após correções desta retomada.
- Correções adicionais: query da KB usa `knowledgeBaseIds` e resposta `chunks`; fixtures do portal refletem paginação, `source` e `args`; erro de criação da KB preserva detalhes textuais; `pipelineId` filtra aprovações; enum aceita `cancelled`; retomada humana usa o executor compartilhado (checkpointer assíncrono, eventos, persistência e novas aprovações); validação de entrada ausente devolve 400 `invalid_graph`; rejeição por 409/429 faz rollback do run ainda não persistido em vez de `delete` em objeto pending (causa do 500).
- Teste HITL reforçado para exigir evento final agregado: conclusão de um nó não comprova conclusão do run.
- Neste host, usar `QA_BASE_URL=http://127.0.0.1` e `QA_DB_DSN=postgresql://agent_portal:agent_portal@127.0.0.1:15432/agent_portal`. IPv6 `::1` expira, tornando `localhost` extremamente lento. Nenhum código de rede de produção alterado por isso.
- E2E do monitor em verificação. Dependências do lockfile e Chromium do Playwright instalados nesta retomada.
- Revisão por subagente não foi executada: o agente revisor encerrou por limite de uso. Não conta como aprovação.
- Orientação atual do usuário: terminar QA Fix; próximos nós não iniciados. O YAML do flow não foi alterado. A duplicação de testes no qa-fix-rest/qa-final foi apontada para decisão posterior.

- **Unit (orchestrator):** 498 passed (inclui novo teste E2 `test_confirm_draft_without_name_rejected`).
- **Portal:** `npx tsc --noEmit` exit 0; `npm run lint` ok; vitest dos componentes tocados 43 passed.
- **Ruff (arquivos tocados):** all checks passed.
- **Integração:** suíte em execução (bg-8) contra stack de pé com banco NOVO (valida F2). Rodada anterior (antes da correção do banco novo): 71 errors todos por `UndefinedTableError` (alembic nunca rodava no dev override em banco novo) + 1 failed (WS no-token timeout, ver abaixo).
- **Stack:** `docker compose -p squad-agentica` com volumes novos; garage bootstrap via CLI (ver F5).

## Tabela falha -> causa -> correção (resumo)

| Falha | Causa raiz | Correção |
|---|---|---|
| F1 (crít) | `graph.get_state` síncrono sobre AsyncPostgresSaver | `aget_state`/`aget_tuple` em `executor.py` |
| F2 (crít) | checkpointer criado no 1º request dentro de transação aberta (CREATE INDEX CONCURRENTLY deadlock) | lifespan em `main.py` inicializa checkpointer + executor no boot |
| F3 (crít) | worker passava `MINIO_ENDPOINT` com esquema p/ `Minio()` | strip de scheme em `agent-worker/app/minio_client.py` |
| F4 (crít) | runtime de pipeline sem filtro de owner | `_load_pipeline(owner)` + checks em pause/resume/stop/runs/checkpoints/resume-from-checkpoint |
| F5 (crít) | `garage-init` usava init.py (S3 API) que não importa a access key; em volume novo NENHUM bucket era criado (AccessDenied) | novo bootstrap `garage/Dockerfile.init` + `init.sh` (CLI `garage`: key import, bucket create agents/skills/knowledge, allow RWO); compose repontado |
| F6 (crít) | hook de aprovação nunca registrado; approvalId = task id LangGraph | lifespan registra `build_approval_hook`; hook retorna id persistida; executor usa no `approval:new` |
| F7 (alta) | 2 runIds (API vs executor) | API cria PipelineRun e passa run_id ao executor; status final persistido (`_persist_run_status`) |
| F8 (alta) | 409/429 deixavam run órfão | delete do run + reset de status em except |
| F9 (alta) | CRUD/validate de pipeline ausentes | `app/api/pipelines.py` (novo) |
| F10 (alta) | sem checkpoints/artefatos; GET /api/artifacts/:id ausente | `_persist_checkpoint`/`_persist_artifacts` no executor; `app/api/artifacts.py` (novo) |
| F11 (alta) | só status agregado no WS | `pipeline:status` por nó + `agent:output` em `_process_stream_update` |
| F12 (alta) | segredos em claro nas respostas | masking em `_to_response` de mcp_servers.py e integrations.py; update preserva `***` |
| F13 (alta) | 422 de field_validator virava 500 (ValueError não serializável) | handler 422 com `jsonable_encoder` em `errors.py` |
| F14 (alta) | worker fora do ar -> failed em vez de paused | `WorkerUnavailableError` (distingue indisponibilidade de falha do agente); executor pausa |
| E2 (alta) | confirm criava "Unnamed Agent" | backend rejeita draft sem nome (400 incomplete_draft); frontend desabilita Save |
| E4 (alta) | porta nova tipo `string` fora da whitelist | PORT_TYPE_OPTIONS = document/code/artifact/signal |
| E5 (alta) | modal sem rolagem | maxHeight 85vh + overflowY auto |
| E6 (crít) | form de KB não enviava `source` | knowledge-view.tsx |
| E8 (alta) | teste de tool enviava `{input}` | `{args}` em tools-editor.tsx |
| E9 (crít) | UI esperava array, endpoint paginado | knowledge-view.tsx |
| E10 (crít) | upload forçava multipart sem boundary | FormData em knowledge-view.tsx |
| E12 (alta) | 404 /pipelines vira "No pipelines yet" | api.ts ApiError + estado de erro na listagem |
| E13 (crít) | EdgePanel não atualizava o grafo salvo | forwardRef `updateEdge` no FlowEditor; page chama em handleEdgeChange |

## Banco novo: alembic no dev override (causa raiz da rodada 1)

`docker-compose.override.yml` (dono infra-docker) trocava o entrypoint de produção por `uvicorn --reload`, pulando `alembic upgrade head`. Em banco preservado é invisível; em `down -v` todo o stack quebra (`UndefinedTableError` no register). Corrigido: o override agora roda `alembic upgrade head || true; python -m app.db.seed || true; exec uvicorn ... --reload`. **Mudança em arquivo de outro dono (infra-docker), aplicada porque era pré-requisito para qualquer teste em banco novo; registrar para o revisor.**

## WSS no-token: 1 falha residual

`test_ws_rejects_invalid_token_with_policy_violation` (test_07): espera close 1008 ou InvalidStatus; obteve timeout no connect. O código do endpoint fecha com 4000 (contrato §7). Provável: nginx dev sem proxy de upgrade correto no caminho, ou o close pós-aceite do upgrade. Verificar após a rodada: checar `docker compose logs nginx` e o header `Upgrade` de volta. Se o close 4000 chega, ajustar o teste para aceitar 4000 (o contrato define 4000, não 1008) OU o nginx. **Não corrigido ainda** (esperando evidência da rodada atual).

## Médias/baixas delegadas ao próximo nó (QA Fix Médias e Baixas)

- E1 (média) mensagem de erro crua na UI (ApiError melhorado parcialmente em E12; resta polimento de `body.error`).
- E3 (baixa) chip de skill mostra UUID em agent-detail.tsx:771.
- E7 (média) placeholder da tool `def main(inputs)` vs `execute(**args)` + erro "Erro" vago (tools-editor.tsx).
- E11 (baixa) editor/lista pipelines/EdgePanel em inglês ou PT sem acento.
- E14 (alta -> feito) link /pipelines na sidebar.
- E15 (baixa) overflow horizontal 13px em /knowledge 390px.
- F15 (média) PDF indexado como bytes crus (knowledge.py decodifica sem extrair texto).
- F16 (média) JWT nos logs (nginx log_format / uvicorn).
- F17 (média) GITHUB_API_BASE fixo (skip do teste de GitHub mockado).
- F18 (média) saída mock do worker usa `output` quando o snapshot tem `outputs` vazia; no caso padrão (ports declaradas) já usa o nome certo.
- F19 (baixa) `_trigger_resume` cria checkpointer por resposta sem fechar (approvals.py).
- F20 (baixa) worker carrega GARAGE_RPC_SECRET/ADMIN_TOKEN no ambiente.
- Jornadas E2E bloqueadas (J6/J8) devem passar com F1/F6/F7/F10/F11/F14 corrigidos; E5/E6/E9/E10/E12/E13 corrigidas. J7 passa.

## Decisões (registradas)

- `_NIL_ENTRY` (UUID nulo) como entryNodeId de pipeline sem nós (coluna NOT NULL); validador regra 9 bloqueia execução; PUT com primeiro nó define a entrada.
- E2: guarda limitada ao NOME (não name+prompt): os testes existentes (`test_confirm_saves_agent`, `test_confirm_invalid_contract_rejected`) definem que draft com nome confirmável; o restante do contrato segue no `invalid_graph`.
- Artefatos: tipo de porta declarado (document/code/artifact) vira ArtifactType quando mapeável; senão inferência por nome/conteúdo.
- `garage-init`: imagem nova `squad-agentica-garage-init` (python:3.11-slim + binário garage copiado) porque a imagem oficial `dxflrs/garage` é distroless (sem shell) e não executa init.sh; o CLI precisa do node key (volume `garage-data:ro`).

## Verificação pendente / a fazer

- [x] unit 498 passed
- [x] portal tsc/lint/vitest
- [x] ruff arquivos tocados
- [x] suíte de integração completa — WS no-token passou; restantes eram F15/F16 (qa-fix-rest) e o PUT com entrada nula (corrigido)
- [x] `docker compose down -v && up -d --build` após todas as correções
- [x] commits por assunto (feat/fix/test qa-fix)
