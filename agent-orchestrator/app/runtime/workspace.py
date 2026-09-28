"""Workspace compartilhado por run: clone, alterações, diff, zip e publicação.

Dono: rt-executor (Task 5, 2026-09-28-projeto-git-e-usabilidade). O worker
escreve arquivos no workspace do run (volume compartilhado orchestrator/
worker) e o orchestrator é quem faz commit/push — ambos os containers rodam
como root, então os arquivos podem ter sido criados por um UID diferente do
processo git; ``-c safe.directory=*`` evita o erro "detected dubious
ownership in repository" do git >= 2.35 sem exigir configuração por caminho.
"""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import time
import unicodedata
import zipfile
from pathlib import Path

from app.core.config import settings


class WorkspaceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# Casa credenciais embutidas em URLs (``https://user:token@host/...``) para
# nunca vazarem em mensagens de erro/log (convenção do projeto).
_CRED = re.compile(r"(https?://)[^@/\s]+@")


def _scrub(text: str) -> str:
    return _CRED.sub(r"\1***@", text)


def slugify_branch(pipeline_name: str, run_id: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", pipeline_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-") or "pipeline"
    return f"agent-portal/{slug}-{run_id.replace('-', '')[:8]}"


async def _git(cwd: Path | None, *args: str, check: bool = True) -> tuple[int, str]:
    # HOME precisa existir para o git não avisar/falhar ao ler config global;
    # ``-c safe.directory=*`` (ver docstring do módulo) confia em qualquer
    # dono de repositório, já que orchestrator e worker rodam como root mas
    # podem ter escrito os arquivos em momentos/processos diferentes.
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
    }
    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "safe.directory=*", *args, cwd=str(cwd) if cwd else None, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    text = _scrub(out.decode("utf-8", errors="replace"))
    if check and proc.returncode != 0:
        raise WorkspaceError(text.strip()[-500:] or f"git {args[0]} falhou")
    return proc.returncode or 0, text


class WorkspaceManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.workspaces_dir)

    def path(self, run_id: str) -> Path:
        return self.root / run_id

    def _safe(self, run_id: str, rel: str) -> Path:
        base = self.path(run_id).resolve()
        target = (base / rel).resolve()
        if target != base and base not in target.parents:
            raise WorkspaceError("caminho fora do workspace")
        return target

    def create_empty(self, run_id: str) -> Path:
        p = self.path(run_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def clone(self, run_id: str, clone_url: str, base_branch: str) -> Path:
        dest = self.path(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        code, out = await _git(None, "clone", "--depth", "1", "--branch", base_branch,
                                clone_url, str(dest), check=False)
        if code != 0:
            shutil.rmtree(dest, ignore_errors=True)
            if "Remote branch" in out and "not found" in out:
                raise WorkspaceError(f"branch '{base_branch}' não existe no repositório")
            if (
                "Authentication failed" in out
                or "403" in out
                or "could not read Username" in out
                or "401" in out
                or "HTTP Basic: Access denied" in out
            ):
                raise WorkspaceError("token inválido ou sem acesso ao repositório")
            raise WorkspaceError(f"falha ao clonar o repositório: {out.strip()[-300:]}")
        # Credencial fora do remote: o worker (e os agentes) nunca veem o token.
        await _git(dest, "remote", "set-url", "origin", _CRED.sub(r"\1", clone_url))
        return dest

    async def changed_files(self, run_id: str) -> list[dict]:
        p = self.path(run_id)
        if not (p / ".git").exists():
            return [{"path": f["path"], "status": "added"} for f in self.tree(run_id)]
        _, out = await _git(p, "status", "--porcelain", "--untracked-files=all")
        result = []
        for line in out.splitlines():
            code, name = line[:2], line[3:]
            if "?" in code or "A" in code:
                status = "added"
            elif "D" in code:
                status = "deleted"
            else:
                status = "modified"
            result.append({"path": name.strip('"'), "status": status})
        return result

    def tree(self, run_id: str) -> list[dict]:
        base = self.path(run_id)
        items = []
        for f in sorted(base.rglob("*")):
            if f.is_file() and ".git" not in f.relative_to(base).parts:
                head = f.read_bytes()[:8000]
                items.append({"path": f.relative_to(base).as_posix(), "size": f.stat().st_size,
                              "binary": b"\x00" in head})
        return items

    def read_file(self, run_id: str, rel_path: str, max_bytes: int = 1_000_000) -> dict:
        f = self._safe(run_id, rel_path)
        if not f.is_file():
            raise WorkspaceError("arquivo não encontrado")
        size = f.stat().st_size
        data = f.read_bytes()[: max_bytes + 1]
        binary = b"\x00" in data[:8000]
        too_large = size > max_bytes
        content = None if binary or too_large else data.decode("utf-8", errors="replace")
        return {
            "path": rel_path,
            "content": content,
            "binary": binary,
            "tooLarge": too_large,
            "size": size,
        }

    async def diff(self, run_id: str) -> str:
        p = self.path(run_id)
        if not (p / ".git").exists():
            return ""
        await _git(p, "add", "-A", "-N")
        _, out = await _git(p, "diff")
        return out

    def zip_bytes(self, run_id: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for item in self.tree(run_id):
                z.write(self.path(run_id) / item["path"], item["path"])
        return buf.getvalue()

    async def commit_and_push(
        self, run_id: str, clone_url: str, branch: str, message: str
    ) -> str | None:
        p = self.path(run_id)
        if not await self.changed_files(run_id):
            return None
        author = ["-c", f"user.name={settings.git_author_name}",
                  "-c", f"user.email={settings.git_author_email}"]
        await _git(p, "add", "-A")
        await _git(p, *author, "commit", "-m", message)
        candidate, n = branch, 1
        while True:
            code, _ = await _git(
                p, "ls-remote", "--exit-code", "--heads", clone_url, candidate, check=False
            )
            if code != 0:
                break
            n += 1
            candidate = f"{branch}-{n}"
        await _git(p, "push", clone_url, f"HEAD:refs/heads/{candidate}")
        return candidate

    def remove(self, run_id: str) -> None:
        shutil.rmtree(self.path(run_id), ignore_errors=True)

    def remove_many(self, run_ids: list[str]) -> None:
        for r in run_ids:
            self.remove(r)

    def purge_older_than(self, days: int) -> int:
        if not self.root.exists():
            return 0
        limit = time.time() - days * 86400
        removed = 0
        for d in self.root.iterdir():
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed
