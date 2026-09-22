# D8 — Capacidades (Skills + Tools Custom + MCP)

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 4 · Orquestração**. Dependência: **D4** (contrato do agente — a mochila é do agente).
> Base: spec (seções 6 "Sistema de Skills", 6.3 "Ferramentas Básicas", 6.4 "Tools Custom", 6.7 "Servidores MCP", 12 ADR-007) + plano.

## Objetivo

Construir a mochila completa do agente: skills (prompts reutilizáveis), ferramentas básicas (read_file, shell opt-in, etc.), tools custom (scripts Python em sandbox), e servidores MCP (stdio/sse/http). Cada camada tem registry, CRUD, e integração com o contrato do agente.

## Escopo (o que FAZ)

- Skill Registry + Loader + skills built-in.
- Ferramentas básicas (9 built-ins).
- Tool Registry + Sandbox + Validator + tools custom API + editor (portal).
- MCP Registry + Client + Validator + MCP servers API + biblioteca (portal).
- Bibliotecas de skills e MCP no portal.

## Escopo (o que NÃO FAZ)

- NÃO implementa o grafo/pipeline (D5), NÃO executa (D6), NÃO implementa human-in-the-loop (D7).
- NÃO implementa knowledge/RAG (D9), NÃO implementa integrações de plataforma além de GitHub (Azure/GitLab — seção 8 da spec, V2+).
- NÃO define o contrato do agente (D4) — só preenche a mochila que o agente consome.

## Dependências

- **D4:** contrato do agente + `Agent.run(inputs, capabilities)`. O D8 expõe `loader.load(agent_snapshot) -> AgentCapabilities`; o D6 (runtime) a consome. O D8 NÃO injeta no snapshot.
- **D3:** models `Skill`, `CustomTool`, `MCPServer`, `MCPToolInfo` + routers stub (`/api/skills`, `/api/tools`, `/api/mcp-servers`) + tipos em `types.ts`.

## Arquivos que OWNS

```
agent-orchestrator/
  app/skills/
    registry.py                 (CRUD skills)
    loader.py                   (carrega por tipo, injeta no agente)
    builtins/                   (code-gen, test-runner, security-scanner, doc-writer, api-client, deploy-runner)
  app/tools/
    registry.py                 (CRUD tools custom)
    sandbox.py                  (subprocesso isolado, timeout)
    validator.py                (valida script + I/O)
    builtins/                   (read_file, write_file, edit_file, shell, web_search, web_fetch, glob, grep, list_directory)
  app/mcp/
    registry.py                 (CRUD servers MCP)
    client.py                   (stdio/sse/http, tools/list, invocação)
    validator.py                (valida config de conexão)
  app/api/skills.py
  app/api/tools.py
  app/api/mcp_servers.py
agent-portal/
  components/SkillsLibrary.tsx
  components/ToolsEditor.tsx
  components/MCPServersLibrary.tsx
```

## Tarefas

### 8.1 Skill Registry
- `skills/registry.py`: CRUD completo de skills no PostgreSQL (tipo `prompt`): `GET /api/skills` (listar), `POST /api/skills` (criar), `GET /api/skills/:id` (detalhe), `PUT /api/skills/:id` (atualizar), `DELETE /api/skills/:id` (remover).
- Aceite: criar/listar/detalhar/atualizar/remover skill via API.

### 8.2 Skill Loader
- `skills/loader.py`: carrega skills (prompts) e injeta no `systemPrompt` do `AgentCapabilities`. O loader é chamado pelo D6 (runtime), não pelo D4.
- Aceite: skill do tipo prompt é renderizada no `systemPrompt` do `AgentCapabilities`.

### 8.3 Skills built-in
- `skills/builtins/`: code-gen, test-runner, security-scanner, doc-writer, api-client, deploy-runner (templates de prompt).
- Aceite: skills built-in carregadas e injetadas no prompt do agente.

### 8.4 Ferramentas básicas
- `tools/builtins/`: read_file, write_file, edit_file, shell, web_search, web_fetch, glob, grep, list_directory. Todas disponíveis por padrão, exceto `shell` que é opt-in (`Agent.shellAccess: boolean`, default `false`). Read-only na UI.
- Aceite: ferramentas básicas disponíveis em todo agente; shell só quando `shellAccess=true`.

### 8.5 Tool Registry
- `tools/registry.py`: CRUD de tools custom.
- Aceite: criar/listar tool custom.

### 8.6 Tool Sandbox
- `tools/sandbox.py`: subprocesso isolado, timeout (30s default, máx 120s), sem acesso ao filesystem do host, variáveis de ambiente (secrets) injetadas. Erro retornado como `{"error": "..."}`.
- Aceite: tool custom roda em sandbox sem acessar host; timeout funciona.

### 8.7 Tool Validator
- `tools/validator.py`: valida script Python (compila) + contrato de I/O (inputs/outputs coerentes).
- Aceite: script inválido é rejeitado no deploy.

### 8.8 API de tools custom
- Preencher router: `GET/POST/PUT/DELETE /api/tools`, `POST /api/tools/:id/deploy`, `POST /api/tools/:id/test`.
- Aceite: criar → validar → deploy → testar via API.

### 8.9 Editor de tools (Portal)
- `ToolsEditor.tsx`: script Python + parâmetros de I/O + deploy + teste.
- Aceite: editar tool no portal, deploy, testar.

### 8.10 MCP Registry
- `mcp/registry.py`: CRUD de servidores MCP.
- Aceite: registrar servidor MCP.

### 8.11 MCP Client
- `mcp/client.py`: conecta via stdio/sse/http, chama `tools/list`, invoca tools. `toolFilter` pra expor subconjunto.
- Aceite: conectar servidor, listar tools descobertas, invocar uma tool.

### 8.12 MCP Validator
- `mcp/validator.py`: valida config de conexão (command para stdio, url para sse/http, env).
- Aceite: config inválida é rejeitada.

### 8.13 API de MCP servers
- Preencher router: `GET/POST/PUT/DELETE /api/mcp-servers`, `POST /api/mcp-servers/:id/test`.
- Aceite: registrar → testar → tools descobertas aparecem via API.

### 8.14 Biblioteca MCP (Portal)
- `MCPServersLibrary.tsx`: registrar, testar conexão, listar tools descobertas.
- Aceite: registrar servidor no portal, testar, ver tools.

### 8.15 Biblioteca de Skills (Portal)
- `SkillsLibrary.tsx`: listar skills, associar a agentes.
- Aceite: listar skills, associar a um agente.

### 8.16 Integração GitHub (backend)
- `integrations/github.py`: client com `GITHUB_TOKEN` (PAT, escopo `repo:read`) do `.env`.
- Endpoints de listagem: `GET /api/integrations/github/repos`, `GET /api/integrations/github/repos/:owner/:repo/pulls`, `GET /api/integrations/github/repos/:owner/:repo/issues`.
- CRUD de integrações: `GET/POST/PUT/DELETE /api/integrations` (model `Integration`, seção 4.7 da spec).
- Exposto como tools ao agente: `list_repos`, `list_pulls`, `list_issues`, `get_pr_diff` (contrato na seção 8.1 da spec).
- Aceite: criar integração GitHub via API; listar repos/PRs/issues via API; agente com integração GitHub invoca tools de listagem.

## Critérios de aceite (DoD)

- [ ] Skills built-in são carregadas e injetadas no prompt do agente
- [ ] Ferramentas básicas estão disponíveis em todo agente (read-only na UI); shell só quando `shellAccess=true`
- [ ] Tool custom: criar → validar → deploy → testar → usar em agente
- [ ] Tool custom roda em sandbox (sem acesso ao host)
- [ ] MCP server: registrar → testar conexão → tools descobertas aparecem
- [ ] MCP server conectado a agente expõe tools na mochila
- [ ] Biblioteca de skills: listar e associar a agentes
- [ ] Editor de tools: script + I/O + deploy + teste

## Contratos de interface (o que entrega aos outros)

- **Para D6:** `loader.load(agent_snapshot) -> AgentCapabilities` é o contrato que o D6 consome. O D6 chama o loader antes de `Agent.run()` e passa o resultado como segundo argumento. O D8 expõe a função; o D6 a consome. O loader resolve: (a) skills → injeta prompts no `systemPrompt`, (b) tools → carrega CustomTools deployadas + básicas habilitadas (shell se `shellAccess=true`), (c) mcpServers → descobre tools via `tools/list`, (d) knowledge → busca contexto via RAG.
- **Para D10:** `SkillsLibrary.tsx`, `ToolsEditor.tsx`, `MCPServersLibrary.tsx`.

## Riscos

- **Sandbox:** subprocesso isolado pode ser frágil (segurança real). Considerar Docker-in-Docker ou gVisor. Timeout agressivo.
- **MCP stdio:** spawn de processo externo (npx) precisa de gerenciamento de ciclo de vida. Testar conexão real.
- **Ferramentas básicas read-only na UI:** não podem ser removidas pelo usuário. Shell é opt-in (`shellAccess`), com blocklist de comandos e diretório restrito.
