# Redesign de usabilidade do Agent Portal — design

Data: 2026-09-29 · Origem: `docs/superpowers/design/2026-09-29-revisao-de-design.md` (revisão tela a tela com referências) · Estado: escrito a pedido do usuário ("crie toda a spec e todo o plano"), aguardando revisão.

## 1. Objetivo

Aplicar as 20 melhorias priorizadas na revisão de design. Junto com elas vêm três correções verificadas depois dela:
1. O rascunho do agente criado por chat se perde quando o orchestrator reinicia (`404 draft_not_found` ao salvar). Foi reproduzido nos logs às 16:55 de 2026-09-29.
2. A avaliação do monitor usou três screenshots idênticos, porque as abas não foram trocadas. As mudanças do monitor ficam valendo e são revalidadas no QA final, com captura por aba.
3. Falta um lugar para descrever as entradas do agente. Com isso, o formulário de execução quase nunca mostra descrições (pendência da Task 12 do plano Git).

Critério de sucesso: um usuário novo consegue, sem ajuda, fazer o fluxo abaixo em desktop e em 390px, e toda falha mostra o que aconteceu e como sair.
1. Criar um agente pelo chat.
2. Montar uma pipeline configurando entradas e arestas pelo painel.
3. Executar a pipeline, aprovar e ler o resultado.
4. Consultar uma base de conhecimento, com as fontes verificáveis.

## 2. Decisões de design (valem para todas as telas)

| Tema | Decisão |
|---|---|
| Termos | Os termos de domínio ficam em inglês: Skills, Tools, MCP, Knowledge. O resto da UI fica em pt-BR com acentos. "Tools Custom" vira "Tools". |
| Navegação | A sidebar lista apenas seções. As ações de criar vão para um botão "+ Novo" na topbar, com menu: Agente, Pipeline, Base de conhecimento. Integrações entra na sidebar, num grupo novo, CONFIGURAÇÃO. |
| Localização | Toda tela de detalhe tem breadcrumb (`Pipelines / Nome`). O "Voltar" é mantido. |
| Busca global | ⌘K / Ctrl+K e `/` abrem uma paleta de comandos. Ela busca agentes, pipelines, bases, skills, tools e servidores MCP, e oferece as ações de criar. `?` abre a lista de atalhos. |
| Erros | Todo erro diz o que o usuário não conseguiu fazer e oferece uma ação de recuperação: "Tentar de novo", "Voltar" ou "Copiar detalhes". Os detalhes técnicos (status, método e caminho) ficam recolhidos. Erro que bloqueia uma ação principal aparece inline, e não apenas como toast. O toast de erro usa `aria-live="assertive"`, fica 8 s na tela e tem "Ver detalhes". |
| Carregamento | Skeletons em todas as listas e no shell, em vez de tela vazia ou spinner central. Os botões de ação têm estado `loading`, com spinner inline e o botão desabilitado. O chat mostra "digitando…". O Knowledge mostra as etapas "Buscando trechos → Lendo → Respondendo". |
| Listas | Tabela densa com busca no topo, filtro, ordenação e menu ⋮ por linha. Abaixo de 768px vira lista de duas linhas. |
| Contraste e acessibilidade | `--text-secondary` ≥ 4.5:1 e `--text-muted` ≥ 4.5:1 sobre `--bg` e `--bg-card`, nos temas claro e escuro. `:focus-visible` em todo elemento interativo. Alvos de toque ≥ 44px abaixo de 768px. `lang="pt-BR"`. |
| Tipografia | H1 20–24px/600. Título de seção 13–14px/500. Rótulo de grupo 11px/500 com espaçamento entre letras. Valores técnicos (modelo, timeout, IDs, logs) em monospace 12–13px. Logs com linhas numeradas. |
| Estados vazios | Mantém o padrão atual (ícone 32px, título 15/600, uma linha, CTA). A tela de Aprovações ganha o link "Como funcionam as aprovações?". |
| Mobile | Barra inferior com 4 itens: Início, Pipelines, Aprovações e Mais (Mais abre a sidebar). A topbar mostra só o logo, o título da tela e ⋯. As métricas viram uma linha de chips. O editor de pipeline abaixo de 768px abre em modo lista de etapas. As telas de detalhe têm barra de ações fixa no rodapé. |

## 3. Mudanças por tela

### 3.1 Login e cadastro
- O placeholder do e-mail passa a ser `voce@empresa.com`.
- A senha ganha o link "Esqueci?", que leva a `/forgot-password`. Essa página explica que a redefinição é feita pelo administrador. Não há backend de e-mail nesta entrega.
- O cadastro mostra "Mínimo 8 caracteres" e valida ao sair do campo. O backend já exige esse mínimo (`auth/schemas.py`).
- O botão Entrar tem estado de carregamento.

### 3.2 Overview (dashboard)
- O título passa a ser "Overview".
- Cada métrica leva à lista correta:
  - "Em execução" → `/pipelines?run=running`;
  - "Runs 24h" → `/pipelines?since=24h`;
  - "Concluídos" → `/pipelines?run=completed`;
  - "Aprovações" → `/approvals`.
- Plural em pt-BR por helper ("1 agente", "2 agentes").
- A busca procura por nome, descrição e tipo, e o rótulo acessível é igual ao placeholder.
- Com tudo zerado (0 agentes e 0 pipelines), a tela mostra um checklist "Primeiros passos" no lugar dos cards de métrica. Os itens são: criar agente, montar pipeline, adicionar documentos, executar. Cada um é marcado automaticamente pelos dados.

### 3.3 Agentes
**Rascunho persistente.**
- Os drafts do chat de construção passam a ficar na tabela `agent_drafts`: `id`, `owner_id`, `messages` JSONB, `config` JSONB, `updated_at`. O TTL de 24h é aplicado pela mesma limpeza periódica do orchestrator.
- `DraftStore` mantém a interface atual (`create`, `get`, `delete`), agora apoiada no banco.
- O portal guarda o `draftId` em `sessionStorage`. Ao recarregar `/agents/new`, recupera o draft.

**Salvar.**
- Uma falha mostra um erro inline no painel do rascunho: "Não foi possível salvar o agente", com o motivo, "Tentar de novo" e "Copiar detalhes". O rascunho nunca é descartado por causa de uma falha.
- Com `404 draft_not_found`, o texto é "O rascunho expirou no servidor", com a ação "Recriar a partir do que está na tela". Essa ação envia a config atual para `POST /api/agents/chat/restore`, que cria um draft novo com essa config.

**Validação do rascunho.**
- O preview mostra "✓ pronto para salvar" ou a lista do que falta: nome, ao menos uma saída, ações. A validação é a mesma do backend, exposta em `POST /api/agents/validate`.

**Detalhe.**
- O detalhe ganha as abas Visão geral, Conversar, Contrato, Mochila e Execução, com a URL `?tab=`.
- O modelo aparece num único lugar: o efetivo em destaque, e o configurado como texto secundário quando diferir.
- Contrato: cada entrada e cada saída ganham o campo "Descrição", salvo em `inputs[].description`. O formulário de execução já exibe esse campo.
- Mochila vazia: o seletor desabilitado dá lugar ao link "Criar skill →", "Criar tool →" ou "Criar base →", abrindo em nova aba.

**Mobile.** O campo do chat fica fixo no rodapé, e o rascunho passa a ser uma aba.

### 3.4 Biblioteca (Skills, Tools, MCP)
- As três telas viram tabela com busca, filtro (categoria para skills, status para tools e MCP), ordenação e menu ⋮. O menu tem Editar, Duplicar e Excluir; skills ganham também "Ver template".
- Coluna "Usos" com "N agentes". O backend soma as referências das mochilas dos agentes do dono e devolve `usageCount` nas listas.
- Inputs e outputs de skill são editados por linhas (nome, tipo, obrigatório, descrição), com "Ver JSON". O componente `PortsEditor` é o mesmo usado no Contrato do agente.
- MCP mostra na lista o status (conectado, erro ou desconectado) e o número de tools. Os dados já existem em `status` e `discoveredTools`.

### 3.5 Knowledge
- Criar uma base já a seleciona.
- Excluir base sai do lado do título e vai para o menu ⋮ da base, com confirmação.

**Documentos.** A linha do documento ganha "Ver", que abre um drawer com:
- nome, tamanho, data e número de chunks;
- os três primeiros trechos;
- ações de Remover e Substituir.

A API nova é `GET /api/knowledge/{kb}/documents/{doc}`, que devolve `{..., chunkCount, createdAt, preview: [text…]}`.

**Resposta do chat.**
- Os marcadores `[n]` da resposta viram sobrescritos clicáveis, e acima das fontes aparece a linha "N fontes".
- Clicar numa fonte ou num sobrescrito abre o drawer do trecho, com documento, score e texto completo.
- Cada fonte tem "Fonte errada", que grava o feedback em `PATCH /api/knowledge/{kb}/conversations/{cid}/messages/{mid}/sources/{index}` com `{wrong: true}`. O feedback fica em `knowledge_messages.feedback` JSONB. Nesta entrega o feedback só é armazenado.

**Conversas.** Excluir conversa passa para o menu ⋮, com confirmação.

**Espera.** Durante a resposta, o chat mostra as etapas "Buscando trechos", "Lendo" e "Respondendo" pela ordem. É um indicador visual por tempo; não depende do servidor.

### 3.6 Pipelines
**Lista.** Tabela com as colunas:
- Nome;
- Repositório;
- "Últimos 10 runs" (✓ x · ✗ y);
- Último run (status e tempo relativo);
- Atualizado;
- ⋮.

Tem busca, filtro de último run (todos, em execução, falhou, concluído, nunca executado) e ordenação por nome, último run ou atualizado. O status do último run deixa de aparecer como se fosse o status da pipeline. O backend inclui `runStats: {recentSucceeded, recentFailed, lastRunStatus, lastRunAt}` na lista. A filtragem por querystring (`run=`, `since=`) atende os links do Overview.

**Editor.** Um painel de propriedades à direita, sempre visível acima de 1024px, mostra conforme a seleção:
- sem seleção: nome, descrição, repositório, nó de entrada e validação;
- nó: agente (com link para ele), entradas do nó com a origem de cada uma (seletor da saída de um nó anterior ou "entrada do run"), arestas que saem e "Excluir nó";
- aresta: tipo (fluxo, condição, dados), condição, mapeamento de dados, aprovação (canal e mensagem) e "Excluir aresta". Aproveita o conteúdo do `EdgePanel`.

A paleta de agentes à esquerda ganha busca. A toolbar agrupa em ⋯ o que não couber.

**Editor abaixo de 768px.** Modo lista de etapas: nós em ordem topológica, cada um com as entradas, as arestas e as ações Editar e Remover. Tem "Adicionar agente" e "Conectar a…" num seletor. O canvas não aparece.

**Monitor.**
- As abas mostram contagens: "Logs (n)", com ponto vermelho se houver erro; "Histórico (n)"; "Arquivos (n alterados)".
- A aba Resultado ganha uma linha do tempo por nó, com início, fim, duração e status. É montada com os eventos WS `pipeline:status` por nó e com os timestamps dos checkpoints ao reabrir.
- O stage strip mostra seta e sombra quando há rolagem, e não repete o nome do card logo abaixo.
- "Ver grafo" continua num modal, que nunca cobre as abas.
- Os logs usam monospace com linhas numeradas.

### 3.7 Aprovações
Fila em cards densos, cada um com:
- título (mensagem da aprovação), pipeline, nó, agente que pediu e tempo de espera ("há 12 min");
- resumo do conteúdo (3 linhas, expansível);
- ações inline: Aprovar, Argumentar (abre o campo de feedback) e Rejeitar;
- "Ver contexto", que leva ao monitor do run (`?tab=resultado&node=<id>`).

Tem filtro de status (pendentes, respondidas) e filtro de pipeline. O card de aprovações do Overview ganha Aprovar e Rejeitar inline.

### 3.8 Integrações
- Tabela com as colunas: Nome, Token (`…últimos 4` via `token_hint`, gravado ao salvar), Status (último teste: válido, falha ou não testado, com a data), Usos (pipelines) e ⋮.
- O modal de conexão ganha "Testar", que valida o token antes de salvar via `POST /api/integrations/test`, com a config ainda não salva. O resultado aparece inline, com o número de repositórios ou o erro.
- Cada teste grava `last_test_status` e `last_tested_at` no `config`.
- Aviso de escopo mínimo: GitHub `repo`, Azure `Code (Read & Write)`. O texto diz que o token fica criptografado e nunca é mostrado de novo.
- A aba "Outras" explica o que existe (Rivvn, sob contrato) e o que está por vir.

## 4. Fora do escopo
- Redefinição de senha por e-mail.
- Temas novos.
- Canvas editável no celular.
- Uso do feedback "Fonte errada" pelo RAG.
- Tracing com tokens por chamada (LangSmith completo).
- i18n.

## 5. Erros e casos-limite
| Situação | Comportamento |
|---|---|
| Draft expirado ou orchestrator reiniciado | "O rascunho expirou no servidor" + "Recriar a partir do que está na tela" (restore). |
| Teste de conexão com token inválido | Resultado inline em vermelho, com o motivo traduzido; salvar continua permitido. |
| Lista com mais de 100 itens | Busca no servidor quando a API já aceitar `q`; senão, filtro no cliente sobre a página carregada, com o aviso "mostrando 100". |
| Paleta sem resultados | "Nada encontrado para '<termo>'" + atalhos de criação. |
| Fonte citada de documento removido | O drawer mostra "Documento removido" e o trecho salvo na mensagem. |

## 6. Testes
- **Unitários no orchestrator:**
  - `agent_drafts` (persistência, TTL, isolamento por dono, restore);
  - `validate` de agente;
  - `usageCount`;
  - `runStats`;
  - detalhe do documento;
  - feedback de fonte;
  - `POST /api/integrations/test` (sem gravar nada e sem vazar o token);
  - `token_hint` e `last_test_status`.
- **Portal (vitest):**
  - helper de plural;
  - `ErrorPanel`, `Button loading` e skeletons;
  - paleta de comandos (atalhos e busca);
  - breadcrumb;
  - `PortsEditor`;
  - abas do agente;
  - painel de propriedades (três modos) e modo lista do editor;
  - fila de aprovações com ações inline;
  - tabela de integrações e teste no modal;
  - citações e drawer;
  - bottom nav abaixo de 768px;
  - contraste dos tokens: teste que calcula a razão WCAG a partir de `globals.css`.
- **E2E:** atualizar as specs afetadas e adicionar "novo usuário, fluxo completo", em 1440px e em 390px.
- **QA visual:**
  - capturar cada tela e cada aba do monitor, em 1440px e 390px, no modo real (Qwen);
  - comparar com as propostas da revisão de design;
  - registrar em `docs/superpowers/validacoes/qa-redesign.md`.

## 7. Adendo (2026-09-30): menus e modais sem corte nem rolagem

Origem: dois problemas vistos pelo usuário no portal rodando, depois das tasks 1–17.

1. **Menu ⋮ cortado.** O menu de linha do `DataTable` é `position: absolute` dentro de um container com `overflow-x: auto`. Como um eixo `auto` força o outro a `auto`, o menu que pende abaixo da última linha é cortado e aparece uma rolagem minúscula (Integrações com uma linha, Skills, Tools, MCP e Pipelines).
2. **Modais com rolagem.** O `Modal` tem largura fixa de 480px e altura máxima de 85vh, com rolagem no corpo. A modal "Nova skill" (nome, descrição, categoria, template, variáveis, inputs e outputs) fica estreita, com scroll, e o usuário não vê o conjunto nem o botão de ação sem rolar.

### 7.1 Decisões

| Tema | Decisão |
|---|---|
| Menus e popovers | Nunca ficam dentro de um container com overflow. Todo menu flutuante (⋮ de linha, menu de ações do pipeline, menus da topbar) é renderizado num portal no `body`, com `position: fixed` calculado pelo botão que o abriu. Abre para cima quando falta espaço embaixo, reposiciona ou fecha ao rolar ou redimensionar, fecha com ESC e ao clicar fora, e devolve o foco ao botão. Existe um único componente (`Popover`/`RowMenu`), sem cópias. |
| Tamanhos de modal | `sm` 440px (confirmações e diálogos de uma pergunta), `md` 640px (formulários curtos, até 4 campos), `lg` 1040px (formulários ricos, em duas colunas), `xl` 1200px (grafo do monitor, aprovações). Largura sempre `min(tamanho, 95vw)`. |
| Regra sem rolagem | A rolagem do corpo da modal não aparece em 1280×720 nem em 1440×900 para nenhuma modal de formulário ou confirmação. O conteúdo é distribuído em colunas e seções para caber. A única rolagem permitida é interna a um componente que por natureza cresce: o editor de texto do template, uma lista longa de itens ou a saída de um teste. Ela fica no componente, nunca no corpo da modal, e o cabeçalho e o rodapé ficam sempre visíveis. |
| Composição | Formulários `lg` usam grade de duas colunas a partir de 1024px: campos curtos e metadados à esquerda, o editor principal à direita, e seções largas (inputs e outputs lado a lado) embaixo. Rótulos acima dos campos, ajuda em uma linha, erros inline junto ao campo. O botão principal fica no rodapé, à direita, e "Cancelar" ao lado. |
| Mobile | Abaixo de 768px toda modal vira folha em tela cheia (altura 100dvh), com cabeçalho e rodapé fixos e a rolagem só no miolo. Alvos de toque ≥ 44px. Nesse tamanho a rolagem do miolo é esperada. |
| Teclado e foco | Foco preso dentro da modal, ESC fecha (exceto durante uma operação em andamento), foco volta ao elemento que abriu. |

### 7.2 Layout da modal "Nova skill" (referência para as demais)

- Tamanho `lg`. Coluna esquerda: Nome, Descrição, Categoria e Variáveis (com a ajuda `{{nome}}` em uma linha). Coluna direita: abas Editar / Pré-visualizar e o editor do template, que ocupa a altura disponível.
- Faixa inferior de largura total: Inputs e Outputs lado a lado (o `PortsEditor` compacto, com "Ver JSON"), cada um com até 3 linhas visíveis e "adicionar".
- Rodapé: Cancelar e "Criar skill".

### 7.3 Modais cobertas

Skills (criar, editar, ver template), Tools (criar, editar, testar), MCP (criar, editar, testar), Integrações (conexão Git), Knowledge (criar base, editar base, documento, excluir), entradas da execução, Aprovações (decisão e confirmações), confirmações de exclusão (agente, pipeline, conversa, documento, nó) e o grafo do monitor. O plano classifica cada uma por tamanho.

### 7.4 Testes

- **Portal (vitest):** `Modal` (tamanhos, folha em tela cheia abaixo de 768px, foco preso, ESC), `Popover`/`RowMenu` (portal, posicionamento para cima, fechar ao rolar), e uma checagem por modal de que o corpo não declara `overflow-y` fora dos componentes permitidos.
- **E2E (Playwright):** abre cada modal em 1280×720 e 1440×900 e afirma `scrollHeight <= clientHeight` no corpo da modal, que o botão principal está dentro da viewport e que o menu ⋮ da última linha de uma tabela com uma linha fica totalmente visível. Em 390px afirma a folha em tela cheia.
- **QA visual:** captura de cada modal em 1440×900 e 390px, registrada em `qa-redesign.md`.

### 7.5 Política de rolagem do portal (todas as telas)

Origem: o usuário percebeu rolagem demais no sistema. Hoje `globals.css` não tem nenhum estilo de scrollbar, então aparece a barra clara padrão do navegador, que destoa do tema escuro. Há rolagem interna em cerca de 22 arquivos (monitor, chat, paleta de agentes, tabelas, sidebar, painéis).

**Preferência: não precisar rolar. Quando for necessário, rolar com estilo.**

| Tema | Decisão |
|---|---|
| Hierarquia | 1º reorganizar para caber (colunas, abas, recolher, paginar ou resumir); 2º rolar dentro de um único contêiner bem delimitado; 3º nunca rolagem aninhada (rolagem dentro de rolagem) nem rolagem horizontal da página. |
| Estilo | Scrollbar fina (8px), trilho transparente, polegar com `var(--border)` que clareia no hover, cantos arredondados, nos temas claro e escuro. `scrollbar-width: thin` e `scrollbar-color` para Firefox, `::-webkit-scrollbar` para Chromium e Safari. Um único conjunto de regras global, com `scrollbar-gutter: stable` nos contêineres rolantes para o layout não pular. |
| Shell | O shell ocupa a altura da janela (`100dvh`); sidebar e topbar fixas. Só a área principal rola, e só quando a página é maior que a janela. Telas de trabalho (editor, monitor, chat, Knowledge) ocupam a altura inteira e dividem o espaço em painéis, cada um com a sua rolagem apenas se necessário, em vez de a página inteira rolar. |
| Listas longas | Tabelas com mais de ~25 linhas paginam ou carregam mais, em vez de crescer sem fim; o cabeçalho da tabela fica fixo (`sticky`) quando a tabela rola. Listas em painéis (paleta de agentes, arquivos, logs) têm altura própria e rolagem estilizada. |
| Conteúdo denso | Saídas longas (markdown, logs, diff) ficam recolhidas com "Ver mais" ou em painel de altura limitada, em vez de esticar a página. |
| Acessibilidade | Contêineres rolantes focáveis por teclado (`tabindex="0"` com rótulo) e com indicação visual de que há mais conteúdo (sombra na borda) quando rolam. Respeita `prefers-reduced-motion` na rolagem suave. |

**Como medir.** Em 1440×900 e 1280×720, cada tela principal (Overview, Agentes, Pipelines, editor, monitor, Aprovações, Knowledge, Skills, Tools, MCP, Integrações) é aberta com um volume realista de dados. Para cada uma se registra: a página inteira rola? há rolagem aninhada? há rolagem horizontal? O objetivo é zero rolagem aninhada e zero rolagem horizontal em todas, e nenhuma rolagem da página nas telas de trabalho.

### 7.6 Fora do escopo

Arrastar ou redimensionar modais, modais empilhadas, animações novas, virtualização de listas muito grandes.

## 8. Adendo (2026-09-30): provedores e modelos de LLM nas Integrações

Origem: pedido do usuário — "nas integrações deve ser possível configurar os providers e os modelos de LLM".

### 8.1 Situação atual

- O LLM e os embeddings são configurados **só por variável de ambiente**, globais para toda a plataforma: `LLM_PROVIDER` (`mock|openai`), `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`.
- `LLM_MODEL`, quando definido, **sobrescreve** o modelo de todo agente (o detalhe mostra `effectiveModel` com uma nota). Não há como ter dois provedores ou modelos diferentes por agente.
- Orquestrador (`core/llm.py`, `core/embeddings.py`) e worker (`agent-worker/app/core/llm.py`) têm fábricas separadas. O worker **não tem banco nem segredos**: recebe o que precisa na requisição `POST /execute`, como já faz com `mcpServers`.
- Trocar de provedor exige editar o `.env` e reiniciar os serviços.

### 8.2 Decisões

| Tema | Decisão |
|---|---|
| Onde | Nova aba **LLM** na tela Integrações, ao lado de GitHub, Azure DevOps e Outras. Mesma tabela (`DataTable`), mesmo modal de conexão e mesmo padrão de teste. Segue as regras da seção 7 (modal `lg` em duas colunas sem rolagem, menu ⋮ em portal). |
| Conexão de LLM | Cada conexão tem: nome, **tipo de provedor**, URL base, chave de API, lista de modelos de chat e modelo padrão, e a configuração de embeddings (modelo, dimensões, prefixos de consulta e de documento). Uma conexão pode servir chat, embeddings ou os dois. |
| Tipos de provedor (esta entrega) | **OpenAI**, **Compatível com OpenAI** (LM Studio, Ollama, vLLM, OpenRouter, Azure OpenAI e similares, via URL base) e **Mock** (desenvolvimento e testes). Um adaptador por tipo, atrás de uma interface única no orquestrador e no worker, para acrescentar outros tipos depois. |
| Modelos | "Descobrir modelos" consulta `GET {url}/models` e preenche a lista; também dá para digitar o nome à mão (servidores que não listam). O modelo padrão da conexão é escolhido da lista. |
| Padrão e escolha | O usuário marca uma conexão como **padrão para chat** e uma como **padrão para embeddings**. O detalhe do agente ganha um seletor de modelo alimentado pelas conexões do dono (`conexão · modelo`), com a opção "Padrão". |
| Precedência | 1) modelo e conexão escolhidos no agente; 2) padrão do usuário; 3) **padrão do ambiente** (as variáveis de hoje). O ambiente vira fallback e continua funcionando sem nenhuma conexão cadastrada, então nada quebra em instalações existentes. O `LLM_MODEL` deixa de sobrescrever um modelo escolhido explicitamente; só vale quando não há escolha. O portal mostra uma linha somente leitura "Padrão do ambiente" na aba LLM. |
| Segredos | A chave de API é criptografada em repouso (Fernet, como o token Git), nunca volta na API (só `apiKeyHint` com os últimos 4 caracteres), é mascarada nos logs e nunca aparece em mensagens de erro. |
| Execução e worker | O orquestrador resolve a conexão no início de cada nó e envia ao worker, em `POST /execute`, o bloco `llm: {kind, baseUrl, apiKey, model}`. O worker usa esse bloco no lugar das variáveis de ambiente (que permanecem como fallback). O bloco não é gravado em run, checkpoint, log nem evento WebSocket; o tráfego segue pela rede interna e pelo NGINX :8081, que não registra corpo de requisição. |
| Outros consumidores | O chat de construção de agentes e o chat da Knowledge usam a conexão padrão de chat do dono. A ingestão e a consulta do RAG usam a conexão padrão de embeddings. |
| Testar | "Testar" faz, sem salvar (`POST /api/integrations/llm/test`), uma chamada mínima de chat e, se houver embeddings configurados, uma de embedding, e mostra inline: sucesso, latência, modelo respondido e as dimensões. O resultado grava `last_test_status` e `last_tested_at`. |
| Embeddings e dimensões | O schema pgvector é fixo em 1536 dimensões. Um modelo com outra dimensão usa o padding já existente; dimensão maior que 1536 é recusada no teste com mensagem clara. Trocar o modelo de embeddings pede confirmação e avisa que os documentos já indexados precisam ser reindexados (ação "Reindexar" na base). |
| Exclusão | Excluir uma conexão avisa quais agentes a usam e se é a padrão; os agentes que a usavam passam para o padrão seguinte, sem ficarem quebrados. |

### 8.3 Dados

- Tabela `integrations` existente com o novo tipo `llm` (migração adiciona o valor ao enum `integration_type`). Campos em `config`: `provider_kind`, `base_url`, `api_key_encrypted`, `api_key_hint`, `models[]`, `default_model`, `embedding: {model, dim, query_prefix, document_prefix}`, `last_test_status`, `last_tested_at`.
- Preferências do usuário: `users.preferences` (JSONB, nova coluna) com `default_llm_integration_id` e `default_embedding_integration_id`.
- Agente: campo opcional `llm: {integrationId, model}` no YAML. O campo atual `model` continua válido; sem `llm`, vale o padrão.

### 8.4 Erros e casos-limite

| Situação | Comportamento |
|---|---|
| Conexão padrão apagada ou desativada | Cai no padrão do ambiente e avisa no detalhe do agente. |
| Teste falha (URL, chave ou modelo inexistente) | Erro inline com o motivo traduzido; salvar continua permitido. |
| Servidor não lista modelos | Mensagem "Este servidor não listou modelos; digite o nome" e campo manual. |
| Run em andamento quando a conexão muda | O run mantém a resolução do nó em curso; a mudança vale a partir do próximo nó. |
| Modelo escolhido no agente some da conexão | O detalhe mostra o aviso e usa o modelo padrão da conexão. |

### 8.5 Testes

- **Orquestrador (pytest):** adaptadores (OpenAI, compatível, mock) com HTTP simulado; resolução de precedência; criptografia e `apiKeyHint`; a chave nunca volta na API nem aparece em log; `POST /llm/test` sem gravar nada; isolamento por dono; migração do enum.
- **Worker:** usa o bloco `llm` da requisição e cai no ambiente sem ele; não loga a chave.
- **Portal (vitest):** aba LLM, modal de conexão (modelos descobertos e manuais, embeddings, teste inline), seletor de modelo no agente, avisos de exclusão e de troca de embeddings.
- **Integração e e2e:** servidor compatível simulado (o fake do `git-test` ganha `/v1/models` e `/v1/chat/completions`) e um pipeline que executa usando uma conexão cadastrada na tela, sem variáveis de ambiente de LLM.

### 8.6 Fora do escopo

Adaptadores nativos que não sejam compatíveis com OpenAI (por exemplo Anthropic e Gemini diretos), cadeia de fallback entre provedores, cotas e custo por token, e compartilhamento de conexões entre usuários.
