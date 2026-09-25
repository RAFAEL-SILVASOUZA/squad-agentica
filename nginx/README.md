# NGINX — Agent Portal

Dono: `infra-nginx` (contrato §9, FASE 1). Imagem: `nginx:1.27-alpine` (contrato §3).

## Estrutura

```
nginx/
├── nginx.conf            # Config principal (events, http, includes)
├── conf.d/
│   ├── 00-upstreams.conf # Upstreams: portal, orchestrator
│   ├── 10-public.conf    # Server público :80
│   └── 20-internal.conf  # Server interno :8081 (worker pool)
└── README.md             # Este arquivo
```

## Tabela de rotas e precedências (server público :80)

Ordem de precedência NGINX: `location =` > `location ~` (regex) > `location ^~` > `location /prefix/`.

| # | Locação | Tipo | Destino | Notas |
|---|---------|------|---------|-------|
| 1 | `= /api/auth` | exact | `portal:3000` | NextAuth (sem barra final) |
| 1 | `/api/auth/` | prefix | `portal:3000` | NextAuth (callbacks, csrf, session) |
| 2 | `= /api/session-token` | exact | `portal:3000` | Route handler JWT de delegação |
| 3 | `= /api/ws` | exact | `orchestrator:8000` | WebSocket upgrade, timeouts 3600s |
| 4 | `= /api/agents/chat` | exact | `orchestrator:8000` | SSE streaming, buffering off |
| 4 | `~ ^/api/agents/[^/]+/chat$` | regex | `orchestrator:8000` | SSE streaming (edição), buffering off |
| 5 | `/api/` | prefix | `orchestrator:8000` | Mantém prefixo `/api` |
| 6 | `/_next/webpack-hmr` | prefix | `portal:3000` | HMR WebSocket (next dev) |
| 6 | `/_next/static/` | prefix | `portal:3000` | Assets cache longo |
| 6 | `/` | prefix | `portal:3000` | SPA, páginas, resto |

### Regras de precedência explicadas

1. **`location = /api/auth`** e **`location /api/auth/`** têm precedência sobre `location /api/` porque:
   - `= /api/auth` é exact match (maior precedência de todas).
   - `/api/auth/` é prefix match mais específico que `/api/` (NGINX escolhe o prefix mais longo).
   - Resultado: `/api/auth/callback/credentials` vai para o portal, não para a API.

2. **`location = /api/session-token`** é exact match, vence sobre `/api/`.

3. **`location = /api/ws`** é exact match, vence sobre `/api/`. O WebSocket upgrade é feito aqui.

4. **SSE locations** (`= /api/agents/chat` e regex `~ ^/api/agents/[^/]+/chat$`):
   - Exact match vence sobre prefix `/api/`.
   - Regex tem precedência sobre prefix (sem `^~`), mas depois de exact.
   - `proxy_buffering off` + `proxy_read_timeout 300s` para streaming.

5. **`location /api/`** (prefix): captura tudo que não casou com as regras acima.
   - `proxy_pass http://orchestrator;` (sem URI) preserva o path original.
   - `/api/agents` → `http://orchestrator:8000/api/agents` (prefixo mantido).

6. **`location /`** (prefix): fallback para o portal.

### Por que o worker NÃO está na :80

O worker (`agent-worker:9000`) **não** tem rota no server público. Ele é acessível **somente** pelo server interno `:8081` (não publicado no host). O orchestrator chama `POST http://nginx:8081/execute`.

## Server interno (:8081) — Worker pool

| Locação | Destino | Notas |
|---------|---------|-------|
| `/execute` | `agent-worker:9000` (round-robin) | POST, timeout 300s, X-Worker-Token pass-through |
| `/health` | `agent-worker:9000` (round-robin) | GET, healthcheck |

### DNS dinâmico e round-robin

O worker pool usa **resolver DNS do Docker** (`127.0.0.11`) com variável no `proxy_pass`:

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;
set $worker_upstream http://agent-worker:9000;
proxy_pass $worker_upstream;
```

- O Docker DNS resolve `agent-worker` para **todos** os IPs do serviço.
- O NGINX faz round-robin entre eles.
- `valid=10s`: re-resolve a cada 10s (sobrevive a recriação de containers).
- **Limitação:** sem `keepalive` (variável no `proxy_pass` não permite `upstream` block). Para V1 local (1-2 workers) o impacto é negligível.

### X-Worker-Token

O orchestrator (`worker_client`) envia `X-Worker-Token` no header do request. O NGINX o **repassa por default** (pass-through de headers do client para o upstream). Não é preciso `proxy_set_header`.

O `WORKER_TOKEN` está no ambiente do container NGINX (exigência do contrato §2.4) para validação futura ou logging.

## Headers de segurança

| Header | Valor | Escopo |
|--------|-------|--------|
| `X-Content-Type-Options` | `nosniff` | Server público :80 |
| `X-Frame-Options` | `DENY` | Server público :80 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Server público :80 |

**Sem CSP** (quebra Next.js em dev). **Sem HSTS** (HTTP local, não faz sentido).

## Streaming (SSE)

Rotas com `proxy_buffering off` + timeouts longos:
- `POST /api/agents/chat` (construção de agente)
- `POST /api/agents/{id}/chat` (edição de agente)

Configuração:
```nginx
proxy_buffering off;
proxy_cache off;
proxy_set_header X-Accel-Buffering no;
proxy_read_timeout 300s;
chunked_transfer_encoding on;
```

## WebSocket

`/api/ws` (exact match):
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
proxy_buffering off;
```

## HMR (next dev)

`/_next/webpack-hmr` (WebSocket do Next.js dev server):
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
```

## client_max_body_size

| Server | Valor | Motivo |
|--------|-------|--------|
| :80 (público) | `25m` | Upload de knowledge (multipart, spec 9.3) |
| :8081 (interno) | `10m` | Inputs de agente no body do execute |

## Rate limiting

**Nenhum** rate limiting no NGINX. A spec 14.1 define rate limiting na aplicação (429 JSON). Limites no NGINX devolveriam 503 e quebrariam o portal (todo o tráfego vem do mesmo IP em V1 local).

## Verificação

### Sintaxe (nginx -t)

```bash
# Com a rede do compose (upstreams resolvem):
docker compose run --rm --no-deps nginx nginx -t

# Sem rede (valida só sintaxe, upstreams não resolvem):
docker run --rm \
  -v $(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v $(pwd)/nginx/conf.d:/etc/nginx/conf.d:ro \
  nginx:1.27-alpine \
  nginx -t
```

Nota: sem a rede do compose, `nginx -t` falha na resolução dos upstreams (`portal`, `orchestrator`). Para validar só a sintaxe, use hosts stub:

```bash
docker run --rm \
  -v $(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v $(pwd)/nginx/conf.d:/etc/nginx/conf.d:ro \
  --add-host portal:127.0.0.1 \
  --add-host orchestrator:127.0.0.1 \
  --add-host agent-worker:127.0.0.1 \
  nginx:1.27-alpine \
  nginx -t
```

### Roteamento (ponta a ponta, do revisor)

```bash
# Portal
curl -s http://localhost/ | head -5

# API health (orchestrator)
curl -s http://localhost/api/health

# NextAuth (portal)
curl -s http://localhost/api/auth/csrf

# Session token (portal)
curl -s http://localhost/api/session-token

# Worker (interno, só da rede)
docker compose exec orchestrator python -c "
import urllib.request
req = urllib.request.Request('http://nginx:8081/health')
print(urllib.request.urlopen(req).status)
"
```

## Mudança solicitada em docker-compose.yml (dono: infra-docker)

O `docker-compose.yml` atual monta apenas:
```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
```

**Necessário** também montar o `conf.d/`:
```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  - ./nginx/conf.d:/etc/nginx/conf.d:ro
```

Sem isso, os server blocks em `conf.d/*.conf` não são carregados e o NGINX sobe sem nenhuma rota.

## Limitações documentadas

1. **Worker pool sem keepalive:** variável no `proxy_pass` impede `upstream` block. Para V1 local (1-2 workers) o impacto é negligível. Em produção com N workers, considerar nginx-plus ou load balancer dedicado.

2. **Resolver 127.0.0.11:** específico do Docker (embedded DNS). Não funciona fora do Docker. Para deploy em Kubernetes, usar `resolver` do CoreDNS.

3. **Sem TLS na V1 local:** o NGINX serve HTTP puro. Em produção, TLS termina no load balancer ou no NGINX (certificados via volume).

4. **`server_name _`:** catch-all. Em produção com domínio, substituir pelo domínio real.
