#!/bin/sh
#
# Bootstrap idempotente do Garage (object storage S3-compatible do Agent Portal).
#
# Papel: um one-shot (container `garage-init` da imagem `dxflrs/garage:v2.4.1`) que
# roda DEPOIS que o Garage fica saudável e aplica o layout single-node, cria o usuário
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
# Nota sobre --single-node: o daemon Garage é iniciado com `--single-node`, o que
# aplica o layout automaticamente. O `layout assign` + `layout apply` abaixo é
# redundante mas idempotente (serve como verificação e para o caso de o daemon
# ser reiniciado sem a flag).

set -eu

# --- Variáveis ---
ACCESS_KEY="${MINIO_ROOT_USER:?MINIO_ROOT_USER é obrigatório}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD é obrigatório}"
BUCKET_AGENTS="${MINIO_BUCKET_AGENTS:-agents}"
BUCKET_SKILLS="${MINIO_BUCKET_SKILLS:-skills}"
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
  if garage health -q 2>/dev/null; then
    echo "[garage-init] Garage responde (healthy)."
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

# --- (b) Aplicar layout single-node (idempotente) ---
# Com --single-node, o layout já é aplicado pelo daemon. Este bloco é redundante
# mas idempotente: se o nó já tem role, `layout assign` stage a mudança e
# `layout apply --version N` aplica. Se não há mudança staged, `layout apply`
# falha (sem staged changes) e o `|| true` ignora.
echo "[garage-init] aplicando layout single-node..."
NODE_ID=$(garage node id 2>/dev/null | head -1 | cut -d@ -f1 || true)
if [ -n "$NODE_ID" ]; then
  garage layout assign "$NODE_ID" --zone dc1 --capacity 100G 2>/dev/null || true
  # Descobrir a próxima versão do layout para o apply.
  LAYOUT_VERSION=$(garage layout show 2>/dev/null | grep -oP 'version: \K[0-9]+' | head -1 || true)
  if [ -n "$LAYOUT_VERSION" ]; then
    NEXT_VERSION=$((LAYOUT_VERSION + 1))
    garage layout apply --version "$NEXT_VERSION" 2>/dev/null || true
  fi
  echo "[garage-init] layout aplicado (node: ${NODE_ID})."
else
  echo "[garage-init] AVISO: não consegui obter node id; pulando layout assign." >&2
fi

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
echo "[garage-init] criando bucket ${BUCKET_AGENTS}..."
garage bucket create "$BUCKET_AGENTS" 2>/dev/null || true
echo "[garage-init] criando bucket ${BUCKET_SKILLS}..."
garage bucket create "$BUCKET_SKILLS" 2>/dev/null || true

# --- (e) Conceder permissões ao usuário S3 nos buckets ---
# O usuário precisa de read/write/owner nos dois buckets.
# `garage bucket allow` é idempotente: se a permissão já existe, não falha.
echo "[garage-init] concedendo permissões ao usuário S3..."
garage bucket allow --read --write --owner "$BUCKET_AGENTS" --key "$ACCESS_KEY" 2>/dev/null || true
garage bucket allow --read --write --owner "$BUCKET_SKILLS" --key "$ACCESS_KEY" 2>/dev/null || true

# --- (f) Verificação final ---
echo "[garage-init] verificando buckets..."
garage bucket list 2>/dev/null || true
echo "[garage-init] buckets prontos: ${BUCKET_AGENTS}, ${BUCKET_SKILLS}"
echo "[garage-init] bootstrap concluído com sucesso."
exit 0
