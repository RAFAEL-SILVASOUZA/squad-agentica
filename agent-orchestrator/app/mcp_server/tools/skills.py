"""Ferramentas MCP de Skills (CRUD).

Registra as ferramentas de gerenciamento de skills no servidor MCP. Cada
ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e delega a
operação ao ``SkillRegistry`` (mesmo service usado pelo router REST).

Erros do registry (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import AppError
from app.db.models import Skill
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError
from app.skills.registry import SkillRegistry
from app.skills.storage import get_skill_storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {"code", "docs", "infra", "communication", "analysis"}


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _skill_to_dict(skill: Skill) -> dict[str, Any]:
    """Converte o model Skill para dict (camelCase, como a API)."""
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "category": skill.category.value if hasattr(skill.category, "value") else str(skill.category),
        "type": skill.type.value if hasattr(skill.type, "value") else str(skill.type),
        "definition": skill.definition,
        "inputs": skill.inputs,
        "outputs": skill.outputs,
        "requiredIntegrations": skill.required_integrations,
        "createdAt": skill.created_at.isoformat() if skill.created_at else "",
        "updatedAt": skill.updated_at.isoformat() if skill.updated_at else "",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_skill(
    name: str,
    description: str = "",
    category: str = "code",
    definition: dict[str, Any] | None = None,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    required_integrations: list[str] | None = None,
) -> dict[str, Any]:
    """Cria uma nova skill.

    ``category`` pode ser 'code', 'docs', 'infra', 'communication' ou
    'analysis'. ``definition`` deve ter a forma ``{'template': str,
    'variables': str[]}``.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    if category not in _VALID_CATEGORIES:
        raise ToolError(
            f"Categoria inválida: {category}. Use code, docs, infra, communication ou analysis."
        )

    async with async_session_factory() as db:
        registry = SkillRegistry(db, get_skill_storage())
        try:
            skill = await registry.create(
                owner_id=user.id,
                name=name,
                description=description,
                category=category,
                definition=definition or {"template": "", "variables": []},
                inputs=inputs or [],
                outputs=outputs or [],
                required_integrations=required_integrations or [],
            )
        except AppError as e:
            raise ToolError(f"Erro ao criar skill: {e.error}") from e
        return _skill_to_dict(skill)


@mcp.tool()
async def list_skills(
    page: int = 1,
    limit: int = 50,
    category: str | None = None,
) -> dict[str, Any]:
    """Lista as skills do usuário autenticado, com paginação e filtro opcional por categoria."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        registry = SkillRegistry(db, get_skill_storage())
        try:
            items, total = await registry.list(
                user.id, page=page, limit=limit, category=category
            )
        except AppError as e:
            raise ToolError(f"Erro ao listar skills: {e.error}") from e
        return {
            "items": [_skill_to_dict(s) for s in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_skill(skill_id: str) -> dict[str, Any]:
    """Obtém uma skill por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(skill_id)

    async with async_session_factory() as db:
        registry = SkillRegistry(db, get_skill_storage())
        try:
            skill = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Skill não encontrada: {e.error}") from e
        return _skill_to_dict(skill)


@mcp.tool()
async def update_skill(
    skill_id: str,
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    definition: dict[str, Any] | None = None,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    required_integrations: list[str] | None = None,
) -> dict[str, Any]:
    """Atualiza uma skill (partial update: só os campos informados são alterados).

    Pelo menos um campo além de ``skill_id`` deve ser fornecido; caso
    contrário, retorna erro.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(skill_id)

    if category is not None and category not in _VALID_CATEGORIES:
        raise ToolError(
            f"Categoria inválida: {category}. Use code, docs, infra, communication ou analysis."
        )

    if all(
        v is None
        for v in (name, description, category, definition, inputs, outputs, required_integrations)
    ):
        raise ToolError("Nenhum campo para atualizar foi fornecido.")

    async with async_session_factory() as db:
        registry = SkillRegistry(db, get_skill_storage())
        try:
            skill = await registry.update(
                skill_id=parsed_id,
                owner_id=user.id,
                name=name,
                description=description,
                category=category,
                definition=definition,
                inputs=inputs,
                outputs=outputs,
                required_integrations=required_integrations,
            )
        except AppError as e:
            raise ToolError(f"Erro ao atualizar skill: {e.error}") from e
        return _skill_to_dict(skill)


@mcp.tool()
async def delete_skill(skill_id: str) -> dict[str, Any]:
    """Remove uma skill (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(skill_id)

    async with async_session_factory() as db:
        registry = SkillRegistry(db, get_skill_storage())
        try:
            await registry.delete(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Skill não encontrada: {e.error}") from e
        return {"deleted": True, "id": skill_id}
