"""Servidor MCP stdio real e determinístico para testes."""

import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "echo", "version": "1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [{"name": "echo", "description": "Eco", "inputSchema": {"type": "object"}}]
        }
    else:
        result = {
            "content": [{"type": "text", "text": request["params"]["arguments"]["text"]}],
            "isError": False,
        }
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
