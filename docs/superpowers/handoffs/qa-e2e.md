# QA E2E: relatório final (2026-09-26)

Nó `qa-e2e`, checkout principal `main`. Suíte Playwright em `e2e/` (Chromium, 1 worker, screenshot e trace nas falhas em `e2e/test-results/artifacts/`, ignorado pelo git). Stack `squad-agentica` de pé (portal em modo dev, `LLM_PROVIDER=mock`). Nenhum código de produto foi alterado. Volumes preservados: os testes usam usuários novos `qa-e2e-*` (um por worker), removidos no teardown; os usuários residuais de execuções interrompidas (`qa-e2e-*`, `qa-probe-*`) foram apagados no fim (contagem final 0). **Limitação:** "banco vazio" não foi validado (volumes existentes preservados).

F1–F20 vêm de `docs/superpowers/handoffs/qa-integration.md` e não foram reinvestigadas. Falhas novas, vistas só pela interface: E1–E15.

## Como rodar

```
cd e2e
npx tsc --noEmit -p tsconfig.json
npx playwright test tests/0X-*.spec.ts --reporter=line   # por arquivo (rate limit de login 5/min por IP)
```

## Resultado por jornada (passagem final, por arquivo)

| # | Jornada / teste | Status | Evidência |
|---|---|---|---|
| 1 | Redirect de rota protegida com callbackUrl | passou | 01-auth |
| 1 | Registro por UI entra direto | passou | 01-auth |
| 1 | Login válido, senha errada (erro genérico), validação client-side, logout | passou (4) | 01-auth |
| 1 | Registro com e-mail duplicado | **falhou E1** | `tests-01-auth-...-cria-conta-chromium-desktop/test-failed-1.png` (alerta "conflict") |
| 2 | Dashboard vazio, skills/tools/MCP/knowledge vazios com convite, aprovações vazia, /pipelines acessível, navegação da sidebar | passou (8) | 02-first-use |
| 3 | Chat de construção com provedor mock real (streaming visível) | **falhou E2** | `tests-03-create-agent-...-streaming-e-preview-.../test-failed-1.png` |
| 3 | Confirmação cria o agente e abre o detalhe (draft simulado) | passou | 03 (limitação: chat interceptado) |
| 3 | Salvar com nome já existente | **falhou E1** | toast "conflict" |
| 3 | Editar contrato (portas) e mochila (skill) e salvar | **falhou E3, E4** | `...-mochila-skill-e-salvar-.../test-failed-1.png` |
| 4a | Skill: criar (template/preview), editar, excluir | **falhou E5** (soft; jornada completa com contorno) | viewport alta para alcançar o botão |
| 4b | Tool custom: criar, testar no sandbox, deploy | **falhou E7, E8** (soft; deploy passou) | `tool-sandbox.png` |
| 4c | MCP: registrar e testar conexão com o fake | passou (connected + `qa_echo`) | `mcp-test.png` |
| 4d | Knowledge: criar base e enviar documento | **falhou E6, E9, E10** (F5 não alcançado) | `...-bucket-knowledge-ausente-.../test-failed-1.png` |
| 5 | Editor: carregar, arrastar agente, conectar, tipo data + mapeamento, aprovação, salvar | **falhou E13** (limitação F9: CRUD mockado) | payload salvo sem `requiresApproval`/tipo data |
| 5 | Validação: grafo inválido mostra erro e bloqueia Execute | passou (validate mockado, F9) | `pipeline-invalid.png` |
| 5 | Lista /pipelines com backend 404 | **falhou E12** (bloqueada por F9) | tela "No pipelines yet" em vez de erro |
| 6 | Executar, status por nó, logs, pause/resume | **bloqueada por F1/F7/F11** | run `failed` no WS; monitor segue "Executando", logs vazios; `monitor-run.png` |
| 6 | Painel do nó e filtros de log | passou | 06 |
| 7 | Aprovar: badge na sidebar, card na fila, aprovar, monitor abre | passou (aprovação semeada, F1/F6) | `approval-approved.png` |
| 7 | Rejeitar argumentando | passou (semeada) | `approval-rejected.png` |
| 7 | Aprovação respondida em outra sessão sai da fila | passou (removida em tempo real via WS) | `approval-409.png` |
| 8 | Loop por rejeição até maxIterations | **bloqueada por F1/F6/F7** (skip documentado) | 08-loop |
| 9 | Telas em 1280px: console, emoji, layout, ações | **falhou E14** (soft) | `screen-audit` anexado |
| 9 | Telas em 390px | **falhou E15** (soft) | `390-_knowledge.png` |
| 9 | Login por teclado (Tab/Enter) | passou | 09 |

Totais da passagem final: 35 testes; 22 passaram, 12 falharam (4 delas só por asserções soft que registram E#, com a jornada concluída), 1 skip (jornada 8). Nenhum erro de console além do 404 de F9; nenhum emoji encontrado.

## Falhas novas

| E# | Sev. | Passo | Esperado | Obtido | Causa provável / arquivo |
|---|---|---|---|---|---|
| E1 | média | Registro com e-mail duplicado; salvar agente com nome existente; salvar agente com porta inválida | Mensagem legível em pt-BR | Texto cru do envelope: "conflict", "validation error" | `ApiError` usa `body.error` como mensagem (`agent-portal/lib/api.ts`, `super(body.error)`); telas repassam `e.message` (`app/(auth)/register/page.tsx:88`, `app/(dashboard)/agents/new/page.tsx:96`, `components/agents/agent-detail.tsx:346`). Mapear `code` para texto. |
| E2 | alta | Chat de construção com o provedor mock real (texto puro, sem `config_update`) | Salvar desabilitado enquanto não há rascunho utilizável | Salvar habilitado com preview vazio; confirmar cria "Unnamed Agent" | `disabled={!draftId}` em `app/(dashboard)/agents/new/page.tsx:151`; backend aceita confirmar draft sem config (`/api/agents/chat/confirm`) |
| E3 | baixa | Adicionar skill na mochila | Chip com o nome da skill | Chip com o UUID | `components/agents/agent-detail.tsx:771` (`label={s.skillId}`) |
| E4 | alta | "Adicionar entrada/saída" e Salvar no detalhe do agente | Porta nova com tipo válido; PUT 200 | Tipo default `string` fora da whitelist (`artifact/code/document/signal`) -> PUT 400 `invalid_graph`; toast "validation error" | `components/agents/agent-detail.tsx:229` |
| E5 | alta | Criar skill em 1280x800 | Rodapé do modal alcançável | Modal sem `max-height`/rolagem; botão "Criar skill" em y=847 (fora da viewport, inclicável) | `components/ui/modal.tsx` (painel sem `maxHeight`/`overflow:auto`) |
| E6 | crítica | Nova base de conhecimento | Base criada | 422 `source` obrigatório; o modal mostra o JSON cru do pydantic | form em `components/library/knowledge-view.tsx` não envia `source` (backend `app/api/knowledge.py:66`) |
| E7 | média | Criar tool custom | Placeholder ensina a assinatura que o sandbox chama | Placeholder `def main(inputs)`; sandbox chama `execute(**args)` (spec usa `def execute(...)`) -> "module has no attribute 'execute'"; a UI mostra só "Erro" sem a mensagem | `components/library/tools-editor.tsx:495` e bloco de resultado do teste |
| E8 | alta | Testar tool no sandbox com input `{"data":"e2e"}` | Resultado `ok:e2e` | `ok:` (input ignorado) | UI envia `{ input }` (`components/library/tools-editor.tsx:240`); backend espera `{ args }` (`app/api/tools.py:71`) |
| E9 | crítica | Selecionar uma base na tela Knowledge | Lista de documentos | Crash "documents.map is not a function" (overlay de erro) | `GET /documents` é paginado (`{items}`), a UI espera array: `components/library/knowledge-view.tsx:117-118,415` |
| E10 | crítica | Enviar documento | Upload aceito (ou erro F5 legível) | 400 "Missing boundary in multipart"; toast de erro vazio | header `Content-Type: multipart/form-data` forçado em `components/library/knowledge-view.tsx:200-202`; toast vazio pela mesma causa de E12 |
| E11 | baixa | Editor/lista de pipelines e EdgePanel | Textos em pt-BR com acentos, como o resto do portal | Inglês ("New Pipeline", "Save", "Unsaved changes", "validation error") e pt sem acento ("Condicao", "aprovacao", "execucao") | `app/(dashboard)/pipelines/**`, `components/FlowEditor.tsx`, `components/EdgePanel.tsx` |
| E12 | alta | Abrir /pipelines com a API respondendo 404 (F9) | Banner de erro com retry | Estado vazio "No pipelines yet" (falha mascarada) | body FastAPI `{"detail"}` sem `error` -> `ApiError.message` vazio -> `setError("")` é falsy (`lib/api.ts`, `app/(dashboard)/pipelines/page.tsx:43-47`) |
| E13 | crítica | Editor: mudar aresta para `data`, mapear output->input, marcar "Requer aprovação", Salvar | Payload do PUT com tipo, mapeamento e `requiresApproval` | Arestas salvas sem nenhuma edição do EdgePanel | `FlowEditor.handleEdgeChange` (`components/FlowEditor.tsx:324`) nunca é usado; o `EdgePanel` chama o handler da página (`app/(dashboard)/pipelines/[id]/page.tsx:153`), que só altera `workEdges`; o Save serializa as arestas internas do FlowEditor |
| E14 | média | Navegação principal | Item que leve a Pipelines (PLANO-FRONTEND §fe-shell) | Nenhum link para `/pipelines`; a tela só abre por URL | `components/layout/app-sidebar.tsx` |
| E15 | baixa | /knowledge em 390px | Sem rolagem horizontal | `main` com overflow de 13px | `components/library/knowledge-view.tsx` (layout em coluna fixa) |

## Mapa jornada -> F#/E#

| Jornada | Falhas |
|---|---|
| 1 Auth | E1 |
| 2 Primeiro uso | (E14 para chegar a Pipelines) |
| 3 Agente por chat + edição | E1, E2, E3, E4 |
| 4 Biblioteca | E5, E6, E7, E8, E9, E10, F5 (não alcançado pela UI) |
| 5 Editor de pipeline | F9 (CRUD mockado), E11, E12, E13 |
| 6 Execução e monitor | F1, F7, F10, F11, F14 |
| 7 Aprovações | F1, F6 (aprovações semeadas) |
| 8 Loop maxIterations | F1, F6, F7 (bloqueada) |
| 9 Transversal | E11, E14, E15 |

## Limitações de harness (não são aprovação da jornada integrada)

- CRUD/validate de pipeline interceptados (`e2e/helpers/pipeline-mock.ts`) por F9; execução, pause/resume, runs e aprovações usam o backend real.
- Aprovações semeadas no banco (`e2e/tools/db.py`) por F1/F6: aprovar/rejeitar não comprova o resume do LangGraph.
- Chat de construção interceptado nos testes de confirmação/edição; o provedor mock real só produz texto puro (ver E2).
- Knowledge: base criada pela API para seguir após E6; `GET /documents` desembrulhado pela suíte após registrar E9.
- Pause/resume pela UI não foi exercitado: o run falha antes (F1). O monitor não reflete o `failed` recebido pelo WS (consistente com F7).
- Rate limit de login (5/min por IP) exige rodar por arquivo; o NextAuth mascara 429 como 401 (o helper faz um cooldown).
