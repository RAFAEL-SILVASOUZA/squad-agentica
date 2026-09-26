# Registro de validação — fe-review-editor

## 2026-09-24 — veredito: APROVADO (1ª rodada, sem rejeição prévia)

Escopo julgado: fe-flow-editor, fe-flow-edges, fe-monitor (telas de editor de pipeline,
arestas/validação e monitor de execução).

### Verificação executada (evidência)
- `npx tsc --noEmit` → exit 0
- `npm run lint` → "No ESLint warnings or errors" (exit 0)
- `npx vitest run` → 43 files, 355 tests passed (exit 0)
- `npm run build` → exit 0 (tabela de rotas emitida; /pipelines, /pipelines/[id], /pipelines/[id]/run presentes)
- Git: 3 merges no main (7865f77 editor, f925aa1 edges, 12b6a42 monitor); sem branch wt/* pendente, sem worktree.

### Jornada end-to-end (Playwright via http://localhost)
NÃO pôde ser completada de ponta a ponta, por dois bloqueios de BACKEND fora dos três
nós julgados:
1. `POST /api/auth/login` → 500. Causa raiz: o e-mail seed do contrato (§2.4) `admin@local`
   é rejeitado pelo regex de e-mail de `LoginRequest` (auth-backend), e o handler de 422
   (`app/core/errors.py`) tenta serializar o `ctx` (ValueError) do Pydantic v2 → 500.
   Verificado no container: `admin@local → False`, `admin@example.com → True`.
2. CRUD de pipeline ausente: `POST/GET /api/pipelines`, `GET/PUT /api/pipelines/{id}` e
   `POST /api/pipelines/validate` → 404 (rota inexistente) com token válido. Só existem as
   rotas de execução (execute/pause/resume/stop/runs/checkpoints) em `pipeline_runs.py`.
   Dono: rt-executor (FASE 6) por contrato §9 + PLANO-BACKEND §F4 + D5 §5.1.

### Avaliação dos nós (independente do bloqueio de backend)
- fe-flow-editor: página trata loading / 404 / erro de carga / 409; valida local + servidor
  com fallback; bloqueia executar com erro; EdgePanel plugado via slot; desabilita em run.
- fe-flow-edges: EdgePanel (tipo, condition, dataMapping, requiresApproval, aprovação);
  validação espelha regras 1-11 com checagem de tipo de porta (dataMapping); highlight de
  erro por nó/aresta via errorIdSets; 409 em PUT tratado.
- fe-monitor: WS com os 5 canais filtrados por pipelineId; status por nó; logs em append;
  auto-scroll pausável + filtro por nó/nível; execute/pause/resume/stop; resume de
  checkpoint; 409 pipeline_already_running em toast; refaz GET ao reconectar (onReconnect→fetchAll).
- Sem endpoints inventados: as chamadas batem com spec §9.1. Sem emoji (lucide-react);
  estados vazio/loading/erro presentes; 355 testes cobrem as jornadas por componente.

### Achados NÃO bloqueantes (para fe-review / QA)
- A1 [rt-executor / backend, FORA deste escopo]: implementar `app/api/pipelines.py`
  (POST/GET/PUT /api/pipelines, GET /api/pipelines/{id}, POST /api/pipelines/validate)
  para destravar a jornada end-to-end (criar pipeline → editar → validar → executar → monitor).
- A2 [auth-backend FASE 3 + infra-docker, FORA deste escopo]: (a) aceitar e-mail sem TLD no
  `LoginRequest` (seed `admin@local`) OU (b) tornar o handler de 422 em `app/core/errors.py`
  tolerante (serializar `ctx`). Qualquer um dos dois restaura o login.

### Veredito
APROVADO: todos os critérios bloqueantes aplicáveis aos três nós passam com evidência.
Os bloqueios da jornada são de backend (documentados em A1/A2) e fora do escopo deste revisor.
