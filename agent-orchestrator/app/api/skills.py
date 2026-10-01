"""Skills CRUD API router.

Dono: be-skills (FASE 4). Rotas (prefixo /api):
- GET /api/skills → 200 {items, total, page, limit}
- POST /api/skills → 201 Skill
- GET /api/skills/{id} → 200 Skill / 404
- PUT /api/skills/{id} → 200 Skill / 404 / 409
- DELETE /api/skills/{id} → 204 / 404
- GET /api/skills/builtins → 200 {items: BuiltinSkill[]}
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.ai_resolution import resolve_llm_client
from app.core.errors import AppError
from app.db.models import User
from app.db.session import get_db
from app.skills.builtins import list_builtin_skills
from app.skills.registry import SkillRegistry
from app.skills.storage import get_skill_storage

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SkillCreateRequest(BaseModel):
    """Body para POST /api/skills."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    category: str = Field(..., pattern="^(code|docs|infra|communication|analysis)$")
    definition: dict[str, Any] = Field(..., description="{'template': str, 'variables': str[]}")
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    required_integrations: list[str] = Field(default_factory=list)


class SkillUpdateRequest(BaseModel):
    """Body para PUT /api/skills/{id}. Todos os campos opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, pattern="^(code|docs|infra|communication|analysis)$")
    definition: dict[str, Any] | None = None
    inputs: list[dict[str, Any]] | None = None
    outputs: list[dict[str, Any]] | None = None
    required_integrations: list[str] | None = None


class SkillResponse(BaseModel):
    """Response para uma skill."""

    id: uuid.UUID
    name: str
    description: str
    category: str
    type: str
    definition: dict[str, Any]
    inputs: list[Any]
    outputs: list[Any]
    required_integrations: list[str]
    created_at: str
    updated_at: str
    usageCount: int = 0


class SkillListResponse(BaseModel):
    """Response para listagem de skills."""

    items: list[SkillResponse]
    total: int
    page: int
    limit: int


class BuiltinSkillResponse(BaseModel):
    """Response para uma skill built-in."""

    name: str
    description: str
    category: str
    template: str
    variables: list[str]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    required_integrations: list[str]


class BuiltinSkillsListResponse(BaseModel):
    """Response para listagem de skills built-in."""

    items: list[BuiltinSkillResponse]


# ---------------------------------------------------------------------------
# Schemas: geração de skill por IA (interativa)
# ---------------------------------------------------------------------------


class SkillGenerateAnswer(BaseModel):
    """Uma pergunta já respondida pelo usuário (histórico acumulado)."""

    question: str
    answer: str


class SkillGenerateRequest(BaseModel):
    """Body para POST /api/skills/generate."""

    description: str = Field(default="", description="Descrição da skill pedida pelo usuário (pode ser vazia; a IA pergunta o que a skill deve fazer).")
    answers: list[SkillGenerateAnswer] = Field(
        default_factory=list,
        description="Histórico de perguntas já respondidas (acumulado entre chamadas).",
    )


class SkillGenerateQuestion(BaseModel):
    """Uma pergunta da IA para o usuário."""

    text: str
    options: list[str] = Field(default_factory=list)


class SkillGenerateSkill(BaseModel):
    """Skill completa gerada pela IA (mesma forma do SkillCreateRequest)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    category: str = Field(..., pattern="^(code|docs|infra|communication|analysis)$")
    template: str = Field(..., min_length=1)
    variables: list[str] = Field(default_factory=list)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    required_integrations: list[str] = Field(default_factory=list)


class SkillGenerateResponse(BaseModel):
    """Response para POST /api/skills/generate.

    A IA devolve UMA das duas formas:
    - status='questions' com question (o frontend abre um mini-modal com a pergunta);
    - status='done' com skill (o frontend preenche o modal inteiro).
    """

    status: str = Field(..., pattern="^(questions|done)$")
    question: SkillGenerateQuestion | None = None
    skill: SkillGenerateSkill | None = None


# Limite de perguntas antes de forçar a geração (evita loop infinito).
MAX_GENERATE_QUESTIONS = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(skill: Any, usage_count: int = 0) -> SkillResponse:
    """Converte um model Skill em SkillResponse."""
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        category=skill.category,
        type=skill.type,
        definition=skill.definition,
        inputs=skill.inputs,
        outputs=skill.outputs,
        required_integrations=skill.required_integrations,
        created_at=skill.created_at.isoformat() if skill.created_at else "",
        updated_at=skill.updated_at.isoformat() if skill.updated_at else "",
        usageCount=usage_count,
    )


# ---------------------------------------------------------------------------
# Helpers: geração de skill por IA
# ---------------------------------------------------------------------------


def _build_generate_system_prompt(answers_count: int) -> str:
    """System prompt da geração de skill.

    Baseado na skill 'skill-creator' da Anthropic (anthropics/skills@skill-creator),
    adaptado para o contexto de uma plataforma de agentes de IA com skills como
    blocos reutilizáveis de prompt.

    Instrui a IA a devolver SEMPRE um único JSON válido, em uma das duas formas:
    - {"status": "questions", "question": {"text": str, "options": [str]}}
    - {"status": "done", "skill": {name, description, category, template,
      variables, inputs, outputs, required_integrations}}
    """
    force = (
        "\n\nIMPORTANT: You have already asked the maximum number of questions. "
        "You MUST now return the complete skill (status='done'), making reasonable "
        "assumptions for anything still unclear."
        if answers_count >= MAX_GENERATE_QUESTIONS
        else ""
    )
    return (
        "You are a skill creation expert for an AI agent platform. "
        "Skills are reusable prompt blocks that agents can use to perform specific tasks.\n"
        "\n"
        "## Your Process (adapted from the Anthropic skill-creator methodology)\n"
        "\n"
        "### 1. Capture Intent\n"
        "Understand what the user wants the skill to do. The key questions are:\n"
        "- What should this skill enable the agent to do?\n"
        "- When should this skill trigger? (what user phrases/contexts)\n"
        "- What is the expected output format?\n"
        "\n"
        "If the user's description is clear enough to answer all three, go straight to "
        "generating the skill. If there is ONE critical ambiguity that would change the "
        "result, ask a single question. Do not ask multiple questions at once.\n"
        "\n"
        "### 2. Interview (only if needed)\n"
        "Proactively ask about edge cases, input/output formats, and success criteria "
        "ONLY when the description is genuinely ambiguous. Come prepared with context "
        "to reduce burden on the user. If the description is specific enough, skip this.\n"
        "\n"
        "### 3. Write the Skill\n"
        "Based on the interview, generate the complete skill with these components:\n"
        "- **name**: kebab-case identifier (e.g., 'code-reviewer', 'doc-writer')\n"
        "- **description**: When to trigger AND what it does. This is the primary "
        "triggering mechanism. Make it a little 'pushy' — include specific contexts "
        "for when to use it, not just what it does.\n"
        "- **category**: one of code, docs, infra, communication, analysis\n"
        "- **template**: The body of the skill in markdown. This is the actual prompt "
        "that the agent will follow. Use {variable} placeholders for dynamic inputs.\n"
        "- **variables**: List of variable names used in the template\n"
        "- **inputs**: Ports the skill receives (name, type, required)\n"
        "- **outputs**: Ports the skill produces (name, type, required)\n"
        "- **required_integrations**: External integrations needed (or empty list)\n"
        "\n"
        "### Writing Style for the Template\n"
        "- Use the imperative form in instructions\n"
        "- Explain WHY things are important rather than using heavy-handed MUSTs\n"
        "- Make the skill general, not narrow to specific examples\n"
        "- Include a clear output format/structure if the skill produces structured output\n"
        "- Keep it focused: one skill, one clear purpose\n"
        "- If the skill produces a report or document, define the exact structure it should follow\n"
        "- Include examples when they clarify the expected behavior\n"
        "\n"
        "### Port Types\n"
        "Use these port types: document, code, artifact, signal\n"
        "- document: text content (reports, descriptions, prompts)\n"
        "- code: source code or code snippets\n"
        "- artifact: files, images, or other binary outputs\n"
        "- signal: control flow indicators (success, failure, needs_review)\n"
        "\n"
        "## Output Format (STRICT)\n"
        "Respond with a SINGLE valid JSON object. No text outside the JSON. No markdown fences.\n"
        "\n"
        "If you need to ask a question:\n"
        '{"status": "questions", "question": {"text": "your question here", "options": ["option1", "option2", "option3"]}}\n'
        "- 'options' should have 2-4 short choices, or be an empty list for free-text answers.\n"
        "\n"
        "When the skill is ready:\n"
        '{"status": "done", "skill": {"name": "kebab-case-name", "description": "...", '
        '"category": "code", "template": "## Instructions\\n\\nDo X with {input}.\\n\\n## Output\\n\\n...", '
        '"variables": ["input"], '
        '"inputs": [{"name": "input", "type": "document", "required": true}], '
        '"outputs": [{"name": "result", "type": "document", "required": false}], '
        '"required_integrations": []}}'
        + force
    )


def _build_generate_user_message(body: SkillGenerateRequest) -> str:
    """Mensagem de usuário com a descrição + histórico de respostas."""
    desc = body.description.strip()
    if desc:
        parts = [f"Descrição da skill: {desc}"]
    else:
        parts = [
            "O usuário não forneceu uma descrição. "
            "Pergunte o que a skill deve fazer (uma única pergunta, com opções se fizer sentido)."
        ]
    if body.answers:
        parts.append("\nRespostas às suas perguntas:")
        for a in body.answers:
            parts.append(f"- P: {a.question}\n  R: {a.answer}")
    return "\n".join(parts)


def _extract_json(raw: str) -> dict[str, Any]:
    """Extrai o primeiro objeto JSON de uma resposta da LLM (tolerante a cercas)."""
    text = raw.strip()
    # Remove cercas de markdown, se houver.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            502, "Resposta da IA não é JSON válido.", "llm_invalid_response"
        ) from exc
    if not isinstance(data, dict):
        raise AppError(502, "Resposta da IA não é um objeto JSON.", "llm_invalid_response")
    return data


def _parse_generate_response(raw: str) -> SkillGenerateResponse:
    """Converte a resposta bruta da LLM em SkillGenerateResponse validado."""
    data = _extract_json(raw)
    status = data.get("status")

    if status == "questions":
        q = data.get("question") or {}
        question = SkillGenerateQuestion(
            text=str(q.get("text", "")).strip(),
            options=[str(o) for o in (q.get("options") or [])],
        )
        if not question.text:
            raise AppError(502, "Pergunta da IA sem texto.", "llm_invalid_response")
        return SkillGenerateResponse(status="questions", question=question)

    if status == "done":
        skill = SkillGenerateSkill(**(data.get("skill") or {}))
        return SkillGenerateResponse(status="done", skill=skill)

    raise AppError(502, "Resposta da IA com status inválido.", "llm_invalid_response")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/builtins", response_model=BuiltinSkillsListResponse)
async def list_builtins() -> BuiltinSkillsListResponse:
    """Lista skills built-in da plataforma."""
    items = [
        BuiltinSkillResponse(
            name=s.name,
            description=s.description,
            category=s.category,
            template=s.template,
            variables=s.variables,
            inputs=s.inputs,
            outputs=s.outputs,
            required_integrations=s.required_integrations,
        )
        for s in list_builtin_skills()
    ]
    return BuiltinSkillsListResponse(items=items)


@router.get("", response_model=SkillListResponse)
async def list_skills(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None),
) -> SkillListResponse:
    """Lista skills do usuario."""
    registry = SkillRegistry(db, get_skill_storage())
    items, total = await registry.list(user.id, page=page, limit=limit, category=category)

    # Calcula usageCount: numero de agentes DISTINCT do usuario que referenciam cada skill.
    result = await db.execute(
        text(
            "SELECT elem->>'skillId' AS item_id, COUNT(DISTINCT a.id) AS cnt "
            "FROM agents a, jsonb_array_elements(a.skills) AS elem "
            "WHERE a.owner_id = :user_id "
            "GROUP BY elem->>'skillId'"
        ),
        {"user_id": str(user.id)},
    )
    usage_map: dict[str, int] = {row[0]: row[1] for row in result.fetchall()}

    return SkillListResponse(
        items=[_to_response(s, usage_map.get(str(s.id), 0)) for s in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Cria uma skill custom."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.create(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        definition=body.definition,
        inputs=body.inputs,
        outputs=body.outputs,
        required_integrations=body.required_integrations,
    )
    return _to_response(skill)


@router.post("/generate", response_model=SkillGenerateResponse)
async def generate_skill(
    body: SkillGenerateRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> SkillGenerateResponse:
    """Gera uma skill completa a partir de uma descrição, de forma interativa.

    A IA analisa a descrição. Se houver ambiguidade crítica, devolve UMA pergunta
    por vez (status='questions'); o frontend re-chama acumulando as respostas até
    a IA devolver a skill completa (status='done').
    """
    llm = await resolve_llm_client(user.id)

    system_prompt = _build_generate_system_prompt(len(body.answers))
    user_message = _build_generate_user_message(body)

    raw = await llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
    )

    return _parse_generate_response(raw)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Obtem uma skill por id."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.get(skill_id, user.id)
    return _to_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Atualiza uma skill."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.update(
        skill_id=skill_id,
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        definition=body.definition,
        inputs=body.inputs,
        outputs=body.outputs,
        required_integrations=body.required_integrations,
    )
    return _to_response(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove uma skill."""
    registry = SkillRegistry(db, get_skill_storage())
    await registry.delete(skill_id, user.id)
    return Response(status_code=204)
