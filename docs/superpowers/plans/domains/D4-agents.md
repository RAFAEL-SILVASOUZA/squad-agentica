# D4 — Agentes (CRUD + Contrato)

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 3 · Núcleo**. Dependência: **D3** (models + routers + tipos).
> Base: spec (seções 4.1 "Agente", 6.3 "Ferramentas Básicas", 10 "Chat de Construção") + plano.

## Objetivo

CRUD completo de agentes com validação de contrato (inputs/outputs/actions), a classe base do agente em Python que executa (monta prompt, chama LLM, retorna output), os 4 agentes built-in (planner, developer, reviewer, deployer), e o chat de construção (API streaming + portal), com persistência do artefato (.yml) no MinIO e metadados no PostgreSQL.

## Escopo (o que FAZ)

- CRUD de agentes: `POST/GET/PUT/DELETE /api/agents` com validação de contrato.
- Persistência do artefato do agente (.yml) no MinIO via S3 API. O CRUD faz: (a) INSERT/UPDATE/DELETE no Postgres (metadados), (b) PUT/DELETE no MinIO (artefato .yml).
- Validador de contrato: nomes de ports únicos, tipos válidos, actions ∈ {follow, return, finalize}.
- `agents/base.py`: classe base que recebe `AgentSnapshot`, monta prompt, chama LLM, retorna output estruturado.
- `agents/planner.py`, `developer.py`, `reviewer.py`, `deployer.py`: subclasses com prompt default.
- Chat de construção (API): `POST /api/agents/chat` (novo agente, sessão efêmera) e `POST /api/agents/:id/chat` (edição) — streaming SSE com IA assistente.
- Chat de construção (Portal): `AgentChat.tsx` — UI de chat com streaming, sugestões estruturadas, preview.

## Escopo (o que NÃO FAZ)

- NÃO implementa o grafo/pipeline (D5), NÃO executa o grafo (D6), NÃO integra skills/tools/MCP (D8 — só a referência no contrato).
- NÃO implementa knowledge/RAG (D9) — o agente consome knowledge via injeção de prompt que o D6/D9 fornecem.
- NÃO implementa human-in-the-loop (D7).
- NÃO cria as ferramentas básicas como execução real (D8 8.4 faz o sandbox); o agente base só precisa saber que elas existem no prompt.

## Dependências

- **D3:** model `Agent` + router `/api/agents` (stub) + tipo `Agent` em `types.ts`.
- **D2:** `get_current_user` pra autenticar.
- **D1:** MinIO disponível com bucket `agents`. Credenciais via env (`MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`).

## Arquivos que OWNS

```
agent-orchestrator/
  app/agents/base.py          (classe base Agent)
  app/agents/planner.py
  app/agents/developer.py
  app/agents/reviewer.py
  app/agents/deployer.py
  app/agents/validator.py     (validação de contrato de ports/actions)
  app/agents/storage.py       (MinIO S3 client: put/get/delete agent .yml)
  app/api/agents.py           (CRUD + validação + chat streaming)
agent-portal/
  components/AgentChat.tsx
  components/AgentPreview.tsx
```

## Tarefas

### 4.1 CRUD de agentes (API)
- Preencher o router stub de D3: `POST` (criar), `GET /api/agents` (listar), `GET /api/agents/:id`, `PUT /api/agents/:id`, `DELETE /api/agents/:id`.
- `ownerId` derivado do JWT (single-user na V1).
- Cada operação de CRUD faz DUAS coisas: (a) operação no Postgres (metadados), (b) operação no MinIO (artefato .yml).
  - **Create:** serializar agente para .yml → PUT `agents/{id}.yml` no MinIO → INSERT no Postgres.
  - **Update:** serializar → PUT `agents/{id}.yml` no MinIO → UPDATE no Postgres.
  - **Delete:** DELETE `agents/{id}.yml` no MinIO → DELETE no Postgres.
  - Se o MinIO falhar, rollback no Postgres (transação compensatória).
- Aceite: criar/agente/listar/atualizar/remover via API com JWT; artefato .yml presente no MinIO após create/update.

### 4.2 Validação de contrato
- `agents/validator.py`: validar que `inputs`/`outputs` têm `name` único, `type` ∈ whitelist (document|code|artifact|signal|...), `actions` ∈ {follow, return, finalize}. Rejeitar com mensagem clara.
- Aceite: contrato inválido (action fora da whitelist, port duplicado) é rejeitado.

### 4.3 Agent base (Python)
- `agents/base.py`: classe `Agent` que recebe um `AgentSnapshot` e um objeto `AgentCapabilities`, monta o prompt (systemPrompt já vem com skills injetadas dentro de `capabilities`), chama o LLM configurado (`model` do snapshot), e retorna output estruturado compatível com `outputs`.
- Interface: `async def run(self, inputs: dict, capabilities: AgentCapabilities) -> dict`.
- O `base.py` NÃO lê capabilities do snapshot. Recebe como parâmetro de `run()`.
- Aceite: instanciar `Agent` com snapshot de planner e chamar `run` com capabilities mock retorna output estruturado (mock LLM se API key ausente, mas deixar o chamador real do LLM presente).

### 4.4 Agentes built-in
- 4 subclasses com prompt default coerente com o tipo (planner planeja, developer escreve código, reviewer revisa, deployer faz deploy).
- Aceite: cada subclass tem prompt default não-vazio e executa via `base.run`.

### 4.5 Chat de construção (API)
- `POST /api/agents/chat` (sem id) — chat de construção de **novo** agente. Sessão efêmera (draft).
  - Body: `{ message: string, draftId?: string }`
  - Se `draftId` ausente: cria sessão efêmera, retorna `draftId` no primeiro evento.
  - Se `draftId` presente: continua a sessão.
  - Response: SSE stream com eventos:
    - `{ type: "text", data: string }` — texto da resposta da IA
    - `{ type: "config_update", data: Partial<Agent> }` — atualização do draft do agente
    - `{ type: "done", data: { draftId } }` — fim da resposta
  - Quando o usuário salva, o draft vira um agente real via `POST /api/agents`.
- `POST /api/agents/:id/chat` — chat de **edição** de agente existente. SSE streaming. IA entende intenção, sugere ajustes em skills/knowledge/integrações e define o contrato (inputs/outputs/actions), gera prompt, valida coerência.
- Na V1: pode usar o mesmo LLM com um system prompt de "assistente de construção". Streaming real via `StreamingResponse`.
- Aceite: POST no chat (novo e edição) retorna stream SSE com resposta da IA; draftId é retornado e pode ser reutilizado.

### 4.6 Chat de construção (Portal)
- `AgentChat.tsx`: UI de chat (mensagens usuário/IA), streaming incremental, painel de sugestões estruturadas (skills, knowledge, integrações, contrato), preview do agente (identidade + contrato). Botão "Salvar" que chama `POST /api/agents`.
- Aceite: conversar no chat, ver sugestões, editar preview, salvar cria o agente (aparece no dashboard).

### 4.7 Agent Storage (`agents/storage.py`)
- Wrapper do client S3 para MinIO. Métodos: `save_agent(agent_id: str, agent_yaml: str)`, `get_agent(agent_id: str) -> str`, `delete_agent(agent_id: str)`.
- Usa `MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET_AGENTS` do ambiente.
- O formato .yml: definição completa do agente (prompt, model, contract, capabilities references, skills list). O schema exato é definido pelo D4.
- Aceite: `save_agent` + `get_agent` round-trip retorna o mesmo conteúdo; `delete_agent` remove o objeto.

## Critérios de aceite (DoD)

- [ ] CRUD de agentes funciona via API
- [ ] Contrato inválido é rejeitado com mensagem clara
- [ ] Chat de construção sugere configuração coerente
- [ ] Agente criado via chat aparece como card no portal
- [ ] Agent base executa e retorna output estruturado

## Contratos de interface (o que entrega aos outros)

- **Para D5:** o contrato do agente (`inputs`/`outputs`/`actions`) é a base que o compiler valida. O compiler (D5) consome o `Agent` do banco.
- **Para D6:** `Agent.run(inputs: dict, capabilities: AgentCapabilities) -> dict` é a assinatura que o runtime executa. O runtime (D6) chama `loader.load(agent_snapshot)` antes de `Agent.run()` e passa o resultado como segundo argumento. O worker baixa o .yml do agente do MinIO em tempo de execução. O orquestrador NÃO passa a definição completa do agente no request HTTP para o worker; passa apenas `agentId` + `inputs` + `capabilities`. O worker busca o .yml por conta própria.
- **Para D7:** o output do agente (com action) é o payload que o nó de aprovação (gerado pelo D5 para edges com `requiresApproval=true`) recebe e passa ao `interrupt()`. O interrupt acontece DENTRO do nó de aprovação, não na edge.
- **Para D8:** o `base.py` recebe `capabilities` como parâmetro de `run()`, não o lê do snapshot. As skills (prompts) já estão injetadas no `systemPrompt` dentro de `capabilities`. O D8 expõe `loader.load(agent_snapshot) -> AgentCapabilities`; o D6 a consome.
- **Para D10:** `AgentChat.tsx` + `AgentPreview.tsx` + o tipo `Agent` pra renderizar cards.

## Riscos

- LLM real precisa de API key. Deixar o chamador real presente mas com fallback mock quando `OPENAI_API_KEY` ausente, pra não bloquear testes.
- Contrato de ports (nomes/tipos) é o contrato que D5 e D6 dependem — qualquer mudança aqui propaga.
- Consistência Postgres+MinIO: se o PUT no MinIO falhar após o INSERT no Postgres, o agente existe no banco mas sem artefato. Mitigação: transação compensatória (DELETE no Postgres se MinIO falhar) ou retry com idempotência.
