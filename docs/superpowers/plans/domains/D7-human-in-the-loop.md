# D7 — Human-in-the-Loop & Notificações

> Brief para worker. Autocontido: não precisa ler os outros domínios.
> Domínio: **FASE 6 · Humano no Loop**. Dependência: **D5** (compiler gera a topologia do nó de aprovação), **D6** (runtime executa o grafo).
> Base: spec (seção 5.3 "Human-in-the-Loop", 4.5 "Notificação/Aprovação", 9.6 "Aprovações", 9.7 WebSocket) + plano.

## Objetivo

Fornecer a **função do nó de aprovação** que o compiler (D5) insere no StateGraph para cada edge com `requiresApproval: true`. O nó de aprovação chama `interrupt()` do LangGraph para pausar a execução, persiste o `ApprovalRequest` (pós-interrupt, com idempotência), envia notificação, e ao retomar roteia via `Command(goto=...)`.

## Modelo (semântica do LangGraph `interrupt()`)

O `interrupt()` é um primitivo de **nó**: só pode ser chamado dentro de uma função de nó. O nó de aprovação é um nó real do StateGraph, gerado pelo compiler (D5). O D7 fornece a implementação da função que roda dentro desse nó.

### Fluxo do nó de aprovação

```
1. GRAFO CHEGA NO NÓ DE APROVAÇÃO
   │
   ├── Monta payload: output do agente source, contexto, artefatos, canal
   │
   ├── Chama interrupt(payload)
   │   └── LangGraph pausa a execução, salva checkpoint
   │
   │   [PAUSA: o nó está "congelado" no interrupt()]
   │
   │   ... tempo passa, humano responde via API ...
   │
   ├── Retomada: interrupt() retorna a resposta armazenada
   │   (o nó re-executa do início; o interrupt() agora retorna em vez de pausar)
   │
   ├── Persiste ApprovalRequest (upsert, chave: pipelineId + nodeId + checkpointId)
   │   └── Idempotente: re-execuções não criam duplicatas
   │
   ├── Envia notificação (canal configurado)
   │
   └── Retorna Command(goto="proceed") ou Command(goto="reject_handler")
       ├── "proceed" → target da edge original
       └── "reject_handler" → source (loop) ou END
```

### Idempotência

O LangGraph re-executa o nó inteiro ao retomar (não retoma da linha do interrupt). Qualquer código antes do `interrupt()` roda de novo. Regras:

- **Persistência do ApprovalRequest:** acontece APÓS o `interrupt()` (no bloco de retomada). Usa **upsert** com chave `(pipelineId, nodeId, checkpointId)` para garantir que re-execuções não criem duplicatas.
- **Notificação:** enviada APÓS a persistência (pós-interrupt). Se o nó re-executa, o upsert detecta que já existe e não reenvia (verificar `status == "pending"` antes de notificar).
- **Efeitos colaterais antes do interrupt:** apenas montagem do payload (operacional pura, sem side effects).

### Multi-interrupt (fan-out)

Se um fan-out gera múltiplos nós de aprovação em paralelo (ex: A → [B aprova, C aprova]), cada nó tem seu próprio `interrupt_id` (gerado pelo LangGraph). A retomada usa um mapa:

```python
Command(resume={"interrupt_id_1": response1, "interrupt_id_2": response2})
```

O endpoint `POST /api/approvals/:id/respond` aceita um mapa de respostas quando há múltiplos interrupts pendentes no mesmo superstep. O D7 gerencia o estado de "aguardando N respostas" e só chama `graph.invoke(Command(resume=...))` quando todas as respostas do superstep estão presentes.

## Escopo (o que FAZ)

- `approvals/node_function.py`: a função do nó de aprovação (chama `interrupt()`, persiste, notifica, roteia).
- `ApprovalRequest`: criação (upsert), persistência, listagem, resposta.
- API de aprovações: `GET /api/approvals` (listar com filtro de status), `POST /api/approvals/:id/respond`, `DELETE /api/approvals/:id` (cancelar pendente).
- Retomada: após resposta humana, chamar `graph.invoke(Command(resume=response), config)`.
- Notificação in-app: WebSocket push → badge + tela de aprovação.
- Notificação email: template com link para o portal (SMTP).
- Retry + fallback: canal principal falha → tenta fallback.
- Painel de aprovações (Portal): `ApprovalPanel.tsx`.
- WebSocket: `approval:new`, `approval:resolved`.

## Escopo (o que NÃO FAZ)

- NÃO executa o grafo (D6), NÃO gera a topologia do nó de aprovação (D5 faz o compiler), NÃO implementa notificações Teams/Slack (V2+).
- NÃO define o contrato do agente (D4).
- NÃO implementa OAuth de plataformas externas (D9/D8).

## Dependências

- **D5:** o compiler gera o nó de aprovação na topologia do StateGraph. O D7 fornece a função que o compiler registra no nó. Contrato: D5 importa `approval_node_function` do D7 e chama `graph.add_node(name, approval_node_function)`.
- **D6:** o runtime executa o grafo. Quando o nó de aprovação chama `interrupt()`, o D6 pausa o stream. O D7 chama `graph.invoke(Command(resume=response), config)` para retomar. O D6 não precisa "expor um ponto de interrupt"; o interrupt é interno ao nó.
- **D3:** model `ApprovalRequest` + router `/api/approvals` (stub) + tipo `ApprovalRequest` em `types.ts`.
- **D2:** `get_current_user` pra autenticar a resposta da aprovação.

## Arquivos que OWNS

```
agent-orchestrator/
  app/approvals/
    node_function.py              (função do nó de aprovação: interrupt + persist + notificar + rotear)
    service.py                    (cria, lista, responde ApprovalRequest; upsert idempotente)
    resume.py                     (chama graph.invoke(Command(resume=...)) após resposta)
    notifications/
      base.py
      inapp.py                    (WebSocket push)
      email.py                    (SMTP)
  app/api/approvals.py            (GET list, POST respond)
agent-portal/
  components/ApprovalPanel.tsx
```

## Tarefas

### 7.1 Função do nó de aprovação
- `approvals/node_function.py`: implementar a função que roda dentro do nó de aprovação gerado pelo compiler.
- **Primeira execução:** montar payload (output do agente source, contexto, artefatos, canal), chamar `interrupt(payload)`. O LangGraph pausa.
- **Retomada:** `interrupt()` retorna a resposta. Persistir `ApprovalRequest` (upsert). Enviar notificação (se ainda pending). Retornar `Command(goto="proceed")` ou `Command(goto="reject_handler")`.
- O nó recebe como parâmetro (via closure ou config) o `edgeId`, `sourceAgentId`, `targetAgentId`, `approvalChannel`, `approvalMessage`.
- Aceite: pipeline com edge `requiresApproval: true` pausa no nó de aprovação; após resposta, retoma e roteia corretamente.

### 7.2 ApprovalRequest (service)
- `approvals/service.py`: criar `ApprovalRequest` com **upsert** (chave: `pipelineId + nodeId + checkpointId`). Se já existe com status `pending`, não recriar. Listar pendentes. Atualizar status ao responder.
- Aceite: re-execução do nó não cria duplicatas; primeira execução persiste com contexto.

### 7.3 API de aprovações
- Preencher router: `GET /api/approvals` (listar, query: `?status=pending|resolved|cancelled`, `?pipelineId=`, `?page=`), `POST /api/approvals/:id/respond` (status: approved | rejected | revised + response), `DELETE /api/approvals/:id` (cancelar aprovação pendente, 404 se já respondida).
- Para multi-interrupt: o endpoint aceita um mapa `{interruptId: response}` quando há múltiplos pendentes no mesmo superstep.
- **Regra:** Ao receber stop da pipeline (`POST /api/pipelines/:id/stop`), cancelar todas as aprovações pendentes daquela pipeline (`status='cancelled'`).
- Aceite: listar por status (pendentes, resolvidas, canceladas); responder aprova/rejeita/revisa; cancelar pendente; multi-interrupt aceita mapa de respostas; stop cancela pendentes.

### 7.4 Retomada (resume)
- `approvals/resume.py`: após persistir a resposta, chamar `graph.invoke(Command(resume=response), config)` com o `thread_id` correto.
- Para multi-interrupt: só chamar `graph.invoke` quando todas as respostas do superstep estão presentes. Usar `Command(resume={id1: resp1, id2: resp2})`.
- Aceite: resposta humana retoma a execução; multi-interrupt retoma quando todas as respostas chegam.

### 7.5 Notificação in-app
- `notifications/inapp.py`: após persistir ApprovalRequest (pós-interrupt), emitir `approval:new` via WebSocket pro portal (badge + notificação). Ao responder, emitir `approval:resolved`.
- Aceite: portal recebe `approval:new` em tempo real quando uma aprovação é criada.

### 7.6 Notificação email
- `notifications/email.py`: template com link para o portal (botão aprovar/rejeitar). SMTP via env (`SMTP_*`). Na V1: email + in-app.
- Aceite: email enviado com link funcional (mock SMTP em dev).

### 7.7 Retry + fallback
- Se canal principal falha, tentar `fallbackChannel` até `maxRetries`. `retryCount`/`attemptedChannels` no ApprovalRequest.
- Aceite: canal principal simulado como falho → fallback é tentado.

### 7.8 Painel de aprovações (Portal)
- `ApprovalPanel.tsx`: lista de aprovações pendentes (via WebSocket + API), botões aprovar/rejeitar/argumentar (este último injeta `response` como feedback). Badge de notificação.
- Aceite: ver pendentes, responder, painel atualiza.

### 7.9 WebSocket
- Servir `approval:new` e `approval:resolved` (integrar com WebSocket base do D3).
- Aceite: frontend recebe os 2 canais.

## Critérios de aceite (DoD)

- [ ] Nó de aprovação pausa a execução via `interrupt()`
- [ ] ApprovalRequest persistido com upsert (idempotente, sem duplicatas)
- [ ] Notificação in-app chega via WebSocket (pós-persistência)
- [ ] Notificação email é enviada (pós-persistência)
- [ ] Humano aprova → `Command(goto="proceed")` → execução retoma para o target
- [ ] Humano rejeita → `Command(goto="reject_handler")` → execução devolve ou encerra
- [ ] Humano argumenta → feedback no State + `Command(goto="proceed")` → agente target retoma com a informação
- [ ] Multi-interrupt: fan-out com 2 nós de aprovação retoma com `Command(resume={id1: r1, id2: r2})`
- [ ] Retry funciona: canal principal falha → fallback é tentado
- [ ] Painel de aprovações mostra pendentes e permite responder

## Contratos de interface (o que entrega aos outros)

- **Para D5 (compiler):** D7 exporta `approval_node_function` (ou uma factory `create_approval_node(edge_config) -> Callable`). O compiler importa e registra no StateGraph via `graph.add_node(name, fn)`. O compiler não precisa saber o que a função faz internamente.
- **Para D6 (runtime):** o nó de aprovação é um nó comum do grafo. O D6 executa o grafo normalmente; quando o nó chama `interrupt()`, o D6 pausa o stream (comportamento nativo do LangGraph). Para retomar, o D7 chama `graph.invoke(Command(resume=response), config)` diretamente (o D6 não precisa de API especial para isso). O D6 precisa apenas garantir que o `thread_id` está disponível e que o PostgresSaver está configurado.
- **Para D10:** `ApprovalPanel.tsx` + canais `approval:new`/`approval:resolved`.

## Riscos

- **Retomada após interrupt:** o LangGraph re-executa o nó inteiro. Se houver side effects antes do `interrupt()`, eles repetem. Mitigação: persistência e notificação são pós-interrupt + upsert idempotente. Testar o ciclo completo pausa→resposta→retomada→re-execução do nó.
- **Multi-interrupt:** fan-out com múltiplos nós de aprovação gera N interrupts no mesmo superstep. O D7 precisa trackear quais interrupts estão pendentes e só retomar quando todos tiverem resposta. Testar com fan-out de 2 e 3 branches.
- **Email na V1:** SMTP real pode não estar configurado. Mock em dev, mas deixar o chamador real presente.
- **Fallback travar pipeline:** timeout global (D6) é a rede de segurança. Se o humano não responde, o timeout encerra a pipeline.
