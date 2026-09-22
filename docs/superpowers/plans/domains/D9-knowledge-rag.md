# D9 — Knowledge & RAG

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 3 · Núcleo**. Dependência: **D3** (models + router knowledge).
> Base: spec (seção 7 "Knowledge Base / RAG", 7.4 "Rivvn", 12 ADR-003/008) + plano.

## Objetivo

Bases de conhecimento com RAG local (upload → chunking → embedding → pgvector → query → injeção no prompt) e integração opcional com Rivvn (OAuth + SDK, somente leitura, gateada por contrato comercial).

## Escopo (o que FAZ)

- Model `KnowledgeBase` + `KnowledgeDocument` (seção 4.6 da spec: nome, escopo, fonte, config RAG, embedding).
- Upload + Chunking (`knowledge/chunker.py`).
- Embedding (`knowledge/embedder.py`).
- RAG Query (`knowledge/rag.py`): similarity search no pgvector, top-K, injeção no prompt.
- API de knowledge (CRUD completo): criar/listar/detalhar/atualizar/remover KB, upload, documentos, query.
- Knowledge UI (Portal): view Knowledge.
- Rivvn: OAuth (`oauth.py`), Client (`client.py`), gate comercial, API (`authorize/callback/status/DELETE`).
- Rivvn UI (Portal): barra de conexão, gate por contrato, escolha de collection.

## Escopo (o que NÃO FAZ)

- NÃO implementa OAuth de Rivvn como integração de plataforma genérica (seção 8 da spec) — Rivvn é fonte de Knowledge (ADR-008).
- NÃO implementa integrações GitHub/Azure/GitLab (V2+).
- NÃO executa agentes (D6) — só fornece a query de knowledge que o D6 injeta no prompt.
- NÃO implementa gate comercial de negócio além do `contractStatus` (decisão de produto, aqui é técnica).

## Dependências

- **D3:** models `KnowledgeBase`, `KnowledgeDocument`, `RivvnConnection` + router `/api/knowledge` (stub) + `/api/integrations/rivvn` (stub) + tipos em `types.ts`. Índice HNSW criado na migration (D3) — D9 não cria índice, apenas usa.
- **D1:** Postgres com extensão `vector` (pgvector) pra similarity search.

## Arquivos que OWNS

```
agent-orchestrator/
  app/knowledge/
    rag.py                      (similarity search, top-K, injeção)
    chunker.py                  (upload → chunks)
    embedder.py                 (texto → embeddings)
    rivvn/
      oauth.py                  (authorization code flow)
      client.py                 (wrapper do SDK do Rivvn)
  app/api/knowledge.py
  app/api/integrations.py       (rivvn: authorize/callback/status/DELETE)
agent-portal/
  components/KnowledgeView.tsx
```

## Tarefas

### 9.1 Knowledge Base model
- `KnowledgeBase`: nome, escopo (global/agent/pipeline), fonte (upload/vector-db/url/rivvn), referência, config RAG (chunkSize, chunkOverlap, topK, similarityThreshold), embedding (model, dim). Ver seção 4.6 da spec.
- `KnowledgeDocument`: nome, source (upload/url), url, size, chunkCount, status.
- Aceite: model persiste + filtra por escopo. CRUD completo via API.

### 9.2 Upload + Chunking
- `chunker.py`: upload de PDFs/docs, chunking inteligente (tamanho + sobreposição).
- Aceite: upload de PDF → N chunks gerados.

### 9.3 Embedding
- `embedder.py`: V1: `text-embedding-3-small` (OpenAI, 1536 dims). Normalizar embeddings antes do insert. Operador de busca: `<=>` (cosine distance).
- Fallback local (`all-MiniLM-L6-v2`, 384 dims) é V2.
- Aceite: texto → embedding (1536 dims) → stored no pgvector.

### 9.4 RAG Query
- `rag.py`: similarity search no pgvector (`ORDER BY embedding <=> query LIMIT top_k`), top-K chunks, formatar pra injeção no prompt.
- Configuração de RAG vem do `KnowledgeBase`: `chunkSize`, `chunkOverlap`, `topK`, `similarityThreshold`. Defaults: 512, 64, 5, 0.7.
- Aceite: query retorna trechos relevantes (topK configurável, default 5).

### 9.5 API de knowledge (CRUD completo)
- Preencher router com todos os endpoints da seção 9.3 da spec:
  - `POST /api/knowledge` (criar KB)
  - `GET /api/knowledge` (listar, filtro: scope, source)
  - `GET /api/knowledge/:id` (detalhe)
  - `PUT /api/knowledge/:id` (atualizar name, description, config RAG)
  - `DELETE /api/knowledge/:id` (remover KB + documentos + vetores)
  - `POST /api/knowledge/:id/upload` (upload multipart)
  - `GET /api/knowledge/:id/documents` (listar documentos)
  - `DELETE /api/knowledge/:id/documents/:docId` (remover documento + vetores)
  - `POST /api/knowledge/query` (busca semântica: `{ query, knowledgeBaseIds[], topK? }`)
- Aceite: CRUD completo funciona; upload indexa; query retorna trechos.

### 9.6 Knowledge UI (Portal)
- `KnowledgeView.tsx`: sidebar de bases, upload, escopo, documentos.
- Aceite: criar base, upload documento, ver documentos.

### 9.7 Rivvn: OAuth
- `rivvn/oauth.py`: authorization code flow (authorize → redirect → callback troca code por token).
- Gate: `contractStatus === "active"` antes de qualquer OAuth (403 se não).
- Aceite: com contrato ativo, authorize retorna URL de redirect; callback troca code por token.

### 9.8 Rivvn: Client
- `rivvn/client.py`: wrapper do SDK do Rivvn (token + query). Token salvo no secrets manager.
- Aceite: query via SDK retorna trechos (mock SDK se ausente).

### 9.9 Rivvn: Gate comercial
- Validar `contractStatus` antes de OAuth e de query. Se `!== "active"`, 403 + CTA comercial.
- Aceite: sem contrato → 403.

### 9.10 Rivvn: API
- Preencher router: `GET /api/integrations/rivvn/authorize`, `callback`, `status`, `DELETE`.
- Aceite: authorize/callback/status/DELETE respondem conforme spec.

### 9.11 Rivvn: UI (Portal)
- Barra de conexão Rivvn na `KnowledgeView`: gate por contrato (botão desabilitado + CTA), escolha de collection.
- Aceite: sem contrato → botão desabilitado; com contrato → conectar + escolher collection.

## Critérios de aceite (DoD)

- [ ] Upload de PDF → chunking → embedding → query retorna trechos relevantes
- [ ] Escopo (global/agent/pipeline) filtra quais agentes acessam a KB
- [ ] Rivvn: sem contrato → botão desabilitado, CTA de contato comercial
- [ ] Rivvn: com contrato → OAuth funciona, collection selecionada, query via SDK
- [ ] Rivvn: token expirado → erro tratável, agente decide como agir
- [ ] Rivvn: contrato expirado → conexão desativada, KB retorna erro

## Contratos de interface (o que entrega aos outros)

- **Para D4/D6:** `knowledge/query(text) -> chunks` é consumido pelo runtime (D6) que injetra os trechos no prompt do agente. Contrato: função de query reutilizável.
- **Para D10:** `KnowledgeView.tsx` + tipos `KnowledgeBase`/`KnowledgeDocument`/`RivvnConnection`.

## Riscos

- **Rivvn SDK externo:** mockar o SDK pra testes; não depender de rede. Gate de contrato antes de qualquer chamada.
- **Embeddings:** V1 usa apenas OpenAI (`text-embedding-3-small`, 1536 dims). Precisa de API key no env. Fallback local (`all-MiniLM-L6-v2`, 384 dims) é V2.
- **pgvector:** similarity search depende da extensão (D1). Testar com dados reais.
