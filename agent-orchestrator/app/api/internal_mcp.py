"""Ponte MCP interna autenticada pelo token compartilhado dos workers."""

import asyncio
import secrets
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_db
from app.mcp.client import CALL_TIMEOUT, CONNECT_TIMEOUT, MCPClient, describe_connection_error
from app.mcp.registry import MCPRegistry

router = APIRouter(prefix="/internal/mcp", tags=["internal"])


class CallRequest(BaseModel):
    ownerId: uuid.UUID
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    workspaceDir: str | None = None


@router.post("/{server_id}/call")
async def call_mcp(
    server_id: uuid.UUID,
    body: CallRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_worker_token: Annotated[str, Header()] = "",
) -> dict[str, Any]:
    if not settings.worker_token or not secrets.compare_digest(
        x_worker_token, settings.worker_token
    ):
        raise AppError(401, "Não autorizado", "worker_token_invalid")
    server = await MCPRegistry(db).get(server_id, body.ownerId)
    workspace = None
    arguments = dict(body.arguments)
    if body.workspaceDir:
        workspace = Path(body.workspaceDir).resolve()
        if Path(settings.workspaces_dir).resolve() not in workspace.parents:
            raise AppError(422, "Workspace inválido para MCP", "invalid_mcp_path")
    # O Excel aceita caminhos absolutos; resolvemos os argumentos conhecidos
    # antes do processo. Servidores cadastrados continuam sendo código confiável.
    if "@negokaz/excel-mcp-server" in (server.command or ""):
        if workspace is None:
            raise AppError(422, "Excel requer o workspace do run", "invalid_mcp_path")
        for key in (
            "fileAbsolutePath",
            "filepath",
            "filePath",
            "path",
            "sourcePath",
            "destinationPath",
        ):
            if key not in arguments:
                continue
            try:
                value = Path(arguments[key])
                resolved = (workspace / value).resolve()
                if workspace not in resolved.parents:
                    raise ValueError
                arguments[key] = str(resolved)
            except (TypeError, ValueError, OSError):
                raise AppError(
                    422, "Caminho fora do workspace do run", "invalid_mcp_path"
                ) from None
    client = MCPClient(
        server.transport,
        server.command,
        server.url,
        server.env,
        cwd=str(workspace) if workspace else None,
    )
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT + CALL_TIMEOUT):
            await client.connect()
            result = await client.call_tool(body.tool, arguments)
        return {"content": result.get("content", []), "isError": bool(result.get("isError", False))}
    except Exception as exc:
        raise AppError(
            502,
            describe_connection_error(exc, server.transport, server.command, server.url),
            "mcp_call_failed",
        ) from None
    finally:
        await client.disconnect()
