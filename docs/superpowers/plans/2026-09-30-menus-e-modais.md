# Menus, modais e rolagem — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Quando executar:** depois de concluir o plano `2026-09-29-redesign-usabilidade.md` (Tasks 1–18). As Tasks 19–26 continuam a numeração dele. O QA visual das modais e da rolagem fica na Task 26 deste plano; no plano anterior, o passo 3 da Task 18 não precisa recapturar modais.

**Goal:** Reduzir a rolagem no portal (preferência: nenhuma; quando necessária, estilizada) e corrigir o menu ⋮ cortado nas tabelas e refazer as modais do portal para que tenham tamanho adequado, conteúdo bem posicionado em colunas e nenhuma rolagem no corpo em 1280×720 e 1440×900, com folha em tela cheia abaixo de 768px.

**Architecture:** Duas peças compartilhadas no `components/ui/`: um `Popover`/`RowMenu` renderizado em portal com posicionamento calculado (resolve o corte), e um `Modal` com tamanhos `sm|md|lg|xl`, helpers de layout (`FormGrid`, `FormSection`) e modo folha no mobile. Depois cada modal existente é migrada para o tamanho e o layout certos. Em seguida, uma política global de rolagem (scrollbar estilizada e telas que ocupam a altura da janela) reduz a rolagem no sistema todo. Nada muda no backend.

**Tech Stack:** Next.js 14, React 18, vitest com Testing Library e Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-redesign-usabilidade-design.md`, seção 7 (adendo de 2026-09-30).

## Global Constraints

- Valem as restrições do plano `2026-09-29-redesign-usabilidade.md` (idioma pt-BR, erros com recuperação, contraste, acessibilidade, commits, nunca fazer push, `git add` só com caminhos explícitos, não tocar em `.codex/`, reiniciar o container `portal` antes de verificar no navegador).
- **Sem rolagem no corpo da modal** em 1280×720 e 1440×900. Rolagem só dentro de componentes que crescem por natureza (editor de texto, lista longa, saída de teste), nunca no corpo.
- **Menus flutuantes em portal**, nunca dentro de container com overflow, e sem cópias do mesmo menu.
- **API do `Modal` compatível:** `size` ganha `sm|md|lg` além de `xl`; quem não passa `size` continua `md`. Nenhuma modal existente pode perder o botão do rodapé ou o foco.
- Não alterar a lógica de negócio das modais; só layout, tamanho e estrutura dos campos. Os testes existentes continuam passando (ajustar seletores só quando o DOM mudar de fato).

## Review Focus

1. **Menu da última linha.** Em uma tabela com uma linha, o menu abre inteiro e visível (para baixo se couber, para cima se não). Nunca gera barra de rolagem na página.
2. **Foco e ESC.** Com um menu ou modal aberto, ESC fecha e o foco volta ao botão de origem. Durante uma operação em andamento (`busy`) a modal não fecha por ESC nem por clique fora.
3. **Sem rolagem no corpo.** Nenhuma modal de formulário em 1280×720 tem `scrollHeight > clientHeight` no corpo. O teste e2e da Task 26 é a prova; não basta olhar.
4. **Mobile.** Em 390px a modal é folha em tela cheia com rodapé fixo, e o teclado virtual não cobre o botão principal (usar `100dvh`).
5. **Edição de textos longos.** O editor do template da skill e os campos de código das tools preservam o conteúdo ao trocar de aba, ao redimensionar e ao abrir/fechar a pré-visualização.

---

## Estrutura de arquivos

- `agent-portal/components/ui/popover.tsx` (novo): `Popover` (portal, `position: fixed`, flip, fechar ao rolar/redimensionar/ESC/clique fora, devolver foco) e `RowMenu` (botão ⋮ + lista de itens `role="menu"`).
- `agent-portal/components/ui/modal.tsx`: tamanhos `sm|md|lg|xl`, modo folha no mobile, foco preso, `busy` que bloqueia fechar.
- `agent-portal/components/ui/form-layout.tsx` (novo): `FormGrid` (1 coluna, 2 colunas a partir de 1024px) e `FormSection` (título, ajuda, largura total opcional).
- `agent-portal/components/ui/data-table.tsx`: usa `RowMenu` nas duas variantes (tabela e lista mobile).
- Modais: `components/library/skills-library.tsx`, `tools-editor.tsx`, `mcp-servers-library.tsx`, `knowledge-view.tsx`; `components/integrations/git-connection-form.tsx` e `git-connections.tsx`; `components/knowledge/kb-header.tsx`, `documents-panel.tsx`, `kb-chat.tsx`; `components/flow/run-inputs-modal.tsx`; `components/approvals/approval-queue.tsx`; `components/agents/delete-agent-modal.tsx`; `components/pipelines/pipeline-actions-menu.tsx` e `pipeline-header.tsx`; `components/monitor/pipeline-monitor.tsx`.
- `agent-portal/app/globals.css` (regras globais de scrollbar) e `agent-portal/components/ui/scroll-area.tsx` (novo).
- `e2e/tests/12-modais-e-menus.spec.ts` (novo) e `docs/superpowers/validacoes/qa-redesign.md` (seção de modais).

---

### Task 19: Popover e RowMenu em portal (corrige o menu ⋮ cortado)

**Files:**
- Create: `agent-portal/components/ui/popover.tsx`, `agent-portal/components/ui/popover.test.tsx`
- Modify: `agent-portal/components/ui/data-table.tsx` (as duas variantes do menu), `agent-portal/components/ui/index.ts`, `agent-portal/components/pipelines/pipeline-actions-menu.tsx`, `agent-portal/components/pipelines/pipeline-header.tsx`, `agent-portal/app/(dashboard)/pipelines/[id]/page.tsx` e `agent-portal/components/layout/app-topbar.tsx` (só se o menu estiver dentro de container com overflow ou duplicar o padrão)

- [ ] **Step 1: Inventário.** Listar todo uso de `role="menu"` e `position: "absolute"` com `top: "100%"` em `components/` e `app/`. Para cada um, anotar se está dentro de um ancestral com `overflow` diferente de `visible` (incluindo `overflowX: "auto"` do `DataTable`, linha ~404). Registrar a tabela no corpo do commit.
- [ ] **Step 2: Testes do `Popover` (falham primeiro).**
  - abre num portal no `body`, fora do container com overflow;
  - posiciona abaixo do botão; quando não cabe abaixo, abre para cima;
  - fecha com ESC, ao clicar fora e ao rolar ou redimensionar a janela; devolve o foco ao botão;
  - setas e Enter navegam pelos itens (`role="menuitem"`).
- [ ] **Step 3: Implementar `Popover` e `RowMenu`.** Posição via `getBoundingClientRect()` do botão, `position: fixed`, `zIndex` acima do container de tabelas e abaixo das modais. Um único componente, sem duplicação.
- [ ] **Step 4: Trocar os menus.** `DataTable` (tabela e lista mobile) usa `RowMenu`; `PipelineActionsMenu` e os demais do inventário que estiverem cortados passam a usar `Popover`. Teste do `DataTable`: tabela com **uma** linha, abrir o menu e afirmar que o menu está no `body` e totalmente dentro da viewport.
- [ ] **Step 5: Rodar** vitest das pastas `ui`, `library`, `integrations` e `pipelines`, `tsc` e lint. Reiniciar o `portal` e conferir no navegador em Integrações (1 conexão), Skills, Tools, MCP e Pipelines.
- [ ] **Step 6: Commit** — `fix(ui): menus em portal para nao serem cortados pela tabela`

---

### Task 20: Modal v2 (tamanhos, folha no mobile) e helpers de formulário

**Files:**
- Modify: `agent-portal/components/ui/modal.tsx`, `agent-portal/components/ui/modal.test.tsx`, `agent-portal/components/ui/index.ts`
- Create: `agent-portal/components/ui/form-layout.tsx`, `agent-portal/components/ui/form-layout.test.tsx`

- [ ] **Step 1: Testes do `Modal` (falham primeiro).**
  - `size="sm"|"md"|"lg"|"xl"` aplicam as larguras da spec 7.1 (440, 640, 1040, 1200), sempre limitadas a `95vw`;
  - `maxHeight` do painel `92vh`, com cabeçalho e rodapé fora da área rolável;
  - abaixo de 768px o painel ocupa `100dvh` e `100vw`, sem bordas arredondadas, com rodapé fixo;
  - ESC e clique fora fecham, exceto com `busy`;
  - foco preso dentro do painel e devolvido ao elemento de origem ao fechar;
  - quem não passa `size` continua com o comportamento atual (`md`).
- [ ] **Step 2: Implementar.** Adicionar as props `size` (novos valores) e `busy?: boolean`. Manter a rolagem do miolo apenas como rede de segurança (o objetivo é não precisar dela). Remover o comentário E5 que justifica a altura de 720px.
- [ ] **Step 3: `FormGrid` e `FormSection`.** `FormGrid` tem 1 coluna e passa a 2 colunas a partir de 1024px, com `gap` de 16px e sem altura fixa. `FormSection` recebe `title`, `hint` e `fullWidth` (ocupa as duas colunas). Testes: renderização das colunas e de `fullWidth`.
- [ ] **Step 4: Rodar** vitest de `ui`, `tsc` e lint. Nenhum teste de modal existente pode quebrar; se um seletor mudar porque o DOM mudou, ajustar e dizer no commit.
- [ ] **Step 5: Commit** — `feat(ui): modal com tamanhos, folha no mobile e helpers de formulario`

---

### Task 21: Modal de skills (referência das demais)

**Files:**
- Modify: `agent-portal/components/library/skills-library.tsx` (criar/editar, linha ~337; ver template, linha ~464), testes correspondentes
- Modify (se necessário): `agent-portal/components/ports/ports-editor.tsx` (variante compacta)

- [ ] **Step 1: Teste do layout (falha primeiro).** A modal "Nova skill" usa `size="lg"`; em 1440×900 (jsdom: checar a estrutura) tem o editor do template na coluna direita, Nome/Descrição/Categoria/Variáveis na esquerda e a faixa de Inputs/Outputs de largura total; o botão "Criar skill" está no rodapé.
- [ ] **Step 2: Reorganizar** conforme a spec 7.2: `FormGrid` de duas colunas, editor do template ocupando a altura disponível com rolagem interna própria, abas Editar/Pré-visualizar mantidas e `PortsEditor` compacto em `FormSection fullWidth` com Inputs e Outputs lado a lado (até 3 linhas visíveis, "adicionar" e "Ver JSON").
- [ ] **Step 3: Modal "Ver template"** em `md` ou `lg` conforme o tamanho do conteúdo, sem rolagem do corpo (o texto do template rola dentro do seu bloco).
- [ ] **Step 4: Validar no navegador** em 1440×900 e 1280×720: corpo sem rolagem, botões visíveis. Conferir que o texto digitado no template não se perde ao alternar abas.
- [ ] **Step 5: Rodar** vitest de `library`, `tsc` e lint.
- [ ] **Step 6: Commit** — `feat(biblioteca): modal de skill em duas colunas sem rolagem`

---

### Task 22: Modais de Tools e MCP

**Files:**
- Modify: `agent-portal/components/library/tools-editor.tsx` (linhas ~395, ~492, ~572), `agent-portal/components/library/mcp-servers-library.tsx` (linhas ~369, ~458, ~537) e os testes

- [ ] **Step 1: Classificar** cada uma das seis modais (criar, editar, testar/confirmar) em `sm`, `md` ou `lg` e registrar a tabela no commit. Formulários com código ou muitos campos → `lg` em duas colunas; confirmações → `sm`.
- [ ] **Step 2: Tools.** Metadados (nome, descrição, categoria, timeout) à esquerda; editor de código à direita com rolagem interna; parâmetros em `FormSection fullWidth`; o resultado do teste aparece num bloco de altura limitada com rolagem interna, sem esticar a modal.
- [ ] **Step 3: MCP.** Transporte, comando ou URL, argumentos e variáveis de ambiente em duas colunas; a lista de tools descobertas em bloco com altura limitada e rolagem interna; o status do teste inline.
- [ ] **Step 4: Validar no navegador** (1440×900 e 1280×720) e rodar vitest de `library`, `tsc` e lint.
- [ ] **Step 5: Commit** — `feat(biblioteca): modais de tools e mcp em colunas sem rolagem`

---

### Task 23: Demais modais (integrações, knowledge, execução, aprovações, confirmações)

**Files:**
- Modify: `components/integrations/git-connection-form.tsx`, `components/integrations/git-connections.tsx`, `components/knowledge/kb-header.tsx`, `components/knowledge/documents-panel.tsx`, `components/knowledge/kb-chat.tsx`, `components/library/knowledge-view.tsx`, `components/flow/run-inputs-modal.tsx`, `components/approvals/approval-queue.tsx`, `components/agents/delete-agent-modal.tsx`, `components/pipelines/pipeline-actions-menu.tsx`, `components/monitor/pipeline-monitor.tsx` e os testes

- [ ] **Step 1: Classificar as 22 ocorrências de `<Modal`** em uma tabela (arquivo, finalidade, tamanho `sm|md|lg|xl`) e registrar no corpo do commit. Regra: confirmação de uma pergunta → `sm`; formulário de até 4 campos → `md`; formulário rico → `lg`; grafo e aprovação com conteúdo → `xl`.
- [ ] **Step 2: Integrações.** A modal de conexão (nome, token, organização, teste inline) em `md` ou `lg`, com o resultado do teste ao lado do botão Testar, sem esticar.
- [ ] **Step 3: Knowledge.** Criar e editar base (nome, descrição, escopo, tamanho de chunk) em duas colunas; excluir documento e conversa em `sm`.
- [ ] **Step 4: Entradas da execução.** Uma entrada por linha com a descrição ao lado; com muitas entradas, `lg` em duas colunas, sem rolagem do corpo.
- [ ] **Step 5: Aprovações.** O conteúdo a aprovar e os botões de decisão visíveis ao mesmo tempo em `xl`; o campo de feedback de "Argumentar" dentro da própria modal, sem rolagem do corpo (o conteúdo longo rola dentro do seu bloco).
- [ ] **Step 6: Confirmações** (excluir agente, pipeline, conversa, documento, nó) todas em `sm`, com o que será perdido em uma linha e o botão destrutivo à direita.
- [ ] **Step 7: Rodar** vitest completo do portal, `tsc` e lint.
- [ ] **Step 8: Commit** — `feat(portal): modais com tamanho e layout adequados`

---

### Task 24: Scrollbar estilizada e `ScrollArea`

**Files:**
- Modify: `agent-portal/app/globals.css`
- Create: `agent-portal/components/ui/scroll-area.tsx`, `agent-portal/components/ui/scroll-area.test.tsx`
- Modify: `agent-portal/components/ui/index.ts`; contêineres rolantes listados no inventário (Step 1)

- [ ] **Step 1: Inventário de rolagem.** Listar todo `overflow`/`overflowY`/`overflowX` em `auto|scroll` e todo `maxHeight` em `components/` e `app/` (cerca de 22 arquivos: monitor `files-tab`, `logs-tab`, `results-tab`, `stage-strip`; `kb-chat`, `documents-panel`; `agent-palette`, `properties-panel`, `EdgePanel`; `agent-chat`; `app-sidebar`, `app-shell`; `data-table`, `table`, `drawer`, `modal`, `toast`; `approval-queue`; `command-palette`; `stats-strip`; `ports-editor`; `pipelines/[id]/page.tsx`). Anotar para cada um: finalidade, se é necessária e se aninha dentro de outra rolagem. Registrar a tabela no corpo do commit.
- [ ] **Step 2: Estilo global (falha primeiro no teste de contraste/estilo).** Em `globals.css`: `scrollbar-width: thin` e `scrollbar-color: var(--border) transparent` em `*`; `::-webkit-scrollbar` de 8px com trilho transparente, polegar arredondado em `var(--border)` que passa a `var(--text-muted)` no hover, e `::-webkit-scrollbar-corner` transparente; valores certos nos temas claro e escuro. O polegar precisa ser visível (razão ≥ 3:1 contra o fundo). Estender `contrast.test.ts` para checar esse par.
- [ ] **Step 3: `ScrollArea`.** Componente que envolve um contêiner rolante com `tabIndex=0`, `role="region"` e `aria-label`, `scrollbar-gutter: stable` e uma sombra sutil nas bordas quando há mais conteúdo para rolar. Testes: sombra aparece só quando há overflow; é focável por teclado; rotula a região.
- [ ] **Step 4: Aplicar.** Trocar os contêineres rolantes necessários do inventário por `ScrollArea` (ou pelas regras globais, quando um `div` simples basta). Nunca dois `ScrollArea` aninhados.
- [ ] **Step 5: Rodar** vitest, `tsc` e lint. Reiniciar o `portal` e conferir visualmente nos dois temas.
- [ ] **Step 6: Commit** — `feat(ui): scrollbar estilizada e ScrollArea acessivel`

---

### Task 25: Reduzir a rolagem nas telas (altura da janela, painéis, paginação)

**Files:**
- Modify: `agent-portal/components/layout/app-shell.tsx`, `agent-portal/app/(dashboard)/layout.tsx` e as telas abaixo (conforme o diagnóstico do Step 1)
- Modify: `agent-portal/components/ui/data-table.tsx` (cabeçalho `sticky` e paginação), `agent-portal/components/monitor/*`, `agent-portal/components/knowledge/*`, `agent-portal/components/flow/agent-palette.tsx`, `agent-portal/app/(dashboard)/pipelines/[id]/page.tsx` e os testes

- [ ] **Step 1: Diagnóstico por tela.** Em 1440×900 e 1280×720, com dados realistas (≥ 12 agentes, ≥ 12 pipelines, um run com 4 etapas, uma base com 10 documentos, conversa com 6 mensagens, logs longos), registrar para Overview, Agentes (lista e detalhe em cada aba), Pipelines, editor, monitor (cada aba), Aprovações, Knowledge, Skills, Tools, MCP e Integrações: a página inteira rola? há rolagem aninhada? há rolagem horizontal? Guardar a tabela em `qa-redesign.md` (seção "Rolagem — antes").
- [ ] **Step 2: Shell na altura da janela.** `100dvh` no shell (em vez de `100vh`), sidebar e topbar fixas, só a área principal rola. Conferir que nenhuma tela produz duas barras verticais ao mesmo tempo (página + miolo).
- [ ] **Step 3: Telas de trabalho em painéis.** Editor, monitor, chat de construção de agente e Knowledge ocupam a altura disponível e dividem em painéis; a rolagem fica dentro de cada painel, e o cabeçalho e as ações da tela ficam sempre visíveis. A página em si não rola nessas telas.
- [ ] **Step 4: Listas.** `DataTable` com cabeçalho `sticky` e paginação (25 linhas por página, com controle "Anterior / Próxima" e contagem), mantendo busca, filtro e ordenação. A paleta de agentes do editor e a lista de arquivos do monitor têm altura própria com `ScrollArea`.
- [ ] **Step 5: Conteúdo denso.** Resultado, logs e diff longos ficam recolhidos com "Ver mais" ou em painel de altura limitada, em vez de esticar a página. O resumo de aprovações já recolhe em 3 linhas; conferir o mesmo padrão nas demais telas.
- [ ] **Step 6: Eliminar rolagem aninhada e horizontal.** Corrigir cada caso do diagnóstico (Step 1). Tabelas largas reduzem colunas ou escondem as secundárias em telas estreitas, em vez de rolar na horizontal; quando não houver como, a rolagem horizontal fica só dentro da tabela, com `ScrollArea`.
- [ ] **Step 7: Testes.** Vitest para paginação, cabeçalho `sticky` e "Ver mais". Reexecutar o diagnóstico do Step 1 e registrar a seção "Rolagem — depois", com a meta: zero rolagem aninhada, zero rolagem horizontal e nenhuma rolagem da página nas telas de trabalho.
- [ ] **Step 8: Rodar** vitest completo, `tsc` e lint.
- [ ] **Step 9: Commit** — `feat(portal): menos rolagem - shell na altura da janela, paineis e paginacao`

---

### Task 26: E2E sem rolagem, QA visual e registro

**Files:**
- Create: `e2e/tests/12-modais-e-menus.spec.ts`
- Modify: `docs/superpowers/validacoes/qa-redesign.md`, `docs/superpowers/validacoes/PENDENCIAS.md`

- [ ] **Step 1: e2e em 1280×720 e 1440×900.** Para cada modal de formulário ou confirmação (nova skill, editar skill, nova tool, novo MCP, conexão Git, criar base, entradas da execução, excluir agente, decisão de aprovação): abrir e afirmar `scrollHeight <= clientHeight` no corpo, que o botão principal está dentro da viewport e que o cabeçalho e o rodapé estão visíveis.
- [ ] **Step 2: e2e do menu ⋮.** Em Integrações com **uma** conexão, abrir o menu da linha e afirmar que está totalmente visível e que a página não ganhou barra de rolagem. Repetir em Skills, Tools, MCP e Pipelines.
- [ ] **Step 2b: e2e de rolagem das telas.** Em 1440×900 e 1280×720, para cada tela principal com dados realistas (as mesmas do diagnóstico da Task 25), afirmar: sem rolagem horizontal da página (`scrollWidth <= clientWidth`); sem rolagem aninhada (nenhum contêiner rolante dentro de outro); nas telas de trabalho (editor, monitor, chat, Knowledge), a página não rola. A scrollbar renderiza com a largura fina (8px) nos contêineres rolantes.
- [ ] **Step 3: e2e em 390px.** As modais abrem como folha em tela cheia, com rodapé visível; o miolo rola quando o conteúdo é maior.
- [ ] **Step 4: QA visual.** Capturar cada modal e o menu ⋮ em 1440×900 e 390px, guardar em `docs/superpowers/validacoes/redesign-screenshots/modais/` e registrar em `qa-redesign.md` "atendido", "parcial" (com o motivo) ou "não atendido" por modal.
- [ ] **Step 5: Regressão.** vitest completo, `tsc`, lint, `npm run build` e as specs e2e afetadas, uma por vez. Registrar as contagens. Levar as pendências para `PENDENCIAS.md`.
- [ ] **Step 6: Commit** — `test(portal): e2e de modais sem rolagem e menus, QA visual`
