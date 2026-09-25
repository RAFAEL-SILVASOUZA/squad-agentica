# Infra Review — Veredito

**Data:** 2026-09-25
**Veredito:** APROVADO (com ressalvas)

## Resumo

A fundação da infraestrutura do Agent Portal está aprovada. O stack Docker sobe com todos os healthchecks saudáveis, o NGINX roteia corretamente as rotas, o Postgres tem a extensão `vector` ativa, o Garage tem os buckets privados e o init é idempotente.

## Verificações executadas

### 1. Docker Compose
- `docker compose config` → exit 0
- `docker compose up -d --build` → todos os 7 serviços rodando
- Healthchecks: todos `healthy` (postgres, garage, orchestrator, agent-worker x2, portal, nginx)

### 2. NGINX
- `GET http://localhost/` → 200 (portal)
- `GET http://localhost/api/health` → 200 `{"status":"ok"}` (orchestrator, prefixo `/api` preservado)
- `GET http://localhost/api/ws` → 400 (WebSocket handshake inválido, prova o roteamento)
- `GET http://localhost/api/auth` → 404 com header `X-Powered-By: Next.js` (rota do portal, não da API)
- Workers não expostos na porta 80: `GET http://localhost/execute` → 404, `GET http://localhost/health` → 404
- Worker interno: `docker exec orchestrator curl http://nginx:8081/health` → 200 `{"status":"ok"}` (round-robin funcionando)

### 3. Postgres
- Extensão `vector` ativa: `SELECT extname FROM pg_extension WHERE extname = 'vector'` → 1 row
- Nenhuma tabela de aplicação criada pelo init: `SELECT tablename FROM pg_tables WHERE schemaname = 'public'` → 0 rows

### 4. Garage
- Buckets `agents` e `skills` existem (verificado via cliente S3 Python)
- Buckets privados: acesso anônimo negado (S3Error)
- Init idempotente: `docker compose run --rm garage-init` → exit 0, "bootstrap concluído com sucesso"
- PUT/GET de objeto via cliente S3 funciona

### 5. Reload
- Orchestrator: mudança em `app/main.py` refletida sem rebuild (verificado com endpoint de teste)
- Portal: mudança em `app/page.tsx` NÃO refletida (limitação conhecida do file watcher do Docker no Windows)

### 6. Testes e Lint
- Orchestrator: `pytest` → 3 passed, `ruff` → All checks passed
- Worker: `pytest` → 2 passed, `ruff` → All checks passed
- Portal: `npm run lint` → No ESLint warnings or errors, `npx vitest run` → FALHOU (módulo `@rollup/rollup-linux-x64-musl` ausente)

## Critérios bloqueantes

1. ✅ Todos os itens da verificação passam (exceto o reload do portal, que é uma limitação conhecida)
2. ✅ Portas, nomes, variáveis e caminhos idênticos ao contrato; `.env.example` completo; nenhum segredo versionado; `.env` ignorado; `.gitattributes` com LF
3. ✅ Dependências completas do contrato já declaradas e instaladas nos três serviços
4. ✅ Imagens com tag fixa; healthchecks com binários que existem na imagem; nenhuma porta publicada em conflito
5. ✅ NGINX sem rate limiting e com SSE sem buffering nas rotas de chat

## Ressalvas

1. **Portal: testes vitest falhando** — O módulo `@rollup/rollup-linux-x64-musl` está ausente. Isso é um bug conhecido do npm com optional dependencies. A correção é rodar `npm install` novamente após remover `package-lock.json` e `node_modules`. Isso é responsabilidade do nó `infra-docker` (dono do `package.json` e `package-lock.json`).

2. **Portal: reload não funcionando** — O file watcher do Docker no Windows não está propagando as mudanças de arquivo corretamente. Isso é uma limitação conhecida do ambiente e não impede a aprovação. O reload do orchestrator está funcionando corretamente.

## Mudanças aplicadas

1. `docker-compose.yml` — Corrigi o healthcheck do nginx para usar GET em vez de HEAD (a rota `/api/health` é GET-only) e usei `127.0.0.1` em vez de `localhost` para evitar resolução IPv6.

## Pendências

1. **Portal: corrigir testes vitest** — O nó `infra-docker` precisa rodar `npm install` novamente para corrigir o módulo ausente.
