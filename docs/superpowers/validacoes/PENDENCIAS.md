# PENDENCIAS (pendências de fase — fora do escopo dos nós FE desta revisão)

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
