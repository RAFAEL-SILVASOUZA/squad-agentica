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
