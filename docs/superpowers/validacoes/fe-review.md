# fe-review — log de validação (trava contra loop infinito)

Formato: data · veredito · resumo. 4ª rejeição pelo MESMO problema (fora de segurança/perda de dados) ⇒ aprovar e registrar em PENDENCIAS.md.

- 2026-09-22 · REJEITADO (rodada 1) ·
  - CRITÉRIO 2 (rotas navegam, sem 404 interno) FALHA — **dashboard inacessível**: conflito de rota `/`. `app/page.tsx` (fe-shell, redirect→`/dashboard`) e `app/(dashboard)/page.tsx` (fe-dashboard) disputam `/`; o build manifest mostra `/(dashboard)/page` AUSENTE (shadowed). `/`→307→`/dashboard`→404. Sidebar "Dashboard" (`href="/dashboard"`) é link morto.
  - CRITÉRIO 3 (sem endpoint inventado) FALHA — fe-library: `github-integration.tsx` chama 4 endpoints inexistentes (`/api/integrations/github/status|connect|test`, `DELETE /github`) + botão "Conectar" morto (criterio 6).
  - CRITÉRIO 1 OK (tsc 0, lint limpo, vitest 355/355, build 14 rotas).
  - Backend fora do escopo FE (não bloqueia): B1 pipeline CRUD ausente (rt-executor/FASE 6), B2 login 500 com credenciais válidas (auth-backend + infra-docker, `core/errors.py` + regex e-mail).
  - Donos dos 4 nós: dashboard OK (exceto a rota), agents OK, approvals OK, library FAIL (github).
