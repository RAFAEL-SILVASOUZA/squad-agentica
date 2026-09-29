"""Ponte MCP interna autenticada pelo token compartilhado dos workers.

Os workers chamam ``POST /internal/mcp/{server_id}/call`` quando o LLM usa uma
tool MCP; o orchestrator abre o servidor do dono e repassa o ``tools/call``.

Servidores stdio são código confiável cadastrado pelo dono: rodam dentro do
container do orchestrator com o acesso ao sistema de arquivos dele (não há
sandbox). Quando a chamada traz um ``workspaceDir`` válido (estritamente dentro
de ``settings.workspaces_dir``), o processo sobe com esse diretório como cwd,
então caminhos relativos nos argumentos caem no workspace do run. Sem
workspace, o processo usa o cwd padrão do orchestrator.
"""

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
    # Bytes: compare_digest com str não-ASCII levanta TypeError (viraria 500).
    if not settings.worker_token or not secrets.compare_digest(
        x_worker_token.encode(), settings.worker_token.encode()
    ):
        raise AppError(401, "Não autorizado", "worker_token_invalid")
    server = await MCPRegistry(db).get(server_id, body.ownerId)
    workspace = None
    if body.workspaceDir:
        try:
            workspace = Path(body.workspaceDir).resolve()
        except (OSError, ValueError):
            workspace = None
        if (
            workspace is None
            or Path(settings.workspaces_dir).resolve() not in workspace.parents
            or not workspace.is_dir()
        ):
            raise AppError(422, "Workspace inválido para MCP", "invalid_mcp_path")
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
            result = await client.call_tool(body.tool, body.arguments)
        return {"content": result.get("content", []), "isError": bool(result.get("isError", False))}
    except Exception as exc:
        raise AppError(
            502,
            describe_connection_error(exc, server.transport, server.command, server.url),
            "mcp_call_failed",
        ) from None
    finally:
        await client.disconnect()
