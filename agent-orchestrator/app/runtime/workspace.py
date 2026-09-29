"""Workspace compartilhado por run: clone, alterações, diff, zip e publicação.

Dono: rt-executor (Task 5, 2026-09-28-projeto-git-e-usabilidade). O worker
escreve arquivos no workspace do run (volume compartilhado orchestrator/
worker) e o orchestrator é quem faz commit/push.

Revisão final (C1): o repositório git do run NÃO fica no workspace. O clone
usa ``--separate-git-dir`` para um diretório privado do orchestrator
(``settings.git_dirs_dir``, fora do volume compartilhado) e todo comando git
recebe ``--git-dir=<privado> --work-tree=<workspace>`` explícitos — um
``.git`` (arquivo ou diretório) plantado por um agente no workspace é
ignorado. Além disso o git roda sem config de sistema/global, sem hooks, sem
fsmonitor, e com ``<gitdir>/info/attributes`` anulando os drivers
filter/diff/merge que um ``.gitattributes`` do workspace pudesse pedir.
Assim nada que o agente escreva vira execução de código no orchestrator
(que guarda INTEGRATIONS_SECRET_KEY, credenciais do banco e os tokens).

Orchestrator e worker rodam como root mas os arquivos podem ter sido criados
por processos diferentes; ``-c safe.directory=*`` evita o erro "detected
dubious ownership in repository" do git >= 2.35.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Iterable
from pathlib import Path

from app.core.config import settings


class WorkspaceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ArchiveTooLargeError(WorkspaceError):
    """O zip do workspace passaria do limite (``ARCHIVE_MAX_BYTES``)."""


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

# Config de linha de comando aplicada a TODO git do orchestrator (C1): sem
# hooks (pre-push receberia a URL com token), sem fsmonitor, sem arquivo de
# atributos global. Config de linha de comando tem precedência sobre a do
# repositório (que, de qualquer forma, é o gitdir privado).
_HARDEN = (
    "-c", "safe.directory=*",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.untrackedCache=false",
    "-c", "protocol.ext.allow=never",
)

# ``<gitdir>/info/attributes`` tem precedência sobre qualquer .gitattributes
# do workspace: anula (estado "unspecified") filter/diff/merge — nenhum
# driver externo (clean/smudge/textconv/command) roda, e o diff continua
# detectando texto x binário pelo conteúdo.
_INFO_ATTRIBUTES = "* !filter !diff !merge\n"

# ``<gitdir>/info/exclude``: ``.git`` plantado no workspace nunca entra num
# commit; diretórios de cache/dependências comuns também não.
_INFO_EXCLUDE = ".git\nnode_modules/\n__pycache__/\n.npm/\n.cache/\n"

# Arquivo (no gitdir privado, fora do alcance do worker) com o SHA da base
# clonada: "há o que publicar" = árvore suja OU HEAD à frente da base.
_BASE_FILE = "agent-portal-base"

# Teto da listagem de arquivos (revisão final I1): workspace com dezenas de
# milhares de arquivos (node_modules) não pode travar a API/portal.
TREE_MAX_ENTRIES = 5000
# Teto do zip (soma dos tamanhos dos arquivos) — 413 archive_too_large.
ARCHIVE_MAX_BYTES = 200 * 1024 * 1024

EXPIRED_MESSAGE = "O workspace deste run expirou e foi removido"


def _scrub(text: str) -> str:
    return _CRED.sub(r"\1***@", text)


# Teto do texto de diff exposto pela API do run (Task 8, fix round 1): um
# ``git diff`` sem limite pode ter milhões de caracteres (run que reescreve
# muitos arquivos), o que travaria o cliente/DevTools ao tentar renderizar a
# resposta JSON inteira. Constante única — reaproveitada por
# ``truncate_diff`` (chamada em app/api/workspaces.py).
DIFF_MAX_CHARS = 500_000


def truncate_diff(text: str, max_chars: int = DIFF_MAX_CHARS) -> tuple[str, bool]:
    """Corta ``text`` em até ``max_chars``, sempre numa quebra de linha (nunca
    no meio de uma linha do diff). Retorna ``(texto, truncated)``."""
    if len(text) <= max_chars:
        return text, False
    cut = text.rfind("\n", 0, max_chars)
    if cut <= 0:
        # Sem quebra de linha antes do limite (linha única enorme): corta
        # mesmo assim, no limite exato.
        cut = max_chars
    return text[:cut], True


def slugify(name: str) -> str:
    """Slug ASCII curto (<=40 chars) a partir de um nome livre (ex.: nome da
    pipeline); usado tanto no nome da branch (``slugify_branch``) quanto no
    nome do arquivo de download do workspace (Task 8)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-") or "pipeline"


def slugify_branch(pipeline_name: str, run_id: str) -> str:
    return f"agent-portal/{slugify(pipeline_name)}-{run_id.replace('-', '')[:8]}"


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    # Ambiente mínimo e explícito: nada de GIT_DIR/GIT_* herdado; sem config
    # de sistema/global nem atributos de sistema (C1).
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
    }
    for key in _PASSTHROUGH_ENV:
        value = os.environ.get(key)
        if value:
            env[key] = value
    if extra:
        env.update(extra)
    return env


async def _git(
    cwd: Path | None,
    *args: str,
    check: bool = True,
    git_dir: Path | None = None,
    work_tree: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    repo_args: list[str] = []
    if git_dir is not None:
        repo_args += [f"--git-dir={git_dir}"]
    if work_tree is not None:
        repo_args += [f"--work-tree={work_tree}"]
    proc = await asyncio.create_subprocess_exec(
        "git", *_HARDEN, *repo_args, *args, cwd=str(cwd) if cwd else None,
        env=_git_env(env),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    text = _scrub(out.decode("utf-8", errors="replace"))
    if check and proc.returncode != 0:
        raise WorkspaceError(text.strip()[-500:] or f"git {args[0]} falhou")
    return proc.returncode or 0, text


def _newest_mtime(*paths: Path) -> float:
    """Maior mtime entre os diretórios e tudo dentro deles (sem seguir links)."""
    newest = 0.0
    for base in paths:
        try:
            newest = max(newest, base.lstat().st_mtime)
        except OSError:
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            for name in (*dirnames, *filenames):
                try:
                    newest = max(newest, os.lstat(os.path.join(dirpath, name)).st_mtime)
                except OSError:
                    continue
    return newest


class WorkspaceManager:
    def __init__(self, root: Path | None = None, git_root: Path | None = None) -> None:
        self.root = Path(root or settings.workspaces_dir)
        if git_root is not None:
            self.git_root = Path(git_root)
        elif root is not None:
            # Raiz explícita (testes): gitdirs num irmão, fora da raiz dos
            # workspaces — mesma separação da produção.
            self.git_root = self.root.parent / f"{self.root.name}.gitdirs"
        else:
            self.git_root = Path(settings.git_dirs_dir)

    def path(self, run_id: str) -> Path:
        # run_id vem de PipelineRun.id (UUID) em todo caminho de produção;
        # a validação aqui é defesa em profundidade contra path traversal
        # em remove()/rmtree caso algo passe um valor não confiável.
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise WorkspaceError("run_id inválido")
        return self.root / run_id

    def git_dir(self, run_id: str) -> Path:
        """Repositório git privado do run (fora do volume compartilhado)."""
        self.path(run_id)  # mesma validação do run_id
        return self.git_root / run_id

    def has_repo(self, run_id: str) -> bool:
        return (self.git_dir(run_id) / "HEAD").is_file()

    async def _rgit(
        self, run_id: str, *args: str, check: bool = True, env: dict[str, str] | None = None
    ) -> tuple[int, str]:
        """git no repositório do run: gitdir privado + work tree explícitos."""
        wt = self.path(run_id)
        return await _git(
            wt, *args, check=check, git_dir=self.git_dir(run_id), work_tree=wt, env=env
        )

    def _safe(self, run_id: str, rel: str) -> Path:
        base = self.path(run_id)
        # Rejeita qualquer segmento do caminho que seja um symlink — mesmo
        # que o alvo resolvido caia (por acaso) dentro do workspace, nunca
        # seguimos link para ler um arquivo (mesma postura de tree()/
        # zip_to_file(), que também nunca seguem symlink).
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

    def _write_info(self, run_id: str) -> None:
        info = self.git_dir(run_id) / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "attributes").write_text(_INFO_ATTRIBUTES)
        (info / "exclude").write_text(_INFO_EXCLUDE)

    async def clone(self, run_id: str, clone_url: str, base_branch: str) -> Path:
        dest = self.path(run_id)
        gd = self.git_dir(run_id)
        if dest.exists():
            raise WorkspaceError("workspace do run já existe")
        if gd.exists():
            shutil.rmtree(gd, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.git_root.mkdir(parents=True, exist_ok=True)
        code, out = await _git(
            None, "clone", "--depth", "1", "--branch", base_branch,
            f"--separate-git-dir={gd}", "--", clone_url, str(dest),
            check=False,
        )
        if code != 0:
            shutil.rmtree(dest, ignore_errors=True)
            shutil.rmtree(gd, ignore_errors=True)
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
        # O clone deixa ``<workspace>/.git`` como arquivo "gitdir: <privado>";
        # removido: o workspace não aponta para o repositório (o orchestrator
        # sempre passa --git-dir/--work-tree).
        dotgit = dest / ".git"
        if dotgit.is_file() or dotgit.is_symlink():
            dotgit.unlink()
        self._write_info(run_id)
        # Credencial fora do remote: o worker (e os agentes) nunca veem o token.
        await self._rgit(run_id, "remote", "set-url", "origin", _CRED.sub(r"\1", clone_url))
        _, base_sha = await self._rgit(run_id, "rev-parse", "HEAD")
        (gd / _BASE_FILE).write_text(base_sha.strip() + "\n")
        return dest

    def copy(self, src_run_id: str, dst_run_id: str) -> None:
        """Cópia do workspace E do gitdir privado de um run para outro (time
        travel): cada run tem o próprio repositório, nunca compartilhado."""
        src, dst = self.path(src_run_id), self.path(dst_run_id)
        shutil.copytree(src, dst, symlinks=True)
        src_gd = self.git_dir(src_run_id)
        if src_gd.is_dir():
            shutil.copytree(src_gd, self.git_dir(dst_run_id), symlinks=True)
            self._write_info(dst_run_id)

    async def _base_sha(self, run_id: str) -> str | None:
        """SHA da base clonada (gravado no clone; fallback: upstream do branch)."""
        marker = self.git_dir(run_id) / _BASE_FILE
        if marker.is_file():
            return marker.read_text().strip() or None
        code, out = await self._rgit(
            run_id, "rev-parse", "--verify", "-q", "@{upstream}", check=False
        )
        return out.strip() if code == 0 and out.strip() else None

    async def changed_files(self, run_id: str) -> list[dict]:
        if not self.has_repo(run_id):
            return [{"path": f["path"], "status": "added"} for f in self.tree(run_id)]
        # ``-z`` + ``core.quotePath=false``: sem isso, nomes não-ASCII saem
        # escapados em octal ("especifica\303\247\303\243o.md") e renames
        # ("a -> b") quebram o parsing por posição fixa.
        _, out = await self._rgit(
            run_id, "-c", "core.quotePath=false", "status", "--porcelain", "-z",
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
        tree()/zip_to_file() se seguido; aqui ele é ignorado por completo —
        tanto o próprio arquivo quanto qualquer diretório symlink (que
        também não é percorrido, via ``followlinks=False``). ``.git``
        (arquivo ou diretório) nunca é listado.
        """
        base = self.path(run_id)
        base_resolved = base.resolve()
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirpath_p = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames
                if d != ".git" and not (dirpath_p / d).is_symlink()
            )
            for name in sorted(filenames):
                if name == ".git":
                    continue
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

    def tree_limited(self, run_id: str, max_entries: int) -> tuple[list[dict], bool]:
        """Como ``tree``, mas no máximo ``max_entries`` itens; ``truncated``
        indica que havia mais arquivos."""
        base = self.path(run_id)
        paths: list[Path] = []
        truncated = False
        for f in self._iter_files(run_id):
            if len(paths) >= max_entries:
                truncated = True
                break
            paths.append(f)
        items = []
        for f in sorted(paths):
            try:
                with f.open("rb") as h:
                    head = h.read(8000)
                size = f.stat().st_size
            except OSError:
                continue
            items.append({
                "path": f.relative_to(base).as_posix(),
                "size": size,
                "binary": b"\x00" in head,
            })
        return items, truncated

    def tree(self, run_id: str) -> list[dict]:
        items, _ = self.tree_limited(run_id, 10**9)
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
        if not self.has_repo(run_id):
            return ""
        # Índice TEMPORÁRIO (cópia do índice do run): o ``add -N`` que faz
        # arquivos novos aparecerem no diff não mexe no índice real — diff e
        # publicação concorrentes não disputam o ``index.lock``.
        gd = self.git_dir(run_id)
        fd, tmp_index = tempfile.mkstemp(prefix="agent-portal-index-")
        os.close(fd)
        try:
            real_index = gd / "index"
            if real_index.is_file():
                shutil.copyfile(real_index, tmp_index)
            else:
                os.unlink(tmp_index)
            env = {"GIT_INDEX_FILE": tmp_index}
            await self._rgit(run_id, "add", "-A", "-N", env=env)
            # ``--no-color``: explícito mesmo sem tty. ``--no-ext-diff`` e
            # ``--no-textconv``: nenhum programa externo roda (C1). Arquivo
            # binário: o git detecta pelo conteúdo e imprime "Binary files
            # a/... and b/... differ" em vez do conteúdo bruto.
            _, out = await self._rgit(
                run_id, "diff", "--no-color", "--no-ext-diff", "--no-textconv", env=env
            )
            return out
        finally:
            try:
                os.unlink(tmp_index)
            except OSError:
                pass

    def zip_to_file(
        self, run_id: str, dest: Path | str, max_bytes: int = ARCHIVE_MAX_BYTES
    ) -> Path:
        """Grava o zip do workspace em ``dest`` (arquivo, não memória).

        ``ArchiveTooLargeError`` se a soma dos tamanhos passa de ``max_bytes``
        (verificado antes de comprimir qualquer coisa)."""
        base = self.path(run_id)
        files = list(self._iter_files(run_id))
        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except OSError:
                continue
            if total > max_bytes:
                raise ArchiveTooLargeError("workspace grande demais para baixar como zip")
        dest = Path(dest)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                try:
                    z.write(f, f.relative_to(base).as_posix())
                except OSError:
                    continue
        return dest

    def zip_bytes(self, run_id: str) -> bytes:
        """Zip em memória (conveniência para testes; a API usa ``zip_to_file``)."""
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            return self.zip_to_file(run_id, tmp).read_bytes()
        finally:
            os.unlink(tmp)

    async def commit_and_push(
        self, run_id: str, clone_url: str, branch: str, message: str
    ) -> str | None:
        if not self.has_repo(run_id):
            # Sem repositório git para o run: nada a commitar/publicar.
            return None
        # Spec §5.9: uma tentativa anterior pode ter commitado e falhado no
        # push/PR — a árvore fica limpa, mas o HEAD está à frente da base e
        # ainda há o que publicar. Commit só se a árvore está suja; publica
        # se HEAD != base.
        dirty = bool(await self.changed_files(run_id))
        base_sha = await self._base_sha(run_id)
        if dirty:
            author = ["-c", f"user.name={settings.git_author_name}",
                      "-c", f"user.email={settings.git_author_email}"]
            await self._rgit(run_id, "add", "-A")
            await self._rgit(run_id, *author, "commit", "--no-verify", "-m", message)
        _, head_out = await self._rgit(run_id, "rev-parse", "HEAD")
        head = head_out.strip()
        if not dirty and (base_sha is None or head == base_sha):
            return None
        candidate, n = branch, 1
        while True:
            code, out = await self._rgit(
                run_id, "ls-remote", "--exit-code", "--heads", "--", clone_url, candidate,
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
        await self._rgit(
            run_id, "push", "--no-verify", "--", clone_url, f"HEAD:refs/heads/{candidate}"
        )
        return candidate

    def remove(self, run_id: str) -> None:
        shutil.rmtree(self.path(run_id), ignore_errors=True)
        shutil.rmtree(self.git_dir(run_id), ignore_errors=True)

    def remove_many(self, run_ids: Iterable[str]) -> None:
        for r in run_ids:
            self.remove(r)

    def purge_older_than(self, days: int, active: Iterable[str] = ()) -> int:
        """Remove workspaces (e gitdirs) sem atividade há mais de ``days`` dias.

        A idade é o mtime MAIS RECENTE dentro do workspace/gitdir (não o do
        diretório raiz, que não muda quando um arquivo aninhado é editado).
        ``active``: ids de runs running/paused — nunca removidos."""
        keep = {str(a) for a in active}
        limit = time.time() - days * 86400
        removed = 0
        names: set[str] = set()
        for base in (self.root, self.git_root):
            if base.is_dir():
                names.update(d.name for d in base.iterdir() if d.is_dir())
        for name in sorted(names):
            if name in keep:
                continue
            try:
                ws, gd = self.path(name), self.git_dir(name)
            except WorkspaceError:
                continue
            if _newest_mtime(ws, gd) < limit:
                self.remove(name)
                removed += 1
        return removed
