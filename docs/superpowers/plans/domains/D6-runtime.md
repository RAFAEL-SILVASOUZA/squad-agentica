# D6 — Runtime & Orquestração

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 5 · Execução**. Dependência: **D5** (compiler), **D8** (capacidades — para a mochila do agente no runtime).
> Base: spec (seções 5 "Fluxo de Execução", 12 ADR-001) + plano.

## Objetivo

Executar o StateGraph compilado (D5) com checkpoints no PostgreSQL (PostgresSaver), gerenciando ciclo de vida (execute/pause/resume/stop), maxIterations por agente, timeout, e expor status/logs/output em tempo real via WebSocket.

## Escopo (o que FAZ)

- `runtime/executor.py`: inicia execução do StateGraph, gerencia ciclo de vida.
- `runtime/checkpoint.py`: PostgresSaver do LangGraph, listagem, retomada.
- API de execução: `POST /pipelines/:id/execute`, `pause`, `resume`, `stop`, `GET /checkpoints`.
- maxIterations: contador por agente, aborta ciclo se excedido.
- Timeout: por agente + timeout global da pipeline.
- Monitor de execução (Portal): `PipelineMonitor.tsx`.
- WebSocket: `pipeline:status`, `pipeline:log`, `agent:output`.

## Escopo (o que NÃO FAZ)

- NÃO compila o grafo (D5 faz o compiler), NÃO implementa human-in-the-loop (D7 fornece a função do nó de aprovação; o D6 executa o grafo normalmente e o `interrupt()` é interno ao nó de aprovação).
- NÃO define o contrato do agente (D4), NÃO implementa skills/tools/MCP (D8 — consome a mochila que o D8 fornece).
- NÃO implementa notificações externas (D7).

## Dependências

- **D5:** `compile_pipeline(pipeline) -> StateGraph` + `State` TypedDict.
- **D4:** `Agent.run(inputs: dict, capabilities: AgentCapabilities) -> dict` (o nó do grafo chama isso).
- **D8:** `loader.load(agent_snapshot) -> AgentCapabilities` — o D6 (runtime) chama o loader ANTES de `Agent.run()` e passa o resultado como segundo argumento. O D6 é o caller do loader, não o D4.
- **D3:** model `Checkpoint` + router `/api/pipelines/:id/checkpoints`.

## Arquivos que OWNS

```
agent-orchestrator/
  app/runtime/executor.py       (inicia/gerencia execução)
  app/runtime/checkpoint.py     (PostgresSaver, listagem, retomada)
  app/runtime/iter_counter.py   (maxIterations por agente)
  app/runtime/timeout.py        (timeout por agente + global)
  app/api/pipelines.py          (execute, pause, resume, stop, checkpoints)
agent-portal/
  components/PipelineMonitor.tsx
  lib/websocket.ts                (D3 entrega; D6 escreve nos canais)
```

## Tarefas

### 6.1 Executor
- `executor.py`: dado um `StateGraph` compilado (D5) + snapshot da pipeline, executar com `astream`/`ainvoke`. Gerar eventos de status por nó (via callback_stream) e emitir no WebSocket `pipeline:status`.
- **Concorrência (execute):** antes de iniciar, verificar se existe `PipelineRun` com status=`'running'` para o `pipelineId`. Se sim, retornar 409 com body `{"error": "pipeline_already_running", "runId": "<id>"}`. O `thread_id` é `f'{pipelineId}:{runId}'` (runId novo por execução).
- **Carregamento de capacidades:** antes de chamar `Agent.run()`, o runtime chama `loader.load(agent_snapshot) -> AgentCapabilities` (contrato D8). O resultado é passado como segundo argumento de `Agent.run(inputs, capabilities)`.
- **Nó de aprovação:** o nó de aprovação (gerado pelo D5, função do D7) é um nó comum do grafo. O executor não trata diferentemente: quando o nó chama `interrupt()`, o LangGraph pausa o stream e salva o checkpoint. O executor detecta a pausa (stream termina sem `END`) e atualiza o status da pipeline para `paused`.
- Ciclo de vida: execute (inicia), pause (para o stream sem perder checkpoint), resume (retoma do último checkpoint), stop (encerra).
- **Stop:** cancela o run (status=`'cancelled'`), cancela aprovações pendentes, emite `pipeline:status` no WebSocket.
- Aceite: pipeline A→B→C executa de ponta a ponta emitindo status; pipeline com nó de aprovação pausa corretamente; execute sobre pipeline running retorna 409.

### 6.2 Checkpoint Manager
- `checkpoint.py`: `PostgresSaver` configurado com `DATABASE_URL`. Salvar checkpoint a cada nó. Listagem (`GET /checkpoints`) e retomada (`POST /checkpoints/:cpId/resume`).
- **thread_id:** o `thread_id` no config é `f'{pipelineId}:{runId}'` (runId novo por execução). Isso isola os checkpoints de execuções diferentes da mesma pipeline.
- **Interrupt e checkpoint:** quando o nó de aprovação (D7) chama `interrupt()`, o LangGraph salva o checkpoint automaticamente via PostgresSaver. O `thread_id` no config identifica a thread de execução. A retomada após interrupt é feita pelo D7 chamando `graph.invoke(Command(resume=response), config)` com o mesmo `thread_id` (não pelo endpoint de checkpoint resume do D6, que é para retomada manual de checkpoint).
- Aceite: checkpoint salvo no Postgres; retomada retoma do ponto; interrupt salva checkpoint automaticamente.

### 6.3 API de execução
- Preencher router: `POST /api/pipelines/:id/execute`, `pause`, `resume`, `stop`, `GET /api/pipelines/:id/checkpoints`, `POST /api/pipelines/:id/checkpoints/:cpId/resume`.
- **Concorrência (execute):** `POST /api/pipelines/:id/execute` retorna 409 se já existe um run com status `'running'` para o pipelineId. Body: `{"error": "pipeline_already_running", "runId": "<id>"}`.
- **Concorrência (edição):** `PUT /api/pipelines/:id` retorna 409 se há run `'running'`. O grafo é imutável durante a execução. O usuário deve esperar o run terminar ou stopar a pipeline.
- **Stop:** `POST /api/pipelines/:id/stop` cancela o run (status=`'cancelled'`), cancela aprovações pendentes, emite `pipeline:status` no WebSocket.
- Aceite: execute inicia, pause pausa, resume retoma, stop encerra; execute sobre pipeline running retorna 409; PUT sobre pipeline running retorna 409.

### 6.4 maxIterations
- `iter_counter.py`: contador por agente por execução. Se um agente excede `maxIterations` no ciclo, abortar a pipeline (estado failed).
- Aceite: pipeline com loop A→B→A e maxIterations baixo aborta.

### 6.5 Timeout
- `timeout.py`: timeout por agente (o nó para se demorar mais que `timeout` s) + timeout global da pipeline.
- Aceite: agente que ultrapassa timeout é encerrado; pipeline com timeout global aborta.

### 6.6 Monitor de execução (Portal)
- `PipelineMonitor.tsx`: status de cada nó (running/completed/failed/interrupted), logs em tempo real, lista de checkpoints, botão "Retomar". Consome WebSocket.
- Aceite: executar uma pipeline mostra os nós mudando de status em tempo real.

### 6.7–6.9 WebSocket
- Servir os canais `pipeline:status`, `pipeline:log`, `agent:output` do lado do backend (integrar com o WebSocket base do D3). Emitir status de nó, logs de execução, output do agente (streaming).
- Aceite: frontend recebe eventos dos 3 canais.

## Critérios de aceite (DoD)

- [ ] Pipeline simples (A→B→C) executa de ponta a ponta
- [ ] Checkpoint salvo a cada nó
- [ ] Retomada de checkpoint funciona
- [ ] maxIterations aborta loop infinito
- [ ] Timeout encerra agente que demora demais
- [ ] Monitor mostra status em tempo real via WebSocket
- [ ] Logs aparecem no monitor em tempo real

## Contratos de interface (o que entrega aos outros)

- **Para D7:** o nó de aprovação (função fornecida pelo D7, topologia gerada pelo D5) é um nó comum do grafo. O D6 executa o grafo normalmente; quando o nó de aprovação chama `interrupt()`, o LangGraph pausa o stream automaticamente (comportamento nativo). Para retomar, o D7 chama `graph.invoke(Command(resume=response), config)` diretamente. O D6 precisa garantir: (a) `thread_id` está disponível no config, (b) PostgresSaver está configurado para persistir o checkpoint no interrupt. O D6 não precisa de API especial para interrupt/resume.
- **Para D10:** `PipelineMonitor.tsx` + canais WebSocket.
- **Para D5:** consome `compile_pipeline`.

## Riscos

- **LangGraph + State complexo:** checkpoint com muitos ports precisa round-trip (save → load → resume). Testar.
- **Async + WebSocket:** FastAPI precisa de broadcaster WebSocket nativo persistente (WebSocket manager com set de conexões ativas por pipelineId).
- **maxIterations:** conta execuções totais do agente ao longo de toda a execução da pipeline (não reseta por ciclo). Implementar no iter_counter (runtime), não no compiler.
- **Concorrência:** execute sobre pipeline running e edição de grafo durante run devem retornar 409. Verificar status do run antes de aceitar execute/PUT. Lock por pipelineId no estado do run.
