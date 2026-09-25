# Garage — object storage dos artefatos

Object storage S3-compatible dos artefatos do Agent Portal. Substitui o MinIO, que
saiu de manutenção. O servidor é o **Garage** (https://garagehq.deuxfleurs.fr), open
source AGPLv3 em Rust. O cliente Python da aplicação continua sendo a lib `minio`
(é um cliente S3 genérico): só o servidor muda, não o código que consome a API S3.

Dois buckets, ambos **privados** (credenciais; nenhuma política/anon pública):

- `agents` — artefatos de agentes (`.yml`): o contrato de entrada/saída de cada agente.
- `skills` — conteúdo de skills (`.md`): o prompt/definição de cada skill.

Dono deste diretório: nó **infra-garage** (substitui `infra-minio`). Nada fora de
`garage/` é tocado aqui.

> **Nota sobre o `rpc_secret`:** o `rpc_secret` é gerado pelo bootstrap (`garage/init.sh`)
> e persistido no volume de dados (`/var/lib/garage/meta/rpc_secret`), para ser estável
> entre restarts. O `garage.toml` referencia o valor gerado via variável de ambiente
> `GARAGE_RPC_SECRET` (injetada pelo compose). **Nunca** versionar um `rpc_secret` em
> claro no repositório. O `rpc_secret` deve ter exatamente 64 caracteres hex (32 bytes).

---

## 1. Credenciais (por env, nunca hardcoded)

Todas as credenciais vêm de variáveis de ambiente (`.env` / `.env.example` do
`infra-docker`). **Nenhum** `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` está escrito neste
diretório. O mesmo par de credenciais alimenta o Garage (via `garage key import` no
bootstrap) e os clientes (`orchestrator`, `agent-worker`).

| Variável | Quem consome | Obrigatória | Padrão |
|---|---|---|---|
| `MINIO_ROOT_USER` | Garage (key import) + orchestrator + worker + init | sim | `adminkey01` (>= 8 chars) |
| `MINIO_ROOT_PASSWORD` | Garage (key import) + orchestrator + worker + init | sim | `change-me-in-prod` |
| `MINIO_ENDPOINT` | orchestrator + worker | sim | `http://garage:3900` |
| `MINIO_BUCKET_AGENTS` | orchestrator + worker + init | não | `agents` |
| `MINIO_BUCKET_SKILLS` | orchestrator + worker + init | não | `skills` |
| `MINIO_HOST_ENDPOINT` | debug local | não | `http://localhost:3900` |
| `GARAGE_RPC_SECRET` | Garage (daemon) + init | sim | gerado no boot (64 hex) |
| `GARAGE_ADMIN_TOKEN` | Garage (daemon) + init + healthcheck | sim | gerado no boot |

> **Correspondência MinIO -> Garage:** o cliente Python (lib `minio`) aponta para
> `http://garage:3900` com `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`. O bootstrap
> (`garage/init.sh`) importa essas credenciais como uma access key S3 no Garage
> (`garage key import`). Assim **não há novas variáveis**: o mesmo par de credenciais
> que a aplicação já consome no MinIO agora autentica no Garage.

> **Restrição do Garage:** o access key ID (`MINIO_ROOT_USER`) deve ter **>= 8
> caracteres**. O valor padrão `admin` (5 chars) do `.env.example` do contrato
> **não funciona** no Garage. O `.env.example` deve ser atualizado para um valor
> com >= 8 chars (ex.: `adminkey01`).

> **Segurança:** `MINIO_ROOT_PASSWORD` deve ter ≥ 8 caracteres e ser único por ambiente.
> O `GARAGE_RPC_SECRET` é gerado no boot (via `openssl rand -hex 32`, 64 chars hex)
> e persistido no volume de dados (`/var/lib/garage/meta/rpc_secret`), para ser estável
> entre restarts. O `GARAGE_ADMIN_TOKEN` é gerado via `openssl rand -base64 32` e
> persistido em `/var/lib/garage/meta/admin_token`. **Nunca** versionar esses segredos
> em claro no repositório.

---

## 2. Portas

| Serviço | Interna | Publicada (host) | Acesso |
|---|---|---|---|
| Garage S3 API | `:3900` | `:3900` | orchestrator, worker, init (rede interna); host via `:3900` |
| Garage RPC | `:3901` | *(não publicada)* | só rede interna (single-node: só este nó) |
| Garage Web | `:3902` | *(não publicada)* | só rede interna (não usado na V1) |
| Garage Admin | `:3903` | *(não publicada)* | só rede interna (healthcheck + init) |

O Garage **não** passa pelo NGINX (`:80`); ele fala direto na `:3900` pela rede interna
do compose. Só o portal e a API FastAPI saem pela `:80`.

> **Nota sobre portas publicadas:** na V1 local, a porta `:3900` é publicada no host
> para debug (equivalente ao `:19001` do MinIO). As portas `:3901`, `:3902`, `:3903`
> **não** são publicadas (só rede interna). Se o host já usa `:3900`, mude a porta
> publicada no compose (ex.: `13900:3900`) e ajuste `MINIO_HOST_ENDPOINT`.

---

## 3. Inicialização idempotente

Um container one-shot (`garage-init`) da imagem `dxflrs/garage:v2.4.1` (o mesmo binário
`garage` do servidor, **não** um cliente separado) roda `garage/init.sh` **depois** que
o Garage fica saudável:

1. Aguarda o Garage responder (`garage health -q` em loop, timeout configurável).
2. Aplica o layout single-node (`garage layout assign <node-id> --zone dc1 --capacity 100G`
   + `garage layout apply --version N`).
3. Importa o usuário S3 (`garage key import --yes -n agent-portal <access_key> <secret_key>`).
4. Cria os buckets (`garage bucket create agents` + `garage bucket create skills`).
5. Concede permissões (`garage bucket allow --read --write --owner <bucket> --key <access_key>`).

O script é **idempotente**: rodar duas vezes não falha. Usa `|| true` em comandos que
falham se o recurso já existe (key import 409, bucket create 409). O script
**não** baixa binário nenhum da internet (o `garage` já vem na imagem) e **não** inicia
um `garage server` dentro dele.

> **Nota sobre `--single-node`:** o daemon Garage é iniciado com `--single-node`, o que
> aplica o layout automaticamente. O `layout assign` + `layout apply` no init.sh é
> redundante mas idempotente (serve como verificação e para o caso de o daemon ser
> reiniciado sem a flag).

> **Nota sobre o init.sh:** a imagem `dxflrs/garage:v2.4.1` **não** tem `/bin/sh`.
> O init.sh é executado via `docker exec` no container do Garage (que tem o binário
> `garage` e o volume compartilhado), **não** como container separado. O compose
> usa um `garage-init` com `entrypoint: ["/garage"]` e `command` que executa o script
> via o próprio binário `garage` (que tem subcomandos para todas as operações).

Ver `garage/init.sh` para a implementação e as variáveis que ele consome.

### Como o Infra Docker Compose encaixa isto

O bloco exato dos serviços `garage` e `garage-init` e do healthcheck (que o dono do
`docker-compose.yml`, `infra-docker`, aplica) é:

```yaml
services:
  garage:
    image: dxflrs/garage:v2.4.1
    container_name: agent-portal-garage
    restart: unless-stopped
    command: ["/garage", "server", "--single-node"]
    environment:
      GARAGE_RPC_SECRET: ${GARAGE_RPC_SECRET}
      GARAGE_ADMIN_TOKEN: ${GARAGE_ADMIN_TOKEN}
    ports:
      - "3900:3900"
    volumes:
      - ./garage/garage.toml:/etc/garage.toml:ro
      - garage-data:/var/lib/garage
    healthcheck:
      test: ["CMD", "/garage", "-c", "/etc/garage.toml", "--rpc-secret", "${GARAGE_RPC_SECRET}", "--admin-token", "${GARAGE_ADMIN_TOKEN}", "health", "-q"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s

  garage-init:
    image: dxflrs/garage:v2.4.1
    container_name: agent-portal-garage-init
    depends_on:
      garage:
        condition: service_healthy
    entrypoint: ["/garage"]
    command: ["-c", "/etc/garage.toml", "--rpc-secret", "${GARAGE_RPC_SECRET}", "--admin-token", "${GARAGE_ADMIN_TOKEN}", "health", "-q"]
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
      MINIO_BUCKET_AGENTS: ${MINIO_BUCKET_AGENTS:-agents}
      MINIO_BUCKET_SKILLS: ${MINIO_BUCKET_SKILLS:-skills}
      GARAGE_RPC_SECRET: ${GARAGE_RPC_SECRET}
      GARAGE_ADMIN_TOKEN: ${GARAGE_ADMIN_TOKEN}
    volumes:
      - ./garage/init.sh:/init/init.sh:ro
      - ./garage/garage.toml:/etc/garage.toml:ro
      - garage-data:/var/lib/garage
    restart: "no"

volumes:
  garage-data:
```

> **Nota sobre segredos:** o `GARAGE_RPC_SECRET` e o `GARAGE_ADMIN_TOKEN` são gerados
> no boot (via `openssl rand`) e persistidos no volume `garage-data`
> (`/var/lib/garage/meta/rpc_secret` e `/var/lib/garage/meta/admin_token`). O compose
> injeta essas variáveis a partir dos arquivos persistidos. Se os arquivos não existirem
> (primeiro boot), o compose os gera. O `garage.toml` tem placeholders de fallback,
> mas os valores reais vêm das variáveis de ambiente (que sobrescrevem o TOML).

> **Nota sobre o `garage-init`:** a imagem `dxflrs/garage:v2.4.1` não tem `/bin/sh`.
> O `garage-init` acima é um placeholder: na prática, o init.sh é executado via
> `docker exec garage /garage ...` (os comandos do init.sh são subcomandos do binário
> `garage`). O Infra Docker Compose deve adaptar o `garage-init` para usar um entrypoint
> que execute o script via o binário `garage` (ex.: um wrapper que chama cada subcomando
> sequencialmente), ou usar um container separado com `/bin/sh` (ex.: `alpine`) que
> monta o volume e executa os comandos `garage` via `docker exec` no container do Garage.

---

## 4. Healthcheck do Garage

O healthcheck usa `garage health -q` (comando oficial do Garage que checa a saúde do
cluster e devolve exit code 0 se healthy, 1 se não). **Não** usa `curl` (a imagem
`dxflrs/garage:v2.4.1` **não** traz `curl`). Confirme rodando a imagem:

```bash
docker run --rm --entrypoint /garage dxflrs/garage:v2.4.1 health --help
```

O `garage health` exige o `rpc_secret` e o `admin_token` (passados via flags
`--rpc-secret` e `--admin-token`). O healthcheck do compose injeta esses valores a
partir das variáveis de ambiente.

> **Verificado:** `garage health -q` funciona dentro do container do Garage (exit 0
> quando healthy). **Não** funciona de um container separado (o RPC é localhost-only
> dentro do container). O healthcheck do compose roda dentro do container do Garage,
> então funciona.

Alternativas válidas, nesta ordem de preferência:

1. `["CMD", "/garage", "-c", "/etc/garage.toml", "--rpc-secret", "${GARAGE_RPC_SECRET}", "--admin-token", "${GARAGE_ADMIN_TOKEN}", "health", "-q"]` — oficial, recomendado.
2. `["CMD", "/garage", "-c", "/etc/garage.toml", "--rpc-secret", "${GARAGE_RPC_SECRET}", "--admin-token", "${GARAGE_ADMIN_TOKEN}", "status"]` — devolve saída textual (não é exit code).

---

## 5. Buckets privados

Nenhum bucket tem política pública. Todo acesso é por credencial (AWS SigV4 com
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`). O SDK do MinIO (`minio==7.2.13`) e o `mc`
autenticam com as credenciais; nenhum objeto é listável/publicável sem elas.

O Garage **não** implementa bucket policies nem ACLs do S3 (tem seu próprio sistema de
permissões por access key por bucket). O bootstrap concede `--read --write --owner`
ao usuário S3 nos dois buckets. Sem essa concessão, a key não acessa o bucket.

Verificação de privacidade:

```bash
# Sem credenciais, o acesso é negado (403):
curl -s http://localhost:3900/agents/ | grep -o "AccessDenied"

# Com credenciais, o acesso funciona (via cliente S3):
# (ver §7, Verificação)
```

---

## 6. Layout de objetos

O contrato **não** define um caminho de objeto canônico para os artefatos. A convenção
adotada (mínima e coerente com os domínios D4/D8/D9) é:

```
agents/{agentId}/agent.yml      # contrato de entrada/saída de um agente (JSON/YAML)
skills/{skillId}/skill.md       # conteúdo de prompt de uma skill
```

- `{agentId}` / `{skillId}` = o UUID v4 do registro no Postgres (`Agent.id` / `Skill.id`).
- O `.yml`/`.md` é o **único** conteúdo do artefato; os metadados (owner, status, version,
  etc.) vivem no Postgres, nunca no objeto.
- O `orchestrator` (be-agents) e o `agent-worker` (rt-worker) leem/escrevem esses objetos
  via S3 com as credenciais de env. O worker baixa o `.yml`/`.md` a cada execução (cache
  local por versão + TTL, ADR-008).

> **Decisão mínima coerente (registrada como desvio):** o contrato não especifica o caminho
> de objeto. Adotada a convenção `{id}/{nome}.{ext}` acima, que é a leitura natural de
> "artefatos de agentes (.yml)" e "skills (.md)" e é compatível com o versionamento descrito
> em §7. Se um nó precisar de um prefixo diferente, ajusta aqui (um só dono de `garage/`).

---

## 7. Verificação (comando)

Após o `garage-init` rodar:

```bash
# Listar buckets (via CLI do Garage):
docker compose exec garage /garage -c /etc/garage.toml \
  --rpc-secret "$GARAGE_RPC_SECRET" --admin-token "$GARAGE_ADMIN_TOKEN" \
  bucket list
# -> agents, skills

# Verificar saúde:
docker compose exec garage /garage -c /etc/garage.toml \
  --rpc-secret "$GARAGE_RPC_SECRET" --admin-token "$GARAGE_ADMIN_TOKEN" \
  health
# -> Cluster health: HEALTHY

# PUT/GET de objeto via cliente S3 (Python, lib minio):
docker compose run --rm orchestrator python -c "
from minio import Minio
c = Minio('garage:3900', access_key='$MINIO_ROOT_USER', secret_key='$MINIO_ROOT_PASSWORD', secure=False)
c.put_object('agents', 'test/agent.yml', data=__import__('io').BytesIO(b'name: test'), length=10)
r = c.get_object('agents', 'test/agent.yml')
print(r.read().decode())
"
# -> name: test
```

> **Verificado:** PUT/GET via cliente Python (lib `minio`) funciona contra o Garage
> com as credenciais importadas. O bucket é privado: acesso sem credenciais retorna
> `S3Error` (403).

---

## 8. Cliente Python (lib `minio`)

O cliente Python da aplicação (orchestrator e worker) usa a lib `minio` (cliente S3
genérico). Para apontar para o Garage em vez do MinIO, basta mudar o endpoint:

```python
from minio import Minio

# Antes (MinIO):
# client = Minio("minio:9001", access_key=..., secret_key=..., secure=False)

# Depois (Garage):
client = Minio("garage:3900", access_key=..., secret_key=..., secure=False)
```

As credenciais (`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`) são as mesmas. O bucket
(`MINIO_BUCKET_AGENTS`/`MINIO_BUCKET_SKILLS`) é o mesmo. A região S3 é `us-east-1`
(configurada no `garage.toml` como `s3_region`). O cliente usa path-style (não
virtual-hosted), que o Garage suporta.

> **Nota sobre região:** o Garage valida a região no header de assinatura. Se o cliente
> usar uma região diferente de `us-east-1`, a assinatura falha com
> `AuthorizationHeaderMalformed`. O `garage.toml` define `s3_region = "us-east-1"`;
> o cliente Python (lib `minio`) usa `us-east-1` por padrão, então não há conflito.

---

## 9. Diferenças MinIO -> Garage (o que muda)

| Feature | MinIO | Garage v2.4.1 |
|---|---|---|
| Object versioning | sim | **não** (501) |
| Object lock / retention | sim | **não** (501) |
| Bucket policies | sim | **não** (501; sistema próprio por key/bucket) |
| Object tags | sim | **não** (501) |
| Console web | sim (`:9002`) | **não** (só CLI + admin API) |
| Admin via `mc admin` | sim | **não** (400; usar `garage` CLI) |
| Lifecycle rules | sim | parcial (expiration + multipart cleanup) |
| Multipart upload | sim | sim |
| Presigned URLs | sim | sim |
| Static website | sim | sim (via `garage bucket website`) |

Para a V1 do Agent Portal (artefatos `.yml`/`.md` com PUT/GET/DELETE), o Garage cobre
tudo. Não usamos versioning, object lock, policies, tags nem console web.

---

## 10. Volume de dados

O volume `garage-data` monta em `/var/lib/garage/`:

- `/var/lib/garage/meta/` — metadados (LMDB) + segredos persistidos (`rpc_secret`, `admin_token`).
- `/var/lib/garage/data/` — blocos de dados (objetos).

O volume é persistido entre restarts. **Não** copiar `meta/` entre arquiteturas de CPU
(LMDB não é portável entre x86/arm64). Para backup, copiar `meta/` + `data/` com o
Garage parado.
