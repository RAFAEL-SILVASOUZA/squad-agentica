# Servidor MCP do Agent Portal — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor todas as operações do Agent Portal como tools MCP, com autenticação OAuth 2.1, permitindo que clientes externos (Claude Desktop, Cursor, etc.) criem agentes, pipelines, servidores MCP, bases de conhecimento, integrações, skills, tools, workspaces, aprovações e runs via protocolo MCP.

**Architecture:** MCP server embutido no orchestrator (FastMCP `stateless_http=True`), montado em `/mcp/mcp`. OAuth 2.1 completo (RFC 9728, RFC 8414, RFC 7591, PKCE S256, RFC 8707). ~45 tools cobrindo todos os domínios da API. Página de consentimento no portal.

**Tech Stack:** Python 3.11, FastAPI, `mcp` (Python SDK oficial), SQLAlchemy, Alembic, Next.js 14, React 18, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-mcp-server-design.md`.

## Global Constraints

- Valem as restrições do projeto: idioma pt-BR, erros com recuperação, commits com `git add` só com caminhos explícitos, nunca fazer push, não tocar em `.codex/`.
- O MCP server não altera nenhuma rota existente da API. É aditivo.
- O middleware ASGI de auth do MCP não interfere no auth global do FastAPI principal.
- As tools MCP chamam a service layer diretamente (sem hop HTTP interno).
- O SDK `mcp` é a única dependência nova no orchestrator.
- O nginx precisa de `proxy_buffering off` no `/mcp/` (SSE).
- Testes do backend rodam dentro do container: `docker exec agent-portal-orchestrator sh -c 'cd /app && python -m pytest tests/ -q'`.
- Testes do portal: `cd agent-portal && npx vitest run`.

## Review Focus

1. **Fluxo OAuth completo.** 401 → metadata → registration → authorize → consent → token → tool call. Cada passo testado.
2. **Isolamento.** O MCP server não quebra nenhuma rota existente. O auth global do FastAPI continua funcionando.
3. **Tools funcionais.** Cada tool chama a service layer correta e retorna o resultado esperado.
4. **Segurança.** Token expirado/revogado/aud errado → 401. PKCE obrigatório. Code não reutilizável.
5. **Frontend.** Consent page funciona (login → consent → redirect). Página de gestão mostra URL, tokens, tools.

---

## Estrutura de arquivos

### Backend (orchestrator)

- `agent-orchestrator/app/mcp_server/__init__.py` (novo)
- `agent-orchestrator/app/mcp_server/server.py` (novo)
- `agent-orchestrator/app/mcp_server/auth.py` (novo)
- `agent-orchestrator/app/mcp_server/context.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/__init__.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/agents.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/pipelines.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/mcp_servers.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/knowledge.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/integrations.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/skills.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/tools.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/workspaces.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/approvals.py` (novo)
- `agent-orchestrator/app/mcp_server/tools/runs.py` (novo)
- `agent-orchestrator/app/api/oauth.py` (novo)
- `agent-orchestrator/app/db/models.py` (modificar: `MCPOAuthClient`, `MCPOAuthToken`)
- `agent-orchestrator/app/core/config.py` (modificar: `mcp_base_url`, `mcp_token_expire_hours`, `mcp_refresh_expire_days`)
- `agent-orchestrator/app/main.py` (modificar: lifespan + mount)
- `agent-orchestrator/alembic/versions/xxx_mcp_oauth_tables.py` (novo)
- `agent-orchestrator/pyproject.toml` (modificar: `mcp[cli]`)
- `agent-orchestrator/tests/test_mcp_server_auth.py` (novo)
- `agent-orchestrator/tests/test_mcp_oauth.py` (novo)
- `agent-orchestrator/tests/test_mcp_tools_agents.py` (novo)
- `agent-orchestrator/tests/test_mcp_tools_pipelines.py` (novo)
- `agent-orchestrator/tests/test_mcp_tools_misc.py` (novo)

### Frontend (portal)

- `agent-portal/app/(auth)/mcp-consent/page.tsx` (novo)
- `agent-portal/app/(dashboard)/mcp/page.tsx` (novo)
- `agent-portal/components/mcp/token-list.tsx` (novo)
- `agent-portal/components/mcp/tools-list.tsx` (novo)
- `agent-portal/components/mcp/mcp-setup-card.tsx` (novo)
- `agent-portal/components/layout/app-sidebar.tsx` (modificar: link MCP)

### Infra

- `nginx/conf.d/10-public.conf` (modificar: locations /mcp/, /oauth/, /.well-known/, /mcp-consent)
- `docker-compose.yml` (modificar: env vars MCP_*)

---

### Task 1: Dependência + config + models + migração

**Files:**
- Modify: `agent-orchestrator/pyproject.toml`, `agent-orchestrator/app/core/config.py`, `agent-orchestrator/app/db/models.py`
- Create: `agent-orchestrator/alembic/versions/xxx_mcp_oauth_tables.py`

- [ ] **Step 1: Adicionar `mcp[cli]` ao `pyproject.toml`.** Na lista de `dependencies`, adicionar `"mcp[cli]>=1.9.0"`. Rodar `pip install .[dev]` dentro do container pra confirmar que instala sem conflito.
- [ ] **Step 2: Config.** Em `app/core/config.py`, adicionar: `mcp_base_url: str = "http://localhost"`, `mcp_token_expire_hours: int = 1`, `mcp_refresh_expire_days: int = 30`.
- [ ] **Step 3: Models.** Em `app/db/models.py`, adicionar `MCPOAuthClient` (id, client_id, client_name, redirect_uris JSONB, grant_types JSONB, created_at) e `MCPOAuthToken` (jti PK, user_id FK, client_id FK, scope, expires_at, revoked_at, created_at).
- [ ] **Step 4: Migração Alembic.** Criar migração que cria as duas tabelas. Rodar `alembic upgrade head` no container.
- [ ] **Step 5: Teste de migração.** `test_migration.py` já existe; adicionar teste que verifica as tabelas novas. Rodar pytest.
- [ ] **Step 6: Commit** — `feat(mcp): dependencia, config, models e migracao para oauth`

---

### Task 2: FastMCP server + lifespan + mount

**Files:**
- Create: `agent-orchestrator/app/mcp_server/__init__.py`, `server.py`, `context.py`
- Modify: `agent-orchestrator/app/main.py`

- [ ] **Step 1: `context.py`.** Criar contextvar `current_user: ContextVar[User | None]` com getter `get_current_mcp_user()`.
- [ ] **Step 2: `server.py`.** Instanciar `FastMCP("AgentPortal", stateless_http=True)`. Criar `mcp_lifespan` (asynccontextmanager) que entra em `mcp.session_manager.run()`. Exportar `mcp` e `mcp_lifespan`.
- [ ] **Step 3: `__init__.py`.** Importar todos os módulos de `tools/` (efeito colateral: registro das tools).
- [ ] **Step 4: `main.py`.** Estender o lifespan existente: usar `AsyncExitStack` pra entrar no `mcp_lifespan` junto com o resto. Após `_discover_routers()`, chamar `app.mount("/mcp", mcp.streamable_http_app())`.
- [ ] **Step 5: Teste de smoke.** `GET /mcp/mcp` sem token → 401 (ou 405, dependendo do método). `GET /health` continua 200. Rodar pytest.
- [ ] **Step 6: Commit** — `feat(mcp): fastmcp server montado em /mcp/mcp`

---

### Task 3: Middleware ASGI de auth

**Files:**
- Create: `agent-orchestrator/app/mcp_server/auth.py`
- Modify: `agent-orchestrator/app/mcp_server/server.py` (aplicar middleware)
- Create: `agent-orchestrator/tests/test_mcp_server_auth.py`

- [ ] **Step 1: Testes (falham primeiro).**
  - Request sem `Authorization` → 401 com `WWW-Authenticate` header;
  - Request com token inválido → 401;
  - Request com token expirado → 401;
  - Request com token válido → 200, `current_user` setado no contextvar;
  - Request com token revogado → 401;
  - Request com `aud` errado → 401.
- [ ] **Step 2: Implementar `auth.py`.** Middleware ASGI que:
  - Lê `Authorization: Bearer <token>`;
  - Decodifica JWT, valida `typ == "mcp"`, `exp`, `aud == settings.mcp_base_url + "/mcp/mcp"`;
  - Checa revogação: `SELECT revoked_at FROM mcp_oauth_tokens WHERE jti = <jti>`;
  - Carrega `User` do banco;
  - Injeta no contextvar;
  - Falhou → responde 401 com `WWW-Authenticate: Bearer resource_metadata="<mcp_base_url>/.well-known/oauth-protected-resource", scope="mcp:full"`.
- [ ] **Step 3: Aplicar middleware.** Em `server.py`, envolver o `streamable_http_app()` com o middleware ASGI.
- [ ] **Step 4: Rodar testes.** Todos passam.
- [ ] **Step 5: Commit** — `feat(mcp): middleware asgi de auth com jwt e revogacao`

---

### Task 4: Endpoints OAuth (metadata + registration + authorize + token + revoke)

**Files:**
- Create: `agent-orchestrator/app/api/oauth.py`
- Create: `agent-orchestrator/tests/test_mcp_oauth.py`

- [ ] **Step 1: Testes (falham primeiro).**
  - `GET /.well-known/oauth-protected-resource` → JSON com `authorization_servers`;
  - `GET /.well-known/oauth-authorization-server` → JSON com endpoints;
  - `POST /oauth/register` → cria client, devolve `client_id`;
  - `GET /oauth/authorize` sem sessão → 302 pro login;
  - `GET /oauth/authorize` com sessão → 302 pro consent com code;
  - `POST /oauth/token` com code válido → access + refresh tokens;
  - `POST /oauth/token` com PKCE inválido → 400;
  - `POST /oauth/token` com code reutilizado → 400;
  - `POST /oauth/revoke` → token revogado.
- [ ] **Step 2: Metadata endpoints.**
  - `GET /.well-known/oauth-protected-resource`: `{"resource": "<mcp_base_url>/mcp/mcp", "authorization_servers": ["<mcp_base_url>"], "scopes_supported": ["mcp:full"]}`.
  - `GET /.well-known/oauth-authorization-server`: `{"issuer": "<mcp_base_url>", "authorization_endpoint": "<mcp_base_url>/oauth/authorize", "token_endpoint": "<mcp_base_url>/oauth/token", "registration_endpoint": "<mcp_base_url>/oauth/register", "code_challenge_methods_supported": ["S256"], "grant_types_supported": ["authorization_code"], "response_types_supported": ["code"]}`.
- [ ] **Step 3: `POST /oauth/register`.** Body: `{client_name, redirect_uris, grant_types}`. Gera `client_id` (uuid), salva em `mcp_oauth_clients`, retorna `{client_id, client_name, redirect_uris, grant_types}`.
- [ ] **Step 4: `GET /oauth/authorize`.** Params: `client_id`, `redirect_uri`, `scope`, `code_challenge`, `code_challenge_method`, `state`, `resource`. Se não logado → 302 pro login com `return_to`. Se logado → 302 pro `/mcp-consent` com params.
- [ ] **Step 5: `POST /oauth/token`.** Body: `grant_type=authorization_code`, `code`, `code_verifier`, `client_id`, `redirect_uri`, `resource`. Valida PKCE (S256), gera access token (JWT `typ: "mcp"`, `aud`, `scope`, `exp`) + refresh token (JWT `typ: "mcp_refresh"`, `exp`), salva em `mcp_oauth_tokens`, retorna `{access_token, refresh_token, token_type: "Bearer", expires_in}`.
- [ ] **Step 6: `POST /oauth/revoke`.** Body: `token`. Marca `revoked_at` em `mcp_oauth_tokens`.
- [ ] **Step 7: Refresh token rotation.** No `POST /oauth/token` com `grant_type=refresh_token`: valida refresh token, invalida o antigo, emite novo par.
- [ ] **Step 8: Rodar testes.** Todos passam.
- [ ] **Step 9: Commit** — `feat(mcp): endpoints oauth 2.1 (metadata, registration, authorize, token, revoke)`

---

### Task 5: Página de consentimento no portal

**Files:**
- Create: `agent-portal/app/(auth)/mcp-consent/page.tsx`
- Modify: `agent-portal/middleware.ts` (se necessário: permitir `/mcp-consent` sem sessão)

- [ ] **Step 1: Teste (falha primeiro).** Renderiza com params: mostra nome do client, escopo, redirect URI. Botões "Autorizar" e "Recusar" presentes.
- [ ] **Step 2: Implementar.**
  - Lê params da URL: `client_id`, `client_name`, `redirect_uri`, `scope`, `code`, `state`, `resource`.
  - Se não logado → redirect pro login com `callbackUrl=/mcp-consent?...`.
  - Mostra: "O client **<client_name>** quer acessar o Agent Portal." + escopo + redirect URI.
  - "Autorizar": faz `POST /api/mcp/consent` (novo endpoint no orchestrator que troca o code por redirect) → redirect pro `redirect_uri?code=...&state=...`.
  - "Recusar": redirect pro `redirect_uri?error=access_denied&state=...`.
- [ ] **Step 3: Endpoint de consent no orchestrator.** `POST /api/mcp/consent` (novo, em `app/api/oauth.py`): body `{code, state}`. Valida que o code é do user logado, redireciona. (Alternativa: o portal faz o redirect direto, sem endpoint extra.)
- [ ] **Step 4: Rodar vitest.** Teste passa.
- [ ] **Step 5: Commit** — `feat(portal): pagina de consentimento mcp`

---

### Task 6: Tools de Agents

**Files:**
- Create: `agent-orchestrator/app/mcp_server/tools/__init__.py`, `agents.py`
- Create: `agent-orchestrator/tests/test_mcp_tools_agents.py`

- [ ] **Step 1: Testes (falham primeiro).**
  - `create_agent` com args mínimos → cria agente, retorna id;
  - `list_agents` → lista agentes do user;
  - `get_agent` com id válido → retorna agente;
  - `get_agent` com id inexistente → ToolError;
  - `update_agent` com partial update → atualiza;
  - `delete_agent` → remove;
  - Tool sem user no contextvar → ToolError.
- [ ] **Step 2: Implementar `tools/agents.py`.** 5 tools: `create_agent`, `list_agents`, `get_agent`, `update_agent`, `delete_agent`. Cada uma: lê `get_current_mcp_user()`, chama `AgentService`, retorna dict. Erros → `ToolError` com mensagem pt-BR.
- [ ] **Step 3: Rodar testes.** Todos passam.
- [ ] **Step 4: Commit** — `feat(mcp): tools de agents`

---

### Task 7: Tools de Pipelines + Runs

**Files:**
- Create: `agent-orchestrator/app/mcp_server/tools/pipelines.py`, `runs.py`
- Create: `agent-orchestrator/tests/test_mcp_tools_pipelines.py`

- [ ] **Step 1: Testes (falham primeiro).**
  - `create_pipeline` → cria pipeline;
  - `list_pipelines` → lista;
  - `get_pipeline` → obtém;
  - `update_pipeline` → atualiza;
  - `delete_pipeline` → remove;
  - `run_pipeline` → dispara run, retorna runId;
  - `list_runs` → lista runs;
  - `get_run` → obtém run;
  - `cancel_run` → cancela.
- [ ] **Step 2: Implementar `tools/pipelines.py`.** 6 tools.
- [ ] **Step 3: Implementar `tools/runs.py`.** 3 tools.
- [ ] **Step 4: Rodar testes.** Todos passam.
- [ ] **Step 5: Commit** — `feat(mcp): tools de pipelines e runs`

---

### Task 8: Tools de MCP Servers + Integrations

**Files:**
- Create: `agent-orchestrator/app/mcp_server/tools/mcp_servers.py`, `integrations.py`
- Create: `agent-orchestrator/tests/test_mcp_tools_misc.py` (seção MCP + Integrations)

- [ ] **Step 1: Testes (falham primeiro).**
  - `create_mcp_server` → cria;
  - `list_mcp_servers` → lista;
  - `get_mcp_server` → obtém;
  - `update_mcp_server` → atualiza;
  - `delete_mcp_server` → remove;
  - `test_mcp_server` → testa conexão;
  - `create_integration` → cria;
  - `list_integrations` → lista;
  - `get_integration` → obtém;
  - `update_integration` → atualiza;
  - `delete_integration` → remove;
  - `test_integration` → testa.
- [ ] **Step 2: Implementar `tools/mcp_servers.py`.** 6 tools.
- [ ] **Step 3: Implementar `tools/integrations.py`.** 6 tools.
- [ ] **Step 4: Rodar testes.** Todos passam.
- [ ] **Step 5: Commit** — `feat(mcp): tools de mcp servers e integrations`

---

### Task 9: Tools de Knowledge + Skills + Tools + Workspaces + Approvals

**Files:**
- Create: `agent-orchestrator/app/mcp_server/tools/knowledge.py`, `skills.py`, `tools.py`, `workspaces.py`, `approvals.py`
- Modify: `agent-orchestrator/tests/test_mcp_tools_misc.py` (seção Knowledge, Skills, Tools, Workspaces, Approvals)

- [ ] **Step 1: Testes (falham primeiro).**
  - `create_knowledge_base` → cria;
  - `list_knowledge_bases` → lista;
  - `get_knowledge_base` → obtém;
  - `delete_knowledge_base` → remove;
  - `upload_knowledge_file` → upload;
  - `query_knowledge` → RAG query;
  - `create_skill` → cria;
  - `list_skills` → lista;
  - `get_skill` → obtém;
  - `update_skill` → atualiza;
  - `delete_skill` → remove;
  - `create_tool` → cria;
  - `list_tools` → lista;
  - `get_tool` → obtém;
  - `update_tool` → atualiza;
  - `delete_tool` → remove;
  - `list_workspaces` → lista;
  - `get_workspace` → obtém;
  - `delete_workspace` → remove;
  - `list_approvals` → lista;
  - `get_approval` → obtém;
  - `approve` → aprova;
  - `reject` → rejeita.
- [ ] **Step 2: Implementar `tools/knowledge.py`.** 6 tools.
- [ ] **Step 3: Implementar `tools/skills.py`.** 5 tools.
- [ ] **Step 4: Implementar `tools/tools.py`.** 5 tools.
- [ ] **Step 5: Implementar `tools/workspaces.py`.** 3 tools.
- [ ] **Step 6: Implementar `tools/approvals.py`.** 4 tools.
- [ ] **Step 7: Rodar testes.** Todos passam.
- [ ] **Step 8: Commit** — `feat(mcp): tools de knowledge, skills, tools, workspaces e approvals`

---

### Task 10: Página de gestão MCP no portal

**Files:**
- Create: `agent-portal/app/(dashboard)/mcp/page.tsx`, `agent-portal/components/mcp/token-list.tsx`, `tools-list.tsx`, `mcp-setup-card.tsx`
- Modify: `agent-portal/components/layout/app-sidebar.tsx`

- [ ] **Step 1: Testes (falham primeiro).**
  - Página renderiza com URL do MCP;
  - Botão "Copiar" funciona;
  - Lista de tokens renderiza;
  - Botão "Revogar" chama API;
  - Lista de tools renderiza;
  - Link "MCP" no sidebar.
- [ ] **Step 2: `mcp-setup-card.tsx`.** Mostra URL (`<MCP_BASE_URL>/mcp/mcp`), botão "Copiar", instruções de configuração (JSON de exemplo pra Claude Desktop).
- [ ] **Step 3: `token-list.tsx`.** Tabela: nome do client, criado em, expira em, botão "Revogar". Chama `GET /api/mcp/tokens` e `DELETE /api/mcp/tokens/{jti}`.
- [ ] **Step 4: `tools-list.tsx`.** Lista das ~45 tools com nome e descrição. Catálogo estático (hardcoded no componente, ou `GET /api/mcp/tools`).
- [ ] **Step 5: `page.tsx`.** Layout: `mcp-setup-card` no topo, `token-list` no meio, `tools-list` embaixo.
- [ ] **Step 6: Sidebar.** Adicionar link "MCP" com ícone de plug/conexão.
- [ ] **Step 7: Endpoints de gestão no orchestrator.** `GET /api/mcp/tokens` (lista tokens do user), `DELETE /api/mcp/tokens/{jti}` (revoga), `GET /api/mcp/tools` (catálogo estático). Adicionar em `app/api/oauth.py` ou novo `app/api/mcp_admin.py`.
- [ ] **Step 8: Rodar vitest.** Testes passam.
- [ ] **Step 9: Commit** — `feat(portal): pagina de gestao mcp (url, tokens, tools)`

---

### Task 11: Nginx + docker-compose

**Files:**
- Modify: `nginx/conf.d/10-public.conf`, `docker-compose.yml`

- [ ] **Step 1: Nginx.** Adicionar locations: `/mcp/` (proxy_buffering off, read_timeout 300s), `/oauth/`, `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`, `/mcp-consent` (portal).
- [ ] **Step 2: Docker-compose.** Adicionar env vars no orchestrator: `MCP_BASE_URL=http://localhost`, `MCP_TOKEN_EXPIRE_HOURS=1`, `MCP_REFRESH_EXPIRE_DAYS=30`.
- [ ] **Step 3: Teste manual.** `docker compose -p squad-agentica up -d --force-recreate orchestrator nginx`. `curl http://localhost/mcp/mcp` → 401 com `WWW-Authenticate`. `curl http://localhost/.well-known/oauth-protected-resource` → JSON.
- [ ] **Step 4: Commit** — `feat(infra): nginx e docker-compose para mcp server`

---

### Task 12: E2E + QA + registro

**Files:**
- Create: `e2e/tests/13-mcp-server.spec.ts`
- Modify: `docs/superpowers/validacoes/PENDENCIAS.md`

- [ ] **Step 1: E2E do fluxo OAuth.** Com Playwright + httpx:
  - `POST /mcp/mcp` sem token → 401;
  - `GET /.well-known/oauth-protected-resource` → JSON;
  - `GET /.well-known/oauth-authorization-server` → JSON;
  - `POST /oauth/register` → client_id;
  - `GET /oauth/authorize` (com sessão) → redirect com code;
  - `POST /oauth/token` (com code + PKCE) → access_token;
  - `POST /mcp/mcp` com token → 200, tools listadas;
  - `tools/call create_agent` → agente criado.
- [ ] **Step 2: E2E da consent page.** Playwright: navegar pro `/mcp-consent`, afirmar que mostra nome do client, clicar "Autorizar", afirmar redirect.
- [ ] **Step 3: QA visual.** Capturar a página de gestão MCP e a consent page em 1440×900.
- [ ] **Step 4: Regressão.** pytest completo do orchestrator, vitest completo do portal, `tsc`, lint.
- [ ] **Step 5: Commit** — `test(mcp): e2e do fluxo oauth e tools, qa visual`
