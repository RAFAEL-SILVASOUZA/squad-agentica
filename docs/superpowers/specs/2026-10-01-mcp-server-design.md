# Servidor MCP do Agent Portal — design

Data: 2026-10-01 · Origem: pedido do usuário ("criar um servidor MCP que exponha como tools tudo que o usuário pode fazer na tela") · Estado: escrito após brainstorming, aguardando revisão.

## 1. Objetivo

Expor todas as operações do Agent Portal como tools MCP (Model Context Protocol), permitindo que clientes externos (Claude Desktop, Cursor, OpenAI, etc.) criem agentes, pipelines, servidores MCP, bases de conhecimento, integrações, skills, tools, workspaces, aprovações e runs — tudo que a UI faz — via protocolo MCP.

Critério de sucesso: um usuário configura o MCP server no Claude Desktop (ou similar), autoriza via fluxo OAuth no portal, e consegue criar um agente e uma pipeline usando apenas o LLM, sem abrir a UI.

## 2. Decisões de design

| Tema | Decisão |
|---|---|
| Arquitetura | MCP server embutido no orchestrator (mesmo processo FastAPI). Acesso direto à service layer, sem hop HTTP interno. |
| SDK | `mcp` (Python SDK oficial, FastMCP) com `stateless_http=True`. Montado via `app.mount("/mcp", mcp.streamable_http_app())`. Endpoint final: `/mcp/mcp`. |
| Transporte | Streamable HTTP (padrão 2025-11-25 do MCP). Suporta SSE para streaming de respostas longas. |
| Autenticação | OAuth 2.1 completo (spec MCP 2025-11-25): Protected Resource Metadata (RFC 9728), Authorization Server Metadata (RFC 8414), Dynamic Client Registration (RFC 7591), PKCE (S256), Resource Indicators (RFC 8707). |
| Fluxo de auth | Client MCP → 401 com `WWW-Authenticate` → browser abre portal → login → página de consentimento → redirect com code → client troca por token. |
| Tokens | Access token JWT (`typ: "mcp"`, exp 1h). Refresh token JWT (`typ: "mcp_refresh"`, exp 30d, rotação). Tabela `mcp_oauth_tokens` para revogação. |
| Escopo | Único escopo: `mcp:full` (acesso completo). Sem granularidade por domínio nesta entrega. |
| URL pública | Controlada por env `MCP_BASE_URL` (default: `http://localhost`). Em produção muda o env e a URL muda. |
| Tools | ~45 tools cobrindo todos os domínios da API. Nomenclatura `verbo_substantivo` (snake_case). Descrições em pt-BR. |
| Erros | `ToolError` com mensagem legível em pt-BR. O LLM lê e decide o próximo passo. |

## 3. Arquitetura

### 3.1 Estrutura de arquivos (backend)

```
agent-orchestrator/app/mcp_server/
├── __init__.py          # importa todos os módulos de tools (registro)
├── server.py            # instância FastMCP + lifespan
├── auth.py              # middleware ASGI (valida Bearer JWT, injeta User)
├── context.py           # contextvar para o User atual
└── tools/
    ├── __init__.py
    ├── agents.py        # create_agent, list_agents, get_agent, update_agent, delete_agent
    ├── pipelines.py     # create_pipeline, list_pipelines, get_pipeline, update_pipeline, delete_pipeline, run_pipeline
    ├── mcp_servers.py   # create_mcp_server, list_mcp_servers, get_mcp_server, update_mcp_server, delete_mcp_server, test_mcp_server
    ├── knowledge.py     # create_knowledge_base, list_knowledge_bases, get_knowledge_base, delete_knowledge_base, upload_knowledge_file, query_knowledge
    ├── integrations.py  # create_integration, list_integrations, get_integration, update_integration, delete_integration, test_integration
    ├── skills.py        # create_skill, list_skills, get_skill, update_skill, delete_skill
    ├── tools.py         # create_tool, list_tools, get_tool, update_tool, delete_tool
    ├── workspaces.py    # list_workspaces, get_workspace, delete_workspace
    ├── approvals.py     # list_approvals, get_approval, approve, reject
    └── runs.py          # list_runs, get_run, cancel_run
```

### 3.2 Estrutura de arquivos (OAuth)

```
agent-orchestrator/app/api/
└── oauth.py             # router: /oauth/register, /oauth/authorize, /oauth/token, /oauth/revoke
                         # + /.well-known/oauth-protected-resource
                         # + /.well-known/oauth-authorization-server
```

### 3.3 Estrutura de arquivos (frontend)

```
agent-portal/app/(auth)/mcp-consent/page.tsx   # página de consentimento
agent-portal/app/(dashboard)/mcp/page.tsx      # página de gestão (URL, tokens, tools)
agent-portal/components/mcp/
├── token-list.tsx       # tabela de tokens ativos + revogar
├── tools-list.tsx       # catálogo de tools
└── mcp-setup-card.tsx   # URL + instruções de configuração
```

### 3.4 Integração no main.py

- O lifespan existente é estendido: entra em `mcp.session_manager.run()` via `AsyncExitStack`.
- `app.mount("/mcp", mcp.streamable_http_app())` após `_discover_routers()`.
- O middleware ASGI de auth é aplicado ao sub-app MCP (não herda o middleware do FastAPI principal).

### 3.5 Nginx

Novas locations no `10-public.conf`:

```nginx
# MCP server (streamable HTTP, pode usar SSE)
location /mcp/ {
    proxy_pass http://orchestrator;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 300s;
}

# OAuth endpoints
location /oauth/ {
    proxy_pass http://orchestrator;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}

# OAuth metadata (well-known)
location = /.well-known/oauth-protected-resource {
    proxy_pass http://orchestrator;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
}
location = /.well-known/oauth-authorization-server {
    proxy_pass http://orchestrator;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
}

# Página de consentimento (portal Next.js)
location = /mcp-consent {
    proxy_pass http://portal;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
}
```

## 4. Autenticação (OAuth 2.1)

### 4.1 Fluxo completo

1. Client MCP faz `POST /mcp/mcp` sem token.
2. Orchestrator responde `401` com:
   ```
   WWW-Authenticate: Bearer resource_metadata="http://localhost/.well-known/oauth-protected-resource", scope="mcp:full"
   ```
3. Client busca `GET /.well-known/oauth-protected-resource` → descobre `authorization_servers: ["http://localhost"]`.
4. Client busca `GET /.well-known/oauth-authorization-server` → descobre `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `code_challenge_methods_supported: ["S256"]`.
5. Client faz `POST /oauth/register` (Dynamic Client Registration) → obtém `client_id`.
6. Client abre browser em `GET /oauth/authorize?client_id=...&redirect_uri=...&scope=mcp:full&code_challenge=...&code_challenge_method=S256&state=...&resource=http://localhost/mcp/mcp`.
7. Portal: se não logado → login → redirect de volta ao authorize com sessão.
8. Portal mostra página de consentimento: "Claude Desktop quer acessar o Agent Portal. Autorizar?"
9. Usuário clica "Autorizar" → portal redireciona browser para `redirect_uri?code=...&state=...`.
10. Client faz `POST /oauth/token` com `code`, `code_verifier`, `client_id`, `redirect_uri`, `resource` → recebe `access_token` + `refresh_token`.
11. Client usa `Authorization: Bearer <access_token>` em todas as requests ao `/mcp/mcp`.

### 4.2 Endpoints OAuth

| Método | Path | Função |
|---|---|---|
| GET | `/.well-known/oauth-protected-resource` | Protected Resource Metadata (RFC 9728) |
| GET | `/.well-known/oauth-authorization-server` | Authorization Server Metadata (RFC 8414) |
| POST | `/oauth/register` | Dynamic Client Registration (RFC 7591) |
| GET | `/oauth/authorize` | Redirect pro portal (consent) |
| POST | `/oauth/token` | Troca code por tokens (PKCE) |
| POST | `/oauth/revoke` | Revoga token |

### 4.3 Tokens

- **Access token:** JWT, `typ: "mcp"`, `sub: user_id`, `scope: "mcp:full"`, `aud: <MCP_BASE_URL>/mcp/mcp`, `exp: 1h`, `jti: uuid`.
- **Refresh token:** JWT, `typ: "mcp_refresh"`, `sub: user_id`, `jti: uuid`, `exp: 30d`. Rotação a cada uso (token antigo invalidado).
- **Revogação:** tabela `mcp_oauth_tokens` (jti, user_id, client_id, scope, expires_at, revoked_at). Middleware checa `revoked_at IS NULL`.

### 4.4 Tabelas novas (migração Alembic)

```sql
CREATE TABLE mcp_oauth_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT UNIQUE NOT NULL,
    client_name TEXT NOT NULL,
    redirect_uris JSONB NOT NULL DEFAULT '[]',
    grant_types JSONB NOT NULL DEFAULT '["authorization_code"]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mcp_oauth_tokens (
    jti UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES mcp_oauth_clients(client_id),
    scope TEXT NOT NULL DEFAULT 'mcp:full',
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.5 Middleware ASGI (app/mcp_server/auth.py)

- Intercepta todo request ao sub-app `/mcp`.
- Lê `Authorization: Bearer <token>`.
- Valida: `typ == "mcp"`, `exp`, `aud` (deve ser `<MCP_BASE_URL>/mcp/mcp`), `scope`.
- Checa revogação: `SELECT revoked_at FROM mcp_oauth_tokens WHERE jti = <jti>`.
- Injeta `User` no contextvar (`app/mcp_server/context.py`).
- Falhou → responde `401` com `WWW-Authenticate` header (mesmo formato do passo 2).

## 5. Tools por domínio

Cada tool: recebe args tipados, lê `User` do contextvar, chama a service layer diretamente, retorna dict JSON-serializável. Erros viram `ToolError` com mensagem em pt-BR.

### 5.1 Agents (tools/agents.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_agent` | name, prompt?, type?, description?, skills?, tools?, mcpServers?, knowledge?, integrations?, inputs?, outputs?, actions?, model?, llm?, maxIterations?, timeout?, shellAccess? | Cria um agente |
| `list_agents` | page?, limit?, type? | Lista agentes |
| `get_agent` | agentId | Obtém agente por id |
| `update_agent` | agentId, name?, prompt?, type?, ... (partial) | Atualiza agente |
| `delete_agent` | agentId | Remove agente |

### 5.2 Pipelines (tools/pipelines.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_pipeline` | name, description?, nodes?, edges? | Cria pipeline |
| `list_pipelines` | page?, limit? | Lista pipelines |
| `get_pipeline` | pipelineId | Obtém pipeline por id |
| `update_pipeline` | pipelineId, name?, description?, nodes?, edges? | Atualiza pipeline |
| `delete_pipeline` | pipelineId | Remove pipeline |
| `run_pipeline` | pipelineId, inputs? | Dispara execução, retorna runId |

### 5.3 MCP Servers (tools/mcp_servers.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_mcp_server` | name, description, transport, command?, url?, env? | Registra servidor MCP |
| `list_mcp_servers` | page?, limit?, transport?, status? | Lista servidores MCP |
| `get_mcp_server` | serverId | Obtém servidor MCP |
| `update_mcp_server` | serverId, name?, description?, transport?, command?, url?, env? | Atualiza servidor MCP |
| `delete_mcp_server` | serverId | Remove servidor MCP |
| `test_mcp_server` | serverId | Testa conexão e descobre tools |

### 5.4 Knowledge (tools/knowledge.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_knowledge_base` | name, description? | Cria base de conhecimento |
| `list_knowledge_bases` | page?, limit? | Lista bases |
| `get_knowledge_base` | kbId | Obtém base por id |
| `delete_knowledge_base` | kbId | Remove base |
| `upload_knowledge_file` | kbId, fileName, content (base64) | Upload de arquivo |
| `query_knowledge` | kbId, question | Consulta RAG |

### 5.5 Integrations (tools/integrations.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_integration` | name, type, config | Cria integração |
| `list_integrations` | page?, limit?, type? | Lista integrações |
| `get_integration` | integrationId | Obtém integração |
| `update_integration` | integrationId, name?, type?, config? | Atualiza integração |
| `delete_integration` | integrationId | Remove integração |
| `test_integration` | integrationId | Testa conexão |

### 5.6 Skills (tools/skills.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_skill` | name, description?, category?, template?, variables?, inputs?, outputs? | Cria skill |
| `list_skills` | page?, limit?, category? | Lista skills |
| `get_skill` | skillId | Obtém skill |
| `update_skill` | skillId, name?, description?, category?, template?, ... | Atualiza skill |
| `delete_skill` | skillId | Remove skill |

### 5.7 Tools (tools/tools.py)

| Tool | Args | Descrição |
|---|---|---|
| `create_tool` | name, description?, category?, code?, params?, timeout? | Cria tool |
| `list_tools` | page?, limit?, category? | Lista tools |
| `get_tool` | toolId | Obtém tool |
| `update_tool` | toolId, name?, description?, category?, code?, params?, timeout? | Atualiza tool |
| `delete_tool` | toolId | Remove tool |

### 5.8 Workspaces (tools/workspaces.py)

| Tool | Args | Descrição |
|---|---|---|
| `list_workspaces` | page?, limit? | Lista workspaces |
| `get_workspace` | workspaceId | Obtém workspace |
| `delete_workspace` | workspaceId | Remove workspace |

### 5.9 Approvals (tools/approvals.py)

| Tool | Args | Descrição |
|---|---|---|
| `list_approvals` | page?, limit?, status? | Lista aprovações |
| `get_approval` | approvalId | Obtém aprovação |
| `approve` | approvalId, feedback? | Aprova |
| `reject` | approvalId, reason? | Rejeita |

### 5.10 Pipeline Runs (tools/runs.py)

| Tool | Args | Descrição |
|---|---|---|
| `list_runs` | page?, limit?, pipelineId?, status? | Lista runs |
| `get_run` | runId | Obtém run |
| `cancel_run` | runId | Cancela run |

## 6. Frontend

### 6.1 Página de consentimento (`/mcp-consent`)

- Rota pública (não exige login prévio; se não logado, redireciona pro login e volta).
- Mostra: nome do client (ex: "Claude Desktop"), escopo ("Acesso completo ao Agent Portal"), redirect URI.
- Botões: "Autorizar" / "Recusar".
- Ao autorizar: troca o code server-side e redireciona o browser para `redirect_uri?code=...&state=...`.
- Ao recusar: redirect para `redirect_uri?error=access_denied&state=...`.

### 6.2 Página de gestão (`/mcp` no dashboard)

- **URL do servidor MCP:** mostra `<MCP_BASE_URL>/mcp/mcp` com botão "Copiar".
- **Instruções:** como configurar no Claude Desktop / Cursor (JSON de exemplo).
- **Tokens ativos:** tabela com nome do client, criado em, expira em, botão "Revogar".
- **Tools disponíveis:** lista das ~45 tools com nome e descrição (catálogo estático).

### 6.3 Navegação

- Link "MCP" no sidebar do dashboard (ícone de conexão/plug).

## 7. Configuração (env vars)

| Var | Default | Descrição |
|---|---|---|
| `MCP_BASE_URL` | `http://localhost` | URL pública do MCP server (usada em metadata, tokens, página) |
| `MCP_TOKEN_EXPIRE_HOURS` | `1` | Expiração do access token |
| `MCP_REFRESH_EXPIRE_DAYS` | `30` | Expiração do refresh token |

## 8. Dependências novas

- `mcp[cli]` (Python SDK oficial do MCP) no `pyproject.toml` do orchestrator.

## 9. Erros e casos-limite

| Situação | Comportamento |
|---|---|
| Token expirado | `401` com `WWW-Authenticate` (client faz re-auth) |
| Token revogado | `401` com `WWW-Authenticate` |
| Client não registrado (Dynamic Registration falhou) | `400` com mensagem clara |
| PKCE verification falhou | `400` com mensagem clara |
| Tool chamada com args inválidos | `ToolError` com mensagem em pt-BR (o LLM lê) |
| Resource (aud) não confere | `401` |
| User não existe mais (excluído) | `401` |
| Pipeline em execução ao cancelar | `ToolError` "Run já concluído" |
| Agente não encontrado | `ToolError` "Agente não encontrado" |

## 10. Testes

### 10.1 Backend (pytest)

- **OAuth:**
  - `GET /.well-known/oauth-protected-resource` devolve JSON correto;
  - `GET /.well-known/oauth-authorization-server` devolve endpoints;
  - `POST /oauth/register` cria client e devolve `client_id`;
  - `GET /oauth/authorize` sem sessão → redirect pro login;
  - `GET /oauth/authorize` com sessão → redirect com code;
  - `POST /oauth/token` com code válido → access + refresh tokens;
  - `POST /oauth/token` com PKCE inválido → 400;
  - `POST /oauth/token` com code reutilizado → 400;
  - `POST /oauth/revoke` → token revogado;
  - Refresh token rotation: usar refresh → novo par, antigo invalidado.
- **Middleware ASGI:**
  - Request sem token → 401 com `WWW-Authenticate`;
  - Request com token válido → 200, User injetado no contextvar;
  - Request com token expirado → 401;
  - Request com token revogado → 401;
  - Request com `aud` errado → 401.
- **Tools (amostra):**
  - `create_agent` cria agente no banco;
  - `list_agents` lista agentes do user;
  - `delete_agent` remove agente;
  - `run_pipeline` dispara run;
  - Tool com args inválidos → `ToolError`.

### 10.2 Portal (vitest)

- Página de consentimento: mostra nome do client, botões funcionam;
- Página de gestão: URL copiável, tokens listados, revogar funciona;
- Navegação: link "MCP" no sidebar.

### 10.3 E2E (Playwright)

- Fluxo completo: client MCP → 401 → login → consent → token → tool call → resultado.
- (Simplificado: simular o fluxo OAuth com httpx e chamar uma tool via MCP client Python.)

## 11. Fora do escopo

- Granularidade de escopo por domínio (ex: `mcp:agents:read`, `mcp:pipelines:write`).
- Rate limiting específico do MCP (o rate limiting global do login já existe).
- Compartilhamento de tokens entre usuários.
- MCP server para o worker (o worker continua usando a ponte interna `/internal/mcp`).
- SSE streaming de resultados longos (o streamable HTTP já suporta, mas as tools atuais retornam JSON simples).
- i18n das descrições de tools.
