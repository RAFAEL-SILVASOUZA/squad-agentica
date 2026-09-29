"""Servidor MCP stdio que trava no tools/call e ignora SIGTERM (testes).

Sobe um neto (``sleep``) para provar que o grupo inteiro é encerrado; o pid do
neto vai para o arquivo passado em argv[1].
"""

import json
import signal
import subprocess
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(["sleep", "300"])
with open(sys.argv[1], "w") as fh:
    fh.write(str(child.pid))

for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    if request["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}}
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
        continue
    while True:
        time.sleep(1)
