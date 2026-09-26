# Handoff: fe-agents (telas de agentes)

## Arquivos criados
- `agent-portal/lib/agent-chat.ts` — cliente SSE do chat de construção (sendAgentChat, confirmAgentDraft).
- `agent-portal/lib/agent-chat.test.ts` — 7 testes.
- `agent-portal/lib/agents.ts` — helpers CRUD (getAgent, updateAgent, deleteAgent, listAgents).
- `agent-portal/components/agents/agent-preview.tsx` + `.test.tsx` — preview do draft (5 testes).
- `agent-portal/components/agents/agent-chat.tsx` + `.test.tsx` — chat SSE com cancel + 429 (6 testes).
- `agent-portal/components/agents/agent-detail.tsx` + `.test.tsx` — formulário de edição (8 testes).
- `agent-portal/components/agents/delete-agent-modal.tsx` + `.test.tsx` — modal de exclusão (4 testes).
- `agent-portal/components/agents/index.ts` — barrel.

## Arquivos alterados
- `agent-portal/app/(dashboard)/agents/new/page.tsx` — página de criação (chat + preview + salvar).
- `agent-portal/app/(dashboard)/agents/[id]/page.tsx` — página de detalhe/edição (chat + form + excluir).

## Contratos públicos expostos
- `sendAgentChat(path, message, draftId, callbacks, signal): Promise<ChatResult>` — consome POST /api/agents/chat e /api/agents/{id}/chat (SSE). Callbacks: onText, onConfigUpdate, onValidationError, onDone, onError. ChatResult: { rateLimited, retryAfter?, draftId? }.
- `confirmAgentDraft(draftId): Promise<Agent>` — POST /api/agents/chat/confirm.
- `getAgent/updateAgent/deleteAgent/listAgents` (lib/agents.ts) — GET/PUT/DELETE /api/agents/{id}, GET /api/agents.
- Componentes: AgentChat, AgentPreview, AgentDetail, DeleteAgentModal (exportados em components/agents/index.ts).

## Endpoints consumidos (todos existem no backend, verificados em agent-orchestrator/app/api/)
- POST /api/agents/chat, POST /api/agents/{id}/chat, POST /api/agents/chat/confirm (agent_chat.py).
- GET/PUT/DELETE /api/agents/{id} (agents.py).
- GET /api/skills, /api/tools, /api/mcp-servers, /api/knowledge (seletores da mochila).

## Decisões
- **SSE fora de lib/api.ts:** o stream precisa de fetch incremental + AbortController; lib/agent-chat.ts usa fetch direto e reutiliza GET /api/session-token para o token (mesmo endpoint de lib/api.ts, cache em memória).
- **429:** sendAgentChat devolve { rateLimited, retryAfter }; AgentChat desabilita o envio e mostra cooldown com contagem regressiva.
- **Cancelamento:** botão "Parar" aborta via AbortController; AbortError não dispara onError.
- **Novo agente:** "Salvar" confirma o draft (confirmAgentDraft) e navega para /agents/{id}. Botão desabilitado até haver draftId (confirmação antes de salvar).
- **Edição:** "Salvar" no AgentDetail faz PUT /api/agents/{id}. Chat de edição usa /api/agents/{id}/chat.
- **Mochila:** seletores listam o que o usuário já cadastrou (skills, tools, MCP, knowledge). Integrações: select de plataforma (azure/github/gitlab/azure-devops/email/custom) — o backend não tem endpoint de listagem de integrações do usuário, então uso plataformas fixas do tipo IntegrationRef.
- **404 no detalhe:** ApiError.status === 404 → empty state + voltar ao dashboard.
- **Exclusão:** modal próprio (DeleteAgentModal), sem window.confirm.

## Pendências / observações
- **Integrações:** não há endpoint `GET /api/integrations` para listar integrações do usuário (o router integrations.py trata Rivvn). O seletor de integrações usa plataformas fixas do tipo. Se o backend expuser listagem de integrações do usuário, o seletor pode ser alimentado por ela.
- **Canal de aprovação:** o campo "Canal de aprovação" (select) é control field real no formulário, mas o tipo Agent da API não tem campo `approvalChannel` (está em PipelineEdge). O valor é mantido em estado local e não é persistido no PUT (o AgentResponse não o carrega). Registrado para alinhamento: se o agente precisar de canal de aprovação próprio, o backend precisa adicionar o campo.
- **Navegação no browser via NGINX + login:** não verificada (Docker/Rancher Desktop desligado). Deixar para o fe-review.

## Verificação (saída real)
- `npx tsc --noEmit`: exit 0.
- `npm run lint`: No ESLint warnings or errors.
- `npx vitest run`: 28 files, 183 tests passed (inclui 27 novos testes de fe-agents).

## Merge
- Merge commit no main: `68021d0` (merge --no-ff wt/fe-agents).
- Worktree e branch removidos; junction de node_modules removida (sem /s).
