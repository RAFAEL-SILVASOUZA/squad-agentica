# Guia de API para o Frontend

> Gerado a partir do OpenAPI da aplicação. Base: `http://localhost:8000` (ou `http://orchestrator:8000` no Docker).
> Autenticação: JWT Bearer token. Obter via `POST /api/auth/login`.

## Autenticação

### POST /api/auth/login
```json
// Request
{ "email": "admin@local", "password": "change-me-in-prod" }

// Response 200
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer" }

// Erros: 401 (credenciais inválidas), 422 (validação)
```

### POST /api/auth/refresh
```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer" }
```

### GET /api/auth/me
```json
// Response 200
{ "id": "uuid", "email": "admin@local", "name": "Admin", "role": "admin" }
```

## Health

### GET /health
```json
// Response 200
{ "status": "ok" }
```

## Agentes

### GET /api/agents
```json
// Query params: page (int, default 1), limit (int, default 20)
// Response 200
{ "items": [ { "id": "uuid", "name": "Meu Agente", "description": "...", "model": "gpt-4", "system_prompt": "...", "inputs": [...], "outputs": [...], "actions": [...], "createdAt": "ISO8601" } ], "total": 10, "page": 1, "limit": 20 }
```

### POST /api/agents
```json
// Request
{ "name": "Meu Agente", "description": "...", "model": "gpt-4", "system_prompt": "...", "inputs": [...], "outputs": [...], "actions": [...] }

// Response 201
{ "id": "uuid", "name": "Meu Agente", ... }

// Erros: 422 (validação)
```

### GET /api/agents/{agent_id}
```json
// Response 200
{ "id": "uuid", "name": "Meu Agente", ... }

// Erros: 404 (não encontrado)
```

### PUT /api/agents/{agent_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "name": "Meu Agente", ... }

// Erros: 404, 422
```

### DELETE /api/agents/{agent_id}
```json
// Response 204 (sem corpo)
// Erros: 404
```

## Pipelines

### POST /api/pipelines/{pipeline_id}/execute
```json
// Request
{ "inputs": { "input1": "valor", "input2": "valor" } }

// Response 202 (aceito, execução assíncrona)
{ "run_id": "uuid", "status": "running" }

// Erros: 404 (pipeline não existe), 409 (já em execução)
```

### POST /api/pipelines/{pipeline_id}/pause
```json
// Response 200
{ "run_id": "uuid", "status": "paused" }

// Erros: 404, 409
```

### POST /api/pipelines/{pipeline_id}/resume
```json
// Response 200
{ "run_id": "uuid", "status": "running" }

// Erros: 404, 409
```

### POST /api/pipelines/{pipeline_id}/stop
```json
// Response 200
{ "run_id": "uuid", "status": "stopped" }

// Erros: 404, 409
```

### GET /api/pipelines/{pipeline_id}/runs
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "status": "running|paused|completed|failed|stopped", "startedAt": "ISO8601", "finishedAt": "ISO8601|null" } ], "total": 5, "page": 1, "limit": 20 }
```

### GET /api/pipelines/{pipeline_id}/checkpoints
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "node_id": "node1", "timestamp": "ISO8601", "state": {...} } ], "total": 3, "page": 1, "limit": 20 }
```

### POST /api/pipelines/{pipeline_id}/checkpoints/{cp_id}/resume
```json
// Response 200
{ "run_id": "uuid", "status": "running" }

// Erros: 404, 409
```

## Aprovações (HITL)

### GET /api/approvals
```json
// Query params:
//   status: "pending" | "approved" | "rejected" | "revised" | "cancelled" (opcional)
//   pipeline_id: "uuid" (opcional)
//   page: int (default 1)
//   limit: int (default 20)
//
// Response 200
{
  "items": [
    {
      "id": "uuid",
      "pipeline_id": "uuid",
      "run_id": "uuid",
      "node_id": "node1",
      "status": "pending",
      "payload": { "message": "Aprovar ação X?", "data": {...} },
      "responded_at": null,
      "response": null,
      "created_at": "ISO8601"
    }
  ],
  "total": 5,
  "page": 1,
  "limit": 20
}
```

### GET /api/approvals/{approval_id}
```json
// Response 200
{ "id": "uuid", "pipeline_id": "uuid", "run_id": "uuid", "node_id": "node1", "status": "pending", "payload": {...}, "responded_at": null, "response": null, "created_at": "ISO8601" }

// Erros: 404 (não encontrado ou de outro owner)
```

### POST /api/approvals/{approval_id}/respond
```json
// Request
{ "decision": "approved" | "rejected" | "revised", "response": "texto opcional (para 'revised')" }

// Response 200
{ "id": "uuid", "status": "approved|rejected|revised", "responded_at": "ISO8601", "response": "texto" }

// Erros:
//   404 (não encontrado ou de outro owner)
//   409 (já respondida)
//   422 (validação)
```

### DELETE /api/approvals/{approval_id}
```json
// Response 204 (sem corpo)
// Erros: 404, 409
```

## Skills

### GET /api/skills
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "name": "Skill 1", "description": "...", "content": "..." } ], "total": 10, "page": 1, "limit": 20 }
```

### POST /api/skills
```json
// Request
{ "name": "Skill 1", "description": "...", "content": "..." }

// Response 201
{ "id": "uuid", "name": "Skill 1", ... }
```

### GET /api/skills/{skill_id}
```json
// Response 200
{ "id": "uuid", "name": "Skill 1", ... }
```

### PUT /api/skills/{skill_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "name": "Skill 1", ... }
```

### DELETE /api/skills/{skill_id}
```json
// Response 204
```

### GET /api/skills/builtins
```json
// Response 200
{ "items": [ { "id": "uuid", "name": "Built-in 1", ... } ] }
```

## Tools

### GET /api/tools
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "name": "Tool 1", "type": "mcp|builtin", "status": "active|inactive" } ], "total": 5, "page": 1, "limit": 20 }
```

### POST /api/tools
```json
// Request
{ "name": "Tool 1", "type": "mcp|builtin", "config": {...} }

// Response 201
{ "id": "uuid", "name": "Tool 1", ... }
```

### GET /api/tools/{tool_id}
```json
// Response 200
{ "id": "uuid", "name": "Tool 1", ... }
```

### PUT /api/tools/{tool_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "name": "Tool 1", ... }
```

### DELETE /api/tools/{tool_id}
```json
// Response 204
```

### POST /api/tools/{tool_id}/deploy
```json
// Response 200
{ "id": "uuid", "status": "deployed" }
```

### POST /api/tools/{tool_id}/test
```json
// Response 200
{ "id": "uuid", "status": "ok|error", "message": "..." }
```

## MCP Servers

### GET /api/mcp-servers
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "name": "MCP Server 1", "url": "http://...", "status": "active|inactive" } ], "total": 3, "page": 1, "limit": 20 }
```

### POST /api/mcp-servers
```json
// Request
{ "name": "MCP Server 1", "url": "http://...", "config": {...} }

// Response 201
{ "id": "uuid", "name": "MCP Server 1", ... }
```

### GET /api/mcp-servers/{server_id}
```json
// Response 200
{ "id": "uuid", "name": "MCP Server 1", ... }
```

### PUT /api/mcp-servers/{server_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "name": "MCP Server 1", ... }
```

### DELETE /api/mcp-servers/{server_id}
```json
// Response 204
```

### POST /api/mcp-servers/{server_id}/test
```json
// Response 200
{ "id": "uuid", "status": "ok|error", "message": "..." }
```

## Knowledge Base

### GET /api/knowledge
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "name": "KB 1", "description": "...", "document_count": 5 } ], "total": 3, "page": 1, "limit": 20 }
```

### POST /api/knowledge
```json
// Request
{ "name": "KB 1", "description": "..." }

// Response 201
{ "id": "uuid", "name": "KB 1", ... }
```

### GET /api/knowledge/{kb_id}
```json
// Response 200
{ "id": "uuid", "name": "KB 1", ... }
```

### PUT /api/knowledge/{kb_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "name": "KB 1", ... }
```

### DELETE /api/knowledge/{kb_id}
```json
// Response 204
```

### POST /api/knowledge/{kb_id}/upload
```json
// Request (multipart/form-data)
//   file: arquivo (PDF, TXT, MD)
// Response 201
{ "id": "uuid", "name": "documento.pdf", "status": "processed" }
```

### GET /api/knowledge/{kb_id}/documents
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "name": "documento.pdf", "status": "processed", "uploaded_at": "ISO8601" } ], "total": 5, "page": 1, "limit": 20 }
```

### DELETE /api/knowledge/{kb_id}/documents/{doc_id}
```json
// Response 204
```

### POST /api/knowledge/query
```json
// Request
{ "kb_id": "uuid", "query": "texto da busca", "top_k": 5 }

// Response 200
{ "results": [ { "document_id": "uuid", "content": "...", "score": 0.95 } ] }
```

## Integrations

### GET /api/integrations
```json
// Query params: page, limit
// Response 200
{ "items": [ { "id": "uuid", "type": "github|rivvn", "name": "Integration 1", "status": "connected|disconnected" } ], "total": 2, "page": 1, "limit": 20 }
```

### POST /api/integrations
```json
// Request
{ "type": "github|rivvn", "name": "Integration 1", "config": {...} }

// Response 201
{ "id": "uuid", "type": "github", ... }
```

### GET /api/integrations/{integration_id}
```json
// Response 200
{ "id": "uuid", "type": "github", ... }
```

### PUT /api/integrations/{integration_id}
```json
// Request (mesmo schema do POST)
// Response 200
{ "id": "uuid", "type": "github", ... }
```

### DELETE /api/integrations/{integration_id}
```json
// Response 204
```

### GitHub

#### GET /api/integrations/github/repos
```json
// Response 200
{ "items": [ { "owner": "user", "name": "repo", "full_name": "user/repo" } ] }
```

#### GET /api/integrations/github/repos/{owner}/{repo}/issues
```json
// Query params: state (open|closed|all), page, limit
// Response 200
{ "items": [ { "number": 1, "title": "...", "state": "open", "created_at": "ISO8601" } ] }
```

#### GET /api/integrations/github/repos/{owner}/{repo}/pulls
```json
// Query params: state (open|closed|all), page, limit
// Response 200
{ "items": [ { "number": 1, "title": "...", "state": "open", "created_at": "ISO8601" } ] }
```

### Rivvn

#### GET /api/integrations/rivvn/authorize
```json
// Response 302 (redirect para URL de autorização)
```

#### GET /api/integrations/rivvn/callback
```json
// Query params: code, state
// Response 302 (redirect para frontend)
```

#### GET /api/integrations/rivvn/status
```json
// Response 200
{ "connected": true, "user": "user@example.com" }
```

#### DELETE /api/integrations/rivvn
```json
// Response 204
```

## Agent Chat

### POST /api/agents/chat
```json
// Request
{ "agent_id": "uuid", "message": "Olá", "history": [ { "role": "user", "content": "..." } ] }

// Response 200
{ "response": "Olá! Como posso ajudar?", "history": [ { "role": "user", "content": "..." }, { "role": "assistant", "content": "..." } ] }
```

### POST /api/agents/{agent_id}/chat
```json
// Request
{ "message": "Olá", "history": [ { "role": "user", "content": "..." } ] }

// Response 200
{ "response": "Olá! Como posso ajudar?", "history": [...] }
```

### POST /api/agents/chat/confirm
```json
// Request
{ "agent_id": "uuid", "action_id": "uuid", "confirmed": true }

// Response 200
{ "status": "confirmed" }
```

## WebSocket

### Conexão
```
ws://localhost:8000/ws?token=<JWT>
```

### Eventos recebidos

#### `approval:new`
```json
{
  "type": "approval:new",
  "data": {
    "id": "uuid",
    "pipeline_id": "uuid",
    "run_id": "uuid",
    "node_id": "node1",
    "payload": { "message": "Aprovar ação X?", "data": {...} },
    "created_at": "ISO8601"
  }
}
```

#### `approval:resolved`
```json
{
  "type": "approval:resolved",
  "data": {
    "id": "uuid",
    "status": "approved|rejected|revised",
    "responded_at": "ISO8601",
    "response": "texto"
  }
}
```

#### `run:started`
```json
{
  "type": "run:started",
  "data": { "run_id": "uuid", "pipeline_id": "uuid", "started_at": "ISO8601" }
}
```

#### `run:completed`
```json
{
  "type": "run:completed",
  "data": { "run_id": "uuid", "pipeline_id": "uuid", "finished_at": "ISO8601", "result": {...} }
}
```

#### `run:failed`
```json
{
  "type": "run:failed",
  "data": { "run_id": "uuid", "pipeline_id": "uuid", "error": "mensagem de erro" }
}
```

#### `node:started`
```json
{
  "type": "node:started",
  "data": { "run_id": "uuid", "node_id": "node1", "started_at": "ISO8601" }
}
```

#### `node:completed`
```json
{
  "type": "node:completed",
  "data": { "run_id": "uuid", "node_id": "node1", "finished_at": "ISO8601", "output": {...} }
}
```

## Envelope de Erro

Todos os erros seguem o formato:
```json
{
  "error": {
    "code": "NOT_FOUND|ALREADY_RESPONDED|VALIDATION_ERROR|UNAUTHORIZED|FORBIDDEN|INTERNAL_ERROR",
    "message": "Mensagem descritiva",
    "details": {...} // opcional
  }
}
```

## Códigos de Erro

| Código | Significado |
|--------|-------------|
| 400 | Requisição inválida |
| 401 | Não autenticado (token inválido ou ausente) |
| 403 | Sem permissão (owner diferente) |
| 404 | Recurso não encontrado |
| 409 | Conflito (ex: já respondida, já em execução) |
| 422 | Erro de validação (schema inválido) |
| 500 | Erro interno do servidor |
