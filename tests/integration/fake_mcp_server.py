"""Servidor MCP fake (JSON-RPC sobre HTTP) usado pela suite qa-integration.

Roda como container sidecar na rede do compose (ver ``mcp_fake`` em
test_02_agent_lifecycle.py), para o orchestrator alcanca-lo por nome.
Implementa ``initialize``, ``tools/list`` e ``tools/call`` (tool ``qa_echo``).
Sem dependencias alem da stdlib.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS = [
    {
        "name": "qa_echo",
        "description": "Ecoa o texto recebido (QA fake MCP).",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    }
]


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._send({"ok": True})

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        req = json.loads(self.rfile.read(n) or b"{}")
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "qa-fake-mcp", "version": "1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            result = {"content": [{"type": "text", "text": "echo:" + str(args.get("text", ""))}]}
        else:
            self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "not found"}})
            return
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
