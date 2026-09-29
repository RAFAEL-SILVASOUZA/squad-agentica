# Revisão de Design e Usabilidade — Agent Portal

Data: 2026-09-29
Escopo: avaliação tela a tela do portal em `http://localhost` (desktop 1440px e mobile 390px), comparada com produtos maduros do mesmo tipo.
Método: navegação real em todas as telas com um usuário próprio criado pelo cadastro do portal (`revisor.design@example.com`), screenshots em `screenshots/` (mesma pasta), snapshots de acessibilidade para validar contraste/labels e consulta de docs/pós públicos das referências.

Avisos de contexto:

- O stack está em **modo mock**: respostas de agentes e do chat são simuladas. A avaliação é de layout e usabilidade, não de qualidade dos textos.
- O portal reiniciou algumas vezes durante os testes (Task 13); cada tela foi recarregada e capturada após o retorno.
- Não foi alterado nenhum código nem dependência; nada fora deste documento e das screenshots foi tocado.

Índice de screenshots:

| # | Arquivo | Tela |
|---|---------|------|
| 01 | `screenshots/01-login.png` | Login |
| 02 | `screenshots/02-cadastro.png` | Cadastro |
| 03 | `screenshots/03-dashboard-vazio.png` | Dashboard (estado inicial) |
| 04 | `screenshots/04-novo-agente-chat-inicial.png` | Novo agente, chat vazio |
| 05 | `screenshots/05-novo-agente-chat-preview.png` | Novo agente, chat com resposta + preview |
| 06 | `screenshots/06-novo-agente-preview-fullpage.png` | Novo agente, página completa |
| 07 | `screenshots/07-novo-agente-erro-salvar-404.png` | Erro "Recurso não encontrado" ao salvar |
| 08 | `screenshots/08-dashboard-com-agente.png` | Dashboard com 1 agente |
| 09 | `screenshots/09-agente-detalhe-fullpage.png` | Detalhe do agente (página completa) |
| 10 | `screenshots/10-skills-empty-modal.png` | Skills: estado vazio + modal de criação |
| 11 | `screenshots/11-skills-lista.png` | Skills: lista com 1 skill |
| 12 | `screenshots/12-tools-empty.png` | Tools Custom (vazio) |
| 13 | `screenshots/13-mcp-empty.png` | MCP Servers (vazio) |
| 14 | `screenshots/14-knowledge-base-criada-sem-selecionar.png` | Knowledge: base criada sem ser selecionada |
| 15 | `screenshots/15-knowledge-chat-resposta.png` | Knowledge: chat com resposta sem fontes |
| 16 | `screenshots/16-pipelines-empty.png` | Pipelines (vazio) |
| 17 | `screenshots/17-pipeline-editor-vazio.png` | Editor de fluxo (sem nós) |
| 18 | `screenshots/18-pipeline-editor-com-no.png` | Editor de fluxo com 1 nó |
| 19 | `screenshots/19-pipeline-monitor-executando.png` | Monitor: execução pendente/executando |
| 20 | `screenshots/20-pipeline-monitor-abas-logs.png` | Monitor: aba Logs |
| 21 | `screenshots/21-pipeline-monitor-abas-historico.png` | Monitor: aba Histórico |
| 22 | `screenshots/22-pipeline-monitor-abas-arquivos.png` | Monitor: aba Arquivos do projeto |
| 23 | `screenshots/23-pipeline-monitor-concluido-resultado.png` | Monitor: concluído, aba Resultado |
| 24 | `screenshots/24-pipelines-lista-com-pipeline.png` | Pipelines: lista com 1 pipeline |
| 25 | `screenshots/25-aprovacoes-empty.png` | Aprovações (vazio) |
| 26 | `screenshots/26-integracoes-empty.png` | Integrações (vazio) |
| 27 | `screenshots/27-integracoes-modal-conexao.png` | Integrações: modal nova conexão |
| 30 | `screenshots/30-mobile-dashboard.png` | Mobile: dashboard |
| 31 | `screenshots/31-mobile-menu-aberto.png` | Mobile: menu lateral aberto |
| 32 | `screenshots/32-mobile-pipeline-editor.png` | Mobile: editor de fluxo |
| 33 | `screenshots/33-mobile-pipeline-monitor.png` | Mobile: monitor |
| 34 | `screenshots/34-mobile-agente-detalhe.png` | Mobile: detalhe do agente |

---

## 1. Login e Cadastro

Telas: `/login` (01), `/register` (02).
Referência: Linear (autenticação), Vercel (autenticação).

### O que funciona

- Card centralizado único, foco total no formulário; hierarquia clara (título > campos > CTA).
- Acento laranja consistente para o botão primário e o link de troca ("Criar conta").
- Fluxo cadastro → login automático sem fricção (observado na prática: após "Criar conta" o usuário cai no dashboard autenticado).

### Problemas (em ordem de gravidade)

1. **Placeholder do e-mail é `admin@local`** (01). Sinaliza uma conta demo dentro de um produto; quem está cadastrando pela primeira vez fica na dúvida se deve usar esse valor.
2. **Sem "Esqueci minha senha"**. Sem o link, a conta é permanente ou perdida, e falta uma opção padrão em qualquer produto maduro.
3. **Sem indicação de requisitos de senha** (tamanho mínimo, complexidade) no cadastro; o usuário só descobre regras no erro, quando houver.
4. **Contraste baixo** do subtítulo ("Acesse o Agent Portal") e do rodapé ("Não tem conta?") sobre o fundo escuro; viola WCAG 1.4.3 para texto pequeno.
5. **Sem loading state no botão** além do texto trocar (no cadastro vira "Criando..."; no login não foi observado estado intermediário).

### Referência que faz melhor e por quê

**Linear/Vercel**: o card de login traz um segundo item útil (SAML/SSO ou "criar conta" com destaque), o placeholder do e-mail é neutro (ex.: "you@company.com"), e há "Forgot password?" como link terciário logo abaixo da senha. O contraste do texto secundário passa em 4.5:1 sobre o fundo.

### Proposta

```
┌─────────────────────────────────────────────┐
│  ┌─────────────────────────────────────┐    │
│  │  [AP]  Entrar                       │    │
│  │  Acesse o Agent Portal   (≥4.5:1)  │    │
│  │                                     │    │
│  │  E-mail                            │    │
│  │  ┌───────────────────────────────┐  │    │
│  │  │ voce@empresa.com              │  │    │
│  │  └───────────────────────────────┘  │    │
│  │  Senha                    Esqueci?  │    │
│  │  ┌───────────────────────────────┐  │    │
│  │  │ ●●●●●●●●                      │  │    │
│  │  └───────────────────────────────┘  │    │
│  │  [        →  Entrar         ]  ← CTA│    │
│  │                                     │    │
│  │  Não tem conta? Criar conta         │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
Cadastro: adicionar "Mínimo 8 caracteres" sob a senha,
com validação inline ao sair do campo (blur).
```

Mudanças: placeholder neutro; link "Esqueci?"; hint de requisitos de senha; subir o contraste do texto secundário para ≥ 4.5:1.

---

## 2. Dashboard

Tela: `/` (03, 08; mobile 30).
Referência: Vercel (overview), Linear (inbox/overview), GitHub (home).

### O que funciona

- Shell clássico (topbar 56px + sidebar 240px + main) com navegação agrupada e legível (PRINCIPAL / PIPELINES / BIBLIOTECA).
- Estados vazios com ícone + explicação + CTA ("Comece criando seu primeiro agente") — o padrão certo para primeiro uso.
- Badges de status por cor (verde/âmbar/vermelho) e contagem de aprovações pendentes sincronizada por WebSocket (badge no sino).
- Em mobile a sidebar vira overlay com hamburger (31): comportamento correto.

### Problemas (em ordem de gravidade)

1. **Título da página é "Agentes"**, mas a tela é um dashboard (03). O primeiro bloco de conteúdo é a lista de agentes, mas existem também runs e aprovações; o usuário não consegue nomear a tela que está olhando.
2. **Cards de métrica apontam para /approvals quando vazios** (03: todos os 4 links vão para /approvals). Clicar em "Runs nas últimas 24h: 0" leva para aprovações — destino errado; quando há dados o link passa a ir para o run (30), o comportamento fica inconsistente.
3. **Gramática**: "1 agentes · 0 pipelines em execução" (08, 30). Plural fixo.
4. **Busca rotulada "Buscar agente"** (a11y) com placeholder "Buscar por nome, descrição ou tipo..." (03) — rótulo e placeholder divergem; o placeholder promete buscar por descrição e tipo, o que o campo talvez não faça.
5. **4 métricas zeradas ocupam 20% da tela** no primeiro uso (03). É espaço que poderia ir para onboarding: "1) crie um agente 2) monte uma pipeline 3) execute".
6. Sem skeleton de carregamento: a lista de agentes aparece só quando a resposta da API chega (sem placeholder entre o shell e o conteúdo).

### Referência que faz melhor e por quê

**Vercel**: o overview tem título "Overview" com o escopo (projeto) explícito, métricas que sempre apontam para as listas corretas (Deployments → /deployments) e um link secundário "View all". **Linear**: o overview usa "Inbox"/"Overview" e, vazio, mostra um checklist de onboarding em vez de cards zerados.

### Proposta

```
┌──────────────────────────────────────────────────────────┐
│  Overview                          [ + Novo Agente ]     │
├──────────────┬──────────────┬──────────────┬─────────────┤
│ ▶ 0          │ ⏱ 0          │ ✓ 0          │ ⚠ 0         │
│ Em execução  │ Runs 24h     │ Concluídos   │ Aprovações  │  ← cada card
│  [ver →]     │  [ver →]     │  [ver →]     │  [responder→]│    liga à sua
├──────────────┴──────────────┴──────────────┴─────────────┤    lista correta
│  PRIMEIROS PASSOS (só enquanto tudo estiver zerado)      │
│  ☐ Crie um agente        ☐ Monte uma pipeline            │
│  ☐ Adicione documentos   ☐ Execute e acompanhe no monitor│
├──────────────────────────────────────────────────────────┤
│  AGENTES (n)              BUSCA [__________] [tipo ▾]    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🤖 Consultor de Catálogo v2  · consultant · Ocioso │  │
│  └────────────────────────────────────────────────────┘  │
├───────────────────────────────┬──────────────────────────┤
│  RUNS RECENTES                │  APROVAÇÕES PENDENTES    │
│  (skeleton de 2 linhas)       │  (skeleton de 1 linha)   │
└───────────────────────────────┴──────────────────────────┘
```

Mudanças: título "Overview"; links das métricas sempre para as listas certas; pluralização pt-BR ("1 agente"); rótulo e placeholder da busca alinhados; onboarding condicional no lugar dos cards zerados; skeletons nas listas.

---

## 3. Agentes

Telas: lista no dashboard (08), construção por chat `/agents/new` (04, 05, 06), detalhe `/agents/[id]` (09; mobile 34).
Referência: ChatGPT com arquivos (construção por conversa), Notion AI (assistente que produz artefato), n8n (painel contextual de configuração).

### O que funciona

- O conceito de "construir conversando" está bem montado: chat à esquerda, **preview vivo** do agente à direita que atualiza conforme a conversa (05) — padrão do tipo generative-UI que funciona.
- O preview resume o agente em blocos legíveis: EXECUÇÃO (modelo, iterações, timeout, shell), MOCHILA (skills, knowledge) e CONTRATO DE FLUXO (entrada/saída/ações).
- No detalhe, o chat de edição abre com contexto do agente ("Posso ajudar a ajustar o agente X. O que você quer mudar?").

### Problemas (em ordem de gravidade)

1. **Salvar agente falha com "Recurso não encontrado" (404)** (07) — reproduzido na tela `/agents/new`: o chat gera o rascunho, o botão "Salvar agente" habilita, e o clique devolve um toast genérico de erro. O fluxo central do produto (agente por chat) **quebra** neste ambiente. Além de bug, o tratamento do erro é opaco: sem dizer o que falhou, sem "Tentar de novo", sem preservar o rascunho de forma explícita.
2. **Sem validação visível do rascunho** no preview: o painel mostra os campos gerados, mas não indica o que está inválido/faltando para o "Salvar" funcionar (ex.: contrato de fluxo sem ações).
3. **Contradição de modelo** no detalhe (09): o header do preview mostra "Qwen3.8-27B-Q8_0 (definido pelo servidor)" enquanto o campo "Modelo" do formulário continua "gpt-4o". O usuário não sabe qual valor vai valer.
4. **Detalhe é uma página única muito longa** (09): chat + identidade + contrato + execução + mochila empilhados. Não há abas nem âncoras; encontrar "Mochila" exige rolagem longa.
5. **Seletores "Nenhuma X cadastrada" desabilitados** na mochila (09): quando não há skills/tools, o botão "Adicionar" fica desabilitado e o usuário não pode sair para criar — falta o affordance "Criar skill →" (o padrão do primeiro uso).
6. **Redundância**: a descrição do preview repete a descrição do chat (05).
7. No mobile (34) o layout empilha chat acima do formulário; o campo de mensagem fica fora da dobra e o painel de preview some até rolar — o loop principal (escrever → ver resultado) quebra no celular.

### Referência que faz melhor e por quê

**ChatGPT**: a resposta com arquivo anexado mostra o artefato ao lado do chat, com ações diretas sobre ele (editar, baixar, usar) e estado de processamento visível. **n8n**: ao selecionar um nó, abre painel lateral de propriedades *contextual*; o resto da tela fica estável. Aqui a "propriedade do agente" deveria ser um painel, não uma página inteira.

### Proposta (detalhe do agente, com abas)

```
┌──────────────────────────────────────────────────────────────┐
│ ←  Consultor de Catálogo v2  · consultant · Ocioso   [⋮]     │
│    "Agente que responde perguntas sobre o catálogo..."       │
│  [Visão geral] [Conversar] [Mochila] [Execução]              │
├───────────────────────────────┬──────────────────────────────┤
│  Conversar com o assistente   │  RASCUNHO (ao vivo)          │
│ ┌───────────────────────────┐ │  ✔ válido para salvar        │
│ │ IA: Posso ajudar a ajustar│ │  ┌────────────────────────┐  │
│ │ o agente X. O que mudar?  │ │  │ Modelo  gpt-4o (efetivo│  │
│ └───────────────────────────┘ │  │ Qwen3.8… — ver aviso)  │  │
│ ┌───────────────────────────┐ │  │ Max it. 5  Timeout 60s │  │
│ │ Usuário: use o modelo…    │ │  │ Skills: Busca de Produto│ │
│ └───────────────────────────┘ │  │ Knowledge: — [Adicionar]│ │
│ ┌───────────────────────────┐ │  │ Entrada: pergunta       │ │
│ │ [escrever aqui…        ➤] │ │  │ Saída: resposta         │ │
│ └───────────────────────────┘ │  │ [   Salvar agente   ]   │ │
└───────────────────────────────┴──────────────────────────────┘
```

Mudanças: erro de salvar com mensagem específica + "Tentar de novo" + rascunho preservado com aviso; um único valor de modelo efetivo em toda a tela (o outro como subtítulo); abas para reduzir a página longa; botões "Criar skill/tool →" quando a lista está vazia; no mobile, fixar o campo de chat na parte inferior (bottom bar) como no padrão mobile de chat.

---

## 4. Biblioteca: Skills, Tools Custom e MCP Servers

Telas: `/skills` (10, 11), `/tools` (12), `/mcp` (13).
Referência: GitHub (Settings → regras/limitações), Vercel (API Keys), Linear (Settings).

### O que funciona

- Três telas com a mesma anatomia (título, estado vazio, CTA "Criar primeira X") — consistência.
- Modal de skill (10) tem o essencial: nome, descrição, categoria, template markdown com **abas Editar/Pré-visualizar**, variáveis `{{nome}}` com helper explicando a sintaxe.
- Toast de sucesso "Skill criada" (11) e card na lista com ações Editar/Excluir.

### Problemas (em ordem de gravidade)

1. **Inputs/Outputs como texto JSON solto** no modal de skill (10): "Inputs (JSON) `[]`". Erro de digitação só aparece no submit; para o público-alvo (montar agentes, não escrever schema) é a forma mais frágil de formulário.
2. **Sem busca/filtro** nas listas: com dezenas de skills, a única navegação é rolagem. As 3 telas (skills, tools, MCP) não têm campo de busca.
3. **Sem detalhe/inspeção**: o card da lista (11) só mostra nome, categoria e descrição; não dá para ver o template, as variáveis ou onde a skill está usada ("usada em 2 agentes") sem abrir o modal de edição.
4. **Ações de editar/excluir como ícones no fim do card** (11) sem menu: pouco alvo de clique e sem agrupamento; em telas menores os ícones podem colidir com o texto.
5. **MCP Servers (13)** não mostra o estado de saúde do servidor (conectado/desconectado) nem as tools expostas por ele, que é a informação que o usuário precisa antes de anexar um MCP a um agente.

### Referência que faz melhor e por quê

**GitHub (Settings)** e **Vercel (API Keys)**: listas em tabela densa com busca no topo, status por cor, ações em menu ⋮ por linha e página de detalhe própria. **Linear**: busca com filtro combinado (`/` abre o buscador) e listagem em 2 linhas que cabe muita informação sem card alto.

### Proposta

```
┌──────────────────────────────────────────────────────────┐
│ Skills                                        [ + Nova ] │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ 🔍 Buscar skill…                 [Categoria ▾]       │ │
│ └──────────────────────────────────────────────────────┘ │
│  NOME              CATEGORIA   USOS        ATUALIZADO ⋮  │
│  Busca de Produto  Código      2 agentes   hoje 12:03  ⋮ │
│  Revisar código    Análise     0           29/09 09:14 ⋮ │
│ ──────────────────────────────────────────────────────── │
│ ⋮ → Editar · Ver template · Duplicar · Excluir           │
└──────────────────────────────────────────────────────────┘
Modal de criação: Inputs/Outputs viram linhas estruturadas:
  Inputs:  [ nome: produto  |  tipo: string ▾ |  obrig. ✓ ] +
           [ nome: limite   |  tipo: number  ▾ |  obrig. ✗ ] +
  (o JSON é gerado; um botão "Ver JSON" mostra o resultado)
```

Mudanças: busca + filtro em skills/tools/MCP; tabela em vez de cards altos; menu ⋮ por item; inputs/outputs estruturados; card MCP com status de conexão e nº de tools.

---

## 5. Knowledge (bases, documentos e chat)

Telas: `/knowledge` (14, 15).
Referência: Perplexity (citações inline), Notion AI (chat com fontes), ChatGPT com arquivos (arquivos como contexto citável).

### O que funciona

- Estrutura de 3 zonas clara: seleção de base (esquerda), documentos (meio), chat (direita) (15).
- Ciclo de documento funciona e mostra estado: `catalogo.md` com status "Pronto" e ícone verde; remoção com botão explícito.
- Conversas são persistidas e viram chips com data e exclusão (15).
- Modal "Nova base" expõe escopo (Global/Agente/Pipeline), fonte (arquivo/URL/Vector DB), limiar e top K — configurações RAG importantes e visíveis.

### Problemas (em ordem de gravidade)

1. **Resposta do chat sem nenhuma fonte** (15): perguntei "Qual o preço do Notebook Pro 15?" e a resposta foi "Não encontrei nada sobre isso nesta base." — **sem citar o documento que deveria ter respondido, sem trecho, sem confiança**. Mesmo no modo mock, a *interface* não tem lugar para fontes: não existe chip de fonte, numeração ou painel de fontes. Para um produto de RAG, a ausência de citação é o problema de confiança nº 1 (é exatamente o que Perplexity resolve).
2. **Criação de base não seleciona a base** (14): depois de "Criar base", o painel principal continua no estado "Selecione uma base", forçando um clique extra.
3. **Documento sem pré-visualização**: dá para ver o nome e o status, mas não o conteúdo, o nº de chunks ou quando foi enviado.
4. **Chips de conversa com exclusão sempre visível** (15): o ícone de lixeira aparece em todo chip; sem confirmação, é risco de apagar conversa errada.
5. **Sem estado de "buscando"**: a resposta aparece de uma vez, sem indicador de que o RAG está recuperando (em produção, o tempo de retrieval seria invisível).
6. O "Excluir base" em vermelho no canto do painel (15) está na mesma linha do título da base, perto do campo que edita o nome — alvo de clique acidental.

### Referência que faz melhor e por quê

**Perplexity**: cada resposta traz superscripts numerados inline + linha "N fontes" e painel lateral com os trechos citados — o usuário verifica a claim em 2 cliques. **Notion AI**: ao perguntar sobre a base, a resposta cita o *bloco* da página, com link direto. **ChatGPT com arquivos**: mostra quais arquivos foram usados como contexto, como chips acima da resposta.

### Proposta

```
┌────────────┬───────────────────────────────────────────────────┐
│ Bases      │  Catálogo de Produtos              [⚙] [Excluir…] │
│ + Nova     │  Documentos (1)                  [ Selecionar ]   │
│ ▸ Catálogo │  ✅ catalogo.md · 1 chunk · hoje 14:10  [Ver ⋮]   │
│   1 doc    ├───────────────────────────────────────────────────┤
│            │  [Nova conversa]  ⌕ Conversas                     │
│            │  Usuário: Qual o preço do Notebook Pro 15?        │
│            │  IA: O Notebook Pro 15 custa R$ 12.499¹ e está    │
│            │      em estoque.¹                                 │
│            │  ┌──────────────────────────────────────────────┐ │
│            │ │ 📄 catalogo.md · trecho · 98% · ver fonte ↗   │ │
│            │ └──────────────────────────────────────────────┘ │
│            │  [ Pergunte algo sobre esta base…           ➤ ]   │
└────────────┴───────────────────────────────────────────────────┘
- Criar base ⇒ seleciona a nova base automaticamente.
- Chip de fonte clicável abre o trecho com o texto real (drawer).
- "Buscando…" com 3 steps visíveis (recuperando → lendo → respondendo).
- Excluir conversa: ⋮ → Excluir, com confirmação.
```

Mudanças: citações como requisito de UI (chip + drawer de trecho); auto-seleção após criar base; drawer de documento; indicador de retrieval; confirmação em exclusões.

---

## 6. Pipelines

Telas: lista `/pipelines` (16, 24), editor `/pipelines/[id]` (17, 18; mobile 32), monitor `/pipelines/[id]/run` (19–23; mobile 33).
Referência: n8n (editor de canvas), GitHub Actions (run com jobs + logs), LangSmith (trace), Vercel (deploys).

### O que funciona

- **Editor (17, 18)**: canvas com dot grid, nó com badge "ENTRADA", legenda de arestas (Fluxo/Condição/Dados), minimapa, toolbar compacta (+ Agente, desfazer/refazer, excluir, zoom, ajustar à tela), badge de validação "Grafo válido" e indicador "Alterações não salvas" com Salvar habilitado só quando há delta. É uma base sólida e alinhada ao padrão n8n.
- **Monitor (19–23)**: header com status + horário + ações (Pausar/Parar, Ver grafo, Atualizar); **stage strip** com chips por nó (19) na ordem topológica; abas Resultado / Arquivos do projeto / Logs / Histórico (20–22); card de resultado recolhível com "Copiar output" (23); URL com `?tab=` persistente (20) — recarregar não perde a aba.
- Aba Histórico (21) e Arquivos do projeto (22) existem, cobrindo o que GitHub Actions separa em runs + job artifacts.

### Problemas (em ordem de gravidade)

1. **Sem painel de configuração de nó/aresta visível no editor**: clicar no nó (18) apenas seleciona e mostra "Validando o grafo"; não abre painel lateral para mapear entradas/saídas nem para definir a condição de uma aresta. O componente de painel de aresta existe (`EdgePanel.tsx`) e a legenda promete arestas de "Condição" e "Dados", mas o affordance para configurar uma aresta não é evidente no canvas — em n8n, selecionar um nó/aresta abre o painel imediatamente. Sem isso, o usuário não sabe como ligar saídas de um agente a entradas de outro.
2. **Lista de pipelines: o card mostra o status do último run como se fosse o status da pipeline** (24: "Novo pipeline · Concluído"). Pipeline e run são coisas diferentes; uma pipeline não "está concluída". O estado do objeto (rascunho/publicada) não aparece na lista, embora o card da criação mostre "Rascunho".
3. **Sem busca/filtros na lista** e sem ordenação visível (por último run, nome, status) — com 20 pipelines a rolagem não resolve.
4. **Stage strip com 1 chip e nome duplicado** (19): o chip "Consultor de Catálogo v2" repete o título do card de resultado logo abaixo; em pipelines maiores a strip não tem zoom/scroll visível e os chips podem passar da tela (o `overflowX: auto` existe, mas sem affordance de scroll).
5. **Abas de monitor sem contagem**: "Logs" (20) não indica quantas linhas/há erro; "Histórico" (21) não indica nº de runs. O usuário não sabe se clicar.
6. **Resultado sem estrutura de eventos** (23): o output é um bloco de texto puro; não há passos (chamou knowledge, chamou tool X, iteração 2) com timestamps — é justamente o que LangSmith expõe e que falta aqui.
7. **Mobile (32, 33)**: a toolbar do editor corta no fim (ícone de zoom/ajustar fora da tela) e o botão "Salvar" aparece solto sobre o canto do canvas; no monitor, abas e stage strip competem por 390px.

### Referência que faz melhor e por quê

**n8n**: seleção de nó ⇒ painel de propriedades à direita, imediatamente; execução ao vivo pinta os nós com dados e tempos por execução. **GitHub Actions**: a run tem jobs com status individual, o log do job falho abre direto na linha do erro, e "Annotate" mostra warnings destacados no arquivo. **LangSmith**: cada span da trace tem duração, input/output e tokens — a timeline é o centro, não a aba secundária.

### Proposta (editor com painel contextual)

```
┌────────────────────────────────────────────────────────────────┐
│ ←  Novo pipeline  [Sem repositório]  ✔ Grafo válido  Salvar ▶  │
│ [ + Agente]  [↶ ↷ 🗑 | ＋ － ⤢]                 [Monitor][Executar]│
├───────────────┬──────────────────────────────┬─────────────────┤
│ AGENTES       │                              │ PROPRIEDADES    │
│ [🔍 buscar]   │   ┌──────────────────┐       │ Consultor v2    │
│ 🤖 Consultor…│   │ ENTRADA          │       │ ─────────────── │
│ 🤖 Analista… │   │ 🤖 Consultor v2 │       │ Entradas do nó  │
│ + Condição    │   └──────────────────┘       │ pergunta ← [se- │
│ + Dados       │        ║ (arrastar)          │ tora ▾]  ✓      │
│               │   ┌──────────────────┐       │ Arestas         │
│               │   │ 🤖 Analista     │       │ → Analista      │
│               │   └──────────────────┘       │   [fluxo|cond.  │
│               │                              │   dados|aprov.] │
│               │                              │   [editar ⋮]    │
│               │            ▣ minimapa        │ [Excluir nó]    │
└───────────────┴──────────────────────────────┴─────────────────┘
- Painel à direita SEMPRE: sem seleção = propriedades da pipeline;
  nó = mapeamento de entradas/arestas; aresta = tipo+condição.
- Lista de pipelines:
  NOME            ESTADO     ÚLTIMO RUN      ATUALIZADO ⋮
  Novo pipeline   Rascunho   Concluído 13min  hoje 14:18  ⋮
  Suporte v1      Publicada  Falha há 2h      ontem 10:02 ⋮
  [🔍 buscar] [Estado ▾] [Ordenar ▾]
- Monitor: contagem nas abas (Logs (3) · Histórico (12)) e timeline
  de eventos por nó com duração (estilo LangSmith) na aba Resultado.
```

Mudanças: painel de propriedades no editor (nó/aresta/pipeline); status da pipeline separado do status do run; busca+filtro na lista; contagens nas abas; timeline de eventos no resultado; toolbar do editor em mobile virar barra fixa com overflow em "⋯".

---

## 7. Aprovações

Tela: `/approvals` (25).
Referência: GitHub (HITL em PRs/reviews), Vercel (aprovamentos de deploy).

### O que funciona

- Badge de contagem pendente no sino da topbar sincronizada por WebSocket (layout do dashboard) — o usuário não precisa visitar a tela para saber que algo espera.
- Estado vazio correto e honesto (25): "Quando um agente precisar de aprovação humana, o pedido aparece aqui."

### Problemas (em ordem de gravidade)

1. **A tela de fila é só texto** (25): sem estrutura para a fila — sem colunas de status, sem busca, sem filtro por pipeline, sem data de criação, sem SLA/tempo aguardando. A aprovação é o momento de maior risco do sistema (um agente pede ação humana) e é a tela mais pobre do portal.
2. **Não há como ver a aprovação em contexto**: o card (quando existe) precisa responder "qual pipeline, qual nó, com qual payload, pedido por quem, há quanto tempo" — nada disso está visível na UI atual.
3. **Sem atalho de ação inline**: aprovar/rejeitar deveria ser possível direto na fila (e no card do dashboard) sem abrir e depois voltar.

### Referência que faz melhor e por quê

**GitHub**: uma review pendente mostra autor, PR, tempo, e o botão Approve/Request changes no card mesmo sem abrir; a tela "Your reviews" filtra por status. **Vercel**: aprovar deploy mostra o commit e o preview, com "Approve" primário em uma linha.

### Proposta

```
┌──────────────────────────────────────────────────────────────┐
│ Aprovações                                    [status ▾ pendente]│
├──────────────────────────────────────────────────────────────┤
│ ⚠  Publicar release  ·  Pipeline: Suporte v1  ·  há 12 min    │
│    Nó: "Enviar e-mail"   Pedido por: agente Analista          │
│    Payload: { para: "contato@…", assunto: "Relatório 9" }    │
│    [ Ver contexto ↗ ]          [ Aprovar ]  [ Rejeitar ]      │
├──────────────────────────────────────────────────────────────┤
│ ⚠  Excluir registros  ·  Pipeline: Limpeza  ·  há 3 h 04 min  │
│    [ Ver contexto ↗ ]          [ Aprovar ]  [ Rejeitar ]      │
└──────────────────────────────────────────────────────────────┘
```

Mudanças: fila com metadados (pipeline, nó, quem, há quanto tempo); ações inline Aprovar/Rejeitar; filtro por status; link "Ver contexto" abre o monitor no nó responsável.

---

## 8. Integrações

Tela: `/integrations` (26, 27).
Referência: Vercel (Integrations/API), GitHub (Settings → Secrets), n8n (Credentials).

### O que funciona

- Abas por provedor (GitHub / Azure DevOps / Outras) — escopo claro (26).
- Estado vazio honesto: "Nenhuma conexão cadastrada."
- Modal "Nova conexão" (27) mínimo e correto: Nome + Token, com helper "PAT com escopo repo".

### Problemas (em ordem de gravidade)

1. **Sem teste de conexão**: o usuário cola um PAT e só descobre que está inválido quando uma pipeline tenta usar a integração. Falta o botão "Testar" com resultado imediato (200/401) — o padrão em todo produto de credenciais (n8n tem "Test credentials").
2. **Sem estado por conexão**: lista não mostra token mascarado, criado em, usado por quantos pipelines, ou status (válida/expirada).
3. **Escopo de risco invisível**: PAT com escopo `repo` dá acesso a todos os repositórios do token; não há aviso nem campo de escopo sugerido (ex.: "use token com escopo mínimo `repo` apenas para o repositório X").
4. **Sem "Outras" preenchida**: a aba Outras (26) sem conteúdo visível não explica o que pode ser conectado.

### Referência que faz melhor e por quê

**n8n**: cada credential tem "Test" com resposta verde/vermelha e os nós referenciam a credential por nome, com contagem de uso. **GitHub Settings**: secret mostra último uso e aviso de rotação.

### Proposta

```
┌──────────────────────────────────────────────────────────────┐
│ Integrações                        [GitHub|Azure DevOps|Outras]│
│ NOME          TOKEN        STATUS     USOS      ATUALIZADO ⋮ │
│ github-prod   ghp_…x92     ● válido   2 pipes   hoje      ⋮  │
│ github-ci     ghp_…m14     ⚠ 401     0         ontem     ⋮  │
└──────────────────────────────────────────────────────────────┘
Modal Nova conexão:
  Nome   [github-prod            ]
  Token  [●●●●●●●●●●●●●●●●●●●●●●]  [ Testar ]  → ✓ 200 (182ms)
  helper: use um PAT com escopo mínimo necessário; o token fica
          criptografado e nunca é mostrado de novo.
```

Mudanças: teste de conexão no modal com status; tabela com token mascarado + status + usos; aviso de escopo mínimo.

---

## 9. Versão celular (390px)

Telas: dashboard (30), menu (31), editor (32), monitor (33), detalhe do agente (34).
Referência: Vercel mobile (app), Linear mobile.

### O que funciona

- O shell adapta: topbar com ações, sidebar vira overlay (31) com o mesmo conteúdo agrupado — navegação acessível.
- O dashboard empilha as métricas em 1 coluna e os cards continuam tateáveis (30).
- Os toppers (notificações, tema, ajuda, sair) continuam visíveis.

### Problemas (em ordem de gravidade)

1. **Editor de fluxo em 390px é inoperável** (32): a toolbar corta no fim (zoom/ajustar fora da tela), o botão "Salvar" sobrepõe o canto do canvas e o canvas fica com ~340px — arrastar nós e arestas com polegar nesse espaço não é viável.
2. **Topbar com 5 ícones circulares em 390px** (30): cada um com ~36px + logo + título = competição por espaço; o título "Agent Portal" quebra em "Agent / Portal" em 2 linhas (30, 31), indicando overflow.
3. **Detalhe do agente empilha chat + formulário inteiro** (34): para "conversar" o usuário rola para o chat; para ajustar um campo, rola para o formulário; não há âncora nem aba.
4. **Cards de métrica em 1 coluna ocupam quase a tela** (30): 4 cards = 4×~90px; o conteúdo útil (agentes, runs) só aparece depois de 2 dobras.
5. **Botão de menu (hamburger) sobre o conteúdo**: o main ganha `padding-top: 64px` em mobile para o conteúdo não cair sob o botão (30) — funciona, mas o "Voltar" das telas internas compete com o hamburger no mesmo canto (32: dois botões adjacentes no topo).
6. **Sem bottom nav**: a navegação entre as 4 áreas principais exige abrir o overlay em cada troca — o padrão mobile maduro (Linear, Vercel app) usa bottom bar.

### Referência que faz melhor e por quê

**Vercel app**: bottom nav com 4 itens (Projects, Domains, Analytics, …), topbar mínima (logo + 1 ação), e telas de detalhe com "actions bar" fixa embaixo. **Linear mobile**: lista com 2 linhas, swipe actions, e bottom tabs.

### Proposta

```
┌─────────────────────────────────────────┐
│ [AP]  Overview                    [⚙]   │  topbar mínima:
├─────────────────────────────────────────┤  logo + título + 1
│  Em execução 0   Runs 24h 0   Aprov. 0  │  ação (restante em ⋯)
├─────────────────────────────────────────┤
│  AGENTES (1)              [buscar]      │
│  ┌───────────────────────────────────┐  │
│  │ 🤖 Consultor v2 · Ocioso      ›  │  │
│  └───────────────────────────────────┘  │
│  RUNS RECENTES                          │
│  ┌───────────────────────────────────┐  │
│  │ ▣ Novo pipeline · Concluído   ›  │  │
│  └───────────────────────────────────┘  │
├─────────────────────────────────────────┤
│ [🏠]   [🤖]   [➜]   [⚠]                │  bottom nav:
│ Início Agentes  Pip. Aprov.             │  Dashboard, Agentes,
└─────────────────────────────────────────┘  Pipelines, Aprovações
(Biblioteca em ⋯/menu; métricas em 1 linha de 3 chips)

Editor mobile: não tentar canvas em 390px —
  [lista de nós em 1 coluna] + [botão "ver em desktop" / modo
  "lista de etapas"]; o canvas fica para ≥ 768px.
```

Mudanças: bottom nav com 4 itens; topbar reduzida a 1 ação + menu ⋯; métricas em 1 linha compacta; editor em 390px vira modo lista de nós; detalhes com action bar fixa no rodapé.

---

## 10. Mudanças transversais

### Navegação

- **Sidebar fixa com 3 grupos** (PRINCIPAL / PIPELINES / BIBLIOTECA) é clara e consistente em todas as telas — manter.
- **"Novo Agente" está na sidebar** ao lado de "Dashboard": ação de CTA misturada com navegação de seção. Padrão maduro (Vercel, Linear): CTA global fica na topbar (botão "+"), a sidebar lista apenas seções.
- **"Integrações" vive só na topbar** (link com ícone), fora dos grupos da sidebar — o usuário não a encontra na navegação primária. Mover para a sidebar (grupo PIPELINES ou um grupo CONFIGURAÇÃO).
- **Sem breadcrumb nem indicador de seção atual** nas telas de detalhe (agente, pipeline): o "Voltar" existe, mas o usuário não sabe onde está na hierarquia (o título mostra o nome do item, não o caminho).
- **Sem atalho global de busca** (ex.: `⌘K` / `/`): o portal tem 8 seções e listas de agentes/pipelines sem busca global — o padrão Linear/Vercel de command palette resolveria também o item "sem busca nas listas".

### Hierarquia

- Um único acento (laranja) para CTAs e estado ativo — **funciona bem**; o risco está no uso excessivo de laranja em foco (múltiplos rings simultâneos no Knowledge, 15).
- **Títulos de seção em MAIÚSCULAS pequenas** (AGENTES, RUNS RECENTES) com peso alto: o contraste entre o H1 da tela e os H2 de seção é pequeno; aumentar o gap tipográfico (H1 20–24px, H2 13–14px em 500, rótulos de seção 11px em 500 com letter-spacing).
- **Cards aninhados** (dashboard: cards de métrica dentro do main; pipelines: card com footer) criam profundidade visual sem aumentar a informação; trocar cards de métrica por tiles planos (Vercel).

### Tipografia e densidade

- Base legível (~14px) com bons espaçamentos — **densidade ok em desktop**, mas **baixa demais no mobile** (30: métricas ocupam 2 dobras).
- **Monospace para valores técnicos** (modelos, timeouts, UUIDs) já aparece no preview do agente (05) — padronizar: todo valor de configuração (modelo, timeout, max it) em monospace 13px.
- **Corpo de log/output**: a aba Logs (20) e o OUTPUT (23) usam corpo de texto; para logs, monospace 12–13px com linhas numeradas é o padrão GitHub Actions — adotar.

### Estados vazios

- **Fortaleza do portal**: quase toda tela tem estado vazio com ícone + texto + CTA (03, 16, 25, 26). Manter e padronizar:
  - Ícone (lucide, traço fino) de 32px, cor `--text-muted`.
  - Título 15px/600 + 1 linha de explicação 13px.
  - CTA primário laranja, alinhado à ação da seção ("Criar primeiro X").
- **Exceção**: a tela de aprovações pendente (25) tem texto mas **sem CTA** — em aprovação, quando a fila está vazia, o CTA não existe (nada a aprovar). Correto, mas adicionar "Como funcionam as aprovações?" como link de ajuda.

### Carregamento

- **Sem skeletons** em nenhuma lista (dashboard, pipelines, skills). O conteúdo "aparece" quando a API responde; em latência real, isso vira tela branca.
- **Spinner genérico no layout do dashboard** (layout.tsx): um círculo girando centralizado no lugar do shell inteiro — trocar por skeleton do shell (topbar + sidebar + main com 2 cards de skeleton).
- **Chat**: sem indicador de digitação/streaming do assistente (o mock responde instantâneo; em produção, o SSE demora e o usuário fica sem feedback). Adicionar "digitando…" com 3 pontos animados.
- **Botões com estado loading**: o cadastro troca o texto ("Criando...") — bom; padronizar para todos os CTAs (Salvar, Executar, Salvar agente) com spinner inline dentro do botão.

### Erros

- **O erro 404 do "Salvar agente" (07) é o exemplo do problema**: toast "Recurso não encontrado." — sem contexto, sem ação, sem detalhe.
- **Proposta de padrão** (aplicar a todos os erros):
  ```
  ┌──────────────────────────────────────────────┐
  │ ⚠  Não foi possível salvar o agente.         │
  │        (HTTP 404 em POST /api/agents/…)      │
  │  [Ver detalhes]  [Tentar de novo]            │
  └──────────────────────────────────────────────┘
  ```
  - Mensagem de **impacto** (o que o usuário não conseguiu fazer) em vez de mensagem técnica.
  - **Ação de recuperação** sempre presente (Tentar de novo / Voltar / Copiar erro).
  - **Detalhamento opcional** (status, endpoint, payload resumido) para debug.
  - Toast de erro com auto-dismiss de 8s + botão para reabrir; erro que bloqueia (404 de salvar) **não** pode ser só toast — precisa de inline com CTA.
- **Sucesso**: toast com texto claro ("Skill criada", 11) — padronizar para todos os creates/updates/deletes.

### Acessibilidade

- **Contraste**: textos secundários (subtítulos, placeholders, helpers) em cinza-escuro sobre fundo quase preto — vários abaixo de 4.5:1 (01, 03). Ajustar `--text-secondary` e `--text-muted` para ≥ 4.5:1 (texto pequeno) / 3:1 (texto grande).
- **Labels**: os inputs têm `aria-label`/placeholder coerentes em geral, mas **busca do dashboard** (03) tem label "Buscar agente" e placeholder diferente — alinhar label e placeholder.
- **Foco visível**: o help (?) da topbar mostra ring de foco laranja (01, 03) — bom; garantir `:focus-visible` em todos os elementos interativos, incluindo nós do canvas (React Flow já expõe, mas o foco do nó precisa de outline distinto da seleção).
- **Teclado**: o editor de canvas (React Flow) suporta teclado (descrição do nó: "Press enter or space to select…"), mas **não há atalho global de ajuda** (o "?" da topbar é um ícone, não um menu de atalhos). n8n tem legenda de atalhos acessível por "?" — adotar.
- **Live regions**: toasts e o chat usam `aria-live` (snapshots mostram `live="polite"` e `live="assertive"`) — **forte**; manter e garantir que o toast de erro também seja `assertive`.
- **Alvos de toque (mobile)**: ícones circulares de ~36px na topbar (30) estão no limite mínimo (44px recomendado); aumentar para 44px em mobile.
- **Idioma**: `lang="pt-BR"` no `<html>` (garantir); termos técnicos em inglês (Skills, MCP, Knowledge, Monitor) mantidos — ok, mas a sidebar mistura "Tools Custom" e "MCP Servers" em inglês com "Skills" e "Knowledge" — padronizar para os 4 em inglês (termos de domínio) ou 4 em pt-BR.

---

## 11. Priorização: impacto no usuário × esforço

Escalas: impacto (alto/médio/baixo) = quão bloqueante/visível para o usuário no fluxo principal; esforço (S/M/L) = ordem de magnitude de implementação.

| # | Mudança | Impacto | Esforço | Racional |
|---|---------|---------|---------|----------|
| 1 | **Salvar agente: erro claro + recuperação** (07) — mensagem de impacto + "Tentar de novo" + rascunho preservado | Alto | S | Bloqueia o fluxo central (criar agente por chat); hoje o usuário não sabe o que fazer |
| 2 | **Citações/fontes no chat do Knowledge** (15) — chip de fonte + drawer de trecho | Alto | M | É a promessa do produto RAG; sem isso a resposta não é verificável |
| 3 | **Painel de propriedades no editor de fluxo** (18) — nó/aresta/pipeline | Alto | M | Sem ele o usuário não configura o grafo; padrão n8n inescapável |
| 4 | **Bottom nav mobile + topbar mínima** (30, 31) | Alto | M | Navegação mobile é hoje por overlay; padrão de app maduro |
| 5 | **Editor de pipeline em modo lista < 768px** (32) | Alto | M | Canvas em 390px é inoperável; alternativa de lista resolve |
| 6 | **Skeletons nas listas + shell** (03, 16) | Médio | S | Tela branca hoje; barato e percebido em toda navegação |
| 7 | **Padrão de erro com recuperação** (transversal) | Médio | S | Todos os erros do portal hoje são toasts opacos |
| 8 | **Título do dashboard "Overview" + links de métricas corretos + plural pt-BR** (03, 08) | Médio | S | 3 correções pequenas que removem confusão na tela mais visitada |
| 9 | **Lista de pipelines: status da pipeline separado do último run + busca/filtro** (24) | Médio | S | Confusão de estado + escala (não escala sem filtro) |
| 10 | **Aprovações: fila com metadados + ação inline** (25) | Médio | M | Tela de maior risco do sistema; hoje é só texto |
| 11 | **Integrações: "Testar" conexão + status na lista** (26, 27) | Médio | S | Evita descobrir token inválido em produção |
| 12 | **Knowledge: auto-selecionar base criada + drawer de documento** (14) | Médio | S | Remove 1 clique e dá visibilidade do conteúdo |
| 13 | **Busca global ⌘K** (transversal) | Médio | M | Padrão Linear/Vercel; resolve busca em todas as listas |
| 14 | **Skills/Tools/MCP: busca + inputs estruturados** (10, 12, 13) | Médio | M | JSON solto e sem busca não escala |
| 15 | **Contraste de texto secundário ≥ 4.5:1** (transversal) | Médio | S | Acessibilidade (WCAG) + legibilidade geral |
| 16 | **Detalhe do agente: abas + modelo efetivo único** (09) | Médio | M | Página longa + contradição de modelo |
| 17 | **Monitor: contagens nas abas + timeline de eventos** (19–23) | Médio | M | Padrão LangSmith/GH Actions; necessário para depurar runs |
| 18 | **Login: placeholder neutro + "Esqueci?" + requisitos de senha** (01, 02) | Baixo | S | Primeiro contato; barato |
| 19 | **CTA "Novo Agente" da sidebar para a topbar; "Integrações" para a sidebar** (transversal) | Baixo | S | Limpeza de navegação |
| 20 | **Monospace para valores técnicos + logs com linhas numeradas** (transversal) | Baixo | S | Consistência visual |

**Sugestão de ordem de execução** (agrupando por ROI):
1. Grupo **S + Alto/Médio** (itens 1, 6, 7, 8, 9, 11, 12, 15, 18, 19, 20): todos pequenos, entregam ganho imediato e removem os bloqueadores mais visíveis.
2. Grupo **M + Alto** (itens 2, 3, 4, 5): as 4 mudanças estruturais (fontes no RAG, painel do editor, mobile).
3. Grupo **M + Médio** (itens 10, 13, 14, 16, 17): escala e profundidade.

---

*Documento gerado em 2026-09-29. Screenshots em `screenshots/` (mesma pasta). Não foram alterados código, dependências, containers nem `.codex/`.*
