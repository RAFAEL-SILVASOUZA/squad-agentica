# Renomear "Mochila" para "Capacidades" — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Quando executar:** depois do plano `2026-09-29-redesign-usabilidade.md` (Tasks 1–18) e **antes da Task 32** do plano `2026-09-30-llm-providers-e-modelos.md`, que também edita `agent-detail.tsx`. É a Task 34, para continuar a numeração, mas pode rodar antes das Tasks 19–33 se o agente preferir.

**Goal:** Trocar o termo "Mochila" por "Capacidades" em toda a interface e no código, alinhando a UI ao vocabulário já usado na documentação (ADR-008, domínio D8 `capabilities`, "Capacidades do agente" no desenho de arquitetura).

**Architecture:** Mudança de nomenclatura, sem alteração de comportamento, de API ou de formato de YAML. Verificado em 2026-09-30: "mochila" **não** aparece como campo de API, de banco ou de YAML; só como rótulo de interface, id de aba (`?tab=mochila`), nomes internos de variáveis e comentários. Por isso não há migração.

**Tech Stack:** Next.js 14, React 18, vitest e Playwright; comentários e docstrings em Python.

**Decisão do usuário:** nome escolhido em 2026-09-30: **Capacidades**.

## Global Constraints

- Valem as restrições dos planos anteriores (pt-BR, commits com `Co-Authored-By`, nunca fazer push, `git add` só com caminhos explícitos, não tocar em `.codex/`, reiniciar o `portal` antes de verificar no navegador).
- **Termos de domínio continuam em inglês:** Skills, Tools, MCP, Knowledge. Só "Mochila" vira "Capacidades".
- **Links antigos continuam funcionando:** `?tab=mochila` deve abrir a aba Capacidades (alias), para não quebrar links salvos nem testes e2e ainda não atualizados.
- **Não reescrever documentos históricos** (handoffs, relatórios de QA, `ANALISE-ESPECIFICACAO.md`, o plano de execução de 21/09 e a revisão de design de 29/09). Eles registram o que foi dito na época. Só os documentos vigentes são atualizados.
- Não renomear identificadores que aparecem em contratos: `skills`, `tools`, `mcpServers`, `knowledge` permanecem.

## Review Focus

1. **Alias da aba.** `?tab=mochila` abre Capacidades e a URL é normalizada para `?tab=capacidades`.
2. **Nada de contrato alterado.** O diff não toca em schemas de API, modelos de banco (só o comentário), YAML de agente nem chaves de JSON.
3. **Busca residual.** Depois da mudança, `grep -ri mochila` só pode restar nos documentos históricos listados acima e no alias da aba.

---

### Task 34: Renomear Mochila para Capacidades

**Files (portal):**
- Modify: `agent-portal/components/agents/agent-detail.tsx` (id da aba `mochila` → `capacidades`, label, `SectionTitle`, `mochilaPanel` → `capacidadesPanel`, comentários das linhas ~42 e ~58, mapa de painéis ~648), `agent-portal/components/agents/agent-detail.test.tsx`
- Modify: `agent-portal/components/agents/agent-preview.tsx` (título da seção ~398, comentários ~35, ~285 e ~392), `agent-portal/components/agents/agent-preview.test.tsx`
- Modify: `agent-portal/components/dashboard/agent-card.tsx` (comentário ~42), `agent-portal/lib/agents.ts` (comentário ~54), `agent-portal/app/(dashboard)/agents/new/page.tsx` (comentários ~47, ~116, ~267)
- Modify (se referenciarem a aba ou o termo): specs e2e em `e2e/tests/`

**Files (backend, só comentários, docstrings e nomes internos):**
- Modify: `agent-orchestrator/app/agents/base.py` (~26, ~40), `agent-orchestrator/app/db/models.py` (~309), `agent-orchestrator/app/skills/loader.py` (~1, ~14, ~141, ~166, ~550), `agent-worker/app/worker.py` (~134, ~150), `agent-orchestrator/tests/test_skills_loader.py`

**Files (docs vigentes):**
- Modify: `docs/superpowers/specs/2026-09-29-redesign-usabilidade-design.md`, `docs/superpowers/plans/2026-09-29-redesign-usabilidade.md`, `docs/superpowers/plans/CONTRATO-TECNICO.md`, `docs/superpowers/plans/domains/D8-capabilities.md`, `docs/superpowers/plans/domains/D10-portal.md`, `docs/superpowers/plans/domains/D6-runtime.md`, `docs/superpowers/plans/PLANO-FRONTEND.md`, `docs/superpowers/specs/2026-09-17-agent-portal-design.md`
- **Não modificar:** `docs/superpowers/handoffs/*`, `docs/superpowers/validacoes/*`, `docs/superpowers/design/2026-09-29-revisao-de-design.md`, `docs/superpowers/plans/2026-09-21-execution-plan.md`, `ANALISE-ESPECIFICACAO.md`, `.superpowers/`.

- [ ] **Step 1: Teste do alias (falha primeiro).** No `agent-detail.test.tsx`: a aba aparece com o rótulo "Capacidades"; abrir com `?tab=capacidades` mostra o painel; abrir com `?tab=mochila` também mostra o painel e normaliza a URL para `?tab=capacidades`.
- [ ] **Step 2: Portal.** Trocar id, rótulo, título da seção, nome da variável do painel e o título da seção do preview do agente; manter o alias `mochila` no tratamento do parâmetro `tab`. Atualizar os comentários listados e os testes (`agent-detail.test.tsx`, `agent-preview.test.tsx`).
- [ ] **Step 3: Backend.** Trocar "mochila" por "capacidades" nos comentários, docstrings e textos do `base.py`, `models.py`, `skills/loader.py`, `worker.py` e `test_skills_loader.py`. Nenhuma assinatura, campo ou chave muda. Conferir com `git diff` que só há mudança de texto.
- [ ] **Step 4: Documentos vigentes.** Substituir "Mochila" por "Capacidades" e "mochila" por "capacidades" nos documentos da lista acima, revisando cada ocorrência no contexto (por exemplo "Tab Mochila" → "aba Capacidades"; frases como "mochila vazia" → "sem capacidades"). Não tocar nos documentos históricos.
- [ ] **Step 5: e2e.** Atualizar seletores e textos nas specs que mencionam a aba ou o termo (`grep -rn mochila e2e/`).
- [ ] **Step 6: Busca residual.** `grep -rni mochila` fora de `node_modules` e `.superpowers`: só podem restar o alias da aba no portal e os documentos históricos. Registrar o resultado no corpo do commit.
- [ ] **Step 7: Rodar** vitest do portal (`agents` e `dashboard`), pytest do `test_skills_loader.py`, `tsc`, lint e `ruff`. Reiniciar o `portal` e conferir a aba em `/agents/<id>?tab=capacidades` e `?tab=mochila`.
- [ ] **Step 8: Commit** — `refactor(portal): renomeia Mochila para Capacidades`
