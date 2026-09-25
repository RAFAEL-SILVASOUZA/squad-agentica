# Postgres — banco de dados do Agent Portal

PostgreSQL 15 com a extensão **pgvector** (`vector`), usado para:

- **Metadados e relações** da aplicação (agentes, pipelines, runs, aprovações,
  knowledge bases, integrações, etc.).
- **Checkpoints do LangGraph** (`PostgresSaver`), que persistem o estado de
  execução das pipelines por `thread_id`.
- **RAG / embeddings** (coluna `vector(1536)` + índice HNSW, spec §7.2).

Dono deste diretório: nó **infra-postgres** (contrato §1). Nada fora de
`postgres/` é tocado aqui.

---

## 1. Imagem

| Item | Valor |
|---|---|
| Imagem | `pgvector/pgvector:pg15` |
| Versão do Postgres | 15 |
| Extensão embutida | `vector` (pgvector) — instalada no cluster, habilitada por banco via `init.sql` |
| Porta interna | `:5432` |
| Porta publicada (host) | `:15432` (evita colidir com um Postgres local do host) |
| Container | `agent-portal-postgres` |
| Volume | `postgres-data:/var/lib/postgresql/data` |

A imagem `pgvector/pgvector:pg15` já traz a extensão `vector` compilada; o
`init.sql` só a **habilita** no banco de aplicação (`CREATE EXTENSION IF NOT
EXISTS vector;`). Não há download de binário nem compilação em runtime.

---

## 2. Credenciais e connection strings

Credenciais vêm de variáveis de ambiente (`.env` / `.env.example` do
`infra-docker`). **Nenhum** usuário/senha está escrito neste diretório.

| Variável | Valor (dev) | Quem consome |
|---|---|---|
| `POSTGRES_USER` | `agent_portal` | entrypoint da imagem (cria o role) |
| `POSTGRES_PASSWORD` | `agent_portal` | entrypoint da imagem |
| `POSTGRES_DB` | `agent_portal` | entrypoint da imagem (cria o banco) |
| `DATABASE_URL` | `postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal` | orchestrator (SQLAlchemy 2 async + asyncpg) |

> **Driver:** `asyncpg` (contrato §3/§6: "SQLAlchemy 2 async + asyncpg"). O
> `psycopg[binary]` fica como dependência instalada, mas a V1 usa `asyncpg` na
> `DATABASE_URL`.

### Connection strings

| Contexto | String |
|---|---|
| **Interna** (rede do compose, usada pelo orchestrator/worker) | `postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal` |
| **Host** (psql local, porta publicada) | `postgresql://agent_portal:agent_portal@localhost:15432/agent_portal` |

O banco de aplicação é **`agent_portal`** (criado pela imagem via
`POSTGRES_DB`). O init roda **dentro** desse banco.

---

## 3. O que o `init.sql` faz (e o que não faz)

Executado pela imagem no **primeiro boot** via
`/docker-entrypoint-initdb.d/init.sql` (montado read-only pelo
`docker-compose.yml`). Idempotente. Contém **apenas**:

1. `CREATE EXTENSION IF NOT EXISTS vector;` — habilita o pgvector no banco.
2. `ALTER ROLE agent_portal WITH CREATEDB;` — dá ao usuário de aplicação
   permissão de criar bancos isolados de teste (contrato §4).

### O que o init NÃO faz (de propósito)

- **Não cria tabelas, índices, tipos (ENUM/COMPOSITE) nem views da
  aplicação.** O schema da aplicação é do **Alembic** (nó `db-migrations`,
  `alembic upgrade head` no entrypoint do orchestrator). Se o init criasse
  tabelas, o `alembic upgrade head` falharia com `relation already exists` e o
  schema passaria a ter **dois donos**.
- **Não cria o índice HNSW** do pgvector: ele é criado na migration (D3), junto
  da coluna `vector(1536)` da tabela de chunks (spec §7.2).
- **Não cria o banco nem o usuário**: a imagem os cria via `POSTGRES_DB` /
  `POSTGRES_USER` / `POSTGRES_PASSWORD`.

### Por que o `CREATEDB`

Cada sessão de pytest cria **um banco próprio com sufixo único**
(`agent_portal_test_<uuid>`) e o destrói no teardown (contrato §4). O fixture
usa a mesma `DATABASE_URL` base mudando só o nome do banco, o que exige que o
usuário `agent_portal` tenha o atributo `CREATEDB`. Sem ele, o `CREATE
DATABASE` do fixture falharia com `permission denied`. **Nunca** use o banco
`agent_portal` em teste.

---

## 4. Quem cria o quê (separação de donos)

| Artefato | Dono | Como |
|---|---|---|
| Banco `agent_portal` + role `agent_portal` | imagem (entrypoint) | `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| Extensão `vector` habilitada | **infra-postgres** | `postgres/init.sql` |
| Atributo `CREATEDB` no role | **infra-postgres** | `postgres/init.sql` |
| **Tabelas/índices/tipos da aplicação** | **db-migrations** (Alembic) | `alembic upgrade head` (entrypoint do orchestrator) |
| **Tabelas de checkpoint do LangGraph** | **LangGraph `PostgresSaver`** | `PostgresSaver.setup()` (nó rt-executor, `app/runtime/checkpoint.py`) |

### O Alembic precisa ignorar as tabelas do `PostgresSaver`

O `PostgresSaver` do LangGraph cria **as próprias** tabelas de checkpoint
(`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`
e afins) via `PostgresSaver.setup()`, apontando para o **mesmo** banco
`agent_portal` (ou o banco de teste). Essas tabelas **não** fazem parte do
schema gerenciado pelo Alembic.

Consequência prática para o nó `db-migrations`:

- A migration inicial (`0001_initial.py`) **não** deve declarar as tabelas de
  checkpoint do LangGraph (o `PostgresSaver` as cria sozinho).
- Ao autogerar/comparar o `MetaData` dos models, o `db-migrations` deve
  **excluir** as tabelas do `PostgresSaver` do conjunto esperado, senão a
  comparação "models vs. banco" acusa diferença.
- O `PostgresSaver` e o Alembic convivem no mesmo banco: o Alembic gerencia o
  schema da aplicação; o `PostgresSaver` gerencia o schema de checkpoint.
  Nenhum dos dois toca nas tabelas do outro.

---

## 5. Como rodar `psql` no container

### Dentro do container (via `docker compose exec`)

```bash
# como o usuário de aplicação (agent_portal), no banco agent_portal
docker compose exec postgres psql -U agent_portal -d agent_portal

# comando único (ex.: listar extensões)
docker compose exec postgres psql -U agent_portal -d agent_portal \
  -c "SELECT extname FROM pg_extension;"

# como superuser (postgres) — só para diagnóstico
docker compose exec postgres psql -U postgres -d agent_portal \
  -c "SELECT rolname, rolcreatedb FROM pg_roles WHERE rolname='agent_portal';"
```

### Do host (porta publicada `:15432`)

```bash
# se o host tiver psql instalado
psql "postgresql://agent_portal:agent_portal@localhost:15432/agent_portal" \
  -c "SELECT extname FROM pg_extension;"
```

---

## 6. Verificação

Após o primeiro boot do stack (o `init.sql` roda no primeiro boot, quando o
data dir está vazio):

```bash
# extensão vector habilitada
docker compose exec postgres psql -U agent_portal -d agent_portal \
  -c "SELECT extname FROM pg_extension;"
# -> vector (e as extensões padrão: plpgsql, etc.)

# atributo CREATEDB presente no role de aplicação
docker compose exec postgres psql -U agent_portal -d agent_portal \
  -c "SELECT rolname, rolcreatedb FROM pg_roles WHERE rolname='agent_portal';"
# -> agent_portal | t

# o usuário consegue criar um banco de teste (e derrubá-lo)
docker compose exec postgres psql -U agent_portal -d agent_portal \
  -c "CREATE DATABASE agent_portal_test_smoke; DROP DATABASE agent_portal_test_smoke;"
# -> CREATE DATABASE / DROP DATABASE (sem "permission denied")
```

### Verificação isolada (container descartável, sem tocar no stack)

Roda o `init.sql` numa instância efêmera da **mesma** imagem, numa porta que
não conflite, e confirma a extensão:

```bash
docker run --rm -d --name pg-init-test \
  -e POSTGRES_USER=agent_portal \
  -e POSTGRES_PASSWORD=agent_portal \
  -e POSTGRES_DB=agent_portal \
  -p 15433:5432 \
  -v "$(pwd)/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  pgvector/pgvector:pg15

# aguarde o boot (pg_isready)
until docker exec pg-init-test pg_isready -U agent_portal -d agent_portal >/dev/null 2>&1; do sleep 1; done

docker exec pg-init-test psql -U agent_portal -d agent_portal \
  -c "SELECT extname FROM pg_extension;"
docker exec pg-init-test psql -U agent_portal -d agent_portal \
  -c "SELECT rolname, rolcreatedb FROM pg_roles WHERE rolname='agent_portal';"

docker rm -f pg-init-test
```

---

## 7. Healthcheck

O healthcheck do serviço `postgres` (no `docker-compose.yml`, dono
`infra-docker`) usa `pg_isready`:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U agent_portal -d agent_portal"]
```

`pg_isready` só confirma que o Postgres aceita conexões; a presença da
extensão `vector` é garantida pelo `init.sql` no primeiro boot (ver §6).
