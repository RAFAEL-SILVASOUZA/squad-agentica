#!/usr/bin/env bash
#
# Inicializa os buckets de object storage do Agent Portal.
#
# Papel: um one-shot (container `minio-init` da imagem `minio/mc`) que espera o
# MinIO ficar saudável e cria os buckets `agents` e `skills` de forma idempotente.
# NÃO é um `minio server` e NÃO baixa binário nenhum do internet no boot: o
# container só roda o binário `mc` que já vem na imagem `minio/mc`.
#
# Fontes (contrato, em ordem de precedência):
#   - CONTRATO-TECNICO.md §2.4 (MINIO_BUCKET_AGENTS=agents, MINIO_BUCKET_SKILLS=skills)
#   - D1-infra.md §1.9 (mc alias set + mc mb --ignore-existing)
#
# Variáveis de ambiente (vêm do `.env`, distribuídas na rede do compose):
#   MINIO_ENDPOINT      host:porta do MinIO API, ex. http://minio:9001  (obrigatória)
#   MINIO_ROOT_USER     credencial de root (obrigatória)
#   MINIO_ROOT_PASSWORD secret de root (obrigatória)
#   MINIO_BUCKET_AGENTS bucket de artefatos de agentes (.yml)   (default: agents)
#   MINIO_BUCKET_SKILLS bucket de conteúdo de skills (.md)      (default: skills)
#   MINIO_ALIAS         nome do alias criado (default: local)
#   MINIO_WAIT_MAX      segundos máx. de espera pela saúde (default: 120)
#
# Saída de sucesso: exit 0. Falha de conexão após MINIO_WAIT_MAX: exit 1.

set -euo pipefail

ENDPOINT="${MINIO_ENDPOINT:?MINIO_ENDPOINT é obrigatório (ex. http://minio:9001)}"
ACCESS_KEY="${MINIO_ROOT_USER:?MINIO_ROOT_USER é obrigatório}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD é obrigatório}"
BUCKET_AGENTS="${MINIO_BUCKET_AGENTS:-agents}"
BUCKET_SKILLS="${MINIO_BUCKET_SKILLS:-skills}"
ALIAS="${MINIO_ALIAS:-local}"
WAIT_MAX="${MINIO_WAIT_MAX:-120}"

echo "[minio-init] aliasing ${ALIAS} -> ${ENDPOINT}"
mc alias set "${ALIAS}" "${ENDPOINT}" "${ACCESS_KEY}" "${SECRET_KEY}"

echo "[minio-init] aguardando o MinIO ficar saudável (timeout ${WAIT_MAX}s)..."
waited=0
while true; do
  if mc admin info "${ALIAS}" >/dev/null 2>&1; then
    echo "[minio-init] MinIO responde."
    break
  fi
  if [ "${waited}" -ge "${WAIT_MAX}" ]; then
    echo "[minio-init] MinIO não ficou saudável em ${WAIT_MAX}s. Abortando." >&2
    exit 1
  fi
  sleep 2
  waited=$((waited + 2))
done

# mc mb --ignore-existing: não falha se o bucket já existe (idempotente).
echo "[minio-init] criando bucket ${BUCKET_AGENTS} ..."
mc mb --ignore-existing "${ALIAS}/${BUCKET_AGENTS}"

echo "[minio-init] criando bucket ${BUCKET_SKILLS} ..."
mc mb --ignore-existing "${ALIAS}/${BUCKET_SKILLS}"

echo "[minio-init] buckets prontos: ${BUCKET_AGENTS}, ${BUCKET_SKILLS}"
exit 0
