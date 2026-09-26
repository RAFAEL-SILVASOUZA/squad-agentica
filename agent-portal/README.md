# Agent Portal

Portal de pipelines de agentes de IA. Next.js 14 App Router + React 18 + next-auth v4.

## Estrutura

```
app/
  layout.tsx              # Root layout (SessionProvider + ToastProvider)
  globals.css             # Tokens do design system
  page.tsx                # Redireciona para /dashboard
  (auth)/
    login/page.tsx        # Tela de login (NextAuth credentials)
    register/page.tsx     # Tela de registro
  (dashboard)/
    layout.tsx            # Layout autenticado (AppShell)
    page.tsx              # Dashboard (placeholder)
    agents/new/page.tsx   # Novo agente (placeholder)
    agents/[id]/page.tsx  # Detalhe do agente (placeholder)
    pipelines/[id]/page.tsx       # Editor de pipeline (placeholder)
    pipelines/[id]/run/page.tsx   # Monitor (placeholder)
    approvals/page.tsx    # Aprovações (placeholder)
    skills/page.tsx       # Skills (placeholder)
    tools/page.tsx        # Tools custom (placeholder)
    mcp/page.tsx          # MCP servers (placeholder)
    knowledge/page.tsx    # Knowledge (placeholder)
  api/
    auth/[...nextauth]/   # NextAuth route handler
    session-token/        # GET /api/session-token (JWT de delegação)

components/
  ui/                     # Primitives de UI (dono: fe-shell)
    button.tsx            # Botão (variantes: default, primary; tamanhos: lg, sm)
    input.tsx             # Input com label e erro
    select.tsx            # Select com label e erro
    textarea.tsx          # Textarea com label e erro
    toggle.tsx            # Toggle on/off
    badge.tsx             # Badge de status (dot + rótulo)
    card.tsx              # Card (variantes: default, stat)
    table.tsx             # Tabela genérica
    modal.tsx             # Modal (ESC fecha, clique fora fecha)
    drawer.tsx            # Drawer lateral (ESC fecha, clique fora fecha)
    tabs.tsx              # Tabs
    toast.tsx             # Toast (provider + useToast)
    empty-state.tsx       # Empty state com CTA
    skeleton.tsx          # Skeleton com shimmer
  layout/                 # Shell (dono: fe-shell)
    app-shell.tsx         # Grid topbar + sidebar + main
    app-sidebar.tsx       # Navegação (Links reais)
    app-topbar.tsx        # Logo + tema + avatar + logout + sino
    notifications-badge.tsx  # Badge de aprovações pendentes

lib/
  api.ts                  # Cliente de API (token, envelope de erro, 401, 429)
  websocket.ts            # WebSocket (conexão única, canais, reconexão)
  types.ts                # Tipos espelhando os schemas da API
```

## Como usar `lib/api.ts`

```tsx
import { api, ApiError } from "@/lib/api";

// GET
const agent = await api.get<Agent>("/api/agents/123");

// POST
const newAgent = await api.post<Agent>("/api/agents", { name: "Meu Agente" });

// PUT
await api.put<Agent>("/api/agents/123", { name: "Atualizado" });

// DELETE
await api.delete<void>("/api/agents/123");

// Lista paginada
const { items, total } = await api.list<Agent>("/api/agents", { page: 1, limit: 20 });

// Tratamento de erro
try {
  await api.post("/api/pipelines/1/execute", {});
} catch (e) {
  if (e instanceof ApiError) {
    if (e.status === 409) {
      // pipeline_already_running
    }
    if (e.status === 429 && e.retryAfter) {
      // desabilitar ação por e.retryAfter segundos
    }
  }
}
```

O token é obtido automaticamente via `GET /api/session-token` e cacheado em memória.
Em 401, o cliente invalida o token e redireciona para `/login`.

## Como usar `lib/websocket.ts`

```tsx
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import { api } from "@/lib/api";

// Obter token e conectar
const token = (await api.get<{ accessToken: string }>("/api/session-token")).accessToken;
const ws = getWebSocketClient(token);
ws.connect();

// Inscrever em canal (filtro opcional por pipelineId)
ws.on("pipeline:status", (data) => {
  console.log("Status:", data);
}, "pipeline-123");

ws.on("approval:new", (data) => {
  console.log("Nova aprovação:", data);
});

// Callback de reconexão (refazer GET REST para sincronizar)
ws.onReconnect(() => {
  // refetch GET /api/pipelines/{id} + /api/pipelines/{id}/runs
});

// Desconectar (ao desmontar)
disposeWebSocketClient();
```

Canais disponíveis: `pipeline:status`, `pipeline:log`, `agent:output`, `approval:new`, `approval:resolved`.

## Como usar `components/ui/*`

```tsx
import { Button, Input, Select, Badge, Card, EmptyState, Modal, useToast } from "@/components/ui";

// Botão
<Button variant="primary" loading={isSaving} onClick={handleSave}>
  Salvar
</Button>

// Input com erro
<Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />

// Badge de status
<Badge status="running" label="Em execução" pulse />

// Card
<Card hoverable onClick={() => router.push(`/agents/${agent.id}`)}>
  <span>{agent.name}</span>
</Card>

// Empty state
<EmptyState
  icon={Bot}
  title="Nenhum agente"
  description="Crie seu primeiro agente"
  action={<Button variant="primary" onClick={() => router.push("/agents/new")}>Criar</Button>}
/>

// Toast
const { addToast } = useToast();
addToast("success", "Agente criado!");
addToast("error", "Falha ao salvar");

// Modal
<Modal open={isOpen} onClose={() => setIsOpen(false)} title="Nova Skill">
  <Input label="Nome" />
</Modal>
```

## Como usar `components/layout/*`

O `AppShell` é aplicado automaticamente pelo `app/(dashboard)/layout.tsx`.
As páginas dentro de `(dashboard)/` não precisam importar o shell.

```tsx
// Para acessar o badge de notificações:
import { NotificationsBadge } from "@/components/layout";
<NotificationsBadge count={3} onClick={() => router.push("/approvals")} />
```

## Testes

```bash
npx vitest run          # roda todos os testes
npx vitest run lib/     # só testes de lib/
npx vitest run components/ui/  # só testes de componentes
```

## Verificação

```bash
npx tsc --noEmit        # type-check
npm run lint            # eslint
npm run build           # build de produção
```
