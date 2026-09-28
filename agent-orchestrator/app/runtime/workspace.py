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
import os
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

# Variáveis de ambiente de rede/TLS que o git pode precisar (proxy corporativo,
# CA customizada) e que devem passar do processo do orchestrator para o
# subprocesso git — sem isso, clone/push/ls-remote falham silenciosamente
# atrás de um proxy ou CA privada mesmo com credenciais corretas.
_PASSTHROUGH_ENV = (
    "HTTPS_PROXY", "https_proxy",
    "HTTP_PROXY", "http_proxy",
    "NO_PROXY", "no_proxy",
    "SSL_CERT_FILE", "GIT_SSL_CAINFO",
)


# Arquivo (dentro de .git, fora do alcance do worker via tree/zip) com o SHA
# da base clonada: "há o que publicar" = árvore suja OU HEAD à frente da base.
_BASE_FILE = "agent-portal-base"


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
    for key in _PASSTHROUGH_ENV:
        value = os.environ.get(key)
        if value:
            env[key] = value
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
        # run_id vem de PipelineRun.id (UUID) em todo caminho de produção;
        # a validação aqui é defesa em profundidade contra path traversal
        # em remove()/rmtree caso algo passe um valor não confiável.
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise WorkspaceError("run_id inválido")
        return self.root / run_id

    def _safe(self, run_id: str, rel: str) -> Path:
        base = self.path(run_id)
        # Rejeita qualquer segmento do caminho que seja um symlink — mesmo
        # que o alvo resolvido caia (por acaso) dentro do workspace, nunca
        # seguimos link para ler um arquivo (mesma postura de tree()/
        # zip_bytes(), que também nunca seguem symlink).
        node = base
        for part in Path(rel).parts:
            node = node / part
            if node.is_symlink():
                raise WorkspaceError("caminho fora do workspace")
        base_resolved = base.resolve()
        target = (base / rel).resolve()
        if target != base_resolved and base_resolved not in target.parents:
            raise WorkspaceError("caminho fora do workspace")
        return target

    def create_empty(self, run_id: str) -> Path:
        p = self.path(run_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def clone(self, run_id: str, clone_url: str, base_branch: str) -> Path:
        dest = self.path(run_id)
        if dest.exists():
            raise WorkspaceError("workspace do run já existe")
        self.root.mkdir(parents=True, exist_ok=True)
        code, out = await _git(
            None, "clone", "--depth", "1", "--branch", base_branch, "--", clone_url, str(dest),
            check=False,
        )
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
        _, base_sha = await _git(dest, "rev-parse", "HEAD")
        (dest / ".git" / _BASE_FILE).write_text(base_sha.strip() + "\n")
        return dest

    async def _base_sha(self, p: Path) -> str | None:
        """SHA da base clonada (gravado no clone; fallback: upstream do branch)."""
        marker = p / ".git" / _BASE_FILE
        if marker.is_file():
            return marker.read_text().strip() or None
        code, out = await _git(p, "rev-parse", "--verify", "-q", "@{upstream}", check=False)
        return out.strip() if code == 0 and out.strip() else None

    async def changed_files(self, run_id: str) -> list[dict]:
        p = self.path(run_id)
        if not (p / ".git").exists():
            return [{"path": f["path"], "status": "added"} for f in self.tree(run_id)]
        # ``-z`` + ``core.quotePath=false``: sem isso, nomes não-ASCII saem
        # escapados em octal ("especifica\303\247\303\243o.md") e renames
        # ("a -> b") quebram o parsing por posição fixa.
        _, out = await _git(
            p, "-c", "core.quotePath=false", "status", "--porcelain", "-z",
            "--untracked-files=all",
        )
        tokens = out.split("\x00")
        result = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if not tok:
                i += 1
                continue
            code, name = tok[:2], tok[3:]
            if code[0] in ("R", "C"):
                # Rename/copy: o próximo token é o caminho ANTIGO (descartado
                # — reportamos só o caminho novo, já capturado em ``name``).
                i += 1
            if "?" in code or "A" in code:
                status = "added"
            elif "D" in code:
                status = "deleted"
            else:
                status = "modified"
            result.append({"path": name, "status": status})
            i += 1
        return result

    def _iter_files(self, run_id: str):
        """Arquivos regulares do workspace, nunca seguindo symlinks.

        Um symlink commitado (ex.: ``leak -> /proc/self/environ`` ou
        ``-> /app/.env``) poderia vazar segredos do orchestrator via
        tree()/zip_bytes() se seguido; aqui ele é ignorado por completo —
        tanto o próprio arquivo quanto qualquer diretório symlink (que
        também não é percorrido, via ``followlinks=False``).
        """
        base = self.path(run_id)
        base_resolved = base.resolve()
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirpath_p = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if d != ".git" and not (dirpath_p / d).is_symlink()
            ]
            for name in filenames:
                fp = dirpath_p / name
                if fp.is_symlink():
                    continue
                try:
                    resolved = fp.resolve()
                except OSError:
                    continue
                if resolved != base_resolved and base_resolved not in resolved.parents:
                    continue
                yield fp

    def tree(self, run_id: str) -> list[dict]:
        base = self.path(run_id)
        items = []
        for f in sorted(self._iter_files(run_id)):
            with f.open("rb") as h:
                head = h.read(8000)
            items.append({
                "path": f.relative_to(base).as_posix(),
                "size": f.stat().st_size,
                "binary": b"\x00" in head,
            })
        return items

    def read_file(self, run_id: str, rel_path: str, max_bytes: int = 1_000_000) -> dict:
        f = self._safe(run_id, rel_path)
        if not f.is_file():
            raise WorkspaceError("arquivo não encontrado")
        size = f.stat().st_size
        with f.open("rb") as h:
            data = h.read(max_bytes + 1)
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
        if not (p / ".git").exists():
            # Sem repositório git no workspace: nada a commitar/publicar.
            # Importante não rodar ``git add`` aqui — sem ``.git`` local, o
            # git subiria procurando um repositório em diretórios pai (ex.:
            # o volume compartilhado de workspaces), o que é sempre errado.
            return None
        # Spec §5.9: uma tentativa anterior pode ter commitado e falhado no
        # push/PR — a árvore fica limpa, mas o HEAD está à frente da base e
        # ainda há o que publicar. Commit só se a árvore está suja; publica
        # se HEAD != base.
        dirty = bool(await self.changed_files(run_id))
        base_sha = await self._base_sha(p)
        if dirty:
            author = ["-c", f"user.name={settings.git_author_name}",
                      "-c", f"user.email={settings.git_author_email}"]
            await _git(p, "add", "-A")
            await _git(p, *author, "commit", "-m", message)
        _, head_out = await _git(p, "rev-parse", "HEAD")
        head = head_out.strip()
        if not dirty and (base_sha is None or head == base_sha):
            return None
        candidate, n = branch, 1
        while True:
            code, out = await _git(
                p, "ls-remote", "--exit-code", "--heads", "--", clone_url, candidate,
                check=False,
            )
            if code == 0:
                remote_sha = next(
                    (
                        line.split("\t", 1)[0]
                        for line in out.splitlines()
                        if line.endswith(f"\trefs/heads/{candidate}")
                    ),
                    None,
                )
                if remote_sha == head:
                    # Já publicado por uma tentativa anterior: reaproveita.
                    return candidate
                # Branch existe com outro conteúdo: tenta o próximo sufixo.
                n += 1
                candidate = f"{branch}-{n}"
                continue
            if code == 2:
                # ``--exit-code``: 2 = nenhuma ref encontrada, candidato livre.
                break
            # Qualquer outro código (128 etc.) é falha de rede/autenticação
            # ao consultar o remoto, não "branch livre" — não dá pra saber
            # se dá pra publicar, então propaga o erro (mensagem já vem
            # escrubada de credenciais por ``_git``).
            raise WorkspaceError("não foi possível consultar o repositório remoto")
        await _git(p, "push", "--", clone_url, f"HEAD:refs/heads/{candidate}")
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
