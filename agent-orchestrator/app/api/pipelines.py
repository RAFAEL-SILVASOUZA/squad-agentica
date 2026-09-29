"""CRUD + validação de pipelines (spec 9.1, contrato §8, PENDENCIAS B1).

Dono: rt-executor (FASE 6; o endpoint de validação vive em ``app/api/``,
por isso é deste nó, não do pe-validator). Endpoints:

- POST   /api/pipelines            (criar pipeline com grafo JSON)
- GET    /api/pipelines            (listar, paginado, ?status=&page=&limit=)
- GET    /api/pipelines/:id        (obter pipeline + estado)
- PUT    /api/pipelines/:id        (atualizar grafo; 409 graph_running em run ativo)
- POST   /api/pipelines/validate   (validar grafo sem persistir; 400 invalid_graph)

Formato do grafo: o da spec 4.2 (mesmo que o executor consome):
    {"name", "description", "entryNodeId", "nodes": [...], "edges": [...]}

Convenções (contrato §8): envelope de erro, camelCase, paginação
{items,total,page,limit}.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.compiler.graph_builder import (
    AgentSnapshot,
    DataMapping,
    EdgeCondition,
    PortDef,
)
from app.compiler.graph_builder import (
    Pipeline as CompilerPipeline,
)
from app.compiler.graph_builder import (
    PipelineEdge as CompilerEdge,
)
from app.compiler.graph_builder import (
    PipelineNode as CompilerNode,
)
from app.compiler.validator import validate_pipeline
from app.core.errors import AppError
from app.db.models import (
    Integration,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PipelineRun,
    User,
)
from app.db.session import get_db
from app.runtime.workspace import WorkspaceManager

router = APIRouter(tags=["pipelines"])

# UUID nulo: usado como entryNodeId enquanto a pipeline não tem nós (a coluna
# é NOT NULL). O validador de grafo (regra 9) bloqueia a execução até a
# entrada apontar para um nó real.
_NIL_ENTRY = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Schemas de entrada (camelCase da spec 4.2)
# ---------------------------------------------------------------------------


class PortDefIn:
    """Definição de porta de entrada (validada manualmente)."""


def _uuid_field(value: Any, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise AppError(422, "unprocessable", "schema_validation", {
            "errors": [f"{field_name}: UUID inválido"]
        }) from None


def _parse_ports(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise AppError(422, "unprocessable", "schema_validation", {
            "errors": ["inputs/outputs deve ser uma lista de portas"]
        })
    ports: list[dict[str, Any]] = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict) or not p.get("name"):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"porta {i}: 'name' obrigatório"]
            })
        ports.append(
            {
                "name": str(p["name"]),
                "type": str(p.get("type", "string")),
                "required": bool(p.get("required", False)),
                "description": str(p.get("description", "")),
            }
        )
    return ports


def _build_pipeline_from_body(
    body: dict[str, Any], *, pipeline_id: uuid.UUID
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Valida o corpo do grafo e devolve (pipeline fields, nodes, edges).

    Regras mínimas de entrada (fora das 11 regras do validador de grafo,
    que rodam em POST /validate e no save do portal):
    - name obrigatório;
    - nodes: lista; cada nó precisa de id (UUID) e agentId (UUID);
    - edges: lista; source/target devem referir a nós existentes;
    - entryNodeId: se ausente/vazio e há nós, usa o PRIMEIRO nó
      (decisão mínima: o editor do portal cria a pipeline vazia e só então
      define a entrada; o validador de grafo regra 9 pega entrada inválida).
    """
    if not isinstance(body, dict):
        raise AppError(422, "unprocessable", "schema_validation", {"errors": ["body inválido"]})

    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AppError(422, "unprocessable", "schema_validation", {
            "errors": ["name: obrigatório"]
        })

    raw_nodes = body.get("nodes")
    raw_edges = body.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise AppError(422, "unprocessable", "schema_validation", {
            "errors": ["nodes e edges devem ser listas"]
        })

    node_fields: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    # O editor cria nós com id local (``node-<ts>-<rand>``); o nó ganha um UUID
    # e as arestas/entrada que citam o id local são traduzidas por este mapa.
    id_map: dict[str, str] = {}
    for i, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"node {i}: objeto inválido"]
            })
        raw_node_id = str(n.get("id", ""))
        try:
            node_id = uuid.UUID(raw_node_id)
        except (ValueError, TypeError):
            node_id = uuid.uuid4()
        if raw_node_id:
            id_map[raw_node_id] = str(node_id)
        try:
            agent_id = uuid.UUID(str(n.get("agentId", "")))
        except (ValueError, TypeError):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"node {i} ({node_id}): agentId inválido"]
            }) from None
        node_ids.add(str(node_id))
        node_fields.append(
            {
                "id": node_id,
                "agent_id": agent_id,
                "position": n.get("position") or {},
                "label": n.get("label"),
                "agent_snapshot": n.get("agentSnapshot") or {},
            }
        )

    edge_fields: list[dict[str, Any]] = []
    for i, e in enumerate(raw_edges):
        if not isinstance(e, dict):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"edge {i}: objeto inválido"]
            })
        try:
            edge_id = uuid.UUID(str(e.get("id", "")))
        except (ValueError, TypeError):
            edge_id = uuid.uuid4()
        source = id_map.get(str(e.get("source", "")), str(e.get("source", "")))
        target = id_map.get(str(e.get("target", "")), str(e.get("target", "")))
        etype = e.get("type", "flow")
        if etype not in ("flow", "data"):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"edge {i}: type deve ser 'flow' ou 'data'"]
            })
        if source not in node_ids:
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"edge {i}: source não é um nó da pipeline"]
            })
        if target not in node_ids:
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": [f"edge {i}: target não é um nó da pipeline"]
            })
        condition = e.get("condition")
        data_mapping = e.get("dataMapping")
        edge_fields.append(
            {
                "id": edge_id,
                "type": etype,
                "source": uuid.UUID(source),
                "target": uuid.UUID(target),
                "condition": condition if isinstance(condition, dict) else None,
                "label": e.get("label"),
                "requires_approval": bool(e.get("requiresApproval", False)),
                "approval_channel": e.get("approvalChannel"),
                "approval_message": e.get("approvalMessage"),
                "data_mapping": data_mapping if isinstance(data_mapping, dict) else None,
                "reject_target": e.get("rejectTarget"),
            }
        )

    entry_raw = str(body.get("entryNodeId") or "")
    entry_raw = id_map.get(entry_raw, entry_raw)
    # O UUID nulo é a entrada que a própria API devolve para pipeline sem
    # nós; ao salvar o primeiro grafo ele equivale a "não definido".
    if entry_raw == _NIL_ENTRY:
        entry_raw = ""
    if entry_raw:
        try:
            entry = uuid.UUID(str(entry_raw))
        except (ValueError, TypeError):
            raise AppError(422, "unprocessable", "schema_validation", {
                "errors": ["entryNodeId: UUID inválido"]
            }) from None
        if str(entry) not in node_ids:
            raise AppError(400, "validation error", "invalid_graph", {
                "errors": [{"rule": 9, "message": "entryNodeId: não é um nó da pipeline"}]
            })
    elif node_fields:
        # Decisão mínima (B1): pipeline criada vazia no portal só ganha
        # entryNodeId quando o primeiro nó é posicionado; sem nós, o campo
        # da coluna é NOT NULL, então usamos o primeiro nó; sem NENHUM nó,
        # usamos um UUID nulo apenas interno (o validador regra 9 bloqueia
        # a execução até a entrada ser definida pelo editor).
        entry = node_fields[0]["id"]
    else:
        entry = uuid.UUID(_NIL_ENTRY)

    fields = {
        "id": pipeline_id,
        "name": name.strip(),
        "description": str(body.get("description", "") or ""),
        "entry_node_id": entry,
    }
    return fields, node_fields, edge_fields


# ---------------------------------------------------------------------------
# Serialização (camelCase, spec 4.2)
# ---------------------------------------------------------------------------


def _node_to_dict(n: PipelineNode) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "agentId": str(n.agent_id),
        "agentSnapshot": n.agent_snapshot,
        "position": n.position,
        "label": n.label,
    }


def _edge_to_dict(e: PipelineEdge) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "type": e.type.value if hasattr(e.type, "value") else e.type,
        "source": str(e.source),
        "target": str(e.target),
        "condition": e.condition,
        "label": e.label,
        "requiresApproval": e.requires_approval,
        "approvalChannel": (
            e.approval_channel
        ),
        "approvalMessage": e.approval_message,
        "dataMapping": e.data_mapping,
        "rejectTarget": e.reject_target,
    }


async def _resolve_repository(
    db: AsyncSession, owner_id: uuid.UUID, raw: Any
) -> dict[str, Any] | None:
    """Valida ``body["repository"]`` e devolve os 3 campos de coluna, ou ``None``.

    ``raw`` é ``None`` (limpa o repositório) ou um dict com ``integrationId``
    (UUID de uma integração do dono, tipo ``github``/``azure``), ``fullName``
    e ``baseBranch`` (strings não vazias); qualquer outro caso é 400
    ``invalid_repository``.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise AppError(400, "validation error", "invalid_repository", {
            "message": "repository deve ser um objeto ou null"
        })

    full_name = raw.get("fullName")
    base_branch = raw.get("baseBranch")
    if not isinstance(full_name, str) or not full_name.strip():
        raise AppError(400, "validation error", "invalid_repository", {
            "message": "repository.fullName obrigatório"
        })
    if not isinstance(base_branch, str) or not base_branch.strip():
        raise AppError(400, "validation error", "invalid_repository", {
            "message": "repository.baseBranch obrigatório"
        })
    try:
        integration_id = uuid.UUID(str(raw.get("integrationId")))
    except (ValueError, TypeError):
        raise AppError(400, "validation error", "invalid_repository", {
            "message": "repository.integrationId inválido"
        }) from None

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.owner_id == owner_id
        )
    )
    integration = result.scalar_one_or_none()
    integ_type = (
        integration.type.value if integration and hasattr(integration.type, "value")
        else (integration.type if integration else None)
    )
    if integration is None or integ_type not in ("github", "azure"):
        raise AppError(400, "validation error", "invalid_repository", {
            "message": "integrationId deve ser uma integração git (github/azure) do usuário"
        })

    return {
        "git_integration_id": integration_id,
        "git_repository": full_name.strip(),
        "git_base_branch": base_branch.strip(),
    }


def _pipeline_to_dict(
    p: Pipeline,
    nodes: list[PipelineNode],
    edges: list[PipelineEdge],
) -> dict[str, Any]:
    has_repo = p.git_integration_id and p.git_repository and p.git_base_branch
    return {
        "id": str(p.id),
        "ownerId": str(p.owner_id),
        "name": p.name,
        "description": p.description,
        "status": p.status.value if hasattr(p.status, "value") else p.status,
        "entryNodeId": str(p.entry_node_id),
        "repository": (
            {
                "integrationId": str(p.git_integration_id),
                "fullName": p.git_repository,
                "baseBranch": p.git_base_branch,
            }
            if has_repo
            else None
        ),
        "nodes": [_node_to_dict(n) for n in nodes],
        "edges": [_edge_to_dict(e) for e in edges],
        "startedAt": p.started_at.isoformat().replace("+00:00", "Z")
        if p.started_at
        else None,
        "completedAt": p.completed_at.isoformat().replace("+00:00", "Z")
        if p.completed_at
        else None,
        "createdAt": p.created_at.isoformat().replace("+00:00", "Z")
        if p.created_at
        else None,
        "updatedAt": p.updated_at.isoformat().replace("+00:00", "Z")
        if p.updated_at
        else None,
    }


async def _load_owned(
    db: AsyncSession, pipeline_id: uuid.UUID, user: User
) -> tuple[Pipeline, list[PipelineNode], list[PipelineEdge]]:
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id, Pipeline.owner_id == user.owner_id
        )
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise AppError(404, "not_found", "pipeline_not_found")
    nodes = list(
        (
            await db.execute(
                select(PipelineNode).where(PipelineNode.pipeline_id == pipeline_id)
            )
        ).scalars().all()
    )
    edges = list(
        (
            await db.execute(
                select(PipelineEdge).where(PipelineEdge.pipeline_id == pipeline_id)
            )
        ).scalars().all()
    )
    return pipeline, nodes, edges


async def _assert_not_running(db: AsyncSession, pipeline_id: uuid.UUID) -> None:
    """409 graph_running se há run ativo (contrato §8 Concorrência)."""
    active = (
        await db.execute(
            select(PipelineRun).where(
                PipelineRun.pipeline_id == pipeline_id,
                PipelineRun.status == "running",
            )
        )
    ).scalars().first()
    if active is not None:
        raise AppError(
            409, "conflict", "graph_running", {"runId": str(active.id)}
        )


async def _replace_graph(
    db: AsyncSession,
    pipeline: Pipeline,
    node_fields: list[dict[str, Any]],
    edge_fields: list[dict[str, Any]],
) -> None:
    """Substitui nós/arestas (apaga tudo e reinsere; PUT é grafo completo)."""
    from sqlalchemy import delete as sa_delete

    await db.execute(
        sa_delete(PipelineNode).where(PipelineNode.pipeline_id == pipeline.id)
    )
    await db.execute(
        sa_delete(PipelineEdge).where(PipelineEdge.pipeline_id == pipeline.id)
    )
    for f in node_fields:
        db.add(
            PipelineNode(
                id=f["id"],
                pipeline_id=pipeline.id,
                agent_id=f["agent_id"],
                position=f.get("position") or {},
                label=f.get("label"),
                agent_snapshot=f.get("agent_snapshot") or {},
            )
        )
    for f in edge_fields:
        channel = f.get("approval_channel")
        db.add(
            PipelineEdge(
                id=f["id"],
                pipeline_id=pipeline.id,
                type=f["type"],
                source=f["source"],
                target=f["target"],
                condition=f.get("condition"),
                label=f.get("label"),
                requires_approval=f.get("requires_approval", False),
                approval_channel=(
                    channel if channel else None
                ),
                approval_message=f.get("approval_message"),
                data_mapping=f.get("data_mapping"),
                reject_target=f.get("reject_target"),
            )
        )


def _pipeline_to_compiler(
    p: Pipeline,
    nodes: list[PipelineNode],
    edges: list[PipelineEdge],
) -> CompilerPipeline:
    """Converte para a Pipeline do compiler (para o validador)."""
    compiler_nodes = []
    for n in nodes:
        snap_raw = n.agent_snapshot or {}
        snap = AgentSnapshot(
            agent_id=str(snap_raw.get("agentId", n.agent_id)),
            version=snap_raw.get("version", 1),
            name=snap_raw.get("name", ""),
            description=snap_raw.get("description", ""),
            prompt=snap_raw.get("prompt", ""),
            strategy=snap_raw.get("strategy", ""),
            skills=snap_raw.get("skills", []),
            tools=snap_raw.get("tools", []),
            mcp_servers=snap_raw.get("mcpServers", snap_raw.get("mcp_servers", [])),
            knowledge=snap_raw.get("knowledge", []),
            integrations=snap_raw.get("integrations", []),
            inputs=[
                PortDef(
                    name=pt.get("name", ""),
                    type=pt.get("type", "string"),
                    required=pt.get("required", False),
                    description=pt.get("description", ""),
                )
                for pt in snap_raw.get("inputs", [])
            ],
            outputs=[
                PortDef(
                    name=pt.get("name", ""),
                    type=pt.get("type", "string"),
                    required=pt.get("required", False),
                    description=pt.get("description", ""),
                )
                for pt in snap_raw.get("outputs", [])
            ],
            actions=snap_raw.get("actions", []),
            model=snap_raw.get("model", ""),
            max_iterations=snap_raw.get("maxIterations", snap_raw.get("max_iterations", 10)),
            timeout=snap_raw.get("timeout", 60),
            shell_access=snap_raw.get("shellAccess", snap_raw.get("shell_access", False)),
        )
        compiler_nodes.append(
            CompilerNode(
                id=str(n.id),
                agent_id=str(n.agent_id),
                agent_snapshot=snap,
                position=n.position or {},
                label=n.label,
            )
        )

    compiler_edges = []
    for e in edges:
        condition = (
            EdgeCondition(
                field=(e.condition or {}).get("field", "action"),
                operator=(e.condition or {}).get("operator", "eq"),
                value=(e.condition or {}).get("value", "follow"),
            )
            if e.condition
            else None
        )
        mapping = (
            DataMapping(
                source_output=(e.data_mapping or {}).get(
                    "sourceOutput",
                    (e.data_mapping or {}).get("source_output", ""),
                ),
                target_input=(e.data_mapping or {}).get(
                    "targetInput",
                    (e.data_mapping or {}).get("target_input", ""),
                ),
            )
            if e.data_mapping
            else None
        )
        compiler_edges.append(
            CompilerEdge(
                id=str(e.id),
                type=e.type.value if hasattr(e.type, "value") else e.type,
                source=str(e.source),
                target=str(e.target),
                condition=condition,
                label=e.label,
                requires_approval=e.requires_approval,
                approval_channel=(
                    e.approval_channel
                ),
                approval_message=e.approval_message,
                data_mapping=mapping,
                reject_target=e.reject_target,
            )
        )

    return CompilerPipeline(
        id=str(p.id),
        name=p.name,
        entry_node_id=str(p.entry_node_id),
        nodes=compiler_nodes,
        edges=compiler_edges,
        description=p.description,
        status=p.status.value if hasattr(p.status, "value") else p.status,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines (spec 9.1): cria a pipeline com o grafo JSON."""
    pipeline_id = uuid.uuid4()
    fields, node_fields, edge_fields = _build_pipeline_from_body(
        body, pipeline_id=pipeline_id
    )
    pipeline = Pipeline(
        id=pipeline_id,
        owner_id=user.owner_id,
        name=fields["name"],
        description=fields["description"],
        status="draft",
        entry_node_id=fields["entry_node_id"],
    )
    if "repository" in body:
        repo_fields = await _resolve_repository(db, user.owner_id, body.get("repository"))
        if repo_fields is not None:
            pipeline.git_integration_id = repo_fields["git_integration_id"]
            pipeline.git_repository = repo_fields["git_repository"]
            pipeline.git_base_branch = repo_fields["git_base_branch"]
    db.add(pipeline)
    await _replace_graph(db, pipeline, node_fields, edge_fields)
    await db.commit()
    return await _load_pipeline_response(db, pipeline_id, user)


async def _load_pipeline_response(
    db: AsyncSession, pipeline_id: uuid.UUID, user: User
) -> dict[str, Any]:
    pipeline, nodes, edges = await _load_owned(db, pipeline_id, user)
    return _pipeline_to_dict(pipeline, nodes, edges)


@router.get("/pipelines")
async def list_pipelines(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """GET /api/pipelines (spec 9.1): listagem paginada do owner."""
    stmt = select(Pipeline).where(Pipeline.owner_id == user.owner_id)
    if status:
        stmt = stmt.where(Pipeline.status == status)
    stmt = stmt.order_by(Pipeline.created_at.desc())
    result = await db.execute(stmt)
    pipelines = list(result.scalars().all())

    offset = (page - 1) * limit
    page_pipelines = pipelines[offset : offset + limit]

    items: list[dict[str, Any]] = []
    for p in page_pipelines:
        nodes = list(
            (
                await db.execute(
                    select(PipelineNode).where(PipelineNode.pipeline_id == p.id)
                )
            ).scalars().all()
        )
        edges = list(
            (
                await db.execute(
                    select(PipelineEdge).where(PipelineEdge.pipeline_id == p.id)
                )
            ).scalars().all()
        )
        items.append(_pipeline_to_dict(p, nodes, edges))

    return {"items": items, "total": len(pipelines), "page": page, "limit": limit}


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """GET /api/pipelines/:id (spec 9.1): pipeline + estado."""
    pipeline, nodes, edges = await _load_owned(db, pipeline_id, user)
    return _pipeline_to_dict(pipeline, nodes, edges)


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: uuid.UUID,
    body: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """PUT /api/pipelines/:id (spec 9.1): atualiza grafo/metadata.

    - 409 ``graph_running`` se há run ativo (contrato §8).
    - Sem ``nodes``/``edges`` no corpo: atualiza só metadados
      (name/description/entryNodeId) — usado pela suíte
      (``{"description": "editada"}``).
    - Com ``nodes``/``edges``: substitui o grafo inteiro.
    """
    pipeline, nodes, edges = await _load_owned(db, pipeline_id, user)
    await _assert_not_running(db, pipeline_id)

    has_graph = "nodes" in body or "edges" in body
    if has_graph:
        # Reconstrói o corpo completo (mantém name/description atuais se
        # ausentes) e substitui o grafo.
        full_body = {
            "name": body.get("name", pipeline.name),
            "description": body.get("description", pipeline.description),
            "entryNodeId": body.get("entryNodeId", pipeline.entry_node_id),
            "nodes": body.get("nodes", [_node_to_dict(n) for n in nodes]),
            "edges": body.get("edges", [_edge_to_dict(e) for e in edges]),
        }
        fields, node_fields, edge_fields = _build_pipeline_from_body(
            full_body, pipeline_id=pipeline_id
        )
        pipeline.name = fields["name"]
        pipeline.description = fields["description"]
        # A pipeline nasce sem nós (entryNodeId nulo); quando o primeiro nó
        # chega, a entrada vira esse nó (decisão mínima, validador regra 9).
        new_entry = fields["entry_node_id"]
        if node_fields and str(new_entry) == _NIL_ENTRY:
            new_entry = node_fields[0]["id"]
        pipeline.entry_node_id = new_entry
        await _replace_graph(db, pipeline, node_fields, edge_fields)
    else:
        if "name" in body:
            name = body.get("name")
            if not isinstance(name, str) or not name.strip():
                raise AppError(422, "unprocessable", "schema_validation", {
                    "errors": ["name: obrigatório"]
                })
            pipeline.name = name.strip()
        if "description" in body:
            pipeline.description = str(body.get("description", "") or "")
        if body.get("entryNodeId"):
            entry = _uuid_field(body["entryNodeId"], "entryNodeId")
            existing_ids = {str(n.id) for n in nodes}
            if str(entry) not in existing_ids:
                raise AppError(422, "unprocessable", "schema_validation", {
                    "errors": ["entryNodeId: não é um nó da pipeline"]
                })
            pipeline.entry_node_id = entry

    if "repository" in body:
        repo_fields = await _resolve_repository(db, user.owner_id, body.get("repository"))
        if repo_fields is None:
            pipeline.git_integration_id = None
            pipeline.git_repository = None
            pipeline.git_base_branch = None
        else:
            pipeline.git_integration_id = repo_fields["git_integration_id"]
            pipeline.git_repository = repo_fields["git_repository"]
            pipeline.git_base_branch = repo_fields["git_base_branch"]

    pipeline.updated_at = datetime.now(UTC)
    await db.commit()

    pipeline2, nodes2, edges2 = await _load_owned(db, pipeline_id, user)
    return _pipeline_to_dict(pipeline2, nodes2, edges2)


@router.post("/pipelines/validate")
async def validate_pipeline_endpoint(
    body: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/validate (spec 4.2 / B1): valida sem persistir.

    400 ``invalid_graph`` com ``details.errors`` no formato da spec 4.2
    (lista de {rule, message, nodeId?, edgeId?}).
    """
    if not isinstance(body, dict):
        raise AppError(422, "unprocessable", "schema_validation", {"errors": ["body inválido"]})
    pipeline_id = uuid.uuid4()
    _fields, node_fields, edge_fields = _build_pipeline_from_body(
        body, pipeline_id=pipeline_id
    )

    # Constrói a Pipeline do compiler direto dos campos já validados.
    snap_map: dict[str, AgentSnapshot] = {}
    compiler_nodes: list[CompilerNode] = []
    for f in node_fields:
        raw = f["agent_snapshot"]
        snap = AgentSnapshot(
            agent_id=str(raw.get("agentId", f["agent_id"])),
            version=raw.get("version", 1),
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            prompt=raw.get("prompt", ""),
            strategy=raw.get("strategy", ""),
            skills=raw.get("skills", []),
            tools=raw.get("tools", []),
            mcp_servers=raw.get("mcpServers", raw.get("mcp_servers", [])),
            knowledge=raw.get("knowledge", []),
            integrations=raw.get("integrations", []),
            inputs=[
                PortDef(
                    name=pt.get("name", ""),
                    type=pt.get("type", "string"),
                    required=pt.get("required", False),
                    description=pt.get("description", ""),
                )
                for pt in raw.get("inputs", [])
            ],
            outputs=[
                PortDef(
                    name=pt.get("name", ""),
                    type=pt.get("type", "string"),
                    required=pt.get("required", False),
                    description=pt.get("description", ""),
                )
                for pt in raw.get("outputs", [])
            ],
            actions=raw.get("actions", []),
            model=raw.get("model", ""),
            max_iterations=raw.get("maxIterations", raw.get("max_iterations", 10)),
            timeout=raw.get("timeout", 60),
            shell_access=raw.get("shellAccess", raw.get("shell_access", False)),
        )
        snap_map[str(f["id"])] = snap
        compiler_nodes.append(
            CompilerNode(
                id=str(f["id"]),
                agent_id=str(f["agent_id"]),
                agent_snapshot=snap,
                position=f.get("position") or {},
                label=f.get("label"),
            )
        )

    compiler_edges: list[CompilerEdge] = []
    for f in edge_fields:
        condition_raw = f.get("condition")
        mapping_raw = f.get("data_mapping")
        compiler_edges.append(
            CompilerEdge(
                id=str(f["id"]),
                type=f["type"],
                source=str(f["source"]),
                target=str(f["target"]),
                condition=(
                    EdgeCondition(
                        field=condition_raw.get("field", "action"),
                        operator=condition_raw.get("operator", "eq"),
                        value=condition_raw.get("value", "follow"),
                    )
                    if condition_raw
                    else None
                ),
                label=f.get("label"),
                requires_approval=f.get("requires_approval", False),
                approval_channel=f.get("approval_channel"),
                approval_message=f.get("approval_message"),
                data_mapping=(
                    DataMapping(
                        source_output=mapping_raw.get(
                            "sourceOutput", mapping_raw.get("source_output", "")
                        ),
                        target_input=mapping_raw.get(
                            "targetInput", mapping_raw.get("target_input", "")
                        ),
                    )
                    if mapping_raw
                    else None
                ),
                reject_target=f.get("reject_target"),
            )
        )

    pipeline = CompilerPipeline(
        id=str(pipeline_id),
        name=_fields["name"],
        entry_node_id=str(_fields["entry_node_id"]),
        nodes=compiler_nodes,
        edges=compiler_edges,
        description=_fields["description"],
        status="draft",
    )

    result = validate_pipeline(pipeline)
    if not result.is_valid:
        raise AppError(
            400,
            "validation error",
            "invalid_graph",
            {"errors": [e.to_dict() for e in result.errors]},
        )
    return result.to_dict()


@router.delete("/pipelines/{pipeline_id}", status_code=204, response_model=None)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    """DELETE /api/pipelines/:id: apaga a pipeline (cascade de nós/arestas/runs).

    409 ``graph_running`` se há run ativo (mesma regra do PUT). Além do
    cascade no banco, remove os workspaces em disco (clone/alterações) de
    cada run da pipeline (Task 5, ``WorkspaceManager``) — os ids são
    coletados ANTES do delete porque o cascade apaga as linhas de
    ``pipeline_runs``.
    """
    pipeline, _nodes, _edges = await _load_owned(db, pipeline_id, user)
    await _assert_not_running(db, pipeline_id)
    run_ids = list(
        (
            await db.execute(
                select(PipelineRun.id).where(PipelineRun.pipeline_id == pipeline_id)
            )
        ).scalars().all()
    )
    await db.delete(pipeline)
    await db.commit()
    # rmtree de cada workspace/gitdir em thread: nunca no loop de eventos.
    await asyncio.to_thread(WorkspaceManager().remove_many, [str(r) for r in run_ids])


@router.post("/pipelines/{pipeline_id}/duplicate", status_code=201)
async def duplicate_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/duplicate: cópia do grafo, sem runs.

    Novos UUIDs para nós e arestas (mapa antigo→novo, remapeando
    source/target e o entryNodeId); nome ``"<nome> (cópia)"``; status
    ``draft``; repositório (se houver) é copiado junto.
    """
    pipeline, nodes, edges = await _load_owned(db, pipeline_id, user)

    new_id = uuid.uuid4()
    id_map: dict[uuid.UUID, uuid.UUID] = {n.id: uuid.uuid4() for n in nodes}
    new_entry = id_map.get(pipeline.entry_node_id, pipeline.entry_node_id)

    new_pipeline = Pipeline(
        id=new_id,
        owner_id=user.owner_id,
        name=f"{pipeline.name} (cópia)",
        description=pipeline.description,
        status="draft",
        entry_node_id=new_entry,
        git_integration_id=pipeline.git_integration_id,
        git_repository=pipeline.git_repository,
        git_base_branch=pipeline.git_base_branch,
    )
    db.add(new_pipeline)

    for n in nodes:
        db.add(
            PipelineNode(
                id=id_map[n.id],
                pipeline_id=new_id,
                agent_id=n.agent_id,
                position=n.position,
                label=n.label,
                agent_snapshot=n.agent_snapshot,
            )
        )
    for e in edges:
        db.add(
            PipelineEdge(
                id=uuid.uuid4(),
                pipeline_id=new_id,
                type=e.type,
                source=id_map.get(e.source, e.source),
                target=id_map.get(e.target, e.target),
                condition=e.condition,
                label=e.label,
                requires_approval=e.requires_approval,
                approval_channel=e.approval_channel,
                approval_message=e.approval_message,
                data_mapping=e.data_mapping,
                reject_target=e.reject_target,
            )
        )

    await db.commit()
    return await _load_pipeline_response(db, new_id, user)
