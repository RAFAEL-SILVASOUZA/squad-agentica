# Design System — Agent Portal

> **Nível:** especificação visual que os nós de frontend implementam à risca. Não é uma sugestão de estética, é a transcrição do protótipo.
> **Autor:** Design System.
> **Fonte de verdade:** `prototype/agent-portal.html` (lido na íntegra). Cada token, cor, raio, sombra e medida abaixo foi extraído literalmente do bloco `:root`, dos temas `[data-theme]` e dos seletores do protótipo.
> **Leiam antes:** `CONTRATO-TECNICO.md` (precedência 1), `PLANO-FRONTEND.md`, `D10-portal.md`.
> **Stack (contrato):** CSS puro com CSS variables. **Sem Tailwind.** Next.js 14 App Router, React 18, `lucide-react`, sem emojis.

---

## Como usar este documento

1. **Tokens → `app/globals.css`.** A Seção 1 entrega o bloco CSS pronto. O `fe-shell` é o dono de `app/globals.css`; cola este bloco lá (com os nomes de variável exatos). Os `components/ui/*` consomem `var(--...)`, nunca cores soltas.
2. **Componentes → `components/ui/*` e `components/layout/*`.** A Seção 2 descreve anatomia, variantes, estados e medidas. Os nós de tela **não** recriam estes componentes; consomem os primitives.
3. **Ícones → `lucide-react`.** A Seção 4 mapeia cada ícone inline do protótipo para o componente lucide equivalente. Sem emojis.
4. **Fidelidade → Seção 6.** O `fe-review` usa este checklist para aprovar ou rejeitar telas.

> **Regra de ouro:** se o protótipo disser uma coisa, o protótipo manda. Onde o protótipo for ambíguo, escolhi a variante mais frequente e registrei a decisão na Seção 7.

---

## 1. Tokens

### 1.1 Cores

O protótipo define **uma raiz** (`:root`) com o accent e metadesign, e **dois temas** (`[data-theme="dark"]` e `[data-theme="light"]`) com o palette completo. Tema é controlado pelo atributo `data-theme` no `<html>` (o toggle troca entre `dark`/`light`; o valor persiste em `localStorage` como `agent-portal-theme`).

#### Raiz (compartilhada pelos dois temas)

| Token | Valor | Uso |
|---|---|---|
| `--accent` | `#E85D26` | Cor de marca / ação primária |
| `--accent-hover` | `#F06B35` | Hover do accent |
| `--accent-subtle` | `rgba(232, 93, 38, 0.12)` | Fundo translúcido do accent (badges ativos, ícones) |
| `--radius` | `10px` | Raio de cartão/painel padrão |
| `--radius-sm` | `6px` | Raio pequeno (botões, inputs, badges) |
| `--font` | `'Segoe UI', system-ui, -apple-system, sans-serif` | Família tipográfica base |
| `--transition` | `0.2s ease` | Duração de transição padrão |

#### Tema escuro (`[data-theme="dark"]`)

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#111113` | Fundo da página/body |
| `--bg-elevated` | `#1A1A1E` | Topbar, sidebar, painéis, cards de chat, fundo de inputs |
| `--bg-card` | `#1E1E22` | Cartões e painéis |
| `--bg-hover` | `#252529` | Hover de linhas/itens |
| `--border` | `#2A2A2E` | Bordas principais |
| `--border-subtle` | `#222226` | Bordas muito sutis (separadores internos) |
| `--text` | `#F0F0F2` | Texto principal |
| `--text-secondary` | `#9A9AA0` | Texto secundário |
| `--text-muted` | `#6A6A72` | Texto muted / metadata |
| `--success` | `#34D399` | Estado de sucesso |
| `--warning` | `#FBBF24` | Estado de alerta |
| `--error` | `#F87171` | Estado de erro |
| `--info` | `#60A5FA` | Estado informativo |
| `--shadow` | `0 2px 12px rgba(0,0,0,0.4)` | Sombra padrão |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.5)` | Sombra grande (drawer, edge-panel, toast) |

#### Tema claro (`[data-theme="light"]`)

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#F7F7F8` | Fundo da página/body |
| `--bg-elevated` | `#FFFFFF` | Topbar, sidebar, painéis, cards de chat, fundo de inputs |
| `--bg-card` | `#FFFFFF` | Cartões e painéis |
| `--bg-hover` | `#F0F0F2` | Hover de linhas/itens |
| `--border` | `#E2E2E6` | Bordas principais |
| `--border-subtle` | `#EEEEF0` | Bordas muito sutis |
| `--text` | `#1A1A1E` | Texto principal |
| `--text-secondary` | `#4B5563` | Texto secundário |
| `--text-muted` | `#6B7280` | Texto muted / metadata |
| `--success` | `#059669` | Estado de sucesso |
| `--warning` | `#D97706` | Estado de alerta |
| `--error` | `#DC2626` | Estado de erro |
| `--info` | `#2563EB` | Estado informativo |
| `--shadow` | `0 2px 12px rgba(0,0,0,0.06)` | Sombra padrão |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.1)` | Sombra grande |

> **Nota de coerência de estado:** nos dois temas o `--accent` é idêntico (`#E85D26`). Os estados success/warning/error/info **diferem** entre temas (escuro mais saturado/claro, claro mais profundo). Não unificar: seguir o valor de cada tema.

### 1.2 Tipografia

| Token | Família | Tamanho | Peso | Line-height |
|---|---|---|---|---|
| Base (`--font`) | `'Segoe UI', system-ui, -apple-system, sans-serif` | 13px (corpo) | 400 | 1.5 |
| Mono (`--font-mono`) | `'Cascadia Code', 'Fira Code', monospace` | 11–12px | 400/600 | 1.6 |

**Tamanhos (escala derivada dos valores do protótipo):**

| Escala | Tamanho | Onde aparece |
|---|---|---|
| `xs` | `10px` | badges, labels, meta, tags, legend, source-badge |
| `sm` | `11px` | subtitles, meta, config-item-value, mcp desc |
| `md` | `12px` | corpo de cartão, nav-item, msg, config, mcp-tool-row |
| `lg` | `13px` | page-subtitle, botões, chat-header-text, approval h4 |
| `xl` | `14px` | knowledge-doc-title |
| `stat` | `18px` | stat-value |
| `title` | `20px` | page-title |

**Pesos:**

| Peso | Onde aparece |
|---|---|
| 400 (regular) | corpo, subtitles |
| 500 (medium) | nav-item ativo, botões, config-item-value, edge-panel-row .v |
| 600 (semibold) | page-title, agent-name, flow-node-name, skill-name, mcp-card-name, tool-card-name, chat-header-text, approval h4 |
| 700 (bold) | stat-value |

**Letra:**
- Títulos de seção: `10px`, `font-weight: 600`, `text-transform: uppercase`, `letter-spacing: 0.8px` (seções de config) a `1px` (sidebar-label, monitor-panel-title).
- Types de agente / categoria: `10px`, uppercase, `letter-spacing: 0.5px` (agent-type) a `0.3px` (skill-category).
- Monospace aplicado a: names de tool (`tool-card-name`), scripts (`tool-script`), config-chip readonly, comandos MCP, variáveis de ambiente, `code` dentro de `.knowledge-doc-body` e `.tool-params-table`.

### 1.3 Espaçamento

O protótipo usa passos de `2px` em `2px`. Derivei uma escala coerente (todos os valores usados aparecem no protótipo):

| Token | Valor | Uso |
|---|---|---|
| `--space-1` | `2px` | bordas internas de dots, gaps muito pequenos |
| `--space-2` | `4px` | gaps de tags, padding interno de dots em chips |
| `--space-3` | `6px` | gap de botões em toolbar, padding de badges |
| `--space-4` | `8px` | gap de nav-item, padding de botões-sm, gaps de painéis |
| `--space-5` | `10px` | padding de ícones, gap de chat-header |
| `--space-6` | `12px` | gap de grids (agents-grid, stats-strip), padding de sidebar |
| `--space-7` | `14px` | padding de cartões, gap de skills-grid |
| `--space-8` | `16px` | padding de topbar-right, gap de page-header |
| `--space-10` | `20px` | gap de agent-detail, knowledge-layout |
| `--space-12` | `24px` | padding de main, margin-bottom de page-header |

**Medidas estruturais fixas do protótipo (não derivam da escala):**
- Largura da sidebar: `240px`.
- Altura do topbar: `56px`.
- Padding do main: `24px`.
- Gap do `agents-grid`: `12px`; `minmax(200px, 1fr)`.
- Gap do `stats-strip`: `12px`; `minmax(160px, 1fr)`.
- Gap do `skills-grid`: `14px`; `repeat(3, 1fr)` (responsiva para 2 colunas ≤ 1000px, 1 coluna < 700px para agents-grid).
- `agent-detail`: grid `1fr 380px` (chat 1fr, config panel 380px), gap `20px`.
- `knowledge-layout` / `monitor-layout`: grid `220px 1fr`, gap `16px` / `12px`.

### 1.4 Raios

| Token | Valor | Onde |
|---|---|---|
| `--radius` | `10px` | cartões, painéis, chat-panel, flow-node |
| `--radius-sm` | `6px` | botões, inputs, selects, textarea, badges circulares |
| Circular (`50%`) | — | avatar, theme-toggle, status-dot, port, nav-badge (pill) |
| Pill (`10px`/`12px`) | — | tags, config-chip, nav-badge, tool-status, mcp-transport, kb-source-badge |
| Code (`3px`) | — | `code` inline |

> **Desvio de conformidade interno:** `.agent-card` usa `--radius` (10px) mas seus cantos internos (ícone `--radius-sm`, msg `--radius`) variam. `.msg-user` tem `border-bottom-right-radius: 4px` explícito; `.msg-ai` tem `border-bottom-left-radius: 4px`. Manter esses 4px nas bolhas de chat.

### 1.5 Sombras

| Token | Valor | Onde |
|---|---|---|
| `--shadow` | `0 2px 12px rgba(0,0,0,0.4)` (dark) / `0 2px 12px rgba(0,0,0,0.06)` (light) | flow-node hover, flow-toolbar buttons, edge-panel (via --shadow-lg), toast |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.5)` (dark) / `0 8px 32px rgba(0,0,0,0.1)` (light) | edge-panel, toast |

> Nota: no protótipo, `.agent-card:hover` aplica `--shadow` e `.edge-panel`/`.toast` aplicam `--shadow-lg`. O `--shadow` escuro (`0.4` de opacidade) é forte; manter como está (fidelidade).

### 1.6 Transições e animações

| Token / regra | Valor | Onde |
|---|---|---|
| `--transition` | `0.2s ease` | transição padrão (hover de botões, nav-item, cards, inputs, toggle) |
| `border-color 0.2s` | explícito | `.flow-node` (hover muda border-color) |
| `pulse` | `2s infinite`, keyframes alterna `opacity: 1` ↔ `0.5` | `.status-dot.running` |
| `toast-in` | `0.3s ease`, de `opacity:0; transform: translateX(30px)` → `opacity:1; transform:none` | entrada de toast |
| `toast-out` | `0.3s ease forwards`, `opacity:0; transform: translateX(30px)` | saída de toast |
| Card approval (saída) | `0.3s` opacity + `translateX(20px)` | `.approval-card` ao responder |
| Chat input focus | `border-color` via `--transition` | `.chat-input:focus`, `.approval-textarea:focus` |

### 1.7 z-index

| Camada | Valor | Elemento |
|---|---|---|
| Tooltip/painel flutuante de editor | `3` | `.edge-panel` |
| Toolbar do flow | `2` | `.flow-toolbar` |
| Topbar | `10` | `.topbar` |
| Toasts | `9999` | `.toast-container` |

> Ordem de sobreposição do flow: canvas (0) → nodes (implícito, acima do canvas) → flow-toolbar (2) → edge-panel (3). Toasts sempre no topo (9999).

### 1.8 Bloco CSS pronto para `agent-portal/app/globals.css`

> Este é o bloco de **tokens**. O `fe-shell` cola isto em `app/globals.css` (dono do arquivo). Mantém exatamente os nomes e valores do protótipo. Os `components/ui/*` consomem `var(--...)`.

```css
:root {
  /* Marca */
  --accent: #E85D26;
  --accent-hover: #F06B35;
  --accent-subtle: rgba(232, 93, 38, 0.12);

  /* Design tokens */
  --radius: 10px;
  --radius-sm: 6px;
  --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
  --font-mono: 'Cascadia Code', 'Fira Code', monospace;
  --transition: 0.2s ease;
}

/* Tema escuro (padrão do protótipo) */
[data-theme="dark"] {
  --bg: #111113;
  --bg-elevated: #1A1A1E;
  --bg-card: #1E1E22;
  --bg-hover: #252529;
  --border: #2A2A2E;
  --border-subtle: #222226;
  --text: #F0F0F2;
  --text-secondary: #9A9AA0;
  --text-muted: #6A6A72;
  --success: #34D399;
  --warning: #FBBF24;
  --error: #F87171;
  --info: #60A5FA;
  --shadow: 0 2px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
}

/* Tema claro */
[data-theme="light"] {
  --bg: #F7F7F8;
  --bg-elevated: #FFFFFF;
  --bg-card: #FFFFFF;
  --bg-hover: #F0F0F2;
  --border: #E2E2E6;
  --border-subtle: #EEEEF0;
  --text: #1A1A1E;
  --text-secondary: #4B5563;
  --text-muted: #6B7280;
  --success: #059669;
  --warning: #D97706;
  --error: #DC2626;
  --info: #2563EB;
  --shadow: 0 2px 12px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.1);
}

/* Escala de espaçamento (derivada dos valores do protótipo) */
:root {
  --space-1: 2px;
  --space-2: 4px;
  --space-3: 6px;
  --space-4: 8px;
  --space-5: 10px;
  --space-6: 12px;
  --space-7: 14px;
  --space-8: 16px;
  --space-10: 20px;
  --space-12: 24px;
}

/* Tamanhos tipográficos */
:root {
  --text-xs: 10px;
  --text-sm: 11px;
  --text-md: 12px;
  --text-lg: 13px;
  --text-xl: 14px;
  --text-icon: 15px;
  --text-xl2: 16px;
  --text-stat: 18px;
  --text-title: 20px;
}

/* Pesos tipográficos */
:root {
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
  --weight-bold: 700;
}
```

> **Decisão (inconsência resolvida):** o protótipo não declara `--font-mono` nem escala de espaçamento/tamanho como variáveis (estão inline). Adicionei `--font-mono`, a escala de espaçamento e a escala tipográfica como **variáveis de apoio** para os componentes não reescreverem valores inline. Os tokens de cor/raio/sombra/transição são extraídos ao pé da letra do protótipo; as escalas de apoio são derivações diretas dos valores inline já usados.

---

## 2. Inventário de componentes

Cada componente abaixo é um primitive que o `fe-shell` entrega em `components/ui/*` (ou `components/layout/*` para shell). Os nós de tela consomem e **não** recriam.

### 2.1 Botão (`.btn`)

**Anatomia:** `inline-flex`, `align-items: center`, `gap: 6px`, padding `8px 16px`, `border-radius: var(--radius-sm)`, `font-size: 13px`, `font-weight: 500`, border `1px solid var(--border)`, fundo `var(--bg-card)`, cor `var(--text)`. Ícone 14px.

**Variantes:**
- `.btn` (default): fundo `var(--bg-card)`, border `var(--border)`.
- `.btn-primary`: fundo `var(--accent)`, border `var(--accent)`, cor `#fff`.
- `.btn-sm`: padding `6px 12px`, `font-size: 12px` (reaproveita base).

**Estados:**
- Default: conforme variante.
- Hover: `.btn` → border `var(--text-muted)`; `.btn-primary` → fundo/border `var(--accent-hover)` (`#F06B35`).
- Focus: `:focus-visible` com outline (ver Seção 5).
- Active: não há variante explícita no protótipo (hover já cobre).
- Disabled: não declarado no protótipo, mas o PLANO-FRONTEND exige `disabled` + `aria-disabled` durante loading. Aplicar `opacity: 0.6`, `cursor: not-allowed`, sem hover.
- Loading: não há spinner no protótipo. Recomendo adicionar um spinner circular (stroke-based) substituindo o texto/ícone; não inventar layout diferente.

**Medidas:** padding `8px 16px` (lg) / `6px 12px` (sm); gap ícone-texto `6px`; min-height implícita ~36px (lg), ~30px (sm). Alvo de toque ≥ 34px (sm) / 36px (lg).

### 2.2 Input de texto (`.chat-input` / inputs genéricos)

**Anatomia:** padding `10px 14px`, `border-radius: var(--radius-sm)`, border `1px solid var(--border)`, fundo `var(--bg-elevated)`, cor `var(--text)`, `font-size: 13px`, `font-family: var(--font)`, `outline: none`.

**Estados:**
- Default: acima.
- Hover: não declarado (border permanece).
- Focus: border `var(--accent)` (`--transition`).
- Disabled: não declarado; aplicar `opacity: 0.6`, `cursor: not-allowed`.

### 2.3 Select (`.config-select`)

**Anatomia:** padding `4px 8px`, `border-radius: var(--radius-sm)`, border `1px solid var(--border)`, fundo `var(--bg-elevated)`, cor `var(--text)`, `font-size: 11px`, `font-family: var(--font)`.

**Estados:** default / focus (sem accent explícito no protótipo — recomendo `border-color: var(--accent)` para consistência com input). Sem estado de loading.

### 2.4 Textarea (`.approval-textarea`, `.tool-script`)

**Anatomia:** padding `8–12px`, `border-radius: var(--radius-sm)` (script usa `--radius-sm`), border `1px solid var(--border)`, fundo `var(--bg-elevated)`, cor `var(--text)`, `resize: vertical`.
- `.approval-textarea`: `font-size: 12px`, `min-height: 60px`, `font-family: var(--font)`.
- `.tool-script`: `font-family: var(--font-mono)`, `font-size: 12px`, `line-height: 1.6`, `min-height: 160px` (editor de código).

**Estados:** default / focus (`border-color: var(--accent)`) / disabled (`opacity: 0.6`).

### 2.5 Checkbox e Toggle

O protótipo **não** renderiza checkbox nem toggle visíveis (o "Canal de aprovação" é um `<select>`). Decisão mínima coerente com o contrato (PLANO-FRONTEND lista toggle como primitive UI):

- **Toggle:** trilha `36px × 36px` (área de toque), bolinha `28px` com `border-radius: 50%`. Trilha off = `var(--border)`; on = `var(--accent)`. Transição da bolinha `transform` `var(--transition)`. Estados: off / on / focus (outline) / disabled (`opacity: 0.6`).
- **Checkbox:** caixa `18px × 18px`, `border-radius: var(--radius-sm)`, border `1px solid var(--border)`, fundo `var(--bg-elevated)`. Marcado: fundo `var(--accent)`, border `var(--accent)`, ícone check branco (stroke 2). Focus: outline `var(--info)`/accent.

> **Decisão:** como o protótipo não mostra estes controles, defini tamanhos mínimos de toque (≥ 34px) e cores derivadas dos tokens. O `fe-review` valida se o controle real bate com tokens; se o protótipo tiver versão futura, prevalece.

### 2.6 Badge de status (`.status-dot`)

**Anatomia:** círculo `7px × 7px`, `border-radius: 50%`, fundo derivado do estado, sem texto próprio (sempre acompanhado de rótulo).

**Estados (cor de fundo):**
| Estado | Cor | Animação |
|---|---|---|
| `running` | `var(--success)` | `pulse 2s infinite` (opacity 1 ↔ 0.5) |
| `pending` | `var(--warning)` | nenhuma |
| `idle` | `var(--text-muted)` | nenhuma |
| `error` | `var(--error)` | nenhuma |

**Variantes de rótulo de status (não-dot):**
- `.tool-status.deployed`: fundo `rgba(52,211,153,0.15)`, cor `var(--success)`.
- `.tool-status.draft`: fundo `rgba(251,191,36,0.15)`, cor `var(--warning)`.
- `.tool-status` genérico (Rivvn "contrato ativo"): usa classe `deployed` no protótipo.

### 2.7 Card de agente (`.agent-card`)

**Anatomia:** `background: var(--bg-card)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, padding `14px`, cursor `pointer`, `position: relative`, `overflow: hidden`, `display: flex; flex-direction: column; min-height: 128px`.

**Estrutura interna:**
1. Ícone (`.agent-icon`): `30px × 30px`, `border-radius: var(--radius-sm)`, fundo `var(--accent-subtle)`, cor `var(--accent)`, ícone 14px.
2. Nome (`.agent-name`): `13px`, weight 600.
3. Tipo (`.agent-type`): `10px`, `var(--text-muted)`, uppercase, `letter-spacing: 0.5px`.
4. Status (`.agent-status`): `12px`, `var(--text-secondary)`, dot + texto.
5. Tags (`.agent-tags`): `margin-top: auto`, `padding-top: 10px`, flex wrap gap `4px`.

**Tags (`.tag`):** `10px`, padding `3px 9px`, `border-radius: 10px`, fundo `var(--bg-hover)`, border `1px solid var(--border)`, cor `var(--text-secondary)`.

**Variantes por tipo de cartão:** `--card-accent` customizável via inline style (`var(--card-accent, var(--accent))`) controla a barra superior animada. Exemplos do protótipo: accent (Planner, Épico, Frontend Dev), info (História, Backend Dev), success (Task, Code Reviewer, Deployer), error (QA).

**Estados:**
- Default: acima.
- Hover: border `var(--accent)`, `transform: translateY(-2px)`, box-shadow `var(--shadow)`, barra superior (`::before`) de `opacity: 0` → `1` (3px no topo, cor `--card-accent`).
- Focus: outline no focus.
- Click (detail): abre `/agents/{id}`.

### 2.8 Card de estatística (`.stat-card`)

**Anatomia:** `background: var(--bg-card)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, padding `12px 14px`, flex `align-items center`, gap `10px`. Sem hover declarado (fica estático na stats-strip).
- Ícone (`.stat-icon`): `30px × 30px`, `border-radius: var(--radius-sm)`, fundo `var(--bg-hover)`, cor `var(--text)`, ícone 14px.
- Valor (`.stat-value`): `18px`, weight 700, line-height 1.1.
- Rótulo (`.stat-label`): `11px`, `var(--text-muted)`.

### 2.9 Tabela (`.tool-params-table`)

**Anatomia:** `width: 100%`, `border-collapse: collapse`, `font-size: 12px`.
- Th: `text-align: left`, `10px`, uppercase, `var(--text-muted)`, padding `4px 8px`, border-bottom `1px solid var(--border)`.
- Td: padding `6px 8px`, border-bottom `1px solid var(--border-subtle)`.
- `code` dentro: fundo `var(--bg-hover)`, padding `1px 5px`, `border-radius: 3px`, `11px`, monospace.

### 2.10 Modal

O protótipo **não** tem modal nativo; as criação de skill/tool/mcp são descritas no PLANO-FRONTEND como "abre modal/form". Decisão mínima coerente:

- **Anatomia:** overlay escuro `rgba(0,0,0,0.4)` (dark) / `0.1` (light) fullscreen, centro: painel `background: var(--bg-card)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, box-shadow `var(--shadow-lg)`, padding `20px`, max-width ~520px.
- **Estados:** aberto / fechado (fade `0.2s`), focus no primeiro campo, ESC fecha, clique fora fecha.
- **Head:** título `13px` weight 600 + botão fechar (ícone X, `var(--text-muted)`).

### 2.11 Drawer / Painel lateral (`.edge-panel`)

**Anatomia:** `position: absolute`, `top: 56px`, `right: 12px`, `width: 240px`, `background: var(--bg-elevated)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, box-shadow `var(--shadow-lg)`, `z-index: 3`, `overflow: hidden`.

**Estrutura:**
- Header (`.edge-panel-header`): flex space-between, padding `10px 12px`, border-bottom `1px solid var(--border)`, título `12px` weight 600. Botão fechar (`.edge-panel-close`): `var(--text-muted)`, hover `var(--text)`.
- Body (`.edge-panel-body`): padding `10px 12px`, flex gap `8px`. Linhas (`.edge-panel-row`): flex space-between, gap `8px`. Chave `.k` = `var(--text-muted)`; valor `.v` = weight 500, text-align right.

### 2.12 Painel lateral (sidebar) (`.sidebar`)

**Anatomia:** `background: var(--bg-elevated)`, border-right `1px solid var(--border)`, padding `16px 12px`, flex column, gap `4px`, largura fixa `240px`.

**Itens de navegação (`.nav-item`):** flex align-center, gap `10px`, padding `9px 12px`, `border-radius: var(--radius-sm)`, `13px`, `var(--text-secondary)`, cursor pointer, `border: none`, fundo `transparent`, width 100%, text-align left.
- Hover: fundo `var(--bg-hover)`, cor `var(--text)`.
- Ativo (`.nav-item.active`): fundo `var(--accent-subtle)`, cor `var(--accent)`, weight 500, `border-left: 2px solid var(--accent)`, `border-radius: 0 var(--radius-sm) var(--radius-sm) 0`.
- Ícone: `18px × 18px`, flex-shrink 0.
- Badge (`.nav-badge`): `10px`, weight 600, padding `1px 6px`, `border-radius: 10px`, fundo `var(--accent)`, cor `#fff` (pill à direita, `margin-left: auto`).

**Label de seção (`.sidebar-label`):** `10px`, weight 600, uppercase, `letter-spacing: 1px`, `var(--text-muted)`, padding `12px 12px 6px`.

### 2.13 Topbar (`.topbar`)

**Anatomia:** grid-column full, flex align-center space-between, padding `0 20px`, fundo `var(--bg-elevated)`, border-bottom `1px solid var(--border)`, `z-index: 10`, altura `56px`.
- Esquerda: logo (`.logo-img` 30px) + `.logo-text` (`13px` weight 600; span `11px` weight 400, `var(--text-muted)`, `margin-left: 6px`).
- Direita: theme-toggle (36px circular, border `var(--border)`, fundo `var(--bg-card)`, cor `var(--text-secondary)`, hover border+cor `var(--accent)` + fundo `var(--accent-subtle)`) + avatar (32px circular, border 2px `var(--accent)`, cor `var(--accent)`, fundo `var(--accent-subtle)`, `12px` weight 600).

### 2.14 Painel de notificações (`.nav-badge` no header + `notifications-badge`)

O protótipo mostra o badge de aprovações **dentro da sidebar** (`.nav-badge` "3"). O PLANO-FRONTEND descreve um `notifications-badge` no header consumindo `approval:new`. Token/estilo reutiliza `.nav-badge` (pill `10px` weight 600, fundo `var(--accent)`, cor `#fff`). Sem toast de notificação no badge; a notificação em tempo real vem pelo WebSocket (canal `approval:new`).

### 2.15 Tabs

O protótipo **não** renderiza tabs (a navegação é por view). Decisão mínima coerente (o PLANO-FRONTEND lista tabs como primitive):
- Container de tabs: border-bottom `1px solid var(--border)`.
- Tab: padding `8px 12px`, `13px`, sem border-bottom, cor `var(--text-secondary)`, cursor pointer.
- Ativa: cor `var(--accent)`, weight 500, `border-bottom: 2px solid var(--accent)`.
- Hover: cor `var(--text)`.

### 2.16 Toast (`.toast`)

**Anatomia:** padding `12px 18px`, `border-radius: var(--radius-sm)`, fundo `var(--bg-elevated)`, border `1px solid var(--border)`, box-shadow `var(--shadow-lg)`, `13px`, cor `var(--text)`, max-width `360px`. Animação `toast-in`/`toast-out` `0.3s ease`. Container `.toast-container`: `position: fixed`, `bottom: 20px`, `right: 20px`, `z-index: 9999`, `pointer-events: none`, flex column gap `8px`; cada toast `pointer-events: auto`.

**Variantes (borda esquerda 3px + cor):**
- `.toast.success`: borda `var(--success)`.
- `.toast.error`: borda `var(--error)`.
- `.toast.info`: borda `var(--info)`.
- `.toast.warning`: borda `var(--warning)`.

**Estados:** entrada (translateX 30px → 0), visível (3s), saída (removing).

### 2.17 Empty state

Não há classe única no protótipo, mas o PLANO-FRONTEND exige empty-state com CTA em toda lista. Decisão coerente:
- Container centralizado, padding `48px 24px`, text-align center.
- Ícone grande (48px, `var(--text-muted)`, em quadro `var(--bg-hover)`).
- Título `13px` weight 600, `var(--text)`.
- Descrição `12px`, `var(--text-secondary)`.
- CTA: `.btn-primary`.

### 2.18 Skeleton

Não declarado no protótipo (exigido pelo PLANO-FRONTEND). Decisão coerente:
- Bloco `background: var(--bg-hover)`, `border-radius: var(--radius-sm)`, com animação de shimmer (gradiente linear que se move). Altura proporcional ao elemento (card ~128px, stat ~44px, linha ~16px).

### 2.19 Nó e aresta do editor de fluxo

**Nó (`.flow-node`):** `position: absolute`, largura `160px` (full), `background: var(--bg-elevated)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, padding `14px`, cursor `grab`, transição `border-color 0.2s`.
- Tamanhos: `.mini` (150px, padding 9px 12px, ícone 22px), `.tiny` (128px, padding 7px 10px, ícone 18px, nome 10px).
- Hover: border `var(--accent)`.
- **Cor por tipo (borda esquerda 3px):** `.mini.backend` → `var(--info)`; `.mini.frontend` → `var(--accent)`.
- Header (`.flow-node-header`): flex align-center gap `8px`, margin-bottom `8px`. Ícone (`.flow-node-icon`): `28px` (mini 22px, tiny 18px), `border-radius: 6px`, fundo `var(--accent-subtle)`, cor `var(--accent)`. Nome (`.flow-node-name`): `12px` weight 600. Tipo (`.flow-node-type`): `10px`, `var(--text-muted)`.
- Ports (`.flow-node-ports`): flex space-between, margin-top `10px`. Port: `10px × 10px`, `border-radius: 50%`, border `2px`, fundo `var(--bg-elevated)`. **Cor por tipo:** `.output` → `var(--success)`; `.input` → `var(--info)`.

**Aresta (`.flow-edge`):** SVG `<path>`, `fill: none`, `stroke-width` variável.
| Tipo | Stroke | Dash | Opacity | Width |
|---|---|---|---|---|
| Flow (default) | `var(--text-muted)` | sólido | 0.5 | 1.5 |
| Flow (active) | `var(--accent)` | sólido | 1 | 2 |
| Data | `var(--info)` | tracejado `5,4` | 0.85 | 1.5 |
| Flow · condição | `var(--text-muted)` | tracejado `5,5` | 0.5 | 1.5 |

- Seta (marker `#arrow`): preenchimento `var(--text-muted)`.
- Rótulo de aresta (`.flow-edge-label`): `10px`, `var(--text-muted)`.
- Hit-test: faixa transparente `stroke-width: 12` (clicável) por baixo da linha visível.

**Legenda (`.flow-legend`):** fundo `var(--bg-elevated)`, border `1px solid var(--border)`, `border-radius: var(--radius-sm)`, box-shadow `var(--shadow)`, `11px`, `var(--text-muted)`. Swatches: Flow (linha cinza sólida), Flow · condição (cinza tracejada), Data (azul tracejada), Backend (azul sólida), Frontend (accent sólida).

**Toolbar (`.flow-toolbar`):** `position: absolute`, `top: 12px`, `left/right: 12px`, flex space-between, wrap, `z-index: 2`. Botões `6px 12px`, `12px`, fundo `var(--bg-elevated)`, box-shadow `var(--shadow)`. Zoom-level (`.flow-zoom-level`): `11px`, `var(--text-muted)`, fundo `var(--bg-elevated)`, border `1px solid var(--border)`, `border-radius: var(--radius-sm)`, padding `0 10px`.

**Canvas (`.flow-canvas`):** fundo com `radial-gradient(circle, var(--border) 1px, transparent 1px)`, `background-size: 24px 24px` (grade de pontos 24px). Cursor `grab` / `grabbing` (`.panning`).

### 2.20 Bolha de chat (`.msg`)

**Anatomia:** `max-width: 85%`, padding `10px 14px`, `border-radius: var(--radius)`, `13px`, line-height 1.5.
- `.msg-user`: `align-self: flex-end`, fundo `var(--accent)`, cor `#fff`, `border-bottom-right-radius: 4px`.
- `.msg-ai`: `align-self: flex-start`, fundo `var(--bg-hover)`, cor `var(--text)`, `border-bottom-left-radius: 4px`.
- Sugestão (`.msg-ai .suggestion`): margin-top `10px`, padding `10px 12px`, fundo `var(--bg-elevated)`, border `1px solid var(--border)`, `border-radius: var(--radius-sm)`, `12px`. Título `.suggestion-title`: `11px`, weight 600, uppercase, `letter-spacing: 0.5px`, `var(--text-secondary)`. Lista sem marcadores; cada `<li>` tem bullet `•` cor `var(--accent)` `margin-right: 6px`, cor `var(--text-secondary)`.

**Container de mensagens (`.chat-messages`):** flex column, gap `14px`, padding `18px`, overflow-y auto.
**Input (`.chat-input-area`):** padding `14px 18px`, border-top `1px solid var(--border)`, flex align-center gap `10px`. Botão enviar (`.chat-send`): `36px × 36px`, `border-radius: var(--radius-sm)`, fundo `var(--accent)`, cor `#fff`, hover `var(--accent-hover)`.

---

## 3. Padrões de tela

### 3.1 Layout base (shell)

Grid de `240px 1fr` (sidebar + main) na coluna, `56px 1fr` (topbar + main) nas linhas, `height: 100vh`. Body: `font-family: var(--font)`, `background: var(--bg)`, `color: var(--text)`, `line-height: 1.5`, `overflow: hidden`. Main: `overflow-y: auto`, padding `24px`.

**Responsivo (≤ 900px):** sidebar recolhida (protótipo `display: none`; PLANO-FRONTEND pede menu hamburger — manter navegação). `agent-detail` empilha (1 coluna).

### 3.2 Grid de cards (dashboard)

`.agents-grid`: `display: grid`, `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`, gap `12px`. ≤ 700px → 1 coluna. Stats strip abaixo: `.stats-strip` → `repeat(auto-fit, minmax(160px, 1fr))`, gap `12px`.

**Empty state:** portal nasce vazio (contrato §0). Sem seed ilustrativo. `empty-state` com CTA "Criar primeiro agente" → `/agents/new`.

### 3.3 Página de detalhe (agent detail)

`.agent-detail`: grid `1fr 380px`, gap `20px`, `height: calc(100vh - 120px)`. Coluna esquerda = chat-panel (card com border, `border-radius: var(--radius)`, flex column, overflow hidden). Coluna direita = config-panel (card, padding `20px`, overflow-y auto).
- **Config panel:** badge superior (`gerado via chat`, `10px`, pill com ícone lock), seções com título uppercase `10px` weight 600 `var(--text-muted)`, border-bottom `var(--border-subtle)`, padding-bottom `6px`, margin-bottom `20px`. Itens (`.config-item`): flex space-between, padding `8px 0`, `13px`. Chips (`.config-chip`): padding `4px 10px`, `border-radius: 12px`, fundo `var(--bg-hover)`, border `var(--border)`, `11px`, `var(--text-secondary)`. Dots de cor: green=`var(--success)`, blue=`var(--info)`, orange=`var(--accent)`. Chip readonly: monospace `10px`, `opacity: 0.7`.

### 3.4 Editor em canvas (flow editor)

`.flow-container`: `position: relative`, largura 100%, altura `calc(100vh - 160px)`, fundo `var(--bg-card)`, border `1px solid var(--border)`, `border-radius: var(--radius)`, overflow hidden, cursor `grab`. Dentro: `.flow-toolbar` (abs, topo), `.flow-canvas` (abs, grade de pontos 24px), `.flow-edges` (SVG overlay, `pointer-events: none`), `.flow-nodes`. Edge-panel flutuante (abs, top 56px, right 12px).

**Interação:** pan (mousedown/mousemove/mouseup), zoom (wheel + botões, range 0.1–2.0), fit-to-view (calcula scale mínima para encher o viewport com padding 32px).

### 3.5 Monitor com log em tempo real

`.monitor-layout`: grid `220px 1fr`, gap `12px`, `height: calc(100vh - 120px)`.
- Coluna esquerda (`.monitor-panel`): título `.monitor-panel-title` (`10px` weight 600, uppercase, `var(--text-muted)`, padding `10px 12px`, border-bottom `var(--border-subtle)`). Lista de nós (`.monitor-node-row`): flex align-center gap `8px`, padding `6px 8px`, `border-radius: var(--radius-sm)`, hover `var(--bg-hover)`, `12px`. Nome `flex: 1`, ellipsis; tempo `10px`, `var(--text-muted)`. Dot de status à esquerda (reaproveita `.status-dot`).
- Coluna direita (`.monitor-main`): flex column gap `12px`. Logs (`.monitor-log-body`): monospace `11px`, line-height 1.7, `var(--text-secondary)`. Cores de log: `.t` (timestamp) = `var(--text-muted)`, `.ok` = `var(--success)`, `.warn` = `var(--warning)`. Checkpoints (`.monitor-checkpoints`): `flex: 0 0 auto`, max-height `180px`. Linha (`.checkpoint-row`): flex space-between, padding `6px 10px`, border-bottom `var(--border-subtle)`, `12px`. Meta `11px`, `var(--text-muted)`.

### 3.6 Fila de aprovações (approvals)

`.approvals-list`: flex column gap `12px`. Cartão (`.approval-card`): grid `auto 1fr auto`, gap `16px`, align-items center, padding `18px`, border `1px solid var(--border)`, `border-radius: var(--radius)`.
- **Urgente (`.approval-card.urgent`):** borda esquerda `3px solid var(--warning)`.
- Ícone (`.approval-icon`): `40px × 40px`, `border-radius: var(--radius-sm)`, fundo `var(--accent-subtle)`, `16px`.
- Info: h4 `13px` weight 600; p `12px`, `var(--text-muted)`.
- Ações (`.approval-actions`): flex gap `8px`. Botões-sm (`.btn-sm`): padding `6px 12px`, `12px`, border `var(--border)`, fundo `var(--bg-elevated)`, cor `var(--text)`, hover border `var(--text-muted)`.
  - `.btn-sm.approve`: fundo `var(--success)`, border `var(--success)`, cor `#fff`, hover opacity 0.9.
  - `.btn-sm.reject`: fundo `var(--error)`, border `var(--error)`, cor `#fff`, hover opacity 0.9.
- Expansão (`.approval-card.expanded`): grid vira `auto 1fr`, ações vão para `grid-column: 1 / -1`, justify-content flex-end. Textarea aparece (`min-height: 60px`).

---

## 4. Ícones (protótipo → `lucide-react`)

Todos os SVGs inline do protótipo são substituídos por componentes `lucide-react`, stroke-based, sempre com `aria-label` e `role="img"`. Sem emojis.

### 4.1 Navegação (sidebar)

| Protótipo | `lucide-react` | Nota |
|---|---|---|
| Dashboard (grid 2×2) | `LayoutGrid` | |
| Pipelines (3 nós ligados) | `GitBranch` | |
| Monitor (monitor + gráfico) | `Monitor` | |
| Aprovações (círculo + check) | `CheckCircle2` | |
| Skills (gem) | `Gem` | |
| Tools Custom (chave de fenda) | `Wrench` | |
| MCP Servers (logo MCP preenchido) | `Cube` | sem ícone de marca MCP no lucide; `Cube` é o substituto neutro |
| Knowledge (livro aberto) | `BookOpen` | |

### 4.2 Dashboard

| Protótipo | `lucide-react` |
|---|---|
| Ícone Planner (documento) | `FileText` |
| Ícone Épico (círculos concêntricos) | `Target` |
| Ícone História (balão) | `MessageSquare` |
| Ícone Task (listas) | `List` |
| Ícone Backend Dev (rack) | `Server` |
| Ícone Frontend Dev (notebook) | `Laptop` |
| Ícone QA (círculo + check) | `CheckCircle2` |
| Ícone Code Reviewer (lupa) | `Search` |
| Ícone Deployer (foguete) | `Rocket` |
| Stats: pipelines em execução (play) | `Play` |
| Stats: aprovações pendentes (relógio) | `Clock` |
| Stats: tarefas concluídas (círculo + check) | `CheckCircle2` |
| Stats: taxa de sucesso (raio) | `Zap` |

### 4.3 Editor de fluxo

| Protótipo | `lucide-react` |
|---|---|
| Agente (adicionar nó, +) | `Plus` |
| Conectar (dois nós ligados) | `GitBranch` |
| Zoom out (lupa −) | `MagnifyingGlass` + `Minus` (compor) |
| Zoom in (lupa +) | `MagnifyingGlass` + `Plus` (compor) |
| Ajustar (expandir) | `Maximize` |
| Fechar painel (X) | `X` |

### 4.4 Chat de construção

| Protótipo | `lucide-react` |
|---|---|
| Ícone do chat (estrela/faísca) | `Sparkles` |
| Enviar (seta + polígono) | `Send` |
| Badge "gerado via chat" (cadeado) | `Lock` |

### 4.5 Aprovações

| Protótipo | `lucide-react` |
|---|---|
| Ícone de aprovação (lupa) | `Search` |
| Ícone de aprovação (documento) | `FileText` |
| Ícone de aprovação (foguete) | `Rocket` |

### 4.6 Biblioteca (skills/tools/mcp)

| Protótipo | `lucide-react` |
|---|---|
| code-gen (colchetes) | `Code` |
| test-runner (círculo + check) | `CheckCircle2` |
| security-scanner (escudo + check) | `ShieldCheck` |
| doc-writer (documento + linhas) | `FileText` |
| api-client (elos) | `Link` |
| deploy-runner (foguete) | `Rocket` |
| Ícone "usado por N agentes" (rack) | `Server` |
| Upload (seta para cima) | `Upload` |

### 4.7 Knowledge

| Protótipo | `lucide-react` |
|---|---|
| Projeto API REST (documento) | `FileText` |
| Padrões de Código (colchetes) | `Code` |
| Docs Azure (nuvem) | `Cloud` |
| Security Guidelines (escudo) | `Shield` |
| Documentação do Time (nodos ligados) | `Network` |

### 4.8 Topbar

| Protótipo | `lucide-react` |
|---|---|
| Toggle de tema (sol/lua) | `Sun` / `Moon` |

> **Nota:** os ícones de status (`.status-dot`) não são ícones, são círculos de cor (CSS). Não mapear para lucide.

---

## 5. Acessibilidade

### 5.1 Contraste mínimo (AA, ratio ≥ 4.5:1 para texto normal; ≥ 3.0:1 para texto grande ≥ 18px/14px bold)

Ratios calculados com WCAG (cor normal, sem ampliação). Fonte: `var(--font)`.

#### Tema escuro

| Par | Tokens | Ratio | AA normal? |
|---|---|---|---|
| Texto / body | `--text` #F0F0F2 · `--bg` #111113 | **16.7:1** | Sim (AAA) |
| Texto secundário / body | `--text-secondary` #9A9AA0 · `--bg` #111113 | **6.7:1** | Sim |
| Texto muted / body | `--text-muted` #6A6A72 · `--bg` #111113 | **3.5:1** | Não (só texto grande ≥ 3.0) |
| Texto / card | `--text` · `--bg-card` #1E1E22 | ~14.0:1 | Sim |
| Texto secundário / card | `--text-secondary` · `--bg-card` | ~6.0:1 | Sim |
| Texto muted / card | `--text-muted` · `--bg-card` | **3.1:1** | Não (só texto grande) |
| Texto / hover | `--text` · `--bg-hover` #252529 | ~13.5:1 | Sim |
| Texto secundário / hover | `--text-secondary` · `--bg-hover` | **5.4:1** | Sim |
| Texto muted / hover | `--text-muted` · `--bg-hover` | **2.85:1** | Não (decorativo) |
| Branco / accent (botão primário) | `#FFFFFF` · `--accent` #E85D26 | **3.5:1** | Não (só texto grande/semibold) |
| Branco / success (botão aprovar) | `#FFFFFF` · `--success` #34D399 | **1.9:1** | **Não** — ver mitigação |
| Branco / error (botão rejeitar) | `#FFFFFF` · `--error` #F87171 | **4.8:1** | Sim |
| Branco / info | `#FFFFFF` · `--info` #60A5FA | ~5.6:1 | Sim |

#### Tema claro

| Par | Tokens | Ratio | AA normal? |
|---|---|---|---|
| Texto / body | `--text` #1A1A1E · `--bg` #F7F7F8 | **16.2:1** | Sim (AAA) |
| Texto secundário / body | `--text-secondary` #4B5563 · `--bg` #F7F7F8 | **7.1:1** | Sim |
| Texto muted / body | `--text-muted` #6B7280 · `--bg` #F7F7F8 | **4.5:1** | Sim (limítrofe) |
| Texto / hover | `--text` · `--bg-hover` #F0F0F2 | ~15.4:1 | Sim |
| Texto secundário / hover | `--text-secondary` · `--bg-hover` | **6.7:1** | Sim |
| Texto muted / hover | `--text-muted` · `--bg-hover` | **4.3:1** | Não (só texto grande) |
| Branco / accent | `#FFFFFF` · `--accent` #E85D26 | **3.5:1** | Não (só texto grande/semibold) |
| Branco / success (light #059669) | `#FFFFFF` · `--success` #059669 | **3.8:1** | **Não** — ver mitigação |
| Branco / warning (light #D97706) | `#FFFFFF` · `--warning` #D97706 | **3.2:1** | Não (só texto grande) |
| Branco / error (#DC2626) | `#FFFFFF` · `--error` #DC2626 | **4.8:1** | Sim |
| Branco / info (#2563EB) | `#FFFFFF` · `--info` #2563EB | **5.2:1** | Sim |

#### Mitigações obrigatórias (registradas, não ignoradas)

1. **Texto branco sobre `--success`** (botão "Aprovar"/"Deploy"): **1.9:1 (dark) / 3.8:1 (light)** — abaixo do AA. **Recomendação:** usar texto branco só se o botão for grande/semibold (≥ 14px semibold conta como "grande"), ou escurecer o verde de fundo do botão para `#047857` (light) / `#047857` (dark) mantendo `--success` para dots/bordas. Manter `--success` como token de estado; a superfície de botão é decisão de implementação do `fe-shell`/`fe-review`.
2. **Texto branco sobre `--accent`** (botão primário, nav-badge): **3.5:1** — abaixo do AA para texto normal. **Recomendação:** manter peso 600 e tamanho ≥ 13px (considere 14px). O accent é a cor de marca; o PLANO-FRONTEND pede botões com ação real, então a legibilidade é crítica.
3. **`--text-muted`** em superfícies `--bg`/`--bg-card`/`--bg-hover`: **2.8–3.5:1** — só texto grande ou decorativo. Não usar `--text-muted` para corpo de texto normal; usar `--text-secondary` quando exigir AA.

### 5.2 Foco visível

- Todo elemento interativo (`button`, `a`, `input`, `select`, `textarea`, `[tabindex]`) deve exibir `:focus-visible` com outline nítido: `outline: 2px solid var(--accent)` (ou `var(--info)`), `outline-offset: 2px`. O protótipo usa `outline: none` nos inputs — **substituir** por outline de foco visível em vez de removê-lo.
- Nunca remover o focus sem substituir.

### 5.3 Tamanhos de alvo de toque

- Botão lg: ~36px de altura (ok). Botão sm: ~30px (abaixo do mínimo 34px recomendado) — aumentar padding vertical do `.btn-sm` para garantir ≥ 34px, ou usar `.btn-sm` só em contextos densos já espaçados.
- Nav-item: padding `9px 12px` → altura ≥ 38px (ok).
- Ícones soltos (theme-toggle, chat-send, fechar): 36px (ok).
- Status-dot (7px): não é alvo; sempre acompanhado de rótulo clicável.
- Arestas do flow: hit-test de 12px de largura (acima do mínimo).

### 5.4 Semântica e navegação por teclado

- Todos os ícones: `role="img"` + `aria-label` (o protótipo já tem `aria-label` nos SVGs; manter ao migrar para lucide).
- Botões só ícone: `aria-label` obrigatório (ex.: theme-toggle, fechar, enviar).
- Formulários: `<label htmlFor>` + `id`, erro com `aria-describedby`.
- Editor de fluxo: atalhos de teclado documentados (React Flow nativo + teclas de ajuda).
- Ordem de tabulação: topbar → sidebar → main → ações.

---

## 6. Checklist de fidelidade (para o `fe-review`)

Aprovar telas só se **todas** as itens passarem. Cada "não" é bloqueante até resolvido ou registrado como desvio.

### Tokens
- [ ] `app/globals.css` contém todos os tokens da Seção 1.1–1.8 com valores exatos.
- [ ] Tema controlado por `data-theme` no `<html>`; toggle alterna `dark`/`light`; persiste em `localStorage` (`agent-portal-theme`).
- [ ] Nenhum valor de cor/raio/sombra inline nos componentes (todos via `var(--...)`).
- [ ] `--font-mono` aplicado a tool-names, scripts, config readonly, comandos MCP, `code` inline.

### Componentes
- [ ] Botão: variantes default/primary/sm; hover e focus corretos; disabled com `aria-disabled`.
- [ ] Input/select/textarea: focus com `border-color: var(--accent)`; sem `outline: none` sem substituição.
- [ ] Status-dot: cores por estado (running=pulse success, pending=warning, idle=muted, error); animação `pulse 2s`.
- [ ] Agent-card: hover (translateY -2px, border accent, shadow, barra superior `--card-accent`); tags, min-height 128px.
- [ ] Toast: 4 variantes (success/error/info/warning) com borda esquerda 3px; animação 0.3s; z-index 9999.
- [ ] Edge-panel / drawer: 240px, shadow-lg, z-index 3, header + body com `.k`/`.v`.
- [ ] Sidebar: 240px, nav-item ativo (accent-subtle, border-left 2px accent), nav-badge pill.
- [ ] Flow-node: tamanhos full/mini/tiny; ports output=success/input=info; border-left por tipo (backend=info, frontend=accent).
- [ ] Flow-edge: cores por tipo (flow=muted, active=accent, data=info tracejado, condição cinza tracejado); seta marker.
- [ ] Bolha de chat: user=accent/branco (canto inferior direito), ai=bg-hover/texto (canto esquerdo), radius 4px; sugestão com bullet accent.
- [ ] Approval-card: grid auto 1fr auto; urgente borda esquerda warning; expande com textarea; botões approve/reject com cores de estado.
- [ ] Monitor: lista de nós com dot + tempo; logs monospace com `.t/.ok/.warn`; checkpoints max-height 180px.

### Telas
- [ ] Shell: grid 240px + topbar 56px; main padding 24px.
- [ ] Dashboard: agents-grid (auto-fill minmax 200px, gap 12px); stats-strip (minmax 160px); "Novo Agente" navega real.
- [ ] Empty states: portal nasce vazio, CTA real em toda lista, sem seed ilustrativo.
- [ ] Agent detail: grid 1fr 380px; config-panel com seções uppercase 10px; chips com dots.
- [ ] Flow editor: toolbar (zoom/fit), canvas com grade 24px, edge-panel flutuante, legenda.
- [ ] Monitor: layout 220px + main; logs em tempo real via WS.
- [ ] Approvals: lista de cartões, aprovar/rejeitar/argumentar reais (sem showToast de tela fake).
- [ ] Library (skills/tools/mcp/knowledge): grids, cards, detalhe, upload, rivvn bar.

### Ícones e acessibilidade
- [ ] Zero emojis; todos os ícones via `lucide-react` com `aria-label` + `role="img"`.
- [ ] Nenhum `showToast` de "em desenvolvimento" como terminal de ação.
- [ ] Todo `<button>` tem ação real (navegação/submit/abre painel/dispara API); nenhum `href="#"` vazio.
- [ ] `:focus-visible` visível em todos os interativos.
- [ ] Contraste AA em todos os pares texto/fundo (ver Seção 5); mitigações do accent/success aplicadas.
- [ ] Alvos de toque ≥ 34px.
- [ ] Labels em todos os inputs; erro com `aria-describedby`.

---

## 7. Decisões e inconsistências resolvidas

Extraídas da leitura do protótipo; registradas para transparência e para o `fe-review`.

1. **`--accent` idêntico nos dois temas; estados diferem.** O protótipo mantém `--accent`/`--accent-hover`/`--accent-subtle` iguais em dark e light, mas os estados success/warning/error/info mudam. Seguir assim (não unificar).
2. **Espaçamento/tipografia não eram variáveis.** O protótipo usa valores inline. Derivei `--space-*`, escala tipográfica e `--font-mono` como variáveis de apoio a partir dos valores já usados. Nenhum valor novo foi inventado; todos derivam do protótipo.
3. **Checkbox/toggle não existem no protótipo.** O "Canal de aprovação" é um `<select>`. Defini controles coerentes (Seção 2.5) com tokens do protótipo; o `fe-review` valida contra o protótipo se houver versão futura.
4. **Modal/skeleton/empty-state não têm classe no protótipo.** Declarados no PLANO-FRONTEND como primitives. Defini anatomias coerentes (Seção 2.10–2.17) com tokens do protótipo.
5. **Botão "Conectar"/"Ajustar"/zoom no flow:** o protótipo usa `showToast` de "informação" como terminal. **Desvio do feedback do usuário** (nenhum botão sem ação). Na implementação real, "Conectar" entra em modo de seleção de dois nós (real), "Ajustar" faz fit-to-view (real), zoom altera o transform (real). Este design system **especifica** o comportamento real; os `showToast` de fake do protótipo não entram.
6. **Ícone MCP:** o protótipo usa o logo preenchido da marca MCP. O lucide não tem ícone de marca MCP; usei `Cube` (neutro). Se houver ícone de marca aprovado, prevalece.
7. **`--card-accent` customizável por cartão.** O protótipo controla a barra superior de cada agent-card via `style="--card-accent: var(--...)"`. Mantivero como variável de cascata (`var(--card-accent, var(--accent))`) para permitir cor por tipo de agente.
8. **Bolhas de chat com radius 4px.** O protótipo sobrescreve `--radius` nas bolhas com `border-bottom-*-radius: 4px` (user = direito, ai = esquerdo). Manter explícito.
9. **Sombra escuro forte.** `--shadow` escuro tem opacidade 0.4 (forte). É intencional no protótipo (profundidade em fundo quase preto). Manter (fidelidade); o `fe-review` não deve "amaciar".
10. **Zoom range.** Protótipo limita zoom entre 0.1–2.0 (wheel) e 0.1–2.0 (botões). Manter.
11. **Grade do canvas.** `radial-gradient` de pontos, `background-size: 24px 24px`, cor `var(--border)`. Manter.
12. **Rivvn bar.** Usa `tool-status.deployed` como badge "contrato ativo" no protótipo; na V1 real a UI fica desabilitada (contrato §10). O token é o mesmo; o estado funcional muda.

---

## 8. Contratos públicos expostos por este design system

- **Tokens CSS** (Seção 1): todos os `var(--...)` listados são a superfície que `components/ui/*` e `components/layout/*` consomem. Nomes e valores são fixos; mudanças pedem revisão do `fe-review`.
- **Mapeamento de ícones** (Seção 4): superfície que os nós de tela consomem para substituir SVGs inline.
- **Variantes de componente** (Seção 2): assinaturas de classe CSS (`.btn`, `.btn-primary`, `.btn-sm`, `.status-dot.running`, `.agent-card.urgent`, etc.) que os nós de tela reutilizam.

> **Arquivos tocados:** nenhum. Este nó só cria `docs/superpowers/plans/DESIGN-SYSTEM.md`. O bloco CSS da Seção 1.8 é entregue **dentro deste documento**; o `fe-shell` (dono de `app/globals.css`) aplica. Nenhuma mudança solicitada a outros donos (cores/tipografia não são de `package.json`, `docker-compose` ou `main.py`).
