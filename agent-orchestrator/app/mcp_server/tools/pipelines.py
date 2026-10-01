"""Ferramentas MCP de pipelines (CRUD + validação).

Registra as ferramentas de gerenciamento de pipelines no servidor MCP. Cada
ferramenta lê o usuário autenticado via ``get_current_mcp_user`` (contextvar
populado pelo middleware de autenticação) e delega a operação às funções
reutilizáveis de ``app.api.pipelines``.

Erros do banco (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.api.pipelines import (
    _build_pipeline_from_body,
    _load_owned,
    _pipeline_to_dict,
    _replace_graph,
    _resolve_repository,
)
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
from app.compiler.validator import validate_pipeline as _validate_graph
from app.core.errors import AppError
from app.db.models import Pipeline, PipelineEdge, PipelineNode
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_pipeline(
    name: str,
    description: str = "",
    entry_node_id: str | None = None,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    repository: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cria um novo pipeline com grafo opcional (nós e arestas).

    O grafo é validado pelo mesmo validador usado pela API REST. Se
    ``repository`` for fornecido, deve conter ``integrationId``,
    ``fullName`` e ``baseBranch``.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    body: dict[str, Any] = {
        "name": name,
        "description": description,
        "entryNodeId": entry_node_id,
        "nodes": nodes or [],
        "edges": edges or [],
    }
    if repository is not None:
        body["repository"] = repository

    pipeline_id = uuid.uuid4()

    async with async_session_factory() as db:
        try:
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
            if repository is not None:
                repo_fields = await _resolve_repository(
                    db, user.owner_id, repository
                )
                if repo_fields is not None:
                    pipeline.git_integration_id = repo_fields["git_integration_id"]
                    pipeline.git_repository = repo_fields["git_repository"]
                    pipeline.git_base_branch = repo_fields["git_base_branch"]
            db.add(pipeline)
            await _replace_graph(db, pipeline, node_fields, edge_fields)
            await db.commit()
        except AppError as e:
            raise ToolError(f"Erro ao criar pipeline: {e.error}") from e

        p, nodes_loaded, edges_loaded = await _load_owned(db, pipeline_id, user)
        return _pipeline_to_dict(p, nodes_loaded, edges_loaded)


@mcp.tool()
async def list_pipelines(
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """Lista os pipelines do usuário autenticado, com paginação e filtro opcional por status."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        try:
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
                            select(PipelineNode).where(
                                PipelineNode.pipeline_id == p.id
                            )
                        )
                    ).scalars().all()
                )
                edges = list(
                    (
                        await db.execute(
                            select(PipelineEdge).where(
                                PipelineEdge.pipeline_id == p.id
                            )
                        )
                    ).scalars().all()
                )
                items.append(_pipeline_to_dict(p, nodes, edges))

            return {
                "items": items,
                "total": len(pipelines),
                "page": page,
                "limit": limit,
            }
        except AppError as e:
            raise ToolError(f"Erro ao listar pipelines: {e.error}") from e


@mcp.tool()
async def get_pipeline(pipeline_id: str) -> dict[str, Any]:
    """Obtém uma pipeline por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(pipeline_id)

    async with async_session_factory() as db:
        try:
            p, nodes, edges = await _load_owned(db, parsed_id, user)
        except AppError as e:
            raise ToolError(f"Erro ao obter pipeline: {e.error}") from e
        return _pipeline_to_dict(p, nodes, edges)


@mcp.tool()
async def update_pipeline(
    pipeline_id: str,
    name: str | None = None,
    description: str | None = None,
    entry_node_id: str | None = None,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    repository: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atualiza uma pipeline (partial update: só os campos informados são alterados).

    Se ``nodes``/``edges`` forem fornecidos, substitui o grafo inteiro.
    Pelo menos um campo além de ``pipeline_id`` deve ser fornecido.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(pipeline_id)

    has_graph = nodes is not None or edges is not None
    has_metadata = (
        name is not None
        or description is not None
        or entry_node_id is not None
        or repository is not None
    )
    if not has_graph and not has_metadata:
        raise ToolError("Nenhum campo para atualizar foi fornecido.")

    async with async_session_factory() as db:
        try:
            pipeline, existing_nodes, existing_edges = await _load_owned(
                db, parsed_id, user
            )

            if has_graph:
                full_body: dict[str, Any] = {
                    "name": name if name is not None else pipeline.name,
                    "description": (
                        description
                        if description is not None
                        else pipeline.description
                    ),
                    "entryNodeId": (
                        entry_node_id
                        if entry_node_id is not None
                        else str(pipeline.entry_node_id)
                    ),
                    "nodes": nodes if nodes is not None else [
                        {
                            "id": str(n.id),
                            "agentId": str(n.agent_id),
                            "agentSnapshot": n.agent_snapshot,
                            "position": n.position,
                            "label": n.label,
                        }
                        for n in existing_nodes
                    ],
                    "edges": edges if edges is not None else [
                        {
                            "id": str(e.id),
                            "type": e.type.value if hasattr(e.type, "value") else e.type,
                            "source": str(e.source),
                            "target": str(e.target),
                            "condition": e.condition,
                            "label": e.label,
                            "requiresApproval": e.requires_approval,
                            "approvalChannel": e.approval_channel,
                            "approvalMessage": e.approval_message,
                            "dataMapping": e.data_mapping,
                            "rejectTarget": e.reject_target,
                        }
                        for e in existing_edges
                    ],
                }
                fields, node_fields, edge_fields = _build_pipeline_from_body(
                    full_body, pipeline_id=parsed_id
                )
                pipeline.name = fields["name"]
                pipeline.description = fields["description"]
                pipeline.entry_node_id = fields["entry_node_id"]
                await _replace_graph(db, pipeline, node_fields, edge_fields)
            else:
                if name is not None:
                    if not name.strip():
                        raise AppError(
                            422, "unprocessable", "schema_validation",
                            {"errors": ["name: obrigatório"]},
                        )
                    pipeline.name = name.strip()
                if description is not None:
                    pipeline.description = description
                if entry_node_id is not None:
                    entry = _parse_uuid(entry_node_id)
                    existing_ids = {str(n.id) for n in existing_nodes}
                    if str(entry) not in existing_ids:
                        raise AppError(
                            422, "unprocessable", "schema_validation",
                            {"errors": ["entryNodeId: não é um nó da pipeline"]},
                        )
                    pipeline.entry_node_id = entry

            if repository is not None:
                repo_fields = await _resolve_repository(
                    db, user.owner_id, repository
                )
                if repo_fields is None:
                    pipeline.git_integration_id = None
                    pipeline.git_repository = None
                    pipeline.git_base_branch = None
                else:
                    pipeline.git_integration_id = repo_fields["git_integration_id"]
                    pipeline.git_repository = repo_fields["git_repository"]
                    pipeline.git_base_branch = repo_fields["git_base_branch"]

            await db.commit()
        except AppError as e:
            raise ToolError(f"Erro ao atualizar pipeline: {e.error}") from e

        p, nodes_loaded, edges_loaded = await _load_owned(db, parsed_id, user)
        return _pipeline_to_dict(p, nodes_loaded, edges_loaded)


@mcp.tool()
async def delete_pipeline(pipeline_id: str) -> dict[str, Any]:
    """Remove uma pipeline (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(pipeline_id)

    async with async_session_factory() as db:
        try:
            pipeline, _nodes, _edges = await _load_owned(db, parsed_id, user)
            await db.delete(pipeline)
            await db.commit()
        except AppError as e:
            raise ToolError(f"Erro ao remover pipeline: {e.error}") from e
        return {"success": True, "message": "Pipeline removida com sucesso."}


@mcp.tool()
async def validate_pipeline(
    name: str,
    entry_node_id: str | None = None,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Valida um grafo de pipeline sem persistir.

    Retorna o resultado da validação (erros e avisos) no formato da spec 4.2.
    Se o grafo for inválido, retorna os erros; se válido, retorna
    ``{"errors": []}`` (e eventuais ``warnings``).
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    body: dict[str, Any] = {
        "name": name,
        "entryNodeId": entry_node_id,
        "nodes": nodes or [],
        "edges": edges or [],
    }

    try:
        pipeline_id = uuid.uuid4()
        fields, node_fields, edge_fields = _build_pipeline_from_body(
            body, pipeline_id=pipeline_id
        )
    except AppError as e:
        raise ToolError(f"Erro ao validar pipeline: {e.error}") from e

    # Constrói a Pipeline do compiler a partir dos campos já validados.
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
            llm=raw.get("llm"),
            max_iterations=raw.get("maxIterations", raw.get("max_iterations", 10)),
            timeout=raw.get("timeout", 60),
            shell_access=raw.get("shellAccess", raw.get("shell_access", False)),
        )
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
        name=fields["name"],
        entry_node_id=str(fields["entry_node_id"]),
        nodes=compiler_nodes,
        edges=compiler_edges,
        description=fields["description"],
        status="draft",
    )

    result = _validate_graph(pipeline)
    return result.to_dict()
