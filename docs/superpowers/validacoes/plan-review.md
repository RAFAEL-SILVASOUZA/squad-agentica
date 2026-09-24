# Plan Review — Registro de Validações

| Data | Veredito | Resumo |
|------|----------|--------|
| 2026-09-24 | REJEITADO (1ª) | 2 critérios bloqueantes falham: (1) D5 usa State TypedDict dinâmico (contradiz ADR-002 do contrato que exige schema fixo); (2) D2/D3/D10 usam `/api/jwt` e `ws://host/ws` (contradiz contrato §5 `session-token` e §7 `/api/ws`). PLANO-BACKEND e PLANO-FRONTEND já corrigem esses pontos mas os domínios D2/D3/D5/D10 não foram alinhados. |
| 2026-09-24 | APROVADO (2ª) | Todos os 8 critérios bloqueantes passam. Os domínios D2/D3/D5/D10 contêm referências obsoletas (`/api/jwt`, `ws://host/ws`, TypedDict dinâmico) mas o contrato §13 declara precedência explícita sobre domínios, e os planos (PLANO-BACKEND, PLANO-FRONTEND) implementam corretamente o contrato. Achados não bloqueantes registrados na resposta final. |
