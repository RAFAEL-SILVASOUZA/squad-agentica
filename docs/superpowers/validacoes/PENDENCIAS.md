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
