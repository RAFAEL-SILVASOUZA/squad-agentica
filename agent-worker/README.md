# agent-worker

Worker stateless e genérico do Agent Portal (FastAPI). Executa **um** agente por
request: baixa o `.yml` do agente e os `.md` de skills do MinIO, roda o agente e
devolve output + action + logs.

- **Porta interna:** `:9000` (não publicada; acessível só pelo server block
  interno do NGINX `:8081`, contrato §2.1/§2.3).
- **Health:** `GET /health` (container).
- **Execução:** `POST /execute` (stub 501 no scaffold; o nó `rt-worker` da
  FASE 6 implementa a execução real).

## Scaffold (dono: infra-docker)

```
app/
  main.py            # FastAPI + /health + /execute (stub)
tests/               # health + execute stub
```

O nó `rt-worker` (FASE 6) adiciona `worker.py`, `minio_client.py` e `loader.py`
(ADR-008 do contrato: o loader roda no worker).

## Rodar (dev, via compose)

```bash
docker compose up -d agent-worker
docker compose logs -f agent-worker
```

## Testes (dentro do container, contrato §4)

```bash
docker compose run --rm agent-worker pytest
```
