"""Servidor MCP stdio real e determinístico para testes."""

import json
import os
import sys

TOOLS = [
    {"name": "echo", "description": "Eco", "inputSchema": {"type": "object"}},
    {"name": "cwd", "description": "Diretório atual", "inputSchema": {"type": "object"}},
]

for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    # Ruído antes de cada resposta: log fora do protocolo, JSON que não é
    # objeto, notificação e request do servidor com o mesmo "id" (tem "method").
    print("log: processando", flush=True)
    print("[1, 2]", flush=True)
    print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message"}), flush=True)
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "method": "roots/list"}), flush=True)
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "echo", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif request["params"]["name"] == "cwd":
        result = {"content": [{"type": "text", "text": os.getcwd()}], "isError": False}
    else:
        result = {
            "content": [{"type": "text", "text": request["params"]["arguments"]["text"]}],
            "isError": False,
        }
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
