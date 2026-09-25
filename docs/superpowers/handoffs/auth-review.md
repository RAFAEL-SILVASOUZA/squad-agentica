# Handoff: auth-review (FASE 3)

**Veredito: APROVADO** (2026-09-25)

## Inventário do orquestrador

### Estrutura de `agent-orchestrator/app/`

```
app/
  main.py              # FastAPI app, CORS, error handlers, global auth, router discovery
  api/
    __init__.py
    auth.py            # Auth router: register, login, refresh, me
  auth/
    __init__.py
    app_setup.py       # apply_global_auth(app) - middleware de proteção global
    dependencies.py    # get_current_user, require_auth, validate_ws_token, PUBLIC_PATHS
    jwt.py             # create_access_token, create_refresh_token, validate_access_token, validate_refresh_token
    rate_limiter.py    # RateLimiter class + login_rate_limiter (5/min per IP)
    refresh_store.py   # RefreshTokenStore (in-memory, thread-safe) + refresh_store singleton
    schemas.py         # Pydantic schemas (camelCase): RegisterRequest, LoginRequest, RefreshRequest, TokenResponse, UserResponse
  core/
    __init__.py
    config.py          # Settings (pydantic-settings), get_settings(), settings singleton
    embeddings.py      # Embedder protocol, MockEmbedder, OpenAIEmbedder, get_embedder()
    errors.py          # AppError, error_response(), register_exception_handlers()
    llm.py             # LLMClient protocol, MockLLMClient, OpenAILLMClient, get_llm_client()
    security.py        # hash_password (bcrypt cost 12), verify_password
  db/
    __init__.py
    models.py          # 17 models: User, Agent, Pipeline, PipelineNode, PipelineEdge, PipelineRun, Checkpoint, Skill, CustomTool, MCPServer, KnowledgeBase, KnowledgeDocument, KnowledgeChunk, ApprovalRequest, Artifact, Integration, RivvnConnection
    seed.py            # Admin user seed (idempotent)
    session.py         # engine, async_session_factory, Base, get_session(), get_db
```

### Models disponíveis

- **User**: id (UUID), email, name, password_hash, owner_id, created_at, updated_at
- **Agent**: id, owner_id, name, description, system_prompt, inputs, outputs, actions, capabilities, shell_access, max_iterations, created_at, updated_at
- **Pipeline**: id, owner_id, name, description, entry_node_id, nodes (JSON), edges (JSON), created_at, updated_at
- **PipelineNode**: id, pipeline_id, node_id, agent_id, config (JSON)
- **PipelineEdge**: id, pipeline_id, source_node_id, target_node_id, edge_type, condition, requires_approval
- **PipelineRun**: id, pipeline_id, status, started_at, finished_at, error
- **Checkpoint**: id, run_id, node_id, state (JSON), created_at
- **Skill**: id, owner_id, name, description, content, created_at, updated_at
- **CustomTool**: id, owner_id, name, description, script, created_at, updated_at
- **MCPServer**: id, owner_id, name, url, config (JSON), created_at, updated_at
- **KnowledgeBase**: id, owner_id, name, description, created_at, updated_at
- **KnowledgeDocument**: id, kb_id, title, content, source_url, created_at
- **KnowledgeChunk**: id, doc_id, content, embedding (vector), position
- **ApprovalRequest**: id, run_id, node_id, status, question, options (JSON), response, created_at, resolved_at
- **Artifact**: id, run_id, node_id, name, content, mime_type, created_at
- **Integration**: id, owner_id, name, type, config (JSON), created_at, updated_at
- **RivvnConnection**: id, owner_id, client_id, client_secret, base_url, redirect_uri, created_at

### Como obter sessão de banco e usuário corrente

```python
from app.db.session import get_db
from app.auth.dependencies import get_current_user
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User

# Em um router:
@router.get("/example")
async def example(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # db: sessão async (commit/rollback manual)
    # user: User autenticado (do JWT Bearer)
    ...
```

- `get_db`: dependency que fornece `AsyncSession` por request
- `get_current_user`: dependency que valida o Bearer token e retorna o `User` object
- Proteção global: `apply_global_auth(app)` já registrado no `main.py`. Toda rota exige usuário exceto `PUBLIC_PATHS` (`/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/health`, `/api/health`)

### Descoberta de routers em `app/api/`

O `main.py` usa `_discover_routers()` que importa automaticamente todo módulo em `app/api/` que exponha `router = APIRouter(...)`. Para criar um novo endpoint:

1. Crie `app/api/<dominio>.py`
2. Defina `router = APIRouter(prefix="/<dominio>", tags=["<dominio>"])`
3. O router é incluído automaticamente com prefixo `/api`
4. A proteção global já está ativa (não precisa de `Depends(get_current_user)` explícito, mas pode usar para obter o `User` object)

### Interfaces `app/core/llm.py` e `app/core/embeddings.py`

**LLM:**
```python
from app.core.llm import get_llm_client, LLMClient

llm = get_llm_client()  # MockLLMClient ou OpenAILLMClient
response = await llm.chat([{"role": "user", "content": "hello"}])
```

- `MockLLMClient`: devolve `f"MOCK_LLM: echo of: {last_user_message}"`
- `OpenAILLMClient`: usa `openai.AsyncOpenAI`, model `gpt-4o-mini`
- Provider selecionado por `LLM_PROVIDER` env var (`mock` | `openai`)

**Embeddings:**
```python
from app.core.embeddings import get_embedder, Embedder

embedder = get_embedder()  # MockEmbedder ou OpenAIEmbedder
vector = embedder.embed("text")  # list[float], dim=1536, normalizado
vectors = embedder.embed_batch(["text1", "text2"])
```

- `MockEmbedder`: hash SHA-256 determinístico, dim=1536, normalizado
- `OpenAIEmbedder`: usa `openai.OpenAI`, model `text-embedding-3-small`
- Provider selecionado por `EMBEDDING_PROVIDER` env var (`mock` | `openai`)

### Testes com banco isolado

Os testes usam `pytest-asyncio` e um engine de teste isolado. O fixture `test_engine` (em `conftest.py`) cria um engine SQLite em memória. Para criar um teste:

```python
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.db.session import get_db

@pytest_asyncio.fixture
async def test_app(test_engine):
    app = FastAPI()
    register_exception_handlers(app)
    # Override get_db com o test engine
    ...
    yield app

@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

Rodar testes:
```bash
docker compose -p squad-agentica run --rm --no-deps --entrypoint "pytest" orchestrator -q
```

### Envelope de erro

```json
{ "error": "string", "code": "string", "details"?: "object" }
```

- 400: `{ "error": "validation error", "code": "invalid_graph", "details": { "errors": [...] } }`
- 401: `{ "error": "unauthorized", "code": "not_authenticated" }`
- 403: `{ "error": "forbidden", "code": "forbidden" }`
- 404: `{ "error": "not_found", "code": "<recurso>_not_found" }`
- 409: `{ "error": "conflict", "code": "<pipeline_already_running|already_responded|graph_running>" }`
- 422: `{ "error": "unprocessable", "code": "schema_validation", "details": { "errors": [...] } }`
- 429: `{ "error": "rate_limited", "code": "rate_limited", "details": { "retryAfter": int } }`
- 500: `{ "error": "internal error", "code": "internal_error" }`

Para lançar um erro:
```python
from app.core.errors import AppError
raise AppError(404, "not_found", "agent_not_found")
```

## Contratos públicos (auth)

### Rotas (prefixo `/api`)

- `POST /api/auth/register` → 201 `{id, email, name}` | 409 `email_already_exists`
- `POST /api/auth/login` → 200 `{accessToken, refreshToken, tokenType, expiresIn}` | 401 `invalid_credentials` | 429 `rate_limited`
- `POST /api/auth/refresh` → 200 `{accessToken, refreshToken, tokenType, expiresIn}` | 401 `invalid_refresh_token` / `refresh_token_reused`
- `GET /api/auth/me` → 200 `{id, email, name}` | 401 `not_authenticated`

### Imports para outros nós

```python
from app.auth.dependencies import get_current_user, validate_ws_token
from app.auth.app_setup import apply_global_auth
from app.auth.jwt import create_access_token, create_refresh_token, validate_access_token
```

### JWT

- Claims: `sub` (ownerId), `iat`, `exp`, `typ` ("access" | "refresh"), `jti`
- Access: 15 min. Refresh: 7 dias.
- Rotação de refresh: token usado é invalidado. Reuso → 401 `refresh_token_reused`.
- `JWT_SECRET` de env var.

### WebSocket

```python
from app.auth.dependencies import validate_ws_token
payload = validate_ws_token(token)  # Raises AppError(401) se inválido
```

## Comandos para subir e testar

```bash
# Subir o stack
docker compose up -d --build

# Testes backend
docker compose -p squad-agentica run --rm --no-deps --entrypoint "pytest" orchestrator -q

# Testes frontend
cd agent-portal && npx vitest run

# Type-check frontend
cd agent-portal && npx tsc --noEmit

# Lint frontend
cd agent-portal && npm run lint

# Build frontend
cd agent-portal && npm run build
```

## Ajustes aplicados pelo revisor

1. **`agent-orchestrator/app/main.py`**: adicionado `apply_global_auth(app)` (pedido pelo auth-backend)
2. **`agent-orchestrator/tests/test_router_discovery.py`**: atualizado para esperar 401 (rota protegida por padrão)
3. **`agent-portal/app/(auth)/login/page.tsx`**: adicionado `<Suspense>` boundary (exigência do Next.js 14 para `useSearchParams`)
4. **`agent-portal/app/(auth)/register/page.tsx`**: adicionado `<Suspense>` boundary
5. **`nginx/conf.d/10-public.conf`**: corrigido roteamento de `/api/auth/*` para separar NextAuth (portal) de endpoints do orchestrator (register, login, refresh, me)

## Ressalvas

- O `rt-websocket` nó deve chamar `validate_ws_token` no handshake (contrato §7)
- O `fe-shell` nó deve estender `globals.css` e substituir `layout.tsx` mantendo `SessionProvider` e `data-theme`
- `lib/api.ts` (fe-shell) deve usar `GET /api/session-token` para obter o JWT e enviar no header `Authorization: Bearer <token>`
