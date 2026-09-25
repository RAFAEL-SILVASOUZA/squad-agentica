"""Seed do sistema: cria APENAS o usuário admin (contrato §0).

Dono do skeleton: infra-docker. O nó db-seed implementa a criação real do admin.
Regras do contrato §0:
- Nunca cria agente/skill/tool/pipeline no boot.
- Não cria nada se ADMIN_EMAIL ou ADMIN_PASSWORD faltarem.
- Idempotente: re-execução não duplica o admin.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def _seed() -> None:
    """Cria o admin se as credenciais estiverem presentes.

    O nó db-seed substitui o corpo desta função pela criação real do ``User``
    (bcrypt custo 12, idempotente por e-mail). Aqui fica o no-op de scaffold.
    """
    if not settings.admin_email or not settings.admin_password:
        logger.info("seed: ADMIN_EMAIL/ADMIN_PASSWORD ausentes; nada a criar (contrato §0).")
        return
    # db-seed: INSERT ... ON CONFLICT (email) DO NOTHING para o admin.
    logger.info("seed: admin seed é responsabilidade do nó db-seed (scaffold).")


def main() -> None:
    """Ponto de entrada: ``python -m app.db.seed``."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
