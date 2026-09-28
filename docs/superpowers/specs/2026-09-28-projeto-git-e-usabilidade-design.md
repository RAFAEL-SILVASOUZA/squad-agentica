# Projeto dos agentes, integração Git e usabilidade do portal — design

Data: 2026-09-28 · Estado: aprovado em conversa, aguardando revisão desta spec.

## 1. Objetivo

Hoje um pipeline de agentes "que constrói um projeto" não produz projeto nenhum: as ferramentas de arquivo dos agentes escrevem em `/workspace`, que não existe no container, cada réplica do worker tem o próprio disco e nada aparece na interface. A saída dos agentes fica espremida numa caixa lateral do monitor, e várias telas são pouco usáveis.

Esta entrega faz um pipeline construir um projeto de verdade:

- os agentes de um run trabalham num **mesmo diretório de projeto**;
- esse projeto vem de um **repositório Git** (GitHub ou Azure DevOps) e o resultado volta como **branch + Pull Request**;
- o usuário **lê o resultado com conforto** (markdown renderizado, arquivos e diff);
- as telas atuais ganham os ajustes de usabilidade levantados no teste.

### Decisões do usuário

| Tema | Decisão |
|---|---|
| Destino no Git | Branch nova + Pull Request num repositório existente |
| Provedores | GitHub e Azure DevOps nesta entrega |
| Onde se escolhe o repositório | No pipeline |
| Área de projeto | Volume compartilhado de workspaces (abordagem 1) |
| Tela de integrações | Tela única com abas por provedor, aberta pela engrenagem no cabeçalho |

### Fora do escopo

Vários hosts (o volume é local), webhooks dos provedores, criação de repositório, merge automático do PR.

## 2. Arquitetura

```
 Portal ──REST/WS──▶ Orchestrator ──HTTP──▶ Worker (2 réplicas)
                        │   ▲                   │
                        │   └── /workspaces ◀───┘   (volume project-workspaces)
                        │
                        └──git/HTTPS + API──▶ GitHub / Azure DevOps
```

- Volume Docker `project-workspaces` montado em `/workspaces` no orchestrator e nas duas réplicas do worker (leitura e escrita).
- Cada run tem `/workspaces/<runId>/`. Só o orchestrator usa o token Git: clona no início e publica no fim. O worker nunca recebe credenciais.
- A imagem do orchestrator passa a instalar o binário `git`, que a imagem slim não traz. Os dois serviços rodam com o mesmo UID nos arquivos do volume, para o orchestrator conseguir commitar o que o worker escreveu.

### Unidades novas

| Unidade | Onde | Responsabilidade |
|---|---|---|
| `git_providers` | `agent-orchestrator/app/integrations/git_providers.py` | Interface `GitProvider` (listar repositórios, branches, criar PR, montar URL de clone autenticada) com `GitHubProvider` e `AzureDevOpsProvider` |
| `secrets` | `agent-orchestrator/app/core/secrets.py` | Criptografia Fernet do token (chave `INTEGRATIONS_SECRET_KEY`) |
| `workspace` | `agent-orchestrator/app/runtime/workspace.py` | Criar, clonar, commitar, publicar e limpar workspaces; listar arquivos e diff |
| API de workspace | `agent-orchestrator/app/api/workspaces.py` | Árvore, conteúdo, diff, zip e "publicar de novo" |
| Confinamento | `agent-worker/app/worker.py` | Resolver caminhos dentro do workspace do run e recusar o que sair dele |

## 3. Conexões Git (tela Integrações)

- Tela `/integrations` com abas **GitHub**, **Azure DevOps** e **Outras** (a caixa do Rivvn sai de Knowledge e vem para cá).
- Acesso por uma engrenagem no cabeçalho, ao lado do tema; a sidebar não ganha itens.
- Cadastro:
  - GitHub: nome e PAT (escopo `repo`).
  - Azure DevOps: nome, organização e PAT (Code: Read & Write).
- Usa a tabela `integrations` existente (`type` `github`/`azure`). O token é gravado **criptografado** em `config.token_encrypted`; a API nunca o devolve (mostra `***`).
- "Testar conexão" valida o token e mostra quantos repositórios ele enxerga.
- Excluir pede confirmação e avisa quais pipelines usam aquela conexão.
- Os tokens atuais em claro no `config` passam a ser criptografados na primeira leitura.

## 4. Repositório no pipeline

- Bloco "Repositório" no cabeçalho do editor: conexão, repositório (lista do provedor, com busca) e branch base (lista do provedor, padrão = branch padrão do repositório).
- Colunas novas em `pipelines` (migration): `git_integration_id` (FK nullable), `git_repository` (texto: `owner/repo` no GitHub, `project/repo` no Azure DevOps) e `git_base_branch`.
- Sem repositório, o pipeline roda com um workspace vazio e o resultado é baixado em zip.

## 5. Fluxo do run

1. `POST /pipelines/:id/execute` cria o run e o workspace. Com repositório: `git clone --depth 1 --branch <base>` usando a URL autenticada, depois remove a credencial do `remote`.
2. Clone com falha (token, repositório, rede): o run falha antes de chamar agentes, com o motivo em `pipeline_runs.error`.
3. O executor passa `workspaceDir` ao worker em cada `POST /execute`. O worker faz todas as ferramentas de arquivo e o `shell` operarem nele, com `cwd` = workspace.
4. Confinamento: todo caminho é resolvido com `resolve()` e precisa começar pelo workspace do run; absoluto fora, `..` e symlink para fora são recusados com erro claro ao agente.
5. Aprovação: o card mostra também os arquivos alterados até ali, com link para o diff.
6. Run concluído com repositório:
   - commit (autor "Agent Portal", mensagem com pipeline e run) na branch `agent-portal/<slug-do-pipeline>-<runId-8>`;
   - push;
   - PR com título "<pipeline>: <resumo da entrada>" e descrição com a entrada, o resumo das saídas e o link do run.
7. URL e número do PR gravados no run (`pipeline_runs.pr_url`, `pr_number`); status de publicação em `pipeline_runs.publish_status` (`none|published|failed`) e `publish_error`.
8. Sem alteração de arquivos: não cria branch nem PR; o monitor diz "Nenhum arquivo alterado".
9. Falha na publicação: o run continua **concluído**; o monitor mostra o motivo e "Tentar publicar de novo" (`POST /runs/:id/publish`), que refaz só commit, push e PR.
10. Runs falhos ou parados não publicam. Os workspaces ficam disponíveis e são apagados após `WORKSPACE_RETENTION_DAYS` (padrão 7) por uma limpeza no startup e a cada 24h.

## 6. Monitor

- Cabeçalho: nome, status, link do PR (ou motivo da falha e botão de republicar) e ações.
- Faixa compacta com as etapas (agentes e aprovações) e seus status; clicar foca o resultado daquele agente. "Ver grafo" abre o grafo completo num painel.
- Abas:
  - **Resultado** (padrão): cada agente em ordem, saída em markdown renderizado (`react-markdown` + `remark-gfm`, sem HTML cru), largura total, recolhível, botão copiar.
  - **Arquivos do projeto**: árvore + visualizador, marcação de novo/alterado/removido, diff contra a base e botão "Baixar .zip".
  - **Logs**: largura total, filtros por agente e nível, ao vivo.
  - **Histórico**: runs e checkpoints (retomar).

## 7. Demais ajustes de usabilidade

- **Pipeline:** nome e descrição editáveis no editor (novo pipeline já abre com o nome em edição); excluir com confirmação; duplicar; card da lista com repositório, último run e atalho para o monitor.
- **Editor:**
  - nós mais largos, nome em até 2 linhas e tooltip com o nome completo;
  - lista de erros de validação clicável, que foca o nó ou a aresta;
  - textos explicativos no painel da aresta.
- **Formulário de execução:** mostra a descrição de cada entrada e o repositório/branch; após executar, abre o monitor na aba Resultado.
- **Aprovações:** arquivos alterados e explicação curta de cada botão.
- **Agentes:** o modelo exibido é o que executa (com `LLM_MODEL` definido, mostra esse com uma nota).

## 8. Erros

| Situação | Comportamento |
|---|---|
| Token inválido ou sem permissão | "Testar conexão" e clone mostram a mensagem do provedor traduzida |
| Repositório ou branch inexistente | Erro no clone, run falha antes dos agentes |
| Branch de destino já existe | Sufixo numérico (`-2`, `-3`) |
| Push recusado / PR falhou | Run concluído, `publish_status=failed` com motivo, botão de republicar |
| Agente tenta sair do workspace | Erro para o agente, registrado no log do run |
| Volume cheio ou I/O | Run falha com o motivo |

## 9. Testes

- **Unitários (orchestrator):** criptografia de token; `GitProvider` com HTTP simulado para os dois provedores (listar, criar PR e erros); `workspace` com repositório git real num diretório temporário (clone, commit, diff, zip e publicação num **remote bare local**).
- **Unitários (worker):** confinamento (absoluto, `..`, symlink) e ferramentas no workspace do run.
- **Portal:** tela de integrações, bloco de repositório, abas do monitor, markdown seguro e formulários.
- **Integração:** stack com um repositório bare local servido por um container `git-daemon` de teste; pipeline de 2 agentes (mock) que escrevem arquivos, commit na branch e PR registrado por um provedor simulado.
- **E2E:** jornada com repositório de teste local e as novas telas.
- **Validação real (manual e assistida):** o usuário cadastra na tela Integrações um PAT do GitHub e/ou Azure DevOps com um repositório de teste; eu executo o pipeline com o Qwen e confiro no navegador que o PR abriu com os arquivos. Eu não digito tokens reais.

## 10. Variáveis novas

`INTEGRATIONS_SECRET_KEY` (Fernet; gerada no `.env`), `WORKSPACES_DIR` (padrão `/workspaces`), `WORKSPACE_RETENTION_DAYS` (padrão 7) e `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` (padrão "Agent Portal" / `agent-portal@localhost`).
