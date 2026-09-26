# Handoff — fe-review-editor (editor de pipeline + monitor)

Revisor de: **fe-flow-editor**, **fe-flow-edges**, **fe-monitor**. Veredito: **APROVADO**
(1ª rodada, sem rejeição prévia). Registro completo em `docs/superpowers/validacoes/fe-review-editor.md`.

## O que as telas fazem (estado real)

### `/pipelines` (fe-flow-editor) — `app/(dashboard)/pipelines/page.tsx`
- Lista pipelines (`GET /api/pipelines?status=&page=&limit=`), estados vazio/loading/erro, botão "Novo Pipeline" (`POST /api/pipelines` → navega pro editor).

### `/pipelines/[id]` (fe-flow-editor + fe-flow-edges) — `app/(dashboard)/pipelines/[id]/page.tsx`
- Carrega grafo (`GET /api/pipelines/{id}`) + agentes da paleta (`GET /api/agents`).
- `FlowEditor` (React Flow) com paleta de agentes, nós custom, arestas flow (sólida) / data (tracejada azul) / condição.
- Clique em aresta abre `EdgePanel` (slot `edgePanelSlot`): tipo, condition (só flow), dataMapping source→target (só data), requiresApproval, approvalChannel.
- **Validação dupla**: local síncrona (`validateGraph`, espelha as 11 regras do compiler) + assíncrona `POST /api/pipelines/validate` (debounce 400ms; fallback local se 404). Erros destacados no canvas (`errorIdSets` → borda vermelha no nó/aresta) e no painel; botão Execute bloqueado enquanto `errors.length>0`.
- **dataMapping checa tipo exato de porta** (`validateDataMapping`: sourceOutput/targetInput existem e têm tipo compatível).
- Salvar = `PUT /api/pipelines/{id}`; **409** (run em andamento) → toast, não propaga.
- Executar: salva o grafo (409 tratado) e `POST /api/pipelines/{id}/execute` (`{inputs:{}}`) → 202/200 navega `/pipelines/{id}/run`; 409 → toast "já em execução".
- Estados: loading (skeleton), 404 (empty "not found" + voltar), erro de carga (banner + Retry + voltar).
- Desabilita edição/execute quando `pipeline.status === "running"`.

### `/pipelines/[id]/run` (fe-monitor) — `app/(dashboard)/pipelines/[id]/run/page.tsx` + `components/monitor/pipeline-monitor.tsx`
- Layout duas colunas: grafo em modo leitura (status por nó) + painel com logs em tempo real + runs + checkpoints.
- **WS** (via `lib/websocket.ts`, `getWebSocketClient(token)` do `/api/session-token`), canais filtrados por `pipelineId`: `pipeline:status`, `pipeline:log`, `agent:output`, `approval:new` (→ `waiting_approval`), `approval:resolved` (→ running/failed).
- **Reconexão**: `onReconnect → fetchAll()` (refaz `GET /api/pipelines/{id}` + `/runs` + `/checkpoints`) para sincronizar.
- Logs: append na ordem, auto-scroll pausável, filtro por nó e nível.
- Ações: execute/pause/resume/stop (otimistas + reconciliam); `POST /api/pipelines/{id}/checkpoints/{cpId}/resume` para checkpoints `interrupted`/`failed`; 409 `pipeline_already_running` → toast.
- Estados: loading (skeleton), vazio (aguardando execução), 404, erro.

## Contratos públicos (rotas/chamadas reais usadas)
- REST: `GET/POST /api/pipelines`, `GET/PUT /api/pipelines/{id}`, `POST /api/pipelines/validate`, `POST /api/pipelines/{id}/execute|pause|resume|stop`, `GET /api/pipelines/{id}/runs|checkpoints`, `POST /api/pipelines/{id}/checkpoints/{cpId}/resume`, `GET /api/agents`, `GET /api/session-token`.
- WS: os 5 canais da spec §9.7 / contrato §7.
- Componentes reutilizados do fe-flow-editor pelo monitor: `components/flow/agent-node.tsx`, `components/flow/pipeline-edge.tsx` (monitor NÃO reescreve os nós/arestas).

## Comandos para subir e testar
- `docker compose up -d --build` (stack de pé).
- Frontend (host, Node 24): em `agent-portal/` → `npx tsc --noEmit`, `npm run lint`, `npx vitest run`, `npm run build`.
- Login no portal: `admin@local` / `change-me-in-prod` (seed) — **ver ressalva B1: hoje dá 500**.

## Ressalvas (não bloqueantes para estes 3 nós; são de OUTROS donos)
- **B1 [auth-backend FASE 3 + infra-docker] — login 500.** `POST /api/auth/login` retorna 500 para CREDENCIAIS VÁLIDAS. Duas causas (qualquer uma corrige):
  (a) o regex de e-mail de `LoginRequest` (`app/auth/schemas.py`) exige TLD e rejeita o seed `admin@local` (contrato §2.4);
  (b) o handler de 422 em `app/core/errors.py` serializa `exc.errors()` do Pydantic v2, cujo `ctx` é um `ValueError` não serializável → `TypeError` → 500.
- **B2 [rt-executor FASE 6] — CRUD/validate de pipeline ausente.** `POST/GET /api/pipelines`, `GET/PUT /api/pipelines/{id}` e `POST /api/pipelines/validate` → **404** (rota inexistente; verificado com token válido). Dono: `rt-executor` (contrato §9 + PLANO-BACKEND §F4 + D5 §5.1, que atribui `app/api/pipelines.py` a ele com CRUD + validação). Hoje só existem as rotas de execução em `pipeline_runs.py`.
- Consequência: **a jornada end-to-end (criar pipeline → editar → validar → executar → monitor) ainda não fecha no stack vivo** por B1+B2, ambos de backend. Os 3 nós FE estão prontos e tratados para consumi-los (com fallback/404/409) e o teste por componente (355 testes) cobre as jornadas.

## Verificação (evidência)
- `npx tsc --noEmit` → exit 0
- `npm run lint` → "No ESLint warnings or errors"
- `npx vitest run` → 43 files, 355 tests passed
- `npm run build` → exit 0 (rotas /pipelines, /pipelines/[id], /pipelines/[id]/run presentes)
- Sem emoji nas telas (apenas `→`/`─` tipográficos); ícones lucide-react; sem botão morto.
- Sem endpoint inventado: todas as chamadas batem com spec §9.1 (B2 é endpoint planejado, ainda não construído pelo backend).

## Merges no main (esta fase)
- `7865f77` fe-flow-editor, `f925aa1` fe-flow-edges, `12b6a42` fe-monitor. Sem branch `wt/*` pendente.
