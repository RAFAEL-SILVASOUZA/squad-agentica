# QA — Projeto Git, Integrações, MCP executável e chat do Knowledge

Data: 2026-09-29. Plano `2026-09-28-projeto-git-e-usabilidade`, Task 13 (última).

## Ambiente de teste com repositório Git local

Para provar o fluxo "arquivos -> commit -> push -> Pull Request" sem GitHub real:

- **Serviço `git-test`** (`docker-compose.yml`, `profiles: ["test"]`, não sobe no `up` normal):
  - `git daemon` com os repositórios bare em `/srv/git` (volume `git-test-repos`), push liberado: `git://git-test/<dono>/<nome>.git`;
  - GitHub fake em `:8080` (`tests/integration/fake_git_api.py`, stdlib): `/user/repos`, `/repos/{o}/{r}/branches`, `POST/GET /repos/{o}/{r}/pulls` (PRs em memória, filtro por `head`) e `GET /_qa/pulls` / `POST /_qa/reset` para as asserções. Aceita só tokens `qa-token...`; os demais recebem 401.
  - Usa a imagem do orchestrator, que já tem `git-daemon` e python. A imagem `alpine/git` não traz o `git daemon`.
- **`GIT_CLONE_BASE_OVERRIDE`** (settings `git_clone_base_override`, vazio por padrão, **só para teste**): quando definido, `GitHubProvider.clone_url` devolve `<override>/<repo>.git`, sem credencial na URL. O compose agora repassa `GITHUB_API_BASE` (padrão `https://api.github.com`) e `GIT_CLONE_BASE_OVERRIDE` (padrão vazio) ao orchestrator.
- **Agente mock grava arquivo:** com `LLM_PROVIDER=mock` e um workspace de run (dentro de `WORKSPACES_DIR`), o `MockLLMClient` pede uma vez a tool `write_file` com `result.md` (as saídas do agente) e depois responde normalmente. Sem workspace de run, o comportamento não muda.

Como subir (modo de teste):

```sh
docker compose -p squad-agentica --profile test up -d git-test
GITHUB_API_BASE=http://git-test:8080 GIT_CLONE_BASE_OVERRIDE=git://git-test \
LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock \
  docker compose -p squad-agentica up -d --no-build orchestrator agent-worker
docker compose -p squad-agentica restart nginx
```

Para voltar ao normal:

```sh
docker compose -p squad-agentica up -d --no-build orchestrator agent-worker   # sem as variáveis acima
docker compose -p squad-agentica --profile test rm -sf git-test
docker compose -p squad-agentica restart nginx
```

Sem o perfil de teste, `test_09_git_project.py` e a Jornada 10 do E2E são **pulados** com o motivo.

## Testes novos

| Onde | Teste | O que prova |
|---|---|---|
| worker | `tests/test_mock_workspace_files.py` (2) | mock grava `result.md` via `write_file` só com workspace de run |
| orchestrator | `tests/test_git_providers.py` (+2) | override de clone desligado por padrão; `provider_for` o aplica |
| integração | `test_09_git_project.py::test_git_connection_test_and_repository_listing` | testar conexão (ok e token inválido sem vazar o token), repositórios e branches pelo fake |
| integração | `test_09_git_project.py::test_pipeline_writes_files_and_opens_pr` | run com repositório: clone, `result.md` na API de arquivos, branch `agent-portal/...` no remoto com o arquivo, PR aberto (head/base/corpo), token fora do PR, republicar é idempotente |
| E2E | `10-integrations.spec.ts` | pela UI: nova conexão + testar, `RepositoryPicker` no cabeçalho do editor, executar, link `PR #N` no cabeçalho do monitor, aba Arquivos do projeto com `result.md`/`README.md` e conteúdo |

TDD: o teste do worker falhou antes da mudança (`iterations 1 == 2`). O de integração falhou com o `llm.py` anterior (`'result.md' in {'README.md'}`) e passou com o novo. Os testes do override falharam antes do setting existir (`AttributeError`).

## Resultados — modo mock (perfil test ligado), 2026-09-29

| Suíte | Resultado |
|---|---|
| orchestrator (`pytest`) | **641 passed** (1ª rodada: 640 + 1 falha no próprio teste novo, que dependia do ambiente; corrigido para ler o default do `Settings`) |
| orchestrator `ruff` (arquivos tocados) | ok. `ruff check app tests` tem 20 erros **preexistentes** em arquivos não tocados (ver PENDENCIAS) |
| worker (`pytest`, `ruff`) | **48 passed**, ruff ok |
| portal `vitest` | **60 arquivos / 483 testes passed** |
| portal `tsc --noEmit` / `npm run lint` | ok / "No ESLint warnings or errors" |
| e2e `tsc --noEmit` | ok |
| integração (`tests/integration`) | **97 passed, 1 skipped** (skip conhecido `test_github_with_mocked_api`, agora coberto pelo test_09) |
| E2E (arquivo a arquivo) | 01: 7 · 02: 8 · 03: 4 · 04: 4 · 05: 3 · 06: 2 · 07: 3 · 08: 1 skipped (Jornada 8, skip conhecido) · 09: 3 · 10: 1 → **35 passed, 1 skipped** |
| `npm run build` | ok (17 rotas). Rodado com o container `portal` parado. Depois o `.next` foi apagado e o portal religado (`next dev`), porque o build e o `next dev` compartilham o `.next` do bind mount |

Observação: a integração precisa de `QA_BASE_URL=http://127.0.0.1`. Com `http://localhost`, o WebSocket leva cerca de 10 s para abrir no Windows (tenta IPv6 primeiro) e estoura o `open_timeout`. Numa rodada com `localhost` deram 14 falhas/erros, todos de WS (`TimeoutError`). Com `127.0.0.1` a suíte passou inteira.

Ao final, o stack voltou ao **modo real**: `LLM_PROVIDER`/`EMBEDDING_PROVIDER=openai`, `GITHUB_API_BASE=https://api.github.com`, override vazio e `git-test` removido. `/api/health` responde 200 e `/login` também.

## Validação real (pendente)

O passo 5 da Task 13 fica com o controlador e o usuário:

- stack no provedor real (já restaurado);
- o usuário cadastra na tela Integrações os PATs de GitHub e/ou Azure DevOps e cria um repositório de teste;
- o repositório é vinculado a um pipeline "Analista → Desenvolvedor → Revisor", que roda com o Qwen, é aprovado e é conferido no navegador:
  - aba Resultado legível;
  - arquivos na aba Arquivos;
  - PR aberto no provedor com os arquivos.
- registrar prints e resultado aqui, e as pendências em `PENDENCIAS.md`.

Resultado: _pendente_.

## Revisão final — correções (2026-09-29)

Revisão do branch inteiro ("With fixes"). Commits `b9ca9f8`, `c80d71c`, `2f5d500`, `0e0ae36`.

| Achado | Correção |
|---|---|
| **C1** agente escrevia `.git/...` no workspace e o orchestrator rodava git ali (fsmonitor, hooks, drivers = execução de código no orchestrator) | Clone com `--separate-git-dir` em `GIT_DIRS_DIR` (`/var/lib/agent-portal/gitdirs`, volume `project-gitdirs` só do orchestrator). Todo git usa `--git-dir`/`--work-tree` explícitos, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_ATTR_NOSYSTEM=1`, `core.hooksPath=/dev/null`, `core.fsmonitor=false`, `core.attributesFile=/dev/null`, `--no-ext-diff --no-textconv`, e `<gitdir>/info/attributes` = `* !filter !diff !merge` (tem precedência sobre o `.gitattributes` do workspace). `info/exclude` tira `.git`, `node_modules/`, `__pycache__/`, `.npm/`, `.cache/` do commit. O arquivo `.git` que o clone deixa no workspace é apagado. Time travel copia o gitdir; remove/purge o apagam. O worker recusa caminho com segmento `.git`. |
| **I1** I/O de disco no loop de eventos | árvore, leitura, zip e rmtree em `asyncio.to_thread`; listagem com teto de 5000 (`truncated: true`, aviso na aba Arquivos); zip gravado em arquivo temporário e enviado por `FileResponse` (apagado depois), teto de 200 MB → 413 `archive_too_large`. |
| **I2** purge ignorava o estado do run; workspace sumido virava "sem alterações" | purge pula runs `running`/`paused` (consulta no banco) e usa o mtime mais recente de workspace+gitdir; publicação sem workspace/gitdir falha com "O workspace deste run expirou e foi removido"; o worker não recria workspace de run (`/execute` → 400 `invalid_workspace`, ferramentas → erro claro). |
| **I3** excluir conexão Git deixava repositório órfão | o delete da integração zera `git_integration_id`, `git_repository` e `git_base_branch` das pipelines; `git_integration_id` nulo = publicação `none`. |
| **I4** ponte MCP só com o token dos workers | HMAC por run (`MCP_CAPABILITY_SECRET`, ou derivado de `INTEGRATIONS_SECRET_KEY`) sobre `runId\|ownerId\|workspaceDir`, emitido ao despachar o nó, repassado pelo worker; sem ele ou adulterado → 403 `mcp_capability_invalid`. |
| **I5** paginação | GitHub segue `Link: rel="next"` (só no host da API) até 10 páginas de 100; Azure segue `x-ms-continuationtoken`; o seletor sempre inclui a branch padrão. |
| Menores | toast de erro quando o execute devolve run `failed`; HOME do shell num diretório temporário fora do workspace; botão "Publicar" para run concluído com repositório e `publishStatus: none`; diff com índice temporário (sem disputa de `index.lock`) e 409 `diff_unavailable`; pipeline excluída durante a publicação não gera 500 (o endpoint responde 404 `run_not_found`); aviso no startup com `GIT_CLONE_BASE_OVERRIDE`; token ausente do gitdir e dos logs depois de clone/push por HTTP autenticado; `.env.example` e compose com as novas variáveis; `revokeObjectURL` ~1 s depois; novos códigos em `CODE_MESSAGES` e `details.message`; relatórios de processo fora do índice do git. |

**Acesso a shell dos agentes (decisão R9):** não há sandbox de shell. O toggle "Acesso a shell" no editor de agentes avisa que ele é para uso **confiável e de um único usuário**: o shell do agente roda no container do worker e enxerga o volume `/workspaces` inteiro (workspaces de outros runs). O repositório git (e o token) não ficam mais nesse volume.

Compatibilidade: workspaces criados antes desta revisão têm o `.git` dentro do workspace e não têm gitdir privado. Para o portal, eles aparecem sem repositório (lista de arquivos sem status, diff vazio, publicar → "expirou"). Os runs antigos do ambiente de desenvolvimento saem na retenção.

### Resultados — modo mock (perfil test ligado)

| Suíte | Resultado |
|---|---|
| orchestrator (`pytest`) | **671 passed** (eram 641; +30 novos) |
| orchestrator `ruff` (arquivos tocados) | ok. `ruff check app tests`: os mesmos 20 erros **preexistentes** |
| worker (`pytest`, `ruff`) | **57 passed** (eram 48), ruff ok |
| portal `vitest` / `tsc --noEmit` / `npm run lint` | **60 arquivos / 489 testes passed** / ok / sem avisos |
| integração (`tests/integration`) | **97 passed, 1 skipped** (skip conhecido). Na 1ª rodada, logo depois de recriar o orchestrator, `test_07::test_tokens_not_logged` falhou: o nginx registrou no error log a URL `/api/ws?token=...` de uma reconexão durante o restart ("Connection refused"). Não é regressão. A rodada seguinte, com o stack estável, passou inteira. |
| `test_09_git_project.py` | passou: clone, arquivos, push e PR usando o gitdir privado. Depois do run, o workspace não tem `.git` e o `config` do gitdir não contém o token. |
| E2E | 06: 2 passed · 10: 1 passed |

Testes de segurança novos (`tests/test_runtime_workspace.py`):
- um `.git` **válido** plantado no workspace, com `core.fsmonitor`, `hooksPath`, `diff.external`, textconv e filter apontando para um script que cria um marcador, mais um `.gitattributes` que pede esses drivers. Controle: um `git status` rodado dentro do workspace, como era antes, executa o script. Com o código novo, `changed_files`, `diff` e `commit_and_push` não criam o marcador, e o `.git` plantado não entra no commit;
- driver `filter`/`textconv` definido por `-c` na linha de comando: o `info/attributes` anula o pedido do `.gitattributes`. Sem esse arquivo, o driver executa (conferido à parte);
- o gitdir privado fica fora da raiz dos workspaces;
- clone e push num servidor git smart-HTTP local com Basic auth (`git http-backend`): o token não aparece em nenhum arquivo do gitdir ou do workspace, nem nos logs.

Ao final o stack voltou ao **modo real**: `LLM_PROVIDER`/`EMBEDDING_PROVIDER=openai` no orchestrator e nos 2 workers, `GITHUB_API_BASE=https://api.github.com`, override vazio e `git-test` removido. `/api/health` e `/login` respondem 200.
