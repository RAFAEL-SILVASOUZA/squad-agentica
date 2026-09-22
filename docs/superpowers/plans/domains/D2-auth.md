# D2 — Autenticação & Segurança

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 1 · Fundação**. Dependência: **D1** (infra funcionando).
> Base: spec (seção 3 "Auth", seção 12 ADR-001/002) + plano `2026-09-21-execution-plan.md`.

## Objetivo

Fazer o portal e a API Python conversarem via JWT. NextAuth.js (portal) é o source of truth da sessão; um route handler emite um JWT que o frontend envia no header `Authorization` para a API Python, que valida com a mesma secret. Na V1 é single-user (credentials), sem RBAC.

## Escopo (o que FAZ)

- NextAuth.js no portal com provider `credentials` (V1). Route handler que emite JWT assinado com `JWT_SECRET`.
- Middleware JWT no FastAPI: dependência `get_current_user` que valida o JWT no header `Authorization: Bearer <token>`.
- Secrets manager V1: leitura de credenciais de env vars. Interface abstrada pra V2 (Azure Key Vault) — só a assinatura, não implementar Key Vault.
- Configuração de CORS no FastAPI para o domínio do portal (`http://localhost:3000`).

## Escopo (o que NÃO FAZ)

- NÃO implementa RBAC, SSO, multi-tenant (V2+).
- NÃO implementa providers OAuth (Google, GitHub) na V1 — só credentials.
- NÃO modela schema de usuários no banco (D3 faz o schema; aqui é single-user, o "usuário" é derivado do JWT).
- NÃO cria UI de login elaborada — um form mínimo que chama a rota de credentials do NextAuth.
- NÃO implementa rate limiting (implementado no middleware do FastAPI, D6/D5). O D2 fornece o JWT com `sub` (ownerId) que é a chave do rate limiter. Limites: chat 30/min, execute 5/min, upload 10/min. Implementação: in-memory dict `{ownerId: {endpoint: [timestamps]}}`.

## Dependências

- **D1:** portal e orchestrator sobem, `.env.example` com `JWT_SECRET` e `NEXTAUTH_SECRET`, rede do compose funcionando.

## Arquivos que OWNS

```
agent-portal/
  auth.ts                     (config NextAuth)
  app/api/auth/[nextauth]/route.ts
  app/api/auth/signin/route.ts (ou page)
  app/api/jwt/route.ts        (emite JWT assinado)
  middleware.ts               (protege rotas do portal)
agent-orchestrator/
  app/security/
    auth.py                   (get_current_user, JWT decode)
    secrets.py                (leitura de env vars, interface V2)
  core/cors.py                (configuração CORS)
```

## Tarefas

### 2.1 NextAuth.js (portal)
- `auth.ts`: provider `credentials` (usuário fixo `admin` / senha de env `ADMIN_PASSWORD` na V1), callback que popula a sessão.
- Route handler `[nextauth]/route.ts` com `NextAuth(authOptions)`.
- `middleware.ts`: protege rotas que precisam de sessão (exceto `/api/auth` e `/signin`).
- Aceite: `/api/auth/signin` autentica com credenciais V1 e cria sessão.

### 2.2 Route handler emite JWT
- `app/api/jwt/route.ts`: GET que, se há sessão NextAuth válida, emite um JWT assinado com `JWT_SECRET` (payload: `sub` = id do usuário, `iss` = portal).
- Aceite: chamando `/api/jwt` com sessão ativa, retorna um token decodificável.

### 2.3 JWT middleware (FastAPI)
- `security/auth.py`: `get_current_user` dependência que extrai `Authorization: Bearer`, valida assinatura com `JWT_SECRET` (python-jose/cryptography), expira token.
- Exceção: 401 se ausente/inválido/expirado.
- Aceite: endpoint de teste na API responde 401 sem token, 200 com token válido.

### 2.4 Secrets manager (V1)
- `security/secrets.py`: `get_secret(name)` lê de env var. Definir protocolo/interface `SecretStore` com implementação `EnvSecretStore` e stub `KeyVaultSecretStore` (levanta `NotImplementedError` com mensagem de V2).
- Aceite: `get_secret("OPENAI_API_KEY")` retorna o valor do env; KeyVault não implementado.

### 2.5 CORS
- `core/cors.py`: `CORSMiddleware` permitindo origem do portal (`CORS_ORIGINS`, comma-separated), métodos PUT/POST/OPTIONS, headers Authorization/Content-Type.
- Aceite: portal (3000) consegue chamar API (8000) sem bloqueio de CORS.

## Critérios de aceite (DoD)

- [ ] Login no portal gera sessão NextAuth
- [ ] Route handler emite JWT válido
- [ ] API Python rejeita request sem JWT (401)
- [ ] API Python aceita request com JWT válido
- [ ] Credenciais nunca aparecem em logs

## Contratos de interface (o que entrega aos outros)

- **Para D3:** `get_current_user` pronto pra ser injetado em todos os routers; `JWT_SECRET` documentada; middleware de auth reutilizável.
- **Para D4–D10:** todo endpoint da API pode usar `Depends(get_current_user)`; padrão de autorização single-user estabelecido.
- **Para D6/D5 (rate limiting):** o JWT contém `sub` (ownerId) que é a chave do rate limiter. O middleware de rate limiting (in-memory, V1) usa esse campo para identificar o usuário. Limites: chat 30/min, execute 5/min, upload 10/min.
- **Para D9 (Rivvn):** gate comercial é lógica de negócio, mas a validação de usuário autenticado vem daqui.

## Riscos

- NextAuth emite cookie + session própria; o JWT é um token de delegação separado. Manter claro que o JWT não é a sessão, é um "cartão" que a API Python valida.
- `JWT_SECRET` e `NEXTAUTH_SECRET` devem ser o mesmo valor no `.env` (ou mapeados) para que o token emitido pelo portal seja aceito pela API.
