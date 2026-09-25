"""Human-in-the-Loop: nó de aprovação, ApprovalRequest e API de aprovações.

Dono: hitl-approval (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md (ADR-006, ADR-009, §7, §8, §9 FASE 7)
- D7-human-in-the-loop.md
- Spec 4.5 (ApprovalRequest), 5.3 (HITL), 9.6 (Aprovações), 9.7 (WebSocket)

Arquivos:
- node_function.py: função do nó de aprovação (interrupt + roteamento).
- service.py: upsert idempotente da ApprovalRequest + hook do executor.
- api/approvals.py: GET /api/approvals, detalhe, POST respond.

`resume.py` é do nó hitl-resume (FASE 7, em paralelo).
"""
