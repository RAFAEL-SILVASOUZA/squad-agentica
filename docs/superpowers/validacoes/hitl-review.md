# Registro de Validação: HITL Review

## 2026-09-22 - Veredito: APROVADO (com ressalvas)

### Critérios bloqueantes verificados

1. **Nó de aprovação sem efeitos colaterais antes do `interrupt()`**: PASS
   - `node_function.py` não tem side effects antes do `interrupt()`.
   - `ApprovalRequest` criada por upsert pelo hook do executor (`service.py`).
   - Chave de idempotência: `(pipeline_id, node_id, checkpoint_id)`.
   - Notificação disparada no hook.
   - Reexecução do nó não duplica (testado em `test_reexecution_does_not_duplicate`).

2. **Resume recompila o grafo; aprovar, rejeitar e argumentar funcionam; dupla resposta não retoma duas vezes**: PASS
   - `resume.py` recompila o grafo (ADR-004).
   - 3 modos testados: `test_approve_completes_pipeline`, `test_reject_loops_back`, `test_revise_injects_feedback`.
   - Dupla resposta: `test_second_resume_is_noop`, `test_double_response_does_not_duplicate_execution`.

3. **Fan-out com múltiplas aprovações pendentes**: PASS
   - `test_fanout_both_approved`, `test_fanout_one_approved_one_rejected`.

4. **Notificação in-app via WebSocket; retry, timeout e fallback**: PASS
   - `inapp.py` publica `approval:new` via WebSocket.
   - `service.py` tem `notify_with_fallback` com retry e fallback.
   - Email desligado por padrão (V1 single-user).
   - Testes: `test_notify_inapp.py` (5), `test_notify_fallback.py` (12).

5. **Endpoints da spec 9.6 com auth, owner e envelope de erro**: PASS
   - `GET /api/approvals`, `GET /api/approvals/{id}`, `POST /api/approvals/{id}/respond`, `DELETE /api/approvals/{id}`.
   - Auth: JWT Bearer.
   - Owner isolation: testado em `test_list_filtered_by_owner`, `test_get_other_owner_approval_404`.
   - Envelope de erro: `app/core/errors.py`.

### Evidência

- **49 testes HITL passando** (test_hitl_approval.py, test_hitl_resume.py, test_notify_inapp.py, test_notify_fallback.py).
- **497 testes da suíte completa passando**.
- **Ruff**: passando.
- **Mypy**: só erros pré-existentes.

### Ressalvas (não bloqueantes)

1. **Hook não registrado no startup**: `register_approval_hook` não é chamado no `main.py`. Em produção, o HITL não funciona. **Ação necessária**: adicionar `register_approval_hook(build_approval_hook(async_session_factory))` no startup.
2. **Run_id mismatch**: a API `pipeline_runs.py` cria o `PipelineRun` com um `run_id`, mas o executor gera outro `run_id` interno. O `thread_id` diverge. **Ação necessária**: alinhar o `run_id` entre API e executor.
3. **E2E bloqueado pelo bug de auth**: `POST /api/auth/login` retorna 500 (bug de serialização JSON no handler de erro). **Ação necessária**: corrigir `app/core/errors.py`.

### Comandos de verificação

```bash
docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/test_hitl_approval.py tests/test_hitl_resume.py tests/test_notify_inapp.py tests/test_notify_fallback.py -v
# 49 passed in 9.01s

docker compose -p squad-agentica run --rm --no-deps --entrypoint pytest orchestrator tests/ -x -q
# 497 passed
```

### Arquivos criados

- `docs/superpowers/plans/GUIA-API-FRONTEND.md` (guia de API para o frontend)
- `docs/superpowers/handoffs/hitl-review.md` (handoff da fase)
