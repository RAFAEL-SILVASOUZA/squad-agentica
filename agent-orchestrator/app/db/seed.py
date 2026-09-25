"""Seed do sistema: cria APENAS o usuário admin (contrato §0).

Dono: db-seed.
Regras do contrato §0:
- Nunca cria agente/skill/tool/pipeline no boot.
- Não cria nada se ADMIN_EMAIL ou ADMIN_PASSWORD faltarem (sai com código 0).
- Idempotente: re-execução não duplica nem altera o admin.
- Não faz drop, truncate nem update de dados existentes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import User
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def _seed() -> None:
    """Cria o admin se as credenciais estiverem presentes."""
    if not settings.admin_email or not settings.admin_password:
        logger.warning(
            "seed: ADMIN_EMAIL ou ADMIN_PASSWORD ausente(s); nada a criar (contrato §0). "
            "Defina as variáveis no ambiente para criar o usuário admin."
        )
        return

    email = settings.admin_email
    password = settings.admin_password
    name = settings.admin_name or "Administrador"

    async with async_session_factory() as session:
        # Idempotência: se o e-mail já existe, não altera nada.
        existing = await session.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("seed: admin %s já existe; nada a fazer.", email)
            return

        # Gera o UUID antes para que owner_id = id (self-referente, §11.19).
        user_id = uuid.uuid4()
        admin = User(
            id=user_id,
            email=email,
            name=name,
            password_hash=hash_password(password),
            owner_id=user_id,
        )
        session.add(admin)
        await session.commit()
        logger.info("seed: admin %s criado com sucesso.", email)


def main() -> None:
    """Ponto de entrada: ``python -m app.db.seed``."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
