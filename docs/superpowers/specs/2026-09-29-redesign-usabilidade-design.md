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
