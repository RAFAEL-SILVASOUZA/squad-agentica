"""Pacote do servidor MCP (FastMCP) do Agent Portal Orchestrator.

Expõe as ferramentas do portal via protocolo MCP (Streamable HTTP) montado
em ``/mcp``. O contexto do usuário autenticado é propagado por
``contextvars`` (ver ``context.py``) para que as ferramentas saibam quem
está chamando.
"""
