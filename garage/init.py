#!/usr/bin/env python3
"""Bootstrap idempotente do Garage (object storage S3-compatible do Agent Portal).

Papel: um one-shot (container `garage-init`) que roda DEPOIS que o Garage fica
saudável e cria os buckets `agents` e `skills` de forma idempotente.

Usa a API S3 (via lib `minio` Python) para criar os buckets. O usuário S3
(access key/secret) é criado separadamente via `garage key import` (que exige
o binário `garage` e o rpc_secret/admin_token).

Variáveis de ambiente (vêm do `.env`, distribuídas na rede do compose):
  MINIO_ROOT_USER     access key S3 do usuário (obrigatória, >= 8 chars)
  MINIO_ROOT_PASSWORD secret key S3 do usuário (obrigatória)
  MINIO_ENDPOINT      endpoint S3 do Garage (ex: http://garage:3900)
  MINIO_BUCKET_AGENTS bucket de artefatos de agentes (.yml)   (default: agents)
  MINIO_BUCKET_SKILLS bucket de conteúdo de skills (.md)      (default: skills)
  MINIO_BUCKET_KNOWLEDGE bucket de documentos de knowledge    (default: knowledge)
  GARAGE_WAIT_MAX     segundos máx. de espera pela saúde (default: 120)

Saída de sucesso: exit 0. Falha de conexão após GARAGE_WAIT_MAX: exit 1.

Idempotência: rodar duas vezes não falha. Verifica existência antes de criar.
"""

import os
import sys
import time


def main() -> int:
    access_key = os.environ["MINIO_ROOT_USER"]
    secret_key = os.environ["MINIO_ROOT_PASSWORD"]
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://garage:3900")
    bucket_agents = os.environ.get("MINIO_BUCKET_AGENTS", "agents")
    bucket_skills = os.environ.get("MINIO_BUCKET_SKILLS", "skills")
    bucket_knowledge = os.environ.get("MINIO_BUCKET_KNOWLEDGE", "knowledge")
    wait_max = int(os.environ.get("GARAGE_WAIT_MAX", "120"))

    # --- Aguardar o Garage responder (via API S3) ---
    print(f"[garage-init] aguardando o Garage responder (timeout {wait_max}s)...")
    waited = 0
    while True:
        try:
            from minio import Minio
            host = endpoint.replace("http://", "").replace("https://", "")
            client = Minio(
                host,
                access_key=access_key,
                secret_key=secret_key,
                secure=endpoint.startswith("https"),
            )
            # Teste de conexão: listar buckets (pode falhar se a key não tem permissão)
            client.list_buckets()
            print("[garage-init] Garage responde (healthy).")
            break
        except Exception as e:
            if waited >= wait_max:
                print(f"[garage-init] ERRO: Garage não ficou saudável em {wait_max}s. Abortando. ({e})", file=sys.stderr)
                return 1
            time.sleep(2)
            waited += 2

    # --- Criar buckets (idempotente) ---
    from minio import Minio
    host = endpoint.replace("http://", "").replace("https://", "")
    client = Minio(
        host,
        access_key=access_key,
        secret_key=secret_key,
        secure=endpoint.startswith("https"),
    )

    for bucket in [bucket_agents, bucket_skills, bucket_knowledge]:
        print(f"[garage-init] criando bucket {bucket}...")
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"[garage-init] bucket {bucket} criado.")
            else:
                print(f"[garage-init] bucket {bucket} já existe.")
        except Exception as e:
            print(f"[garage-init] AVISO: falha ao criar bucket {bucket}: {e}", file=sys.stderr)

    # --- Verificação final ---
    print("[garage-init] verificando buckets...")
    try:
        buckets = client.list_buckets()
        for b in buckets:
            print(f"[garage-init]   {b.name}")
    except Exception as e:
        print(f"[garage-init] AVISO: falha ao listar buckets: {e}", file=sys.stderr)

    print(f"[garage-init] buckets prontos: {bucket_agents}, {bucket_skills}, {bucket_knowledge}")
    print("[garage-init] bootstrap concluído com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
