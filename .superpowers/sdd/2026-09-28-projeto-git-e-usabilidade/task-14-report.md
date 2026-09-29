# Task 14 report — MCP tools through orchestrator

## Implementation

- Added Node.js 24 LTS, npm, and npx to the orchestrator image; the built image reports `npx 11.19.0`.
- Added `POST /internal/mcp/{server_id}/call`, authenticated with `X-Worker-Token`, scoped to the requesting owner, with sanitized errors. Public nginx explicitly rejects `/internal/`.
- MCP stdio commands use `shlex.split`, correlate JSON-RPC responses, send `notifications/initialized`, enforce call timeouts, terminate subprocess groups, and accept lines up to 8 MiB.
- The worker resolves MCP tools against the orchestrator for every dispatch, including legacy agent artifacts, gives native tools precedence on name collisions, and sends MCP calls with owner and run workspace.
- Excel paths are resolved under the per-run workspace and checked through symlinks. MCP arguments and responses are omitted from worker logs.

## Verification

- Orchestrator full suite: **619 passed**. Output included 17 existing warnings (pytest fixture loop scope, Starlette deprecation, and async cleanup warnings in executor tests).
- Worker full suite: **42 passed**. Output included the existing pytest fixture loop scope and Starlette deprecation warnings.
- Ruff check: all touched orchestrator and worker files passed. `git diff --check` passed.
- MCP coverage: authenticated echo, missing token, other-owner 404, missing command 502 with safe message, real stdio discovery, legacy snapshot dispatch, 100 KB stdio response, MCP collision handling, Excel workspace path traversal and symlink rejection, and secret-free MCP logging.
- Real Excel/Qwen validation: the registered Excel server connected and exposed six tools. An agent dispatched through the worker called `excel_read_sheet` and returned the workbook values `TASK14_REAL` and `42`. The temporary agent and run workspace were removed afterward.
- Final runtime mode: `LLM_PROVIDER=openai`, `LLM_MODEL=Qwen3.8-27B-Q8_0`.

## Review

The task review found that the default 64 KiB subprocess reader limit would reject larger Excel results and that existing agent artifacts lacked newly discovered tools. Both findings were addressed: the stdio line limit is 8 MiB with a 100 KB regression test, and each dispatch now materializes MCP refs from the owner-scoped registry. Re-review found no remaining critical or important issues.

## Fix round 1

### Changes
- **R7 (Excel branch removed):** `app/api/internal_mcp.py` no longer special-cases `@negokaz/excel-mcp-server` nor rewrites path arguments. A valid `workspaceDir` (resolved, strictly under `settings.workspaces_dir`, existing directory) becomes the stdio server's cwd; invalid/outside/root/missing -> 422 `invalid_mcp_path`; no workspace -> default cwd (no 422). Module docstring documents that stdio MCP servers are trusted code with the orchestrator's filesystem access and that relative paths land in the run workspace.
- **MCP ref resolution unified:** new `resolve_mcp_refs(db, owner_id, refs) -> (servers, warnings)` in `app/mcp/registry.py`; invalid ref or missing/foreign server is skipped with a warning. Used by `AgentService._artifact_yaml` (no more 422/404 on save) and by `resolve_pipeline_mcp()` in `app/runtime/executor.py`, called in `execute`/`resume` before the concurrency check and passed to `compile_pipeline(..., mcp_servers_by_agent=)` -> node -> `worker_client.execute(mcp_servers=...)`. `HttpWorkerClient` no longer touches the DB; it only forwards `ownerId`/`mcpServers`. DB failure during resolution logs a warning and falls back to the artifact refs (no traceback, run continues).
- `compare_digest` on bytes (non-ASCII token -> 401, not 500).
- `MCPClient.disconnect`: SIGTERM, wait 5 s, then SIGKILL to the process group unconditionally in a `finally` (also on cancellation); ProcessLookupError/PermissionError ignored.
- `MCPClient._send_jsonrpc`: skips non-JSON lines, non-dict JSON and messages carrying `method` (server notifications/requests).
- Worker: orchestrator error bodies (`{"error", "code", "details"}`) are surfaced to the LLM (`_mcp_error_message`); non-dict content items become `[unknown]`; transport errors return a pt-BR message. Reserved names for custom tools now read `definition.name` (hoisted out of the loop).
- `tests/verify_excel_mcp.py` -> `scripts/verify_excel_mcp.py` (indentation fixed, usage `python -m scripts.verify_excel_mcp`). Note: the `git mv` was staged in the shared index and got swept into Task 12's commit 460ae89; the indentation fix is in this round's commit.

### Tests added/changed
- orchestrator `tests/test_internal_mcp.py`: echo server reports `os.getcwd()` == run workspace (and default cwd without workspace); workspace outside/traversal/root/missing -> 422; non-ASCII token -> 401; hanging fixture (`tests/fixtures/hang_mcp_server.py`, ignores SIGTERM, spawns a grandchild) -> call times out and leader + grandchild are gone; cancelled disconnect still kills the group; `resolve_mcp_refs` skips deleted/invalid refs; worker client forwards `mcpServers`; run with a deleted MCP server still executes, worker gets only the surviving server, warning logged with no `exc_info`. Echo fixture now emits log noise, a non-dict JSON line, a notification and a server request with the same id before every response.
- worker `tests/test_mcp_tools.py`: pt-BR orchestrator error reaches the LLM; non-JSON error body -> generic; non-dict content items; custom-tool collision by `definition.name`.

### Commands and outputs
- Focused: `pytest tests/test_internal_mcp.py tests/test_mcp_client_mock.py tests/test_rt_executor.py tests/test_rt_worker_client.py` -> 64 passed.
- Orchestrator full suite -> **639 passed**, 17 warnings (pre-existing).
- Worker full suite -> **46 passed**, 1 warning (pre-existing).
- `ruff check` on all touched orchestrator/worker files -> All checks passed.
- Dockerfile unchanged (no rebuild). `docker compose -p squad-agentica exec -T orchestrator npx --version` -> `11.19.0`.
- Excel connection test inside the container (`test_mcp_connection_detail` with the DB row, command `npx -y @negokaz/excel-mcp-server`): `{"status": "connected", "reason": null, "tools": ["excel_copy_sheet", "excel_create_table", "excel_describe_sheets", "excel_format_range", "excel_read_sheet", "excel_write_to_sheet"]}`. Afterwards no `node`/`npx`/`excel` processes remained in the container (checked via /proc).
