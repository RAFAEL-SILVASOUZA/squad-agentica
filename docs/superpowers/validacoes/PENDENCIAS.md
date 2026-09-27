# PENDENCIAS (pendências de fase — fora do escopo dos nós FE desta revisão)

## Atualização QA Fix + QA Fix Médias e Baixas — 2026-09-27

- **B1 resolvido:** CRUD/validate de pipelines implementado e coberto por integração e E2E.
- **B2 (500) resolvido:** erro de validação serializado no envelope 422.
- **F15–F18, F20 resolvidos** no qa-fix-rest; F19 resolvido pelo qa-fix. Detalhe: `docs/superpowers/handoffs/qa-fix-rest.md`.
- **Aberto — E2E da Jornada 8 (loop até maxIterations):** o teste `e2e/tests/08-loop.spec.ts` continua `test.skip` incondicional (escrito quando F1/F6/F7 bloqueavam). O loop por rejeição é coberto pela integração (`test_05_hitl.py::test_reject_loops_back_to_source`). Risco baixo; reescrever o E2E com aprovações reais é trabalho futuro.
- **Aberto — GitHub com API fake contra o stack:** pulado na integração (exige subir o orchestrator com `GITHUB_API_BASE` de um servidor fake); a configuração é coberta por teste unitário.
- **Aberto — `next dev` no Windows não recarrega** mudanças do bind mount: após editar o portal, reiniciar o container `portal`. Só afeta desenvolvimento.
- **Ressalva — provedor real local:** em 2026-09-27 os servidores `192.168.18.4:1234` (LLM) e `:4321` (embeddings) recusaram conexão; a jornada de aceite rodou com mock. Repetir a jornada com o provedor real quando estiverem no ar (`.env` já configurado).
- **Aberto (baixa) — card de aprovação** mostra UUID da pipeline e id interno do nó (`approval_node_…`) em vez de nomes (`components/approvals/approval-panel.tsx`).
- **Aberto (baixa) — logs do monitor** emitidos antes de abrir a tela não voltam (sem endpoint de histórico de logs no contrato); o status dos nós é recomposto pelos checkpoints.
- **Aberto (baixa) — editor antes do 1º save** mostra erros de entrada indefinida (UUID nulo) que somem ao salvar.
- **Aberto (dev) — avisos de console:** tags SVG do React Flow (`defs/marker/path`) e setState durante render em `ApprovalPanel`.
- **E2E a frio:** a 1ª execução de `01-auth` após (re)start do `next dev` estoura 30s na compilação do dashboard; aquecido passa. Aquecer as rotas antes da suíte.
- **Débito de lint preexistente:** ruff acusa imports não usados em `app/approvals/resume.py`, `tests/test_hitl_resume.py` e `tests/test_pe_review_integration.py` (arquivos não tocados pelo QA).

As seções abaixo preservam o histórico da revisão de frontend.

Pendências registradas que NÃO bloqueiam os 4 nós de frontend (dashboard/agents/approvals/library)
porque não são código FE. Detalhamento completo em `docs/superpowers/handoffs/fe-review.md`.

## B1 [rt-executor / FASE 6] — Pipeline CRUD ausente no backend
Endpoints mandados pelo CONTRATO-TECNICO (linha 443, linha 503, resolução 16) que não existem em
`agent-orchestrator/app/api/` (só há o ciclo de execução em `pipeline_runs.py`):
- `GET /api/pipelines` (listagem, paginada)
- `POST /api/pipelines` (criar)
- `GET /api/pipelines/{id}` (detalhe)
- `PUT /api/pipelines/{id}` (salvar)
- `POST /api/pipelines/validate` (validação do grafo)
Impacto: editor + monitor (já aprovados) tratam 404 com fallback local; o **dashboard NÃO quebra**
porque deriva runs por aprovações pendentes + `GET /api/pipelines/{id}/runs` (que EXISTE).
Dono: rt-executor (contrato §9 + PLANO-BACKEND §F4 + D5 §5.1).

## B2 [auth-backend + infra-docker] — `POST /api/auth/login` → 500 com credenciais válidas
Seed: `admin@local` / `change-me-in-prod` (do .env). Verificado ao vivo: 500.
Causa dupla (confirmando o B2 do fe-review-editor):
1. `agent-orchestrator/app/auth/schemas.py:12` — `_EMAIL_RE = ^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$`
   exige TLD; o seed `admin@local` (sem TLD) falha a validação → 422.
2. `agent-orchestrator/app/core/errors.py:44` — `validation_error_handler` passa `{"errors": exc.errors()}`
   para `error_response` → `JSONResponse` → `json.dumps`; no Pydantic v2 o campo `ctx` do erro de
   field_validator carrega um `ValueError` (não serializável) → `TypeError: Object of type ValueError is
   not JSON serializable` → o handler quebra → FastAPI devolve 500 `internal_error`.
Correção (donos acima, qualquer um dos dois): (a) aceitar e-mails sem TLD (ou seedar com TLD, ex.
`admin@local.localhost`); e (b) serializar `exc.errors()` de forma segura
(`[{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]`, dropping `ctx`).
Impede e2e autenticado no browser; não é código FE.

## C1 [backend futuro / opcional] — Integração GitHub (se a equipe quiser)
O fe-library incluiu `GitHubIntegration` com `GET/POST /api/integrations/github/{status,connect,test}`
+ `DELETE /api/integrations/github` — endpoints que NÃO existem nem no backend nem no plano/contrato
(o PLANO-FRONTEND §fe-library manda a view-KNOWLEDGE exibir **Rivvn** desabilitado, não GitHub).
Por isso foi rejeitado no fe-library (A2). Se GitHub for realmente desejado: criar endpoints no
backend + entrada no contrato/plano, e só então reimplementar no FE. Fora do escopo desta fase.

## C2 [fe-shell] — Hydration error em todas as páginas (NÃO bloqueante — revisor já corrigiu)
`components/ui/toast.tsx` `ToastProvider` renderizava `typeof document !== "undefined" && createPortal(...)`,
que diverge do HTML do SSR e quebra a hidratação ("Hydration failed ... switch to client rendering") em TODAS as
páginas (reproduz em dev E prod). O `ToastProvider` mora no root layout (fora de qualquer Suspense boundary),
por isso o erro não é isolado pelo `<Suspense>` da página de login. **Revisor APLICOU o fix** (guard `mounted`
+ `useEffect`, mesmo padrão do `app-topbar.tsx`); tsc/lint/toast-test passam. Verificação visual em browser
pendente (chrome-devtools session caiu durante o review). Não é dos 4 nós FE.

## C3 [fe-approvals + fe-agents + fe-library] — Contraste AA dos botões de ação (BLOQUEANTE, rejeição rodada 3)
Texto BRANCO sobre superfície de estado (`var(--success)`/`var(--error)`) falha WCAG AA no tema default (dark):
branco sobre `--success` = 1.92:1 (dark) / 3.77:1 (light); sobre `--error` = 2.77:1 (dark) / 4.83:1 (light).
DESIGN-SYSTEM §5.1 lista o botão "Aprovar" (branco sobre `--success`) como mitigação obrigatória; §6 checklist
exige AA em todos os pares. Locais: [fe-approvals] `approval-panel.tsx:503`(Aprovar) e `:525`(Rejeitar);
[fe-agents] `delete-agent-modal.tsx:46`; [fe-library] botões "Excluir" em `knowledge-view.tsx:351,588`,
`mcp-servers-library.tsx:606`, `skills-library.tsx:553`, `tools-editor.tsx:634`.
**Correção preparada pelo revisor** (arquivo compartilhado `app/globals.css`): tokens `--success-strong:#047857`
e `--error-strong:#B91C1C` (branco 5.48:1 / 6.47:1, passam AA nos dois temas). Cada nó troca o
`background`/`borderColor` do botão para o token `*-strong`, mantendo texto branco e `--success`/`--error` como
token de estado (dots/bordas/badges). [fe-dashboard] sem mudança (usa `--accent`).

> **Atualização 2026-09-26 (fe-review rodada 4):** C3 RESOLVIDO (retries mergeados: `211c4f2`, `dcf4d38`, `1f2505a`; grep confirma que não há texto sobre `--success`/`--error` no portal). C2 VERIFICADO em build de produção com Chromium headless: 0 erros de hidratação em `/login` e `/register`.

## C4 [fe-agents / fe-dashboard] — Grid de agentes editado fora do mapa de donos (NÃO bloqueante)
`2b88668` (fe-agents) acrescentou busca e filtro por tipo em `app/(dashboard)/page.tsx` (dono: fe-dashboard, contrato linha 529). A mudança é aditiva e coberta por testes. Pequena melhoria de UX: montar as opções do select de tipo a partir da lista sem filtro, porque hoje, depois de filtrar, só aparece o tipo escolhido.
