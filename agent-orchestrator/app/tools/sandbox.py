"""Tools custom sandbox: execucao isolada em subprocesso.

Dono: be-skills (FASE 4). Spec 6.4:
- Subprocesso isolado, sem acesso ao filesystem do host.
- Timeout configuravel (30s default, max 120s).
- Variaveis de ambiente (secrets) injetadas pelo secrets manager.
- Erros capturados e retornados como {"error": "..."}.

Risco residual da V1 (documentado):
O sandbox usa subprocesso com restricoes de ambiente e timeout, mas NAO
e uma isolacao de nivel de kernel (como gVisor ou seccomp-bpf). Um script
malicioso pode:
- Fazer chamadas de sistema que nao sao bloqueadas (ex: socket, fork).
- Acessar o filesystem fora do WORKSPACE_DIR se nao houver restricao de
  mount namespace (na V1, o container Docker ja fornece essa isolacao).
- Consumir recursos (CPU, memoria) ate o timeout.

Mitigacao na V1: o sandbox roda DENTRO do container Docker do orchestrator,
que ja tem restricoes de recursos (CPU/memory limits no docker-compose).
Na V2, considerar gVisor, seccomp-bpf ou Docker-in-Docker para isolacao
de nivel de kernel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Timeout default e maximo (spec 6.4).
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

# Diretorio de trabalho do sandbox.
SANDBOX_WORKDIR = Path(os.environ.get("SANDBOX_WORKDIR", "/tmp/sandbox"))

# Template do wrapper que executa o script do usuario.
_WRAPPER_TEMPLATE = '''
import json
import sys
import traceback

def _main():
    # Importa o modulo do usuario.
    sys.path.insert(0, {workdir!r})
    import user_script

    # Carrega os argumentos.
    with open({args_file!r}, "r") as f:
        args = json.load(f)

    # Executa a funcao execute.
    result = user_script.execute(**args)

    # Escreve o resultado.
    with open({result_file!r}, "w") as f:
        json.dump(result, f, default=str)

if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        with open({result_file!r}, "w") as f:
            json.dump({{"error": str(e), "traceback": traceback.format_exc()}}, f)
        sys.exit(1)
'''


class ToolSandbox:
    """Executa tools custom em subprocesso isolado."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = min(timeout, MAX_TIMEOUT)

    async def execute(
        self,
        script: str,
        args: dict[str, Any],
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Executa o script do usuario em subprocesso isolado.

        Args:
            script: Codigo Python da tool (deve ter funcao `execute`).
            args: Argumentos para a funcao execute.
            env: Variaveis de ambiente adicionais (secrets injetados).
            timeout: Timeout em segundos (max 120).

        Returns:
            dict com o resultado ou {"error": "..."}.
        """
        effective_timeout = min(timeout or self._timeout, MAX_TIMEOUT)

        # Cria diretorio temporario isolado.
        workdir = Path(tempfile.mkdtemp(prefix="tool_sandbox_"))
        try:
            # Escreve o script do usuario.
            script_path = workdir / "user_script.py"
            script_path.write_text(script, encoding="utf-8")

            # Escreve os argumentos.
            args_file = workdir / "args.json"
            args_file.write_text(json.dumps(args, default=str), encoding="utf-8")

            # Resultado.
            result_file = workdir / "result.json"

            # Gera o wrapper.
            wrapper_code = _WRAPPER_TEMPLATE.format(
                workdir=str(workdir),
                args_file=str(args_file),
                result_file=str(result_file),
            )
            wrapper_path = workdir / "wrapper.py"
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            # Ambiente isolado: sem acesso a secrets do host.
            safe_env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": str(workdir),
                "LANG": "en_US.UTF-8",
                "PYTHONPATH": str(workdir),
                "TMPDIR": str(workdir),
            }
            if env:
                safe_env.update(env)

            # Executa em subprocesso.
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(wrapper_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env=safe_env,
            )

            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "error": f"Tool execution timed out after {effective_timeout}s"
                }

            # Le o resultado.
            if result_file.exists():
                try:
                    result = json.loads(result_file.read_text(encoding="utf-8"))
                    return result
                except json.JSONDecodeError:
                    return {"error": "Tool returned non-JSON result"}

            # Se nao ha resultado, retorna o stderr.
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            if proc.returncode != 0:
                err = f"Tool execution failed (exit {proc.returncode}): {stderr_text[:2000]}"
                return {"error": err}

            return {"error": "Tool produced no output"}

        except Exception as e:
            logger.exception("Sandbox execution error")
            return {"error": f"Sandbox error: {str(e)}"}
        finally:
            # Limpa o diretorio temporario.
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)
