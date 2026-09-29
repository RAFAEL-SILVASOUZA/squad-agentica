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
