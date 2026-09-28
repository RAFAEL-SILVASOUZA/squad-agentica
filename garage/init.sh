#!/bin/sh
#
# Bootstrap idempotente do Garage (object storage S3-compatible do Agent Portal).
#
# Papel: um one-shot (container `garage-init` da imagem `dxflrs/garage:v2.4.1`) que
# roda DEPOIS que o daemon Garage responde, aplica o layout (1ª vez), cria o usuário
# S3 e os buckets `agents` e `skills` de forma idempotente.
#
# NÃO baixa binário nenhum da internet no boot: usa o binário `garage` que já vem na
# imagem `dxflrs/garage:v2.4.1`.
#
# Fontes (contrato, em ordem de precedência):
#   - CONTRATO-TECNICO.md §2.4 (MINIO_ROOT_USER/PASSWORD, MINIO_BUCKET_AGENTS/SKILLS)
#   - PLANO-BACKEND.md §2.3 (infra-minio -> infra-garage)
#   - docs/superpowers/plans/domains/D1-infra.md (seção de object storage)
#
# Variáveis de ambiente (vêm do `.env`, distribuídas na rede do compose):
#   MINIO_ROOT_USER     access key S3 do usuário (obrigatória, >= 8 chars)
#   MINIO_ROOT_PASSWORD secret key S3 do usuário (obrigatória)
#   MINIO_BUCKET_AGENTS bucket de artefatos de agentes (.yml)   (default: agents)
#   MINIO_BUCKET_SKILLS bucket de conteúdo de skills (.md)      (default: skills)
#   GARAGE_RPC_SECRET   segredo RPC (obrigatória; 64 chars hex)
#   GARAGE_ADMIN_TOKEN  token admin (obrigatória)
#   GARAGE_WAIT_MAX     segundos máx. de espera pela saúde (default: 120)
#
# Saída de sucesso: exit 0. Falha de conexão após GARAGE_WAIT_MAX: exit 1.
#
# Idempotência: rodar duas vezes não falha. Verifica existência antes de criar;
# usa `|| true` onde apropriado (key import, bucket create).
#
# Layout: o daemon roda em modo normal (sem --single-node) e o layout é aplicado
# por este script apenas quando ainda não existe (versão 0).

set -eu

# --- Variáveis ---
ACCESS_KEY="${MINIO_ROOT_USER:?MINIO_ROOT_USER é obrigatório}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD é obrigatório}"
BUCKET_AGENTS="${MINIO_BUCKET_AGENTS:-agents}"
BUCKET_SKILLS="${MINIO_BUCKET_SKILLS:-skills}"
BUCKET_KNOWLEDGE="${MINIO_BUCKET_KNOWLEDGE:-knowledge}"
RPC_SECRET="${GARAGE_RPC_SECRET:?GARAGE_RPC_SECRET é obrigatório}"
ADMIN_TOKEN="${GARAGE_ADMIN_TOKEN:?GARAGE_ADMIN_TOKEN é obrigatório}"
WAIT_MAX="${GARAGE_WAIT_MAX:-120}"
CONFIG="/etc/garage.toml"

# Função para chamar o binário garage com config e segredos.
garage() {
  /garage -c "$CONFIG" --rpc-secret "$RPC_SECRET" --admin-token "$ADMIN_TOKEN" "$@"
}

echo "[garage-init] aguardando o Garage responder (timeout ${WAIT_MAX}s)..."
waited=0
while true; do
  # `node id` responde sem layout (num volume novo o layout é aplicado abaixo;
  # `health` só fica ok depois disso).
  if garage node id -q >/dev/null 2>&1; then
    echo "[garage-init] Garage responde."
    break
  fi
  if [ "${waited}" -ge "${WAIT_MAX}" ]; then
    echo "[garage-init] ERRO: Garage não ficou saudável em ${WAIT_MAX}s. Abortando." >&2
    exit 1
  fi
  sleep 2
  waited=$((waited + 2))
done

# --- (a) Verificar segredos ---
if [ -z "$RPC_SECRET" ] || [ -z "$ADMIN_TOKEN" ]; then
  echo "[garage-init] ERRO: GARAGE_RPC_SECRET ou GARAGE_ADMIN_TOKEN vazios." >&2
  exit 1
fi
echo "[garage-init] rpc_secret e admin_token presentes."

# --- (b) Aplicar layout (só na primeira vez) ---
# O daemon roda sem --single-node; o layout é aplicado aqui uma única vez e
# persiste no volume. Antes, `layout assign` + `apply` rodava a cada boot e
# subia a versão do layout; com --single-node o Garage então recusava subir
# ("layout version is already superior to 1") e o stack não voltava após
# reiniciar o Docker. Só aplica se a versão atual for 0 (nó sem papel).
echo "[garage-init] verificando layout..."
LAYOUT_VERSION=$(garage layout show 2>/dev/null | sed -n 's/.*Current cluster layout version: \([0-9][0-9]*\).*/\1/p' | head -1)
if [ "${LAYOUT_VERSION:-0}" = "0" ]; then
  NODE_ID=$(garage node id -q 2>/dev/null | head -1 | cut -d@ -f1)
  if [ -z "$NODE_ID" ]; then
    echo "[garage-init] ERRO: não consegui obter o node id." >&2
    exit 1
  fi
  garage layout assign "$NODE_ID" --zone dc1 --capacity 100G
  garage layout apply --version 1
  echo "[garage-init] layout aplicado (node: ${NODE_ID})."
else
  echo "[garage-init] layout já aplicado (versão ${LAYOUT_VERSION})."
fi
# Os buckets/keys exigem o layout ativo: espera o cluster ficar saudável.
waited=0
until garage health -q >/dev/null 2>&1; do
  if [ "${waited}" -ge "${WAIT_MAX}" ]; then
    echo "[garage-init] ERRO: cluster não ficou saudável após o layout." >&2
    exit 1
  fi
  sleep 2
  waited=$((waited + 2))
done

# --- (c) Criar usuário S3 com access key/secret ---
# O Garage não tem "root user"; cada access key tem permissões por bucket.
# Usamos `garage key import` para importar a key com o access key/secret exatos
# (MINIO_ROOT_USER/MINIO_ROOT_PASSWORD), que a aplicação já consome no cliente Python.
# `key import` falha com 409 se a key já existe; usamos `|| true` para idempotência.
# ATENÇÃO: o access key ID deve ter >= 8 caracteres (regra do Garage).
echo "[garage-init] importando usuário S3 (access key: ${ACCESS_KEY})..."
garage key import --yes -n "agent-portal" "$ACCESS_KEY" "$SECRET_KEY" 2>/dev/null || true
echo "[garage-init] usuário S3 importado (ou já existia)."

# --- (d) Criar buckets ---
# `garage bucket create` falha com 409 se o bucket já existe; usamos `|| true`
# para idempotência. Os buckets são privados por padrão (sem política pública).
# O bucket `knowledge` é obrigatório (F5: upload de documentos de knowledge
# falhava com AccessDenied porque o bucket não existia nem estava autorizado).
for BUCKET in "$BUCKET_AGENTS" "$BUCKET_SKILLS" "$BUCKET_KNOWLEDGE"; do
  echo "[garage-init] criando bucket ${BUCKET}..."
  garage bucket create "$BUCKET" 2>/dev/null || true
done

# --- (e) Conceder permissões ao usuário S3 nos buckets ---
# O usuário precisa de read/write/owner em todos os buckets.
# `garage bucket allow` é idempotente: se a permissão já existe, não falha.
echo "[garage-init] concedendo permissões ao usuário S3..."
for BUCKET in "$BUCKET_AGENTS" "$BUCKET_SKILLS" "$BUCKET_KNOWLEDGE"; do
  garage bucket allow --read --write --owner "$BUCKET" --key "$ACCESS_KEY" 2>/dev/null || true
done

# --- (f) Verificação final ---
echo "[garage-init] verificando buckets..."
garage bucket list 2>/dev/null || true
echo "[garage-init] buckets prontos: ${BUCKET_AGENTS}, ${BUCKET_SKILLS}, ${BUCKET_KNOWLEDGE}"
echo "[garage-init] bootstrap concluído com sucesso."
exit 0
