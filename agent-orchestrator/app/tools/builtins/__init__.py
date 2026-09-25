"""Built-in tools: ferramentas basicas disponiveis em todo agente.

Dono: be-skills (FASE 4). Spec 6.3: 9 ferramentas basicas.
Shell e opt-in (Agent.shellAccess: boolean, default false).
Regras de seguranca (spec 14.1):
- Shell: diretorio restrito, blocklist de comandos, timeout 30s, sem secrets.
- Todas as demais: disponiveis por padrao, nao removiveis.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Security: Shell blocklist (spec 14.1)
# ---------------------------------------------------------------------------

SHELL_BLOCKLIST: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf $HOME",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
    "curl | sudo",
    "wget | sudo",
    "dd if=",
    "mkfs",
    "fdisk",
    "parted",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    ":(){ :|:& };:",  # fork bomb
    "chmod -R 777 /",
    "chown -R",
    "iptables",
    "systemctl stop",
    "systemctl disable",
    "service stop",
    "kill -9 1",
    "killall",
    "pkill -9",
    "crontab",
    "at -f",
    "mount",
    "umount",
    "swapoff",
    "swapon",
    "ifconfig",
    "ip link set",
    "route del",
    "arp -d",
    "nmap",
    "netcat",
    "nc -e",
    "socat",
    "telnet",
    "ssh -R",
    "scp",
    "rsync",
    "tar -xzf /dev",
    "python -c 'import os;os.system",
    "python3 -c 'import os;os.system",
    "perl -e 'system",
    "ruby -e 'system",
    "bash -i",
    "sh -i",
    "/etc/",
    ".env",
    "/proc/",
    "/sys/",
    "/dev/",
    "sudo",
    "su ",
    "doas",
    "pkexec",
    "pkexec",
    "setcap",
    "capsh",
    "useradd",
    "usermod",
    "userdel",
    "groupadd",
    "passwd",
    "shadow",
    "crontab",
    "at ",
    "batch",
    "nohup",
    "disown",
    "screen",
    "tmux",
    "docker",
    "kubectl",
    "helm",
    "terraform",
    "ansible",
    "vagrant",
    "podman",
    "nerdctl",
    "ctr",
    "runc",
    "containerd",
    "crio",
    "buildah",
    "skopeo",
    "oc",
    "minikube",
    "kind",
    "k3s",
    "rancher",
    "etcd",
    "consul",
    "vault",
    "nomad",
    "mesos",
    "kubernetes",
    "k8s",
    "openstack",
    "cloud-init",
    "cloudctl",
    "gcloud",
    "aws",
    "az",
    "aliyun",
    "tencentcloud",
    "huaweicloud",
    "ibmcloud",
    "oracle",
    "oci",
    "digitalocean",
    "doctl",
    "linode",
    "hetzner",
    "ovh",
    "scaleway",
    "upcloud",
    "vultr",
    "hetznercloud",
    "ionos",
    "hostinger",
    "namecheap",
    "godaddy",
    "bluehost",
    "siteground",
    "dreamhost",
    "a2hosting",
    "inmotion",
    "ipage",
    "newfold",
    "webhosting",
    "hostgator",
    "bluehost",
    "greengeeks",
    "hostinger",
    "siteground",
    "dreamhost",
    "a2hosting",
    "inmotion",
    "ipage",
    "newfold",
]

# Simplified blocklist: only the truly dangerous patterns (lowercase, pois
# o comando e lowercased antes do match).
SHELL_BLOCKLIST: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf $home",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
    "dd if=",
    "mkfs",
    "fdisk",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    ":(){ :|:& };:",
    "chmod -r 777 /",
    "chown -r",
    "iptables",
    "systemctl stop",
    "systemctl disable",
    "kill -9 1",
    "killall",
    "pkill -9",
    "mount",
    "umount",
    "nmap",
    "netcat",
    "nc -e",
    "socat",
    "ssh -r",
    "/etc/",
    ".env",
    "/proc/",
    "/sys/",
    "/dev/",
    "sudo",
    "su ",
    "doas",
    "pkexec",
    "setcap",
    "capsh",
    "useradd",
    "usermod",
    "userdel",
    "groupadd",
    "passwd",
    "shadow",
    "crontab",
    "docker",
    "kubectl",
    "helm",
    "terraform",
    "ansible",
    "vagrant",
    "podman",
    "nerdctl",
    "runc",
    "containerd",
    "crio",
    "buildah",
    "skopeo",
    "minikube",
    "kind",
    "k3s",
    "etcd",
    "consul",
    "vault",
    "nomad",
    "gcloud",
    "aws",
    "az ",
]


# Patterns que exigem match por regex (nao substring simples).
SHELL_BLOCKLIST_REGEX: list[str] = [
    r"curl\s+\S+\s*\|\s*(sh|bash|sudo)",
    r"wget\s+\S+\s*\|\s*(sh|bash|sudo)",
    r"rm\s+-rf\s+(/|~|\$HOME|/\*)",
]


def check_shell_command(command: str) -> str | None:
    """Valida um comando shell contra a blocklist.

    Retorna None se o comando e seguro, ou a mensagem de erro se bloqueado.
    """
    cmd_lower = command.lower().strip()

    # Verifica patterns por substring.
    for pattern in SHELL_BLOCKLIST:
        if pattern in cmd_lower:
            return f"Command blocked by security policy: contains '{pattern}'"

    # Verifica patterns por regex.
    for pattern in SHELL_BLOCKLIST_REGEX:
        if re.search(pattern, cmd_lower):
            return f"Command blocked by security policy: matches pattern '{pattern}'"

    return None


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuiltinTool:
    """Definicao de uma ferramenta basica."""

    name: str
    description: str
    input_schema: dict[str, Any]
    is_opt_in: bool = False  # True apenas para shell


BUILTIN_TOOLS: list[BuiltinTool] = [
    BuiltinTool(
        name="read_file",
        description="Le conteudo de um arquivo",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho do arquivo"},
            },
            "required": ["path"],
        },
    ),
    BuiltinTool(
        name="write_file",
        description="Cria ou sobrescreve um arquivo",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho do arquivo"},
                "content": {"type": "string", "description": "Conteudo a escrever"},
            },
            "required": ["path", "content"],
        },
    ),
    BuiltinTool(
        name="edit_file",
        description="Edita secoes de um arquivo existente",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho do arquivo"},
                "old_text": {"type": "string", "description": "Texto a substituir"},
                "new_text": {"type": "string", "description": "Texto de substituicao"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    ),
    BuiltinTool(
        name="shell",
        description="Executa comando no terminal (opt-in por agente)",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Comando a executar"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout em segundos (max 120)",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
        is_opt_in=True,
    ),
    BuiltinTool(
        name="web_search",
        description="Busca na web (DuckDuckGo)",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca"},
                "limit": {"type": "integer", "description": "Maximo de resultados", "default": 5},
            },
            "required": ["query"],
        },
    ),
    BuiltinTool(
        name="web_fetch",
        description="Busca e extrai texto de uma URL",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL a buscar"},
            },
            "required": ["url"],
        },
    ),
    BuiltinTool(
        name="glob",
        description="Lista arquivos por padrao (glob)",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Padrao glob (ex: **/*.py)"},
                "path": {"type": "string", "description": "Diretorio base (opcional)"},
            },
            "required": ["pattern"],
        },
    ),
    BuiltinTool(
        name="grep",
        description="Busca texto em arquivos (regex)",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Padrao regex"},
                "path": {"type": "string", "description": "Diretorio ou arquivo"},
                "glob": {"type": "string", "description": "Filtro de extensao (ex: *.py)"},
            },
            "required": ["pattern", "path"],
        },
    ),
    BuiltinTool(
        name="list_directory",
        description="Lista estrutura de diretorio",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Caminho do diretorio"},
                "max_depth": {
                    "type": "integer",
                    "description": "Profundidade maxima",
                    "default": 3,
                },
            },
            "required": ["path"],
        },
    ),
]


def get_builtin_tool(name: str) -> BuiltinTool | None:
    """Retorna uma ferramenta basica pelo nome."""
    for tool in BUILTIN_TOOLS:
        if tool.name == name:
            return tool
    return None


def list_builtin_tools(shell_access: bool = False) -> list[BuiltinTool]:
    """Lista ferramentas basicas disponiveis.

    Se shell_access=False (default), shell nao e incluida.
    """
    if shell_access:
        return list(BUILTIN_TOOLS)
    return [t for t in BUILTIN_TOOLS if not t.is_opt_in]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

# Diretorio de trabalho restrito (spec 14.1).
WORKSPACE_DIR = Path(os.environ.get("AGENT_WORKSPACE", "/workspace"))


async def execute_read_file(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de read_file."""
    path = Path(args["path"])
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
    if not path.exists():
        return {"error": f"File not found: {path}"}
    if not path.is_file():
        return {"error": f"Not a file: {path}"}
    try:
        content = path.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}


async def execute_write_file(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de write_file."""
    path = Path(args["path"])
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        return {"success": True, "path": str(path)}
    except Exception as e:
        return {"error": str(e)}


async def execute_edit_file(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de edit_file."""
    path = Path(args["path"])
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
    if not path.exists():
        return {"error": f"File not found: {path}"}
    try:
        content = path.read_text(encoding="utf-8")
        if args["old_text"] not in content:
            return {"error": "old_text not found in file"}
        new_content = content.replace(args["old_text"], args["new_text"], 1)
        path.write_text(new_content, encoding="utf-8")
        return {"success": True, "path": str(path)}
    except Exception as e:
        return {"error": str(e)}


async def execute_shell(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de shell com restricoes de seguranca (spec 14.1).

    - Diretorio de trabalho restrito
    - Blocklist de comandos
    - Timeout 30s (max 120s)
    - Sem acesso a variaveis de ambiente de secrets
    """
    command = args["command"]
    timeout = min(args.get("timeout", 30), 120)

    # Verifica blocklist.
    block_result = check_shell_command(command)
    if block_result:
        return {"error": block_result}

    # Executa em diretorio restrito, sem secrets no ambiente.
    safe_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(WORKSPACE_DIR),
        "LANG": "en_US.UTF-8",
    }

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKSPACE_DIR),
            env=safe_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
    except TimeoutError:
        proc.kill()
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


async def execute_web_search(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de web_search (DuckDuckGo)."""
    query = args["query"]
    limit = args.get("limit", 5)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            # Extrai resultados simples do HTML.
            results = []
            for match in re.finditer(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                resp.text,
            ):
                url, title = match.group(1), re.sub(r"<[^>]+>", "", match.group(2))
                results.append({"title": title, "url": url})
                if len(results) >= limit:
                    break
            return {"results": results}
    except Exception as e:
        return {"error": str(e)}


async def execute_web_fetch(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de web_fetch."""
    url = args["url"]
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            # Extrai texto simples (remove tags HTML).
            text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return {"content": text[:50000]}  # Limita a 50KB
    except Exception as e:
        return {"error": str(e)}


async def execute_glob(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de glob."""
    pattern = args["pattern"]
    base = Path(args.get("path", "."))
    if not base.is_absolute():
        base = WORKSPACE_DIR / base
    try:
        matches = sorted(str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file())
        return {"files": matches[:1000]}  # Limita a 1000 resultados
    except Exception as e:
        return {"error": str(e)}


async def execute_grep(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de grep."""
    pattern = args["pattern"]
    path = Path(args["path"])
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
    glob_filter = args.get("glob")
    try:
        regex = re.compile(pattern)
        matches = []
        if path.is_file():
            files = [path]
        else:
            files = [f for f in path.rglob("*") if f.is_file()]
            if glob_filter:
                files = [f for f in files if fnmatch.fnmatch(f.name, glob_filter)]

        for f in files[:100]:  # Limita a 100 arquivos
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append({"file": str(f), "line": i, "text": line.strip()[:200]})
                        if len(matches) >= 100:
                            break
            except Exception:
                continue
            if len(matches) >= 100:
                break
        return {"matches": matches}
    except Exception as e:
        return {"error": str(e)}


async def execute_list_directory(args: dict[str, Any]) -> dict[str, Any]:
    """Implementacao de list_directory."""
    path = Path(args["path"])
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
    max_depth = args.get("max_depth", 3)
    try:
        if not path.exists():
            return {"error": f"Directory not found: {path}"}
        entries = []

        def _walk(p: Path, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                for item in sorted(p.iterdir()):
                    rel = str(item.relative_to(path))
                    entries.append({"name": rel, "is_dir": item.is_dir()})
                    if item.is_dir():
                        _walk(item, depth + 1)
            except PermissionError:
                pass

        _walk(path, 1)
        return {"entries": entries[:2000]}  # Limita a 2000 entradas
    except Exception as e:
        return {"error": str(e)}


# Mapa de nome -> funcao de execucao.
TOOL_EXECUTORS: dict[str, Any] = {
    "read_file": execute_read_file,
    "write_file": execute_write_file,
    "edit_file": execute_edit_file,
    "shell": execute_shell,
    "web_search": execute_web_search,
    "web_fetch": execute_web_fetch,
    "glob": execute_glob,
    "grep": execute_grep,
    "list_directory": execute_list_directory,
}
