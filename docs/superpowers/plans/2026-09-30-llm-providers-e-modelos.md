# Provedores e modelos de LLM nas Integrações — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Quando executar:** depois do plano `2026-09-30-menus-e-modais.md` (Tasks 19–26). As Tasks 27–33 continuam a numeração. A aba LLM usa o `Popover`, o `Modal` `lg` e o `ScrollArea` daquele plano.

**Goal:** Permitir cadastrar, testar e escolher provedores e modelos de LLM (chat e embeddings) na tela Integrações, sem editar `.env`, mantendo as variáveis de ambiente como fallback para que instalações existentes continuem funcionando.

**Architecture:** O tipo `llm` entra na tabela `integrations` existente, com a chave criptografada como o token Git. Um resolvedor único no orquestrador aplica a precedência (agente → padrão do usuário → ambiente) e entrega uma conexão pronta para o chat de construção, o chat da Knowledge, o RAG e a execução dos agentes. Para a execução, o orquestrador envia o bloco `llm` ao worker em cada `POST /execute`, como já faz com `mcpServers`, porque o worker não tem banco nem segredos. O portal ganha a aba LLM e o seletor de modelo no detalhe do agente.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, cryptography (Fernet), openai SDK, pytest; Next.js 14, React 18, vitest e Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-redesign-usabilidade-design.md`, seção 8 (adendo de 2026-09-30).

## Global Constraints

- Valem as restrições dos planos anteriores (pt-BR, erros com recuperação, contraste, regras de modal e rolagem da seção 7 da spec, commits com `Co-Authored-By`, nunca fazer push, `git add` só com caminhos explícitos, não tocar em `.codex/`, reiniciar o `portal` antes de verificar no navegador).
- **Compatibilidade:** sem nenhuma conexão cadastrada, o comportamento é exatamente o de hoje (variáveis de ambiente). Nenhuma API existente muda de forma incompatível; campos novos são aditivos.
- **Segredos:** a chave de API é criptografada em repouso (`core/secrets.py`), nunca devolvida pela API (só `apiKeyHint`), mascarada por `core/log_redaction.py` e ausente de runs, checkpoints, eventos WebSocket, logs do worker e mensagens de erro.
- **Migrações:** encadeadas na head vigente no momento da execução (conferir com `alembic heads`), com `alembic check` limpo. `ALTER TYPE ... ADD VALUE` não roda em transação; usar `op.get_context().autocommit_block()`.
- **Sem chamadas reais em testes:** HTTP simulado; nenhum teste usa chave ou servidor real.

## Review Focus

1. **Vazamento da chave.** Procurar a chave em respostas de API, logs do orquestrador e do worker, payloads de checkpoint e eventos WS, com um teste que grava uma chave sentinela e varre tudo.
2. **Precedência.** Agente com modelo explícito vence padrão do usuário, que vence o ambiente; `LLM_MODEL` só vale sem escolha. Um teste por degrau.
3. **Isolamento por dono.** Um `integrationId` de outro usuário responde 404, nunca a conexão dele.
4. **Worker sem `llm`.** Requisição sem o bloco usa o ambiente, exatamente como hoje.
5. **Embeddings e dimensões.** Dimensão > 1536 é recusada no teste; troca de modelo exige confirmação e oferece reindexar.

---

## Estrutura de arquivos

- `agent-orchestrator/app/core/llm.py` e `core/embeddings.py`: interface de adaptador e fábrica por conexão; `OpenAILLMClient` já serve para OpenAI e compatível.
- `agent-orchestrator/app/llm/` (novo): `resolver.py` (precedência), `connections.py` (CRUD e leitura com segredo), `discovery.py` (`/models`), `schemas.py`.
- `agent-orchestrator/app/api/integrations.py` (ou `api/llm_connections.py`): rotas da aba LLM e `POST /llm/test`.
- `agent-orchestrator/app/db/models.py` e migração: valor `llm` no enum e `users.preferences`.
- `agent-orchestrator/app/runtime/executor.py` e `runtime/worker_client.py`: resolver e enviar o bloco `llm`.
- `agent-worker/app/main.py`, `app/worker.py` e `app/core/llm.py`: aceitar e usar o bloco `llm`.
- `agent-orchestrator/app/agents/` (validator e storage): campo opcional `llm` no YAML; `api/agents.py`: `effectiveModel` e a conexão efetiva.
- `agent-portal/components/integrations/`: `llm-connections.tsx`, `llm-connection-form.tsx`; `components/agents/agent-detail.tsx`: seletor de modelo.
- `tests/integration/fake_git_api.py`: endpoints `/v1/models` e `/v1/chat/completions` do fake.

---

### Task 27: Modelo de dados e armazenamento seguro das conexões

**Files:**
- Modify: `agent-orchestrator/app/db/models.py`, `agent-orchestrator/app/core/secrets.py` (se precisar de helpers)
- Create: migração Alembic, `agent-orchestrator/app/llm/__init__.py`, `app/llm/connections.py`, `tests/test_llm_connections.py`

- [ ] **Step 1: Testes (falham primeiro).** Criar conexão `llm` com chave; o banco guarda `api_key_encrypted` e não a chave em claro; a leitura pública devolve só `apiKeyHint` (últimos 4); leitura com segredo só por função interna; isolamento por dono; nome único por dono; migração sobe e desce e `alembic check` fica limpo.
- [ ] **Step 2: Migração.** Adicionar `llm` ao enum `integration_type` (com `autocommit_block`) e a coluna `users.preferences` JSONB com default `{}`.
- [ ] **Step 3: `connections.py`.** CRUD com criptografia, `apiKeyHint`, validação de `provider_kind` (`openai|compatible|mock`), `base_url`, `models[]`, `default_model` e bloco `embedding` (`model`, `dim` ≤ 1536, prefixos). Preferências do usuário: `default_llm_integration_id` e `default_embedding_integration_id`, validadas como do dono.
- [ ] **Step 4: Rodar** pytest dos arquivos novos, `ruff` e `alembic check`.
- [ ] **Step 5: Commit** — `feat(llm): conexoes de LLM nas integracoes com chave criptografada`

---

### Task 28: Adaptadores e resolvedor de precedência

**Files:**
- Modify: `agent-orchestrator/app/core/llm.py`, `app/core/embeddings.py`
- Create: `agent-orchestrator/app/llm/resolver.py`, `tests/test_llm_resolver.py`

- [ ] **Step 1: Testes (falham primeiro).** Precedência em três degraus: agente com `llm` explícito; padrão do usuário; ambiente. `LLM_MODEL` só vale sem escolha explícita. Conexão apagada ou inativa cai para o ambiente com aviso. Modelo do agente ausente na conexão cai para o padrão da conexão com aviso. `integrationId` de outro dono responde "não encontrado".
- [ ] **Step 2: Interface única.** `get_llm_client(connection=None)` e `get_embedder(connection=None)` aceitam uma conexão resolvida; sem ela, mantêm o comportamento atual (variáveis de ambiente). Adaptadores: OpenAI, compatível (mesma classe com `base_url`) e mock.
- [ ] **Step 3: `resolver.py`.** `resolve_chat(owner, agent_llm=None)` e `resolve_embedding(owner)` devolvem `ResolvedLLM(kind, base_url, api_key, model, source, warnings)`. `source` indica `agent|user|env`, usado pela UI.
- [ ] **Step 4: Rodar** pytest do orquestrador (arquivos tocados), `ruff`.
- [ ] **Step 5: Commit** — `feat(llm): resolvedor de conexao com precedencia agente, usuario e ambiente`

---

### Task 29: API de conexões LLM, descoberta de modelos e teste

**Files:**
- Modify: `agent-orchestrator/app/api/integrations.py` (ou criar `app/api/llm_connections.py` e registrar)
- Create: `agent-orchestrator/app/llm/discovery.py`, `tests/test_llm_api.py`

- [ ] **Step 1: Testes (falham primeiro).**
  - listar, criar, editar e excluir conexões LLM do dono; a resposta nunca contém a chave;
  - `POST /api/integrations/llm/models` (sem salvar) consulta `GET {url}/models` e devolve os ids; servidor sem listagem devolve lista vazia com o motivo;
  - `POST /api/integrations/llm/test` (sem salvar, corpo com a chave digitada) faz um chat mínimo e, se houver embeddings, uma chamada de embedding, e devolve `{ok, latencyMs, model, embeddingDim, error?}`; a chave não aparece na resposta nem nos logs; não grava nada;
  - embedding com dimensão > 1536 falha com mensagem clara;
  - `PUT /api/users/me/llm-defaults` (ou equivalente) grava os padrões; excluir a padrão os limpa e lista os agentes afetados.
- [ ] **Step 2: Implementar** as rotas com o mesmo padrão de `last_test_status` e `last_tested_at` das integrações Git. Erros do provedor traduzidos para pt-BR.
- [ ] **Step 3: Varredura de vazamento.** Teste com chave sentinela que executa criar, testar e listar e varre respostas e logs capturados.
- [ ] **Step 4: Rodar** pytest e `ruff`.
- [ ] **Step 5: Commit** — `feat(llm): api de conexoes, descoberta de modelos e teste sem salvar`

---

### Task 30: Execução — orquestrador envia o bloco `llm` e o worker o usa

**Files:**
- Modify: `agent-orchestrator/app/runtime/executor.py`, `app/runtime/worker_client.py`, `app/api/agent_chat.py`, `app/knowledge/chat.py`, `app/knowledge/embedder.py`, `app/agents/` (campo `llm` no YAML e no validador)
- Modify: `agent-worker/app/main.py`, `agent-worker/app/worker.py`, `agent-worker/app/core/llm.py`
- Create/Modify: testes em ambos os serviços

- [ ] **Step 1: Testes (falham primeiro).**
  - executor resolve a conexão por nó e passa `llm` ao `WorkerClient`; sem conexão, não envia o bloco;
  - worker com `llm` usa `base_url`, chave e modelo do bloco; sem `llm`, usa o ambiente como hoje; a chave não aparece em log do worker;
  - chat de construção e chat da Knowledge usam a conexão padrão de chat do dono; RAG usa a de embeddings;
  - mudança de conexão durante um run vale a partir do próximo nó;
  - a chave não é gravada em run, checkpoint nem evento WS (teste com sentinela).
- [ ] **Step 2: Campo `llm` do agente.** `llm: {integrationId, model}` opcional no YAML e no validador, ignorado por quem não o conhece. Nada de migração de agentes existentes.
- [ ] **Step 3: Implementar** o envio do bloco `llm` no `POST /execute` (Pydantic do worker com `llm: dict | None`), a fábrica do worker por bloco e a troca dos consumidores do orquestrador para o resolvedor. Garantir que o NGINX :8081 não registra corpo de requisição.
- [ ] **Step 4: Rodar** pytest dos dois serviços e `ruff`.
- [ ] **Step 5: Commit** — `feat(llm): execucao usa a conexao resolvida; worker recebe o bloco llm`

---

### Task 31: Portal — aba LLM nas Integrações

**Files:**
- Create: `agent-portal/components/integrations/llm-connections.tsx`, `llm-connection-form.tsx` e testes
- Modify: `agent-portal/components/integrations/integrations-view.tsx`, `agent-portal/lib/types.ts`, `agent-portal/lib/api.ts`

- [ ] **Step 1: Testes (falham primeiro).** A aba LLM aparece ao lado de GitHub, Azure DevOps e Outras; a tabela mostra nome, provedor, URL, modelo padrão, chave (`…últimos 4`), status do último teste e ⋮ (Editar, Testar, Definir como padrão, Excluir); a primeira linha, somente leitura, é "Padrão do ambiente" com provedor e modelo e sem chave. Excluir avisa quais agentes usam a conexão e se é padrão.
- [ ] **Step 2: Modal de conexão** (`size="lg"`, duas colunas, sem rolagem, regra da seção 7). Esquerda: nome, tipo de provedor, URL base, chave (com aviso de que fica criptografada e nunca é mostrada de novo). Direita: modelos (botão "Descobrir modelos", lista selecionável e campo para digitar à mão), modelo padrão e, em seção de largura total, embeddings (modelo, dimensões, prefixos) com aviso de reindexação ao trocar. "Testar" mostra inline sucesso, latência, modelo e dimensões, ou o erro traduzido; salvar continua permitido com teste falho.
- [ ] **Step 3: Padrões.** Ações "Definir como padrão para chat" e "para embeddings", com indicação visual na tabela.
- [ ] **Step 4: Rodar** vitest de `integrations`, `tsc` e lint. Reiniciar o `portal` e conferir no navegador em 1440×900 e 390px.
- [ ] **Step 5: Commit** — `feat(portal): aba LLM nas integracoes`

---

### Task 32: Portal — seletor de modelo no agente e avisos

**Files:**
- Modify: `agent-portal/components/agents/agent-detail.tsx` (aba Execução/Visão geral), `agent-portal/lib/agents.ts`, testes; `agent-orchestrator/app/api/agents.py` (conexão e modelo efetivos)

- [ ] **Step 1: Testes (falham primeiro).** O detalhe do agente mostra o seletor `conexão · modelo` alimentado pelas conexões do dono, com "Padrão"; o modelo efetivo e sua origem (agente, padrão do usuário, ambiente) aparecem num lugar só; aviso quando a conexão escolhida foi apagada ou o modelo sumiu; o chat de construção de agente propõe e grava o mesmo campo.
- [ ] **Step 2: Implementar** o seletor e a origem do modelo (`effectiveModel` + `modelSource`), no lugar da nota atual sobre `LLM_MODEL`. O campo `model` legado continua lido.
- [ ] **Step 3: Rodar** vitest de `agents`, pytest de `api/agents`, `tsc` e lint.
- [ ] **Step 4: Commit** — `feat(agentes): escolher conexao e modelo de LLM no agente`

---

### Task 33: Fake, e2e, QA e registro

**Files:**
- Modify: `tests/integration/fake_git_api.py` (endpoints `/v1/models` e `/v1/chat/completions`)
- Create: `agent-orchestrator/tests/integration/test_llm_connections.py`, `e2e/tests/13-llm-providers.spec.ts`
- Modify: `docs/superpowers/validacoes/qa-redesign.md`, `docs/superpowers/validacoes/PENDENCIAS.md`

- [ ] **Step 1: Fake compatível.** Acrescentar ao serviço `git-test` os endpoints `GET /v1/models` e `POST /v1/chat/completions` (resposta determinística com o nome do modelo) e `POST /v1/embeddings` (vetor fixo).
- [ ] **Step 2: Integração.** Subir a stack com o ambiente em `mock`, cadastrar uma conexão compatível apontando para o fake, definir como padrão e executar um pipeline de dois agentes; afirmar que a resposta vem do fake (nome do modelo no resultado). Afirmar também que a chave sentinela não aparece em nenhuma resposta nem log.
- [ ] **Step 3: e2e.** Na tela, criar a conexão, descobrir modelos, testar, definir como padrão, escolher o modelo no agente, executar e ler o resultado; repetir o fluxo em 390px. Conferir as regras de modal e rolagem (sem rolagem do corpo em 1280×720).
- [ ] **Step 4: QA real (opcional, com o usuário).** O usuário cadastra uma conexão real (LM Studio local ou OpenAI) pela tela; eu executo o pipeline e confiro o resultado. Eu não digito chaves reais.
- [ ] **Step 5: Regressão e registro.** pytest dos dois serviços, vitest, `tsc`, lint, `npm run build` e as specs e2e afetadas, uma por vez; registrar contagens e capturas em `qa-redesign.md` e as pendências em `PENDENCIAS.md`.
- [ ] **Step 6: Commit** — `test(llm): integracao e e2e de provedores e modelos, QA e registro`
