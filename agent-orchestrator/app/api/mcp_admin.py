from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import MCPOAuthClient, MCPOAuthToken, User
from app.db.session import get_db
from app.mcp_server.server import mcp

router = APIRouter(prefix="/mcp", tags=["mcp admin"])


@router.get("/tokens")
async def list_mcp_tokens(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List MCP OAuth tokens for the current user."""
    query = (
        select(
            MCPOAuthToken.jti,
            MCPOAuthClient.client_name,
            MCPOAuthToken.scope,
            MCPOAuthToken.expires_at,
            MCPOAuthToken.revoked_at,
            MCPOAuthToken.created_at,
        )
        .join(MCPOAuthClient, MCPOAuthToken.client_id == MCPOAuthClient.client_id)
        .where(MCPOAuthToken.user_id == current_user.id)
        .order_by(MCPOAuthToken.created_at.desc())
    )
    result = await db.execute(query)
    tokens = result.all()

    return [
        {
            "jti": t.jti,
            "client_name": t.client_name,
            "scope": t.scope,
            "expires_at": t.expires_at,
            "revoked_at": t.revoked_at,
            "created_at": t.created_at,
        }
        for t in tokens
    ]


@router.delete("/tokens/{jti}")
async def revoke_mcp_token(
    jti: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Revoke a specific MCP OAuth token."""
    query = select(MCPOAuthToken).where(MCPOAuthToken.jti == jti)
    result = await db.execute(query)
    token = result.scalar_one_or_none()

    if token is None or token.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Token not found"
        )

    if token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        await db.commit()

    return {"revoked": True}


@router.get("/tools")
async def list_mcp_tools(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all registered MCP tools."""
    tools = await mcp.list_tools()
    return [
        {"name": tool.name, "description": tool.description}
        for tool in tools
    ]
