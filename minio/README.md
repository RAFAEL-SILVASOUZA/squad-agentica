# MinIO — object storage dos artefatos

Object storage dos artefatos do Agent Portal. Dois buckets, ambos **privados**
(credoenciais; nenhuma política/anon pública).

- `agents` — artefatos de agentes (`.yml`): o contrato de entrada/saída de cada agente.
- `skills` — conteúdo de skills (`.md`): o prompt/definição de cada skill.

Dono deste diretório: nó **infra-minio** (contrato §1). Nada fora de `minio/` é tocado aqui.

---

## 1. Credenciais (por env, nunca hardcoded)

Todas as credenciais vêm de variáveis de ambiente (`.env` / `.env.example` do
`infra-docker`). **Nenhum** `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` está escrito neste
diretório. O mesmo par de credenciais alimenta o MinIO (`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`
no entrypoint do serviço `minio`) e os clientes (`orchestrator`, `agent-worker`).

| Variável | Quem consome | Obrigatória | Padrão |
|---|---|---|---|
| `MINIO_ROOT_USER` | MinIO (entry) + orchestrator + worker + init | sim | `admin` |
| `MINIO_ROOT_PASSWORD` | MinIO (entry) + orchestrator + worker + init | sim | `change-me-in-prod` |
| `MINIO_ENDPOINT` | orchestrator + worker + init | sim | `http://minio:9001` |
| `MINIO_BUCKET_AGENTS` | orchestrator + worker + init | não | `agents` |
| `MINIO_BUCKET_SKILLS` | orchestrator + worker + init | não | `skills` |
| `MINIO_HOST_ENDPOINT` | debug local (console) | não | `http://localhost:19001` |

> **Segurança:** `MINIO_ROOT_PASSWORD` deve ter ≥ 8 caracteres e ser único por ambiente
> (nunca `minioadmin`). O console web fica em `:9002` (host `:19002`); use-o só para debug,
> nunca para acesso de produção.

---

## 2. Portas

| Serviço | Interna | Publicada (host) | Acesso |
|---|---|---|---|
| MinIO API (S3) | `:9001` | `:19001` | orchestrator, worker, init (rede interna); host via `:19001` |
| MinIO console | `:9002` | `:19002` | só host (debug) |

O MinIO **não** passa pelo NGINX (`:80`); ele fala direto na `:9001` pela rede interna do
compose. Só o portal e a API FastAPI saem pela `:80`.

---

## 3. Inicialização idempotente dos buckets

Um container one-shot (`minio-init`) da imagem `minio/mc` (o cliente do MinIO, **não** o
servidor) roda `minio/init-buckets.sh` **depois** que o MinIO fica saudável:

1. `mc alias set local http://minio:9001 <user> <password>`
2. `mc admin info local` em loop até o MinIO responder (timeout configurável)
3. `mc mb --ignore-existing local/agents`
4. `mc mb --ignore-existing local/skills`

`--ignore-existing` torna o init **idempotente**: rodar duas vezes não falha se os buckets
já existirem. O script **não** baixa binário nenhum da internet (o `mc` já vem na imagem) e
**não** inicia um `minio server` dentro dele.

Ver `minio/init-buckets.sh` para a implementação e as variáveis que ele consome.

### Como o Infra Docker Compose encaixa isto

O bloco exato do serviço `minio-init` e do healthcheck do MinIO (que o dono do
`docker-compose.yml`, `infra-docker`, aplica) é:

```yaml
services:
  minio:
    image: minio/minio:RELEASE.2024.09.22T01.12.59Z
    command: server /data --console-address ":9002"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    expose:
      - "9001"
      - "9002"
    ports:
      - "19001:9001"
      - "19002:9002"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10
    # o alias "local" do healthcheck aponta para o próprio MinIO (host interno "minio",
    # porta 9001); a imagem minio/mc traz o binário "mc". Ver §4.

  minio-init:
    image: minio/mc:RELEASE.2024.09.22T00.31.45Z
    entrypoint: >
      /bin/sh -c "mc alias set local http://minio:9001 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
      && until mc admin info local >/dev/null 2>&1; do sleep 2; done
      && mc mb --ignore-existing local/agents && mc mb --ignore-existing local/skills"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    depends_on:
      minio:
        condition: service_healthy
    restart: "no"
```

> **Nota:** o bloco acima usa um `entrypoint` inline para clareza didática. O mesmo
> comportamento pode ser obtido montando `minio/init-buckets.sh` como entrypoint
> (`entrypoint: ["/bin/sh", "/init/init-buckets.sh"]`, com o volume bind do script).
> O `minio-init` **não** precisa do MinIO como `depends_on` com `service_healthy` para rodar
> o `mc alias set` (o script espera sozinho), mas a condição evita re-execuções inúteis.

---

## 4. Healthcheck do MinIO

O healthcheck usa `mc ready local` (comando oficial do `minio/mc` que checa se o cluster
responde), **não** `curl` (a imagem `minio/minio` **não** traz `curl`). Confirme rodando a
imagem:

```bash
docker run --rm --entrypoint=/bin/sh minio/mc:RELEASE.2024.09.22T00.31.45Z -c 'mc --version'
```

O `mc ready local` exige um alias `local` configurado (o `minio-init` ou o entrypoint do
serviço criam). Alternativas válidas, nesta ordem de preferência:

1. `["CMD", "mc", "ready", "local"]` — oficial, recomendado (usado pelo compose do MinIO).
2. `["CMD", "mc", "admin", "info", "local"]` — exige credenciais no alias.
3. Endpoint `/minio/health/live` via binário disponível na imagem (só se `curl`/`wget`
   existirem; **não** é o caso da imagem `minio/minio`, por isso não é a escolha padrão).

---

## 5. Buckets privados

Nenhum bucket tem `mc anonymous set download`/`set public` nem política anônima. Todo
acesso é por credencial (AWS SigV4 com `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`). O SDK do
MinIO (`minio==7.2.13`) e o `mc` autenticam com as credenciais de root; nenhum objeto é
listável/publicável sem elas.

Verificação de privacidade:

```bash
docker compose exec minio mc anonymous get local/agents   # -> "none"
docker compose exec minio mc anonymous get local/skills   # -> "none"
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
> em §7. Se um nó precisar de um prefixo diferente, ajusta aqui (um só dono de `minio/`).

---

## 7. Versionamento de objetos

**Decisão (mínima, coerente com a V1):** a V1 **não** versiona objetos no MinIO. O versionado
é o **conteúdo** via Postgres (metadados) e, futuramente, o versionamento de pipelines (que
também não existe na V1, contrato §10). Cada `PUT` de `agents/{id}/agent.yml` **sobrescreve**
o objeto anterior (last-write-wins); o `.yml` vigente é sempre o atual.

- **Não** se ativa versioning de bucket na V1 (contrato §10: "sem versionamento de pipelines").
- Se no futuro se quiser histórico de artefatos, ativa-se o **bucket versioning** do MinIO
  (`mc versioning enable local/agents`) e passa-se a usar `VersionId` nas leituras — sem
  mudar o layout de caminho.
- Para rollback de conteúdo, usa-se o Postgres (metadados) como fonte de verdade histórica.

---

## 8. Verificação (comando)

Após o `minio-init` rodar:

```bash
docker compose exec minio mc ls local/          # -> agents, skills
docker compose exec minio mc ls local/agents    # -> (vazio até um agente ser criado)
docker compose exec minio mc anonymous get local/agents   # -> none (privado)
```
