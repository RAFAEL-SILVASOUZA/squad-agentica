# QA Final Approval — Agent Portal V1 (2026-09-27)

## Veredito

**Aprovado com ressalvas.** O critério 1 foi atendido: todas as suítes passaram em banco vazio. O critério 2 foi atendido com uma exceção de ambiente. O provedor real local (`192.168.18.4:1234` LLM e `:4321` embeddings) recusou conexão durante toda a sessão, então a jornada rodou com mock, como prevê o prompt. Dois passos só se completam com o provedor real:

1. **Criar agente pelo chat de construção.** O LLM mock só faz eco e nunca propõe `config` com nome, então "Salvar agente" fica desabilitado. Os agentes da jornada foram criados pela API (`POST /api/agents`) com o mesmo usuário; todo o resto da jornada foi pela UI.
2. **Relevância da busca na knowledge base.** Os embeddings mock são hash, não semânticos: a consulta volta vazia (abaixo do limiar) e a UI mostra o estado vazio. Ingestão e fluxo de consulta funcionam.

Repita esses dois passos quando o provedor estiver no ar. O `.env` já está configurado; basta subir sem as sobrescritas `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock`.

## 1. Ambiente do zero

`docker compose down -v` e `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock docker compose up -d --build`. Todos os serviços ficaram healthy, e `garage-init` terminou com "buckets prontos: agents, skills, knowledge" (exit 0).

## 2. Suítes (execução desta sessão, banco vazio, provedores mock)

| Suíte | Resultado |
|---|---|
| pytest orchestrator | 515 passed |
| pytest worker | 24 passed |
| portal vitest / tsc / eslint | 376 passed / ok / ok (após as correções abaixo) |
| integração `tests/integration` | 91 passed, 1 skipped (GitHub fake contra o stack) |
| E2E Playwright (9 arquivos) | 34 passed, 1 skipped (Jornada 8, `test.skip` incondicional) |
| `npm run build` | Compiled successfully |

A primeira execução de `01-auth` logo após o (re)start do `next dev` falha por tempo: a compilação a frio do dashboard passa dos 30s do teste. Com o portal aquecido, passa 7/7. Isso é só do dev server; o build de produção compila antes.

## 3. Jornada de aceite (mock)

| Passo | Resultado | Evidência |
|---|---|---|
| Registrar e entrar | ok | redireciona ao dashboard vazio |
| Criar agente pelo chat | **ressalva** (mock) | chat responde por streaming; aviso "Rascunho incompleto" |
| Criar skill | ok (após correção do modal) | registro no banco com nome, descrição, template e variável completos |
| Knowledge: base + documento | ok | `guia-especificacao.md` com status "Pronto"; contador "1 documentos" |
| Knowledge: busca | **ressalva** (mock) | estado vazio "Nenhum trecho acima do limiar" |
| Pipeline de 2 agentes com aresta de aprovação no editor | ok | paleta, conexão por arraste, painel da aresta, "Pipeline salvo", "Grafo válido" |
| Executar e acompanhar no monitor | ok | "Executando"; badge de aprovação em tempo real no sino e na sidebar |
| Aprovar | ok | fila zera em tempo real |
| Run termina com resultado do modelo | ok | "Concluído"; artefatos `…spec` e `…review` com saída do modelo |

## 4. Tela por tela

| Tela | Resultado | Observação |
|---|---|---|
| /login, /register | ok | 01-auth 7/7; registro entra direto |
| / (dashboard) | ok após correção | contadores e runs recentes com nome da pipeline |
| /agents/new | ok (mock) | chat e estado de rascunho incompleto |
| /agents/[id] | ok | detalhe, contrato de fluxo, chat de edição |
| /pipelines | ok | status em pt-BR, "N nós / N arestas" |
| /pipelines/[id] (editor) | ok após correções | paleta sem sobreposição, handles clicáveis, salvar com nó novo |
| /pipelines/[id]/run (monitor) | ok após correção | status dos nós recomposto pelos checkpoints |
| /approvals | ok | aprovar em tempo real; card mostra ids (ver pendências) |
| /skills | ok após correção | criar, pré-visualizar, excluir |
| /tools, /mcp | ok | estados vazios; criação coberta pelo E2E 04 |
| /knowledge | ok após correção | estado vazio da busca, Enter, contador |
| 390px | ok | E2E 09 |

## 5. Defeitos encontrados e corrigidos nesta etapa

| Defeito | Causa | Correção | Teste |
|---|---|---|---|
| Registro não entrava direto (401) | rate limit de login por IP; todo login vem do IP do portal (5/min para todos) | chave IP+e-mail | `test_auth.py::test_login_rate_limit_is_per_account` |
| Salvar pipeline com nó novo dava 422 | nó com id local ganhava UUID, mas as arestas mantinham o id antigo | mapa id local → UUID em arestas e entrada | integração `test_editor_local_node_ids_are_translated_in_edges` |
| Handle de porta coberto pelo card | sem z-index | `zIndex: 1` nos handles | E2E 05 |
| Modal gravava só o 1º caractere | `onClose` novo por render re-executava `panel.focus()` | foco só ao abrir (ref para `onClose`) | `modal.test.tsx` (falha sem a correção) |
| Nó da paleta sobreposto | posição aleatória fixa | à direita do nó mais à direita + fitView | E2E 05 e verificação no navegador |
| Monitor sem status de nós já concluídos | eventos WS anteriores à abertura não voltam | status a partir dos checkpoints do run | verificação no navegador |
| Dashboard sem runs concluídos | só consultava pipelines com aprovação pendente | usa `GET /api/pipelines` | `page.test.tsx` |
| Busca vazia sem feedback; Enter não buscava; contador desatualizado | — | estado vazio, Enter, contador | `knowledge-view.test.tsx` |
| Status de pipeline em inglês | — | rótulos pt-BR | `pipelines/page.test.tsx` |

## 6. Pendências (não bloqueantes) — detalhes em `PENDENCIAS.md`

- Card de aprovação mostra UUID da pipeline e id interno do nó em vez dos nomes (baixa).
- Logs do monitor anteriores à abertura da tela não são recuperáveis (o contrato não tem histórico de logs).
- Antes do primeiro save, o editor mostra erros de entrada ainda não definida (somem ao salvar).
- Avisos de console só em dev: tags SVG do React Flow e setState durante render em `ApprovalPanel`.
- Provedor real fora do ar: repetir os passos 1–2 da seção 3.

Skills usadas: superpowers:systematic-debugging, superpowers:verification-before-completion, superpowers:test-driven-development (testes de regressão antes de fechar cada correção).
