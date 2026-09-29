"""GitHub fake (API REST mínima) para a suíte qa-integration e o E2E.

Roda no serviço ``git-test`` (perfil ``test`` do compose), ao lado de um
``git daemon`` que serve os repositórios bare de ``/srv/git`` (git://git-test/).
O orchestrator é apontado para cá só no modo de teste:
``GITHUB_API_BASE=http://git-test:8080`` e ``GIT_CLONE_BASE_OVERRIDE=git://git-test``.

Rotas (formato do GitHub, só os campos que o GitHubProvider lê):
  GET  /user/repos                    repositórios em /srv/git/<dono>/<nome>.git
  GET  /repos/{o}/{r}/branches        branches reais do repositório bare
  POST /repos/{o}/{r}/pulls           abre PR (guardado em memória)
  GET  /repos/{o}/{r}/pulls?head=o:b  PRs abertos (filtro por head)
  GET  /_qa/pulls                     todos os PRs (asserções dos testes)
  POST /_qa/reset                     limpa os PRs

Token: aceita só ``Bearer qa-token...`` (qualquer outro -> 401), para o
"testar conexão" ter caminho de erro. Sem dependências além da stdlib.
"""

import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

GIT_ROOT = Path("/srv/git")
PULLS: list[dict] = []


def _repos() -> list[str]:
    return sorted(
        f"{p.parent.name}/{p.name[:-4]}" for p in GIT_ROOT.glob("*/*.git") if p.is_dir()
    )


def _branches(repo: str) -> list[str] | None:
    path = GIT_ROOT / f"{repo}.git"
    if not path.is_dir():
        return None
    out = subprocess.run(
        ["git", "-c", "safe.directory=*", "--git-dir", str(path), "for-each-ref",
         "refs/heads", "--format=%(refname:short)"],
        capture_output=True, text=True, check=False,
    ).stdout
    return [b for b in out.splitlines() if b]


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer qa-token"):
            return True
        self._send({"message": "Bad credentials"}, 401)
        return False

    def _repo_from(self, parts: list[str]) -> str | None:
        # /repos/{o}/{r}/...
        if len(parts) >= 4 and parts[0] == "repos":
            return f"{parts[1]}/{parts[2]}"
        return None

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = parse_qs(url.query)
        if url.path == "/health":
            return self._send({"ok": True})
        if url.path == "/_qa/pulls":
            return self._send(PULLS)
        if not self._authorized():
            return None
        if url.path == "/user/repos":
            return self._send([{"full_name": r, "default_branch": "main"} for r in _repos()])
        repo = self._repo_from(parts)
        if repo and parts[3] == "branches":
            branches = _branches(repo)
            if branches is None:
                return self._send({"message": "Not Found"}, 404)
            return self._send([{"name": b} for b in branches])
        if repo and parts[3] == "pulls":
            head = (query.get("head") or [""])[0].split(":", 1)[-1]
            items = [p for p in PULLS if p["repo"] == repo and p["state"] == "open"
                     and (not head or p["head"]["ref"] == head)]
            return self._send(items)
        return self._send({"message": "Not Found"}, 404)

    def do_POST(self):  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        if url.path == "/_qa/reset":
            PULLS.clear()
            return self._send({"ok": True})
        if not self._authorized():
            return None
        repo = self._repo_from(parts)
        if repo and parts[3] == "pulls":
            branches = _branches(repo)
            if branches is None:
                return self._send({"message": "Not Found"}, 404)
            if body.get("head") not in branches:
                return self._send({"message": "Validation Failed: head"}, 422)
            number = len(PULLS) + 1
            pr = {
                "number": number,
                "html_url": f"https://github.example/{repo}/pull/{number}",
                "repo": repo,
                "state": "open",
                "title": body.get("title", ""),
                "body": body.get("body", ""),
                "head": {"ref": body.get("head")},
                "base": {"ref": body.get("base")},
            }
            PULLS.append(pr)
            return self._send(pr, 201)
        return self._send({"message": "Not Found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
