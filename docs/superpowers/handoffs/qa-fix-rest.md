# QA Fix Médias e Baixas — handoff (nó qa-fix-rest)

Sessão de 2026-09-27, logo após o fechamento do qa-fix (mesma sessão, checkout principal, `main`).

## Tabela falha -> causa -> correção -> teste

| Falha | Causa raiz | Arquivos | Correção | Teste |
|---|---|---|---|---|
| E1 (média) | UI exibia `error` do envelope (`conflict`, `validation error`), que o contrato §8 define como texto de máquina; o registro lia `data.error` direto | `agent-portal/lib/api.ts`, `lib/auth-client.ts` | Mensagem pt-BR a partir do `code` (específico) ou do `error` (classe) + primeiro item de `details.errors`; `errorMessageFromBody` reusado no registro | `lib/api.test.ts` (3 novos) |
| E3 (baixa) | chips da mochila usavam o id guardado (`skillId`, `toolId`, `serverId`, `reference`) | `components/agents/agent-detail.tsx` | `nameOf(options, id)` para skill, tool, MCP e knowledge (id sem correspondência cai no id) | `agent-detail.test.tsx` |
| E7 (média) | já corrigido pelo qa-fix junto com E8 (mesmo arquivo): placeholder `def execute(**kwargs)` e erro do sandbox exibido | `components/library/tools-editor.tsx` | sem mudança de código aqui | `tools-editor.test.tsx` (2 novos: placeholder e mensagem do sandbox) |
| E11 (baixa) | textos do editor/lista de pipelines em inglês e pt sem acento | `app/(dashboard)/pipelines/page.tsx`, `[id]/page.tsx`, `components/FlowEditor.tsx`, `EdgePanel.tsx`, `flow/agent-node.tsx`, `flow/agent-palette.tsx`, `flow/validation.ts` | Tradução pt-BR com acentos (textos, aria-labels, toasts, legendas, mensagens de validação local, "N nós / N arestas") | testes unitários e E2E atualizados para os novos textos |
| E15 (baixa) | grid fixo `240px 1fr` sem quebra estourava 390px | `components/library/knowledge-view.tsx` | layout flex com wrap (sidebar `1 1 240px`, painel `999 1 320px`, `minWidth: 0`) | E2E 09 (390px) |
| F15 (média) | upload decodificava os bytes do PDF como UTF-8 | `app/knowledge/extract.py` (novo), `app/api/knowledge.py`, `pyproject.toml` (`pypdf==5.1.0`) | texto das páginas via `pypdf`, antes de salvar; PDF ilegível -> 400 `invalid_file_type` | `tests/test_knowledge_extract.py`; integração `test_pdf_text_is_extracted_not_raw_bytes` |
| F16 (média) | JWT do WebSocket na query string registrado pelo nginx (`$request`) e pelo uvicorn (`"WebSocket /api/ws?token=..."`) | `nginx/nginx.conf`, `app/core/log_redaction.py` (novo), `app/main.py` | `map` no nginx gera `$request_redacted`; filtro de logging nos loggers `uvicorn.error`/`uvicorn.access` troca `token=`/`access_token=` por `[REDACTED]` | `tests/test_log_redaction.py`; integração `test_tokens_not_logged` |
| F17 (média) | `GITHUB_API_BASE` fixo | `app/integrations/github.py`, `app/core/config.py`, `.env.example` | `settings.github_api_base` (default api.github.com) | `test_integrations_github_mock.py::test_api_base_configurable` |
| F18 (média) | resposta JSON do LLM (o mock devolve `{"output": ...}`) era usada como veio, ignorando a porta declarada | `agent-worker/app/worker.py` | `_map_to_declared_outputs`: sem nenhuma porta declarada na resposta, o conteúdo vai para a primeira porta | `agent-worker/tests/test_output_ports.py` |
| F19 (baixa) | resolvida pelo qa-fix (mesma causa: `_trigger_resume` agora usa o executor compartilhado, sem checkpointer por resposta) | — | — | integração HITL |
| F20 (baixa) | worker recebia o `.env` inteiro (`env_file`) | `docker-compose.yml` | worker sem `env_file`; só `WORKER_TOKEN`, `MINIO_*`, LLM | `docker compose config` (lista de env do worker) |
| Extra | `PUT` com `entryNodeId` nulo (pipeline vazia) dava 400 | `app/api/pipelines.py` | UUID nulo = não definido | integração `test_empty_pipeline_accepts_first_graph` |

## Provedor compatível com OpenAI (item obrigatório)

- Orchestrator: `OPENAI_BASE_URL`, `LLM_MODEL`, `EMBEDDING_BASE_URL` (vazio = `OPENAI_BASE_URL`), `EMBEDDING_MODEL` em `app/core/config.py`; `app/core/llm.py` e `app/core/embeddings.py`.
- Worker: `OPENAI_BASE_URL` e `LLM_MODEL` em `app/core/llm.py`.
- Provider real ativa com `LLM_PROVIDER=openai` (ou `EMBEDDING_PROVIDER=openai`) e chave **ou** URL; chave vazia vira o placeholder `local`.
- `LLM_MODEL`, se definido, sobrepõe o modelo de cada agente (servidor local só serve o modelo carregado). Decisão registrada.
- Embeddings: vetor menor que `EMBEDDING_DIM` é completado com zeros; maior falha com `ValueError` claro.
- `docker-compose.yml` e `.env.example`: novas variáveis, defaults mantêm o mock.
- `.env` local configurado com o provedor da rede (`192.168.18.4`). As suítes rodam em mock sobrescrevendo por ambiente: `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock docker compose -p squad-agentica up -d`.
- Testes: `tests/test_core_providers.py` (orchestrator, 9) e `agent-worker/tests/test_llm_provider.py` (4).
- Disponibilidade em 2026-09-27: LLM `http://192.168.18.4:1234/v1/models` respondeu com `Qwen3.8-27B-Q8_0`; embeddings `http://192.168.18.4:4321` recusou conexão (curl exit 7). Ressalva para o QA Final.

## Commits

Os arquivos tocados pelos dois nós (ex.: `docker-compose.yml`, `lib/api.ts`, `agent-detail.tsx`, `FlowEditor.tsx`, `main.py`) não foram separados hunk a hunk: cada arquivo entrou no commit do assunto mais recente que o tocou, com nota no corpo.
