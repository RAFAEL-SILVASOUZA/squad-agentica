# Análise de Planos e Especificação — Agent Portal

> **Data de abertura:** 2026-09-22
> **Status:** Análise concluída (1ª rodada)
> **Método:** análise criteriosa e detalhada, por dimensões independentes, com achados registrados aqui para ajuste futuro.
> **Escopo analisado:**
> - `docs/superpowers/specs/2026-09-17-agent-portal-design.md` (especificação, 1180 linhas)
> - `docs/superpowers/plans/2026-09-21-execution-plan.md` (plano por domínio, 395 linhas)
> - `docs/superpowers/plans/domains/D1..D10` (10 briefs de domínio)
> - `prototype/agent-portal.html` (protótipo, 2861 linhas)

---

## Como ler este documento

Cada achado tem:
- **ID** estável (ex: `C-01` para consistência, `X-01` para coerência, `L-01` para lacunas, `V-01` para viabilidade).
- **Severidade:** 🔴 crítico · 🟠 alto · 🟡 médio · 🔵 baixo.
- **Local:** seção/arquivo + referência.
- **Descrição:** o que foi encontrado.
- **Impacto:** por que importa.
- **Recomendação:** ajuste sugerido (não aplicado, apenas registrado).

Achados são **registrados, não corrigidos**. A correção é decisão futura do dono do projeto.

---

## Resumo Executivo

A análise identificou **69 achados** distribuídos em 5 dimensões. O quadro geral:

| Dimensão | 🔴 Crítico | 🟠 Alto | 🟡 Médio | 🔵 Baixo | Total |
|----------|:---------:|:------:|:-------:|:-------:|:-----:|
| 1. Consistência interna da spec | 1 | 3 | 4 | 1 | 9 |
| 2. Coerência spec ↔ plano ↔ domínios | 2 | 4 | 4 | 1 | 11 |
| 3. Completude e lacunas | 3 | 8 | 9 | 4 | 24 |
| 4. Viabilidade técnica e riscos | 2 | 5 | 4 | 2 | 13 |
| 5. Alinhamento com o protótipo | 0 | 3 | 5 | 4 | 12 |
| **Total** | **8** | **23** | **26** | **12** | **69** |

### Os 8 achados críticos (bloqueantes de design)

Estes 8 achados, se não resolvidos, impedem a implementação de funcionar de ponta a ponta. São os que merecem atenção imediata antes de qualquer código:

1. **V-01** — `interrupt()` do LangGraph é primitiva de **nó**, não de aresta. O modelo de HITL da spec/D5/D7 (flag na edge + "chamar interrupt na aresta") não casa com o LangGraph. O HITL precisa ser redesenhado para o paradigma de `interrupt()` em nó + `Command(goto=...)`.
2. **V-02** — Retomada do LangGraph **re-executa o nó do zero**. Efeitos colaterais antes do `interrupt()` (ex: criar `ApprovalRequest`) se repetem a cada resume, gerando aprovações e notificações duplicadas.
3. **X-01** — O campo `capabilities` no `AgentSnapshot` não existe na spec, e o mecanismo de injeção diverge entre D4 (campo no snapshot) e D8 (função `loader.load()`). O contrato da "mochila" fica sem dono.
4. **X-02** — D6 depende de D8, mas o grafo de dependências do plano omite a aresta `D8 → D6`. Quem orquestra pela tabela pode disparar D6 sem a mochila pronta.
5. **L-01** — Integração GitHub (escopo V1) sem backend, model, API nem credenciais. Inimplementável como está.
6. **L-02** — A ferramenta básica `shell` dá execução arbitrária a **todo** agente, anulando o sandbox. Prompt injection e sandbox escape não tratados.
7. **L-03** — `KnowledgeBase` sem model na spec e sem API de CRUD (só upload/query). O RAG não é utilizável de ponta a ponta.
8. **C-01** — `NotificationChannel` é usado em 5 campos mas nunca declarado como tipo.

### Temas transversais que se repetem em várias dimensões

- **Human-in-the-loop (V-01, V-02, V-03, X-09):** o modelo de aprovação precisa ser redesenhado para o LangGraph. É o tema com mais achados críticos/altos.
- **Contrato da mochila (X-01, L-02, C-07):** a injeção de capacidades (skills/tools/MCP) no agente não tem contrato único e tem um buraco de segurança.
- **KnowledgeBase (L-03, X-10, L-11, L-18):** a entidade central do RAG não está formalizada na spec.
- **Protocolo de tempo real (V-08, L-07):** Socket.IO no frontend vs WebSocket nativo no backend são incompatíveis; e o WS não tem autenticação.
- **Infra de V1 (V-06, L-24):** a imagem `postgres:15` não tem pgvector e o pacote `langgraph-checkpoint-postgres` não está nas dependências.

### Recomendação de ordem de ajuste

1. **Redesenhar o HITL** (V-01, V-02, V-03, X-09) — afeta o contrato D5↔D6↔D7, o coração do sistema.
2. **Fechar o contrato da mochila** (X-01, C-07, L-02) — afeta D3, D4, D6, D8.
3. **Formalizar KnowledgeBase** (L-03, X-10, L-11, L-18) — afeta spec §4, D3, D9.
4. **Corrigir a infra de V1** (V-06, V-08, L-24) — quebras de build/conexão no D1/D3.
5. **Completar a API** (L-01, L-05, L-04, L-09, L-10, L-21, L-22) — endpoints ausentes.
6. **Documentar segurança** (L-02, L-07, L-14, L-15) — gaps estruturais.
7. **Ajustes de consistência e nomenclatura** (C-02..C-09, X-03..X-08) — refinamentos.
8. **Alinhar o protótipo** (P-01..P-12) — botões mortos e dados de exemplo.

---

## 1. Consistência Interna da Especificação

_Contradições entre seções, termos usados de forma inconsistente, interfaces que não batem entre definição e uso, fluxos descritos de forma diferente em seções diferentes._

**9 achados (1 crítico, 3 altos, 4 médios, 1 baixo).**

### C-01 — `NotificationChannel` é usado mas nunca declarado
- **Severidade:** 🔴 crítico
- **Local:** Seção 4.1 (linha 127), 4.2 (linha 213), 4.5 (linhas 339, 345, 346)
- **Descrição:** O tipo `NotificationChannel` é referenciado em 5 campos (`Agent.approvalChannel`, `AgentSnapshot.approvalChannel`, `ApprovalRequest.channel`, `ApprovalRequest.attemptedChannels`, `ApprovalRequest.fallbackChannel`), mas nunca há uma declaração `type NotificationChannel = ...` no documento. A linha 127 tem apenas um comentário: `// "in-app" | "email" | "teams" | "slack"`, que é documentação, não uma declaração de tipo.
- **Impacto:** Qualquer implementação TypeScript que tente compilar estas interfaces falhará com "Cannot find name 'NotificationChannel'". Além disso, a seção 13 (Escopo V1) inclui apenas "in-app via WebSocket, email" como canais de notificação, mas o tipo (pelo comentário) inclui "teams" e "slack" que estão fora de escopo V1. A ausência da declaração impede saber se o tipo deve refletir o escopo V1 ou o conjunto completo.
- **Recomendação:** Adicionar explicitamente `type NotificationChannel = "in-app" | "email" | "teams" | "slack";` na seção 4.5 (ou 4.1), e clarificar se na V1 apenas `"in-app" | "email"` são implementados (os demais podem estar no tipo mas desabilitados).

### C-02 — `AgentSnapshot` omite campos presentes em `Agent`
- **Severidade:** 🟠 alto
- **Local:** Seção 4.1 (interface `Agent`, linhas 96-129) vs. Seção 4.2 (interface `AgentSnapshot`, linhas 197-214)
- **Descrição:** O `AgentSnapshot` é descrito como "cópia imutável do agente no momento da execução" (linha 216). Porém, ele omite três campos que existem em `Agent`:
  - `strategy: string` (linha 106) — a abordagem/passo a passo do agente
  - `approvalMessage: string` (linha 128) — o template da notificação de aprovação
  - `name: string` e `description: string` (linhas 100-101) — metadados básicos

  Se o snapshot é a fonte de verdade durante a execução (o agente original pode ser editado), e `strategy` é parte da definição do agente ("Definição via chat: prompt + estratégia"), a execução não terá acesso à estratégia. Da mesma forma, sem `approvalMessage`, o sistema não sabe qual template de notificação usar.
- **Impacto:** O runtime não terá os dados necessários para executar o agente corretamente (sem estratégia) nem para enviar a notificação de aprovação (sem template). Implementadores terão que decidir se buscam esses campos no agente original (que pode ter mudado) ou se o snapshot é incompleto.
- **Recomendação:** Adicionar `strategy`, `approvalMessage`, `name` e `description` ao `AgentSnapshot`, ou explicitar que esses campos são lidos do agente original no momento da execução (e justificar por que não são congelados).

### C-03 — Semântica de `maxIterations` contraditória entre seção 4.1 e seção 5.2
- **Severidade:** 🟠 alto
- **Local:** Seção 4.1 (linha 122) vs. Seção 5.2 (linha 421)
- **Descrição:**
  - Linha 122 (comentário em `Agent.maxIterations`): "limite de execuções deste agente **POR CICLO** (A→B→A conta como 1 ciclo)" — implica que o contador é resetado a cada ciclo completo.
  - Linha 421 (seção 5.2): "maxIterations conta execuções do agente **isoladamente dentro de um ciclo**. Se o agente A executa 5 vezes seguidas (mesmo que alternando com B), **o ciclo é abortado**. O limite é por agente, não por ciclo global."

  A primeira diz "por ciclo" (contador resetado por ciclo). A segunda diz "o limite é por agente, não por ciclo global" e dá o exemplo de "5 vezes seguidas" abortando o ciclo. Se o limite é "por agente" e não "por ciclo", então o contador nunca reseta — é um contador de vida total do agente na pipeline. Mas a linha 122 diz explicitamente "POR CICLO (A→B→A conta como 1 ciclo)", o que implica reset.

  Além disso, a linha 421 diz "Se o agente A executa 5 vezes seguidas (mesmo que alternando com B), o ciclo é abortado" — mas se A→B→A conta como 1 ciclo (linha 122), então A executou 2 vezes em 1 ciclo, não 5. Para A executar 5 vezes, seriam 4 ciclos completos (A→B→A→B→A→B→A→B→A). A frase "5 vezes seguidas (mesmo que alternando com B)" é ambígua: "seguidas" sugere sem reset, mas "alternando com B" sugere que há ciclos intermediários.
- **Impacto:** A implementação do anti-loop-infinito depende diretamente desta semântica. Se o contador reseta por ciclo, um loop A→B→A com maxIterations=3 nunca aborta (cada ciclo A só executa 1 vez). Se não reseta, aborta após 3 execuções totais de A. A diferença é crítica para o comportamento do sistema.
- **Recomendação:** Unificar a semântica. Sugestão: "maxIterations é o número máximo de vezes que este agente pode executar ao longo de toda a pipeline (não reseta por ciclo). Ex: maxIterations=3 significa que o agente A pode executar no máximo 3 vezes no total, independentemente de quantos ciclos A→B→A ocorram."

### C-04 — `Pipeline.status` não tem valor para "paused" mas a API tem endpoint de pause
- **Severidade:** 🟡 médio
- **Local:** Seção 4.2 (interface `Pipeline`, linha 175) vs. Seção 9.1 (API, linha ~680)
- **Descrição:** A interface `Pipeline` declara `status: "draft" | "running" | "paused" | "completed" | "failed"`. A API tem `POST /api/pipelines/:id/pause` e `POST /api/pipelines/:id/resume`. Porém, a seção 5.1 (ciclo de vida) não descreve o fluxo de pause/resume como parte do ciclo de vida — apenas mostra "Pipeline completa / falhou" como estados terminais. O estado "paused" aparece na enumeração mas não há nenhuma seção que descreva quando e como uma pipeline entra em "paused" (é diferente de "interrupt" por aprovação humana, que é um estado de espera, não de pausa pelo usuário).
- **Impacto:** Ambiguidade sobre se "paused" é um estado do usuário (pausou manualmente) ou do sistema (aguardando aprovação). Se for do usuário, a transição de estado e o comportamento do runtime (o que acontece com agentes em execução quando se pausa) não estão especificados.
- **Recomendação:** Adicionar na seção 5.1 (ou uma subseção 5.4) o fluxo de pause/resume manual: o que acontece com agentes em execução, como o checkpoint é salvo, e a diferença entre "paused" (usuário) e "interrupted" (aprovação).

### C-05 — `EdgeCondition.field` inclui "status" e "output" mas não há definição do que são
- **Severidade:** 🟡 médio
- **Local:** Seção 4.2 (interface `EdgeCondition`, linhas 255-258)
- **Descrição:** A interface `EdgeCondition` declara `field: "action" | "status" | "output"`. A spec explica o caso `field === "action"` (value deve ser `FlowAction | FlowAction[]`). Porém, não há nenhuma definição do que `field === "status"` ou `field === "output"` significam:
  - "status": qual status? O status da pipeline? O status do checkpoint? O status do agente?
  - "output": qual output? O nome de um port? O valor de um output?

  A seção 5.2 só usa `field: "action"` como exemplo. As regras de validação (1-8) não mencionam validação para "status" ou "output".
- **Impacto:** O compiler não tem regras claras para validar condições com `field: "status"` ou `field: "output"`. Implementadores terão que inventar a semântica, o que pode levar a comportamentos inconsistentes.
- **Recomendação:** Ou (a) restringir `field` a apenas `"action"` na V1 e deixar "status"/"output" para V2, ou (b) definir explicitamente o que cada campo representa e como o `value` é validado para cada um.

### C-06 — Regra 6 de validação vs. regra 7: conflito em fan-out com inputs required
- **Severidade:** 🟡 médio
- **Local:** Seção 4.2, regras 5, 6 e 7 (linhas 268-283)
- **Descrição:**
  - Regra 5: "Um agente pode ter uma data edge para B e uma flow edge para C (alvos diferentes) — nesse caso ambos rodam em fan-out a partir do source, mas só B recebe o dado."
  - Regra 6: "Se um agente target tem inputs required e não recebe data edge correspondente, o compiler rejeita o grafo."

  Conflito: Se C tem inputs `required` e recebe apenas uma flow edge (sem data edge) do source, a regra 5 diz que é válido (fan-out com C não recebendo dado), mas a regra 6 diz que o compiler deve rejeitar porque C tem inputs required sem data edge correspondente. A regra 5 descreve um cenário que a regra 6 proíbe.
- **Impacto:** O compiler não sabe se aceita ou rejeita o grafo. Se seguir regra 6, o cenário da regra 5 é impossível. Se seguir regra 5, a regra 6 precisa de exceção.
- **Recomendação:** Clarificar que a regra 6 se aplica apenas a agentes que são target de data edges (ou que têm inputs required que *deveriam* ser atendidos). Alternativamente, reformular a regra 5 para: "Se C não tem inputs required, pode receber apenas flow edge sem data edge."

### C-07 — `Skill.type` inclui "tool" e "function" mas a seção 6.2 e 6.4 tratam tools como camada separada
- **Severidade:** 🟡 médio
- **Local:** Seção 4.4 (interface `Skill`, linha 303) vs. Seção 6.2 (tabela de tipos) vs. Seção 6.4 (Tools Custom) vs. Seção 6.6 (Mochila)
- **Descrição:** A interface `Skill` (seção 4.4) tem `type: "prompt" | "tool" | "function"` e um `SkillDefinition` que inclui variantes para "tool" (com `schema` e `endpoint`) e "function" (com `module`, `functionName`, `args`). Porém:
  - A seção 6.2 descreve 3 tipos de skill: `prompt`, `tool` (function calling), `function` (Python custom).
  - A seção 6.4 descreve "Tools Custom" como uma camada **separada** de Skills, com sua própria interface `CustomTool`, seu próprio registry, sua própria API (`/api/tools`), e seu próprio fluxo de deploy.
  - A seção 6.6 (Mochila) lista "Skills" e "Tools Custom" como camadas **distintas**.
  - A interface `Agent` tem `skills: SkillRef[]` e `tools: ToolRef[]` como arrays separados.

  Se "tool" e "function" são tipos de Skill (seção 4.4), por que Tools Custom têm interface, registry e API próprios? A `SkillDefinition` com `type: "tool"` (schema + endpoint) parece descrever uma tool genérica com endpoint HTTP, enquanto `CustomTool` (seção 6.4) é um script Python com sandbox. São coisas diferentes usando o mesmo nome "tool".
- **Impacto:** Confusão na implementação: o `Skill Registry` deve armazenar tools? Ou o `Tool Registry`? A API `/api/skills` retorna tools? A UI de "Skills" mostra tools? O `SkillRef` referencia uma tool?
- **Recomendação:** Ou (a) remover "tool" e "function" de `Skill.type` (deixando apenas "prompt") e tratar Tools Custom exclusivamente pela interface `CustomTool`, ou (b) unificar: Tools Custom são um subtipo de Skill com `type: "function"`, e a seção 6.4 descreve o detalhe de implementação. A opção (a) é mais coerente com a arquitetura de camadas separadas da seção 6.6.

### C-08 — `PipelineNode` não tem `id` próprio, mas `PipelineEdge.source/target` referenciam "agentId"
- **Severidade:** 🟡 médio
- **Local:** Seção 4.2 (interface `PipelineNode`, linhas 189-193; interface `PipelineEdge`, linhas 220-228)
- **Descrição:** `PipelineNode` não tem um campo `id` próprio — ele tem `agentId: string` (referência ao agente). `PipelineEdge` tem `source: string` e `target: string` com o comentário "agentId de origem/destino". Porém, `Pipeline.entryNodeId: string` é descrito como "O nó de entrada é explícito".

  Problema: Se um agente pode aparecer **mais de uma vez** no grafo (ex: o mesmo agente em posições diferentes, ou o mesmo agente em dois ramos de um fan-out), como se distingue um nó de outro? O `entryNodeId` referenciaria o `agentId`, mas se há dois nós com o mesmo `agentId`, qual é o entry?

  Além disso, a seção 5.2 mostra um loop A→B→A onde o agente A aparece em duas posições do grafo. Se `PipelineNode` é identificado por `agentId`, não há como ter dois nós com o mesmo agente.
- **Impacto:** O grafo não suporta múltiplas instâncias do mesmo agente (que é o caso do loop A→B→A da seção 5.2). O compiler não consegue construir um StateGraph com nós duplicados. A referência `entryNodeId` fica ambígua.
- **Recomendação:** Adicionar `id: string` (nodeId) ao `PipelineNode` como identificador único do nó no grafo, distinto de `agentId`. As edges devem referenciar `nodeId` (não `agentId`). O `entryNodeId` referenciará o `nodeId`.

### C-09 — Seção 13 (Escopo V1) inclui "Integração: GitHub" mas a seção 8 não detalha o comportamento
- **Severidade:** 🔵 baixo
- **Local:** Seção 13 (Escopo V1, linha ~1133) vs. Seção 8 (Integrações)
- **Descrição:** A seção 13 inclui "Integração: GitHub (leitura de PRs/issues)" no escopo V1. A seção 8 lista GitHub na tabela de plataformas com "PRs, issues, code review, CI/CD" como capacidades. Porém, não há nenhuma seção que detalhe:
  - Qual o contrato de uma integração GitHub (quais tools/expoés para o agente)?
  - Como o agente usa a integração (é uma tool? é injetado no contexto? é uma skill?).
  - Qual a diferença prática entre uma "Integração" (seção 8) e uma "Tool Custom" (seção 6.4) ou um "Servidor MCP" (seção 6.7) que faz a mesma coisa (chamar API do GitHub).

  A seção 6.7 explica por que MCP não é Integração, mas não explica o que uma Integração **é** em termos de implementação — apenas que tem "comportamento fixo na plataforma".
- **Impacto:** Implementadores não sabem como modelar a integração GitHub: é um conjunto de tools pré-definidas? É um wrapper de API? Como o agente a invoca? A distinção conceitual entre Integração e Tool Custom/MCP fica vaga na prática.
- **Recomendação:** Adicionar uma subseção em 8 (ex: 8.1) que descreva o contrato de uma Integração: como é exposta ao agente (como tools pré-definidas? como contexto?), qual o formato do `config` em `IntegrationRef`, e dar o exemplo concreto da integração GitHub (quais operações expõe, como o agente as chama).

---

## 2. Coerência entre Especificação, Plano e Domínios

_Divergências entre o que a spec define, o que o plano de execução declara e o que os briefs de domínio (D1–D10) assumem. Contratos de interface quebrados entre domínios, dependências inconsistentes, escopos que não se alinham._

**11 achados (2 críticos, 4 altos, 4 médios, 1 baixo).**

### X-01 — Campo `capabilities` no `AgentSnapshot` não existe na spec e o mecanismo de injeção diverge entre D4 e D8
- **Severidade:** 🔴 crítico
- **Local:** spec §4.2 (`AgentSnapshot`) · D4 "Contratos de interface → Para D8" · D8 "Contratos de interface → Para D4/D6"
- **Descrição:** A spec define `AgentSnapshot` com os campos `agentId, version, prompt, skills, tools, mcpServers, knowledge, integrations, inputs, outputs, actions, model, maxIterations, timeout, requiresApproval, approvalChannel` — **não há campo `capabilities`**. O D4 declara: *"o `base.py` deve injetar no prompt as capacidades associadas (interface: `capabilities` no snapshot)"*. O D8 declara: *"a mochila (skills/tools/MCP) é injetada no `AgentSnapshot` e consumida pelo `Agent.run` no runtime. Contrato: `loader.load(agent_snapshot) -> capabilities`."* São dois mecanismos distintos: D4 pressupõe um **campo** `capabilities` dentro do snapshot (que o D8 preencheria), D8 pressupõe uma **função** `loader.load(snapshot) -> capabilities` que o runtime chama. Nenhum dos dois está na spec, e o D3 (que modela `AgentSnapshot` como JSONB e entrega o tipo `AgentSnapshot` em `types.ts`) não sabe qual dos dois contratos materializar.
- **Impacto:** O D3 modela o snapshot sem `capabilities`; o D4 escreve `base.py` lendo `snapshot.capabilities`; o D8 escreve `loader.load()`. Na integração (D6 orquestra `Agent.run`), ninguém sabe quem monta a mochila nem onde ela vive. O contrato de injeção de capacidades — o coração da "mochila" da spec (§6.6) — fica sem dono claro e sem campo no modelo.
- **Recomendação:** Decidir um único contrato e documentá-lo nos três lugares: (a) adicionar `capabilities` ao `AgentSnapshot` da spec (ou declarar que é derivado, não persistido), (b) fixar que o D8 expõe `loader.load(snapshot) -> capabilities` e que o **D6** (não o D4) chama esse loader antes de `Agent.run`, ou (c) o D4 chama o loader internamente. Atualizar D3 para refletir o campo/derivação.

### X-02 — D6 depende de D8, mas o grafo de dependências do plano e a ordem de fases não registram essa aresta
- **Severidade:** 🔴 crítico
- **Local:** plano "Visão Geral" (tabela de dependências + grafo ASCII) · plano "Ordem de Execução (Fases)" · D6 "Dependências"
- **Descrição:** O D6 declara explicitamente: *"Dependência: **D5** (compiler), **D8** (capacidades — para a mochila do agente no runtime)"* e *"**D8:** mochila do agente (skills/tools/MCP injetadas no prompt/capacidades) — o `Agent.run` precisa das capacidades prontas."* Porém a tabela de dependências do plano lista D6 como `D5` apenas, e o grafo ASCII mostra só `D5 ──→ D6`. A FASE 5 (D6) vem **depois** da FASE 4 (D5 + D8), então a ordem cronológica até funciona, mas a aresta D8→D6 está ausente do grafo e da tabela. O risco é real: se D6 for executado em paralelo com D8 (o plano permite paralelizar dentro da FASE 4, e D6 só "depende de D5" na tabela), o `Agent.run` do D6 não terá a mochila pronta.
- **Impacto:** Quem orquestra a execução pela tabela do plano pode disparar D6 sem D8 concluído, quebrando a injeção de capacidades no runtime. A dependência declarada no brief é a fonte de verdade, mas o plano (que é o artefato de coordenação) a omite.
- **Recomendação:** Adicionar a aresta `D8 ──→ D6` ao grafo ASCII e à tabela de dependências do plano, e deixar explícito na FASE 5 que D6 requer D5 **e** D8 concluídos.

### X-03 — `EdgePanel.tsx` entregue pelo D5 não está na lista de componentes da spec (§11) nem no plano (D10)
- **Severidade:** 🟠 alto
- **Local:** spec §11 (`components/`) · D5 "Arquivos que OWNS" + "Contratos de interface → Para D10" · D10 "Dependências" + "Contratos de interface"
- **Descrição:** O D5 OWNS `components/EdgePanel.tsx` (painel de configuração da aresta) e o declara como entregável para o D10: *"Para D10: `FlowEditor.tsx` + `EdgePanel.tsx` são a UI do editor."* O D10 consome os dois: *"D5: `FlowEditor.tsx`, `EdgePanel.tsx` (D5 entrega; D10 integra no route de pipeline)."* Porém a spec §11 lista em `components/` apenas `FlowEditor.tsx` (com o comentário "React Flow wrapper") e **não lista `EdgePanel.tsx`**. O plano (tabela D10) também não menciona `EdgePanel.tsx`. Ou seja, um componente que dois domínios tratam como contrato real não existe na spec nem no plano.
- **Impacto:** Menor que os críticos (o D5 e o D10 estão alinhados entre si), mas a spec — fonte de verdade da UI — fica incompleta: o painel de aresta (que carrega tipo, dataMapping, condition, requiresApproval, exigido pela ADR-006 "Painel lateral ao clicar na aresta") não tem registro na spec. Risco de o D10 não reservar a view/route para ele.
- **Recomendação:** Adicionar `EdgePanel.tsx` à lista de componentes da spec §11 e à tabela de entregas do D10 no plano, alinhando com o que D5 já declara.

### X-04 — `AgentPreview.tsx` entregue pelo D4 não está na spec (§11) nem no plano
- **Severidade:** 🟠 alto
- **Local:** spec §11 (`components/`) · D4 "Arquivos que OWNS" + "Contratos de interface → Para D10" · D10 "Contratos de interface → D4"
- **Descrição:** O D4 OWNS `components/AgentPreview.tsx` e o declara para o D10: *"Para D10: `AgentChat.tsx` + `AgentPreview.tsx` + o tipo `Agent` pra renderizar cards."* O D10 consome: *"D4: `AgentChat.tsx`, `AgentPreview.tsx`, tipo `Agent`."* Mas a spec §11 lista `AgentChat.tsx` e **não lista `AgentPreview.tsx`**; o plano também não o menciona. Mesmo padrão do X-03: componente que é contrato entre D4 e D10, ausente da spec e do plano.
- **Impacto:** A spec fica incompleta sobre a UI de preview do agente (que o chat de construção do §10.1 exige: "preview antes de salvar", risco §14). Risco de o D10 não integrar o preview no Agent Detail.
- **Recomendação:** Adicionar `AgentPreview.tsx` à spec §11 e ao plano, alinhando com D4/D10.

### X-05 — `KnowledgeView.tsx` (D9) vs "view Knowledge" (spec §11 não lista; D10 chama de "Knowledge"): nome divergente
- **Severidade:** 🟠 alto
- **Local:** spec §11 (`components/`) · D9 "Arquivos que OWNS" + "Contratos de interface → Para D10" · D10 "Dependências" + "Contratos de interface → D9"
- **Descrição:** O D9 OWNS `components/KnowledgeView.tsx` e declara: *"Para D10: `KnowledgeView.tsx` + tipos `KnowledgeBase`/`RivvnConnection`."* O D10 consome exatamente `KnowledgeView.tsx` (alinhado entre si). Porém a spec §11 **não lista nenhum componente de Knowledge** em `components/` (a lista termina em `PipelineMonitor.tsx`), e o plano (tabela D10) chama a view de "Knowledge" sem nomear o arquivo. Diferente de `SkillsLibrary.tsx`/`ToolsEditor.tsx`/`MCPServersLibrary.tsx` (que a spec §11 lista explicitamente), o componente de Knowledge não tem nome na spec.
- **Impacto:** A spec não fixa o nome do componente de Knowledge, enquanto D9 e D10 já o fixaram (`KnowledgeView.tsx`). Inconsistência de nomenclatura entre o nível da spec e o nível dos briefs; risco de drift se a spec for a referência de aceite.
- **Recomendação:** Adicionar `KnowledgeView.tsx` à spec §11 (e ao plano) para fechar o loop de nomenclatura, já que D9/D10 estão alinhados entre si.

### X-06 — Endpoint `GET /api/pipelines` (listar) ausente da spec §9.1, mas implementado por D5 e D3
- **Severidade:** 🟠 alto
- **Local:** spec §9.1 (tabela de endpoints de pipelines) · D5 tarefa 5.1 · D3 "Contratos de interface → Para D5"
- **Descrição:** A spec §9.1 lista para pipelines: `POST /api/pipelines`, `GET /api/pipelines/:id`, `PUT /api/pipelines/:id`, `POST .../execute`, `pause`, `resume`, `stop`, `GET .../checkpoints`, `POST .../checkpoints/:cpId/resume`. **Não há `GET /api/pipelines` (listar todos).** O D5, porém, implementa: *"Preencher o router stub: `POST /api/pipelines` (criar grafo), `GET /api/pipelines`, `GET /api/pipelines/:id`, `PUT /api/pipelines/:id`."* — inclui `GET /api/pipelines`. O D3 declara entregar *"router `/api/pipelines`"* (plural, genérico). Ou seja, D5 e D3 criam um endpoint de listagem que a spec não especificou.
- **Impacto:** Escopo creep leve: o D3 (que faz stubs "para todos os recursos da seção 9") não tem na spec o endpoint `GET /api/pipelines` para criar o stub, e o D5 o implementa mesmo assim. Se o aceite for "todos os endpoints da spec respondem", este endpoint extra fica fora do escopo formal da spec.
- **Recomendação:** Adicionar `GET /api/pipelines` (listar) à spec §9.1, já que o dashboard do portal (D10) precisa listar pipelines para navegar.

### X-07 — Regras 9, 10, 11 do validador (D5) estendem a spec sem registro: regra 10 contradiz a flexibilidade de `actions` da spec
- **Severidade:** 🟡 médio
- **Local:** spec §4.2 (regras 1-8) + §4.1 (`actions`) · D5 tarefa 5.2 (regras 1-11) + "Comportamento do Compiler"
- **Descrição:** A spec §4.2 define **8** regras de validação. O D5 declara implementar *"as 8 regras da seção 4.2 **+ 3 regras adicionais**"* (9, 10, 11). As regras 9 (`entryNodeId` referencia nó existente) e 11 (rejeitar flow edges idênticas duplicadas) são extensões razoáveis e não contradizem a spec. A **regra 10** é problemática: *"Se um agente declara `actions: ["return"]` mas nenhuma flow edge com condition `action == "return"` sai dele → rejeitar (loop sem destino)."* A spec §4.1 define `actions: FlowAction[]` como o que o agente **pode** produzir, e o §4.2/ADR-006 trata `return` como opcional (o agente declara o que *pode* fazer; o grafo decide o que *acontece*). A spec **nunca** exige que todo `action` declarado tenha uma edge correspondente — na verdade a spec permite que o usuário declare `actions` livres (o tipo é livre, §4.1). A regra 10 do D5 impõe um acoplamento contrato↔grafo que a spec não pede e que pode rejeitar grafos válidos por spec (ex: agente que declara `return` como capacidade mas o grafo atual não usa loop).
- **Impacto:** O validador do D5 pode rejeitar grafos que a spec considera válidos. Se o usuário declara `actions: ["follow","return","finalize"]` (capacidades) mas só usa `follow` no grafo, a regra 10 rejeita por falta de edge `return`. Isso conflita com o princípio da spec de que `actions` é o que o agente *pode* produzir, não o que o grafo *deve* rotear.
- **Recomendação:** Documentar as regras 9-11 na spec (seção 4.2) para que a extensão seja rastreável. Para a regra 10, alinhar com a spec: ou a spec passa a exigir edge para cada `action` declarada, ou o D5 relaxa a regra 10 para "aviso" (não erro) quando o `action` declarado não tem edge correspondente, preservando a semântica de "capacidade" da spec.

### X-08 — `maxIterations`: a spec diz "por agente, não por ciclo global", mas o D5 implementa a guarda no compiler (route_fn) e o D6 no runtime — duplicação de responsabilidade não resolvida
- **Severidade:** 🟡 médio
- **Local:** spec §4.1 (`maxIterations`) + §5.2 · D5 "maxIterations no State" + "Comportamento do Compiler" · D6 tarefa 6.4 + "Riscos"
- **Descrição:** A spec §4.1 define `maxIterations` como *"limite de execuções deste agente POR CICLO"* e o §5.2 reforça: *"maxIterations conta execuções do agente isoladamente dentro de um ciclo... O limite é por agente, não por ciclo global."* O D5 implementa a guarda **no compiler** (route_fn): *"Se `state["{agentId}.iterations"] >= maxIterations` → rotear para `END` (aborta o ciclo). Isso é uma **guarda de segurança** no compiler, independente do D6."* O D6 implementa **no runtime** (iter_counter.py): *"contador por agente por execução. Se um agente excede `maxIterations` no ciclo, abortar a pipeline (estado failed)."* Os dois breves reconhecem a sobreposição (D5: "São complementares, não redundantes"), mas a spec **não** define onde o limite é aplicado (compiler vs runtime). Há dois mecanismos que abortam a mesma condição, com comportamentos ligeiramente diferentes: D5 roteia para `END` (encerra o grafo limpo), D6 "aborta a pipeline (estado failed)".
- **Impacto:** Duplicação de responsabilidade: quem é a fonte de verdade do abort? Se o compiler já roteia para `END` ao exceder, o iter_counter do D6 nunca dispara (o grafo já terminou). Se o D6 é a fonte, a guarda do compiler é dead code. O estado final diverge (`completed` via END vs `failed` via abort). A spec não resolve.
- **Recomendação:** A spec deve declarar onde `maxIterations` é aplicado (recomendo: runtime/D6, já que o compiler não deve ter lógica de execução). O D5 remove a guarda de maxIterations da route_fn (deixa só a topologia) e o D6 é a única fonte de verdade do abort, com estado `failed` consistente.

### X-09 — `requiresApproval`: a spec o coloca na **edge** (§4.2/§16), mas o D7 o detecta na edge e o D4 o liga ao **output do agente** — e o `AgentSnapshot` tem `requiresApproval` no **agente**, não na edge
- **Severidade:** 🟡 médio
- **Local:** spec §4.1 (`Agent.requiresApproval`) + §4.2 (`PipelineEdge.requiresApproval`) + §16 · D5 "requiresApproval no compiler" · D7 tarefa 7.1 · D4 "Contratos de interface → Para D7"
- **Descrição:** A spec tem `requiresApproval` em **dois** lugares: (a) `Agent.requiresApproval` (§4.1, "Human-in-the-loop") e (b) `PipelineEdge.requiresApproval` (§4.2, "se true, a transição por esta aresta passa por humano"). O §16 ("Return policy") esclarece que é **por edge**: *"Cada `PipelineEdge` tem `requiresApproval: boolean`... Se `true`, a transição por aquela aresta passa por aprovação humana."* O D5 e o D7 tratam corretamente a flag **da edge** (D5: "se a edge tem `requiresApproval: true`"; D7: "detecta `requiresApproval` na edge"). Porém o D4 declara: *"Para D7: o output do agente (com action) é o que dispara interrupts em edges com `requiresApproval`."* — isso é coerente com a edge. O problema é que a spec **também** tem `Agent.requiresApproval` (§4.1) e `AgentSnapshot.requiresApproval` (§4.2), que **nenhum** domínio usa para disparar interrupt. O D3 modela `ApprovalRequest` e o snapshot, mas a flag do agente fica órfã.
- **Impacto:** A spec define `requiresApproval` em dois níveis (agente e edge) sem dizer qual governa o interrupt. Os domínios (D5/D7) usam a da edge, deixando `Agent.requiresApproval`/`AgentSnapshot.requiresApproval` sem consumidor. Se o usuário setar `requiresApproval: true` no agente (não na edge), nada acontece — comportamento não documentado.
- **Recomendação:** A spec deve declarar que o interrupt é governado **apenas** pela `PipelineEdge.requiresApproval` (conforme §16) e remover ou redefinir `Agent.requiresApproval`/`AgentSnapshot.requiresApproval` (ex: como default herdado pela edge, ou removê-lo). Os domínios já estão alinhados com a edge; basta a spec fechar a ambiguidade.

### X-10 — `KnowledgeBase` model: a spec §4 não define a interface `KnowledgeBase`, mas D3/D9 a modelam com campos (escopo, fonte) que a spec só descreve em prosa (§7.3)
- **Severidade:** 🟡 médio
- **Local:** spec §4 (Modelo de Dados) + §7.3 (Escopo) · D3 "Contratos de interface → Para D9" · D9 tarefa 9.1
- **Descrição:** A spec §4 define interfaces para `Agent`, `Pipeline`, `Checkpoint`, `Skill`, `ApprovalRequest` — mas **não define uma interface `KnowledgeBase`**. O §7.3 descreve em prosa que a KB pode ser "Global / Por agente / Por pipeline" (escopo), e o §7.1 lista as fontes (upload/vector-db/url/rivvn). O D3 declara entregar o model `KnowledgeBase` e o D9 o modela: *"KnowledgeBase: nome, escopo (global/agent/pipeline), fonte (upload/vector-db/url/rivvn), referência."* Ou seja, D3 e D9 criam um model com campos (nome, escopo, fonte, referência) que a spec **não formaliza em interface**. O `KnowledgeRef` da spec (§4.1) tem só `source` e `reference` — não tem `name` nem `scope`.
- **Impacto:** O model `KnowledgeBase` do D3/D9 tem campos (`name`, `scope`) que não têm correspondência na interface da spec. O `KnowledgeRef` (que é o que o agente referencia) é diferente do `KnowledgeBase` (que é a entidade da biblioteca). A spec não define a relação entre os dois nem a interface da entidade. Risco de o D3 modelar campos que a spec não validou.
- **Recomendação:** Adicionar à spec §4 uma interface `KnowledgeBase` (id, name, scope: "global"|"agent"|"pipeline", source, reference, ownerId) e esclarecer a relação com `KnowledgeRef` (o agente referencia uma `KnowledgeBase` por id, e `KnowledgeRef.reference` guarda o id da KB ou a collection).

### X-11 — Protótipo `prototype/agent-portal.html` referenciado pelo plano e pelo D10 não existe no workspace
- **Severidade:** 🔵 baixo
- **Local:** plano (cabeçalho "Base") · D10 (cabeçalho "Base" + "Nota sobre o protótipo")
- **Descrição:** O plano declara: *"Base: Spec `2026-09-17-agent-portal-design.md` + protótipo `prototype/agent-portal.html`."* O D10 reforça: *"Base: spec (...) + protótipo `prototype/agent-portal.html`"* e *"Basear a UI no protótipo `prototype/agent-portal.html` (estrutura, cores dark, layout)."* Porém o arquivo **não existe** no workspace (a estrutura do projeto só contém `docs/superpowers/` e `ANALISE-ESPECIFICACAO.md`; o `glob` não encontra `prototype/agent-portal.html`).
- **Impacto:** O D10 (e o plano) dependem de um artefato de referência que não está disponível. O worker do D10 não pode "basear a UI no protótipo" se ele não existe. As regras de design (sem emojis, SVGs Lucide, menus funcionais) vêm do protótipo, que está ausente.
- **Recomendação:** Adicionar o protótipo ao workspace (ou ao repositório) antes de executar o D10, ou documentar as regras de design do protótipo diretamente na spec/plano para que o D10 não dependa de um arquivo ausente.

**Observação sobre eixos sem achado:**
- **Canais WebSocket (§9.7):** os 5 canais (`pipeline:status`, `pipeline:log`, `agent:output`, `approval:new`, `approval:resolved`) têm emissor e consumidor consistentes — D3 define as constantes, D6 emite `pipeline:*`/`agent:output`, D7 emite `approval:*`, D10 consome todos. ✓
- **Modelos de dados (§4 vs D3):** todos os models da spec têm correspondência no D3, exceto `KnowledgeBase` (X-10, que é ausência na spec, não no D3). ✓
- **Endpoints de API (§9 vs D3/D4-D9):** todos os endpoints da spec têm um domínio responsável, exceto `GET /api/pipelines` que está nos domínios mas não na spec (X-06). ✓
- **Ordem de execução:** as fases são acíclicas e viáveis; a única aresta ausente é D8→D6 (X-02). ✓

---

## 3. Completude e Lacunas

_Itens de escopo V1 sem especificação detalhada, interfaces/APIs mencionadas mas não documentadas, casos de borda não cobertos, dependências não declaradas, fluxos de erro não especificados, configurações necessárias não documentadas._

**24 lacunas (3 críticas, 8 altas, 9 médias, 4 baixas).**

### L-01 — Integração GitHub (escopo V1) sem backend, model, API nem credenciais
- **Severidade:** 🔴 crítico
- **Local:** spec seção 13 (item "Integração: GitHub (leitura de PRs/issues)"), seção 8, seção 9; plano D10 (10.12); ausente em D3/D8
- **Descrição:** A integração GitHub é o único item de integração de plataforma incluído no escopo V1, mas não tem: model de dados (D3 lista `Agent, Pipeline, ..., RivvnConnection` e não há model `Integration`), nenhum endpoint na seção 9 (só existe `/api/integrations/rivvn/*`), nenhum domínio que implemente a leitura de PRs/issues (D8 declara explicitamente "NÃO implementa integrações de plataforma (GitHub/Azure)"), e D10 10.12 é só UI ("listar PRs/issues num painel"). Não há definição de credenciais (token OAuth/PAT), escopo, nem contrato de request/response.
- **Impacto:** O item de escopo V1 é inimplementável como está: o worker do D10 não tem API para consumir, e nenhum backend existe.
- **Recomendação:** Adicionar model `Integration` (ou `GitHubConnection`) em D3, endpoints em seção 9 (ex: `GET /api/integrations/github/repos`, `.../pulls`, `.../issues`), uma tarefa de backend (D8 ou novo sub-domínio) com contrato de credenciais (token em secrets manager) e request/response.

### L-02 — Ferramenta básica `shell` dá execução arbitrária a todo agente; sandbox e prompt injection não tratados
- **Severidade:** 🔴 crítico
- **Local:** spec seção 6.3 (tabela de ferramentas básicas), seção 6.4 (regras de sandbox); D8 (8.4, Riscos)
- **Descrição:** `shell` (executar comando no terminal) é injetada automaticamente em **todo** agente e "não podem ser removidas". Isso anula o isolamento do sandbox de Tools Custom: qualquer agente (inclusive um com prompt de terceiros) pode rodar `rm -rf`, ler `.env`, exfiltrar credenciais. Não há: restrição de comandos, allowlist, separação de permissões entre ferramentas básicas e tools custom, nem qualquer menção a prompt injection (conteúdo de knowledge/PR/URL injetado no prompt pode instruir o agente a usar `shell`). O risco de "sandbox escape" aparece só como "considerar gVisor" nos Riscos do D8, sem decisão.
- **Impacto:** Buraco de segurança estrutural: o "guarda-corpo" (princípio da seção 1) é quebrado pela própria ferramenta básica.
- **Recomendação:** Decidir se `shell` é habilitada por padrão ou opt-in por agente; definir escopo de permissões (diretório de trabalho, comandos bloqueados, sem acesso a secrets); documentar mitigação de prompt injection (sanitização de conteúdo externo, separação de instruções vs dados).

### L-03 — KnowledgeBase sem model na spec e sem API de CRUD (só upload/query)
- **Severidade:** 🔴 crítico
- **Local:** spec seção 4 (ausente), seção 7.3 (escopo), seção 9.3; D3 (3.1), D9 (9.1, 9.5)
- **Descrição:** A seção 4 da spec define Agent, Pipeline, Checkpoint, Skill, ApprovalRequest, mas **não define a interface `KnowledgeBase`**, embora D3 e D9 a tratem como model central (nome, escopo global/agent/pipeline, fonte, referência). A seção 9.3 só tem `POST /api/knowledge/upload` e `POST /api/knowledge/query`. Não há endpoint para: criar uma base, listar bases, definir escopo, associar a agente/pipeline, listar documentos de uma base, remover base/documento. A UI (D9 9.6, D10 10.10) precisa de "criar base, upload, escopo, ver documentos", mas não há API correspondente.
- **Impacto:** O RAG não é utilizável de ponta a ponta: não há como criar a base nem ligá-la a um agente.
- **Recomendação:** Adicionar interface `KnowledgeBase` na seção 4 (id, ownerId, name, scope, scopeRef, source, reference, documents[]) e endpoints em 9.3 (`POST/GET/DELETE /api/knowledge`, `GET /api/knowledge/:id/documents`, `DELETE /api/knowledge/:id/documents/:docId`).

### L-04 — Chat de construção exige `:id` mas o agente ainda não existe
- **Severidade:** 🟠 alto
- **Local:** spec seção 9.2 (`POST /api/agents/:id/chat`), seção 10.1; D4 (4.5, 4.6)
- **Descrição:** O fluxo da seção 10.1 é "Criar Agente → chat → salvar → POST /api/agents". Mas o endpoint de chat é `POST /api/agents/:id/chat`, que requer um id já existente. Não há endpoint para iniciar um chat de um agente ainda não persistido, nem se o chat opera em rascunho efêmero. O contrato de request/response do chat (payload da mensagem, formato do stream SSE, como o preview estruturado é devolvido) também não está definido.
- **Impacto:** O caminho "criar agente via chat" (item de escopo V1) não fecha: não se sabe como o primeiro turno é disparado.
- **Recomendação:** Definir `POST /api/agents/chat` (sem id, cria rascunho) ou criar o agente vazio antes do chat; documentar payload do request, formato dos eventos SSE e o objeto de preview retornado.

### L-05 — Endpoints de listagem ausentes na seção 9 (GET /api/agents e GET /api/pipelines)
- **Severidade:** 🟠 alto
- **Local:** spec seção 9.1 e 9.2; D4 (4.1), D5 (5.1)
- **Descrição:** A seção 9.2 tem `POST /api/agents`, `GET /api/agents/:id`, `PUT`, `DELETE`, `chat` — mas **não tem `GET /api/agents`** (listar). O dashboard (D10 10.2) consome `api.get('/api/agents')`. A seção 9.1 tem `POST /api/pipelines`, `GET /api/pipelines/:id`, `PUT` — mas **não tem `GET /api/pipelines`** (listar), embora D5 5.1 a implemente. A spec (fonte de verdade) diverge do que os domínios implementam.
- **Impacto:** A spec não documenta endpoints que o frontend depende; quem implementar só pela spec não os cria.
- **Recomendação:** Adicionar `GET /api/agents` e `GET /api/pipelines` na seção 9 com contrato de listagem (paginação, ordenação).

### L-06 — Falha de LLM sem contrato de erro no `Agent.run`
- **Severidade:** 🟠 alto
- **Local:** spec seção 5.1, seção 14 (riscos); D4 (4.3), D6 (6.1)
- **Descrição:** `Agent.run(inputs) -> dict` não define o que acontece quando a chamada ao LLM falha (erro de API, timeout, rate limit, resposta malformada, output fora do contrato de `outputs`). D4 menciona "mock LLM se API key ausente" mas não o fluxo de falha em produção. Não há: retry de LLM, backoff, como o estado do nó fica (`status: failed`?), se a pipeline aborta ou se o erro vira input de outro nó, nem como o usuário vê a falha.
- **Impacto:** Falha de LLM (evento comum) deixa o runtime sem comportamento definido; checkpoint pode ficar em estado inconsistente.
- **Recomendação:** Definir contrato de erro de `Agent.run` (exceção tipada ou `{"error": ...}`), política de retry/backoff, mapeamento para `status: failed` e propagação no grafo, e o que o monitor exibe.

### L-07 — Autenticação do WebSocket não especificada
- **Severidade:** 🟠 alto
- **Local:** spec seção 9.7; D3 (3.6), D6 (6.7-6.9), D10 (10.11)
- **Descrição:** Os canais WebSocket (`pipeline:status`, `approval:new`, etc.) não têm mecanismo de autenticação definido. O JWT vai no header HTTP, mas WebSocket não usa header `Authorization` no handshake de forma padrão. Não se sabe se o token vai em query string, em primeiro frame, ou se a conexão é aberta. Em V1 single-user o risco é menor, mas o canal `approval:new` expõe dados de execução a qualquer cliente que se conectar.
- **Impacto:** Canal de tempo real potencialmente não autenticado; incoerência com o modelo de auth do D2.
- **Recomendação:** Especificar como o WS autentica (token no handshake/query, validação no servidor, escopo por ownerId).

### L-08 — Sem model de usuário; `ownerId` sem valor definido
- **Severidade:** 🟠 alto
- **Local:** spec seção 4.1 (`ownerId`), seção 3 (Auth); D2 (2.1), D3 (3.1)
- **Descrição:** Todo model tem `ownerId`, mas não existe model `User` nem tabela de usuários (D2 declara "NÃO modela schema de usuários"). O D2 diz que o "usuário é derivado do JWT" com `sub` = id do usuário, mas o valor concreto do `sub`/`ownerId` na V1 single-user nunca é definido (é um UUID fixo? a string "admin"?). Não há como saber qual `ownerId` os registros recebem.
- **Impacto:** Filtro por `ownerId` (usado em listagens e no gate do Rivvn por `ownerId`) não tem valor de referência; o `RivvnConnection` é chaveado por `ownerId` que não existe em lugar nenhum.
- **Recomendação:** Definir o valor de `ownerId` na V1 (constante/seed) ou um model `User` mínimo com o id usado no JWT `sub`.

### L-09 — Sem modelo de execução/run; re-execução e histórico indefinidos
- **Severidade:** 🟠 alto
- **Local:** spec seção 4.2 (`currentCheckpoint`, `startedAt`, `completedAt`), seção 9.1; D6 (6.1, 6.2)
- **Descrição:** `Pipeline` tem um único `currentCheckpoint`, `startedAt` e `completedAt` — ou seja, um único estado de execução. Não há conceito de "run" (execução) separado do grafo. Não está definido: como re-executar uma pipeline já `completed`/`failed`, se há histórico de execuções, como `thread_id` do LangGraph se relaciona a uma run, e o que acontece ao executar de novo (os `iterations` e outputs antigos são zerados?).
- **Impacto:** Não dá para rodar a mesma pipeline duas vezes nem auditar execuções anteriores; o caminho crítico "executar → concluir → executar de novo" não fecha.
- **Recomendação:** Introduzir model `PipelineRun` (id, pipelineId, threadId, status, startedAt, completedAt, checkpoint atual) e endpoints de listagem de runs; definir reset de estado na re-execução.

### L-10 — Artefatos sem storage nem API
- **Severidade:** 🟠 alto
- **Local:** spec seção 4.5 (`artifacts?: string[]`), seção 4.1 (`PortDef.type: "artifact"`); D6, D7
- **Descrição:** `ApprovalRequest.artifacts` são "links para artefatos (print, doc, code)" e `PortDef` tem tipo `artifact`, mas não há: onde artefatos são armazenados (Postgres? filesystem? S3?), como são gerados por um agente, nem API para baixá-los. O conteúdo de um port do tipo `artifact`/`code`/`document` fica no `state` (JSONB) sem limite de tamanho definido.
- **Impacto:** Aprovações com artefatos e outputs de código/documento não têm persistência nem entrega ao usuário.
- **Recomendação:** Definir storage de artefatos (tabela + blob ou caminho), API de download, e limite de tamanho de conteúdo de port.

### L-11 — Modelo de embedding e dimensão do vetor não especificados
- **Severidade:** 🟠 alto
- **Local:** spec seção 7.2, ADR-003; D9 (9.3)
- **Descrição:** O `embedder.py` usa "OpenAI ou local como fallback", mas não se qual modelo local, nem a **dimensão do embedding** (ex: 1536 para OpenAI, diferente para modelos locais). A coluna do pgvector precisa da dimensão correta na migration (D3 3.2), que é gerada antes de se saber o modelo. Trocar de modelo depois que há dados exige re-embed.
- **Impacto:** Migration do pgvector sem dimensão definida; incompatibilidade se o modelo local e o OpenAI tiverem dimensões diferentes.
- **Recomendação:** Fixar o modelo de embedding da V1 e a dimensão; documentar a coluna `vector(N)` na migration; política de re-embed ao trocar modelo.

### L-12 — SDK do Rivvn e variáveis `RIVVN_*` não declarados
- **Severidade:** 🟠 alto
- **Local:** spec seção 7.4; D1 (1.5 `.env.example`), D9 (9.7, 9.8)
- **Descrição:** A integração Rivvn depende de "SDK do Rivvn" (nome do pacote, versão, linguagem, método de instalação nunca declarados) e de variáveis `RIVVN_*` (D1 lista `RIVVN_*` de forma genérica). Não se sabe quais: client id, client secret, base URL, redirect URI, endpoint do OAuth. O `RivvnConnection.scope` (escopos OAuth) não tem valores possíveis.
- **Impacto:** Dependência externa não declarada no `pyproject.toml`/`.env.example`; o OAuth não é implementável sem os parâmetros.
- **Recomendação:** Declarar o pacote do SDK (nome+versão) nas dependências e detalhar cada `RIVVN_*` no `.env.example` (client_id, client_secret, base_url, redirect_uri) + escopos OAuth suportados.

### L-13 — Limites de upload e validação de entrada não documentados
- **Severidade:** 🟡 médio
- **Local:** spec seção 7.1 (fontes: upload, URL); D9 (9.2)
- **Descrição:** `POST /api/knowledge/upload` não define: tipos de arquivo aceitos (só PDF? doc? código?), tamanho máximo, número máximo de arquivos, validação de conteúdo (arquivo corrompido, PDF com senha). A fonte `url` não define se o portal faz fetch server-side, limites de tamanho da página, ou tratamento de URL inválida/inacessível.
- **Impacto:** Uploads grandes ou malformados podem estourar memória/disco; URL inválida sem tratamento.
- **Recomendação:** Documentar allowlist de MIME, limite de tamanho por arquivo e por base, e fluxo de erro para arquivo inválido e URL inacessível.

### L-14 — Sem rate limiting nem proteção contra abuso
- **Severidade:** 🟡 médio
- **Local:** spec seção 9 (API), seção 3; D2
- **Descrição:** Não há rate limiting em nenhum endpoint, nem no chat de construção (que chama LLM a cada turno, custo direto), nem no upload, nem no execute. Em V1 single-user local o risco é baixo, mas o chat e o execute são caros e não têm guarda.
- **Impacto:** Uso intensivo do chat/execute pode esgotar cota de LLM ou travar o runtime.
- **Recomendação:** Definir rate limit por endpoint crítico (chat, execute, upload) e comportamento em 429.

### L-15 — Concorrência: executar pipeline já em execução / editar grafo durante a execução
- **Severidade:** 🟡 médio
- **Local:** spec seção 5.1, seção 9.1; D6 (6.1, 6.3)
- **Descrição:** Não está definido o que acontece se `POST /pipelines/:id/execute` for chamado quando a pipeline já está `running` (segunda execução paralela? erro 409?). Também não se define o que acontece se o usuário fizer `PUT /api/pipelines/:id` (editar grafo) durante uma execução em andamento: o `agentSnapshot` protege o agente, mas a edição do grafo (nós/arestas) durante a run não é tratada.
- **Impacto:** Execuções duplicadas ou grafo inconsistente entre o que está rodando e o que foi salvo.
- **Recomendação:** Definir lock/estado que rejeita execute sobre pipeline `running` (409) e bloquear `PUT` do grafo durante execução (ou versionar).

### L-16 — Persistência do contador de `maxIterations` ao retomar de checkpoint
- **Severidade:** 🟡 médio
- **Local:** spec seção 5.2; D5 (State `{agentId}.iterations`), D6 (6.4)
- **Descrição:** O contador `{agentId}.iterations` vive no State. Ao retomar de um checkpoint (após pause/interrupt/falha), não está explícito se o contador persiste no checkpoint e é restaurado, ou se zera. Se zerar, o anti-loop-infinito perde a contagem acumulada e o loop pode passar do limite real.
- **Impacto:** Retomada pode invalidar a guarda de `maxIterations`.
- **Recomendação:** Confirmar que `iterations` faz parte do checkpoint salvo/restaurado e testar o ciclo loop → pause → resume → limite.

### L-17 — Defaults de timeout (agente e global) não documentados
- **Severidade:** 🟡 médio
- **Local:** spec seção 4.1 (`timeout`), seção 14; D6 (6.5)
- **Descrição:** `Agent.timeout` existe mas sem default nem máximo. O "timeout global da pipeline" (D6 6.5, seção 14) não tem valor definido nem onde é configurado (campo do Pipeline? env?). Só o timeout de Tools Custom tem valor (30s/120s).
- **Impacto:** Sem defaults, o comportamento de timeout é arbitrário por implementação.
- **Recomendação:** Definir default e máximo de `Agent.timeout` e o valor/local de configuração do timeout global.

### L-18 — Parâmetros de RAG (top-K, chunk size, overlap) não documentados como configuração
- **Severidade:** 🟡 médio
- **Local:** spec seção 7.2, seção 14; D9 (9.2, 9.4)
- **Descrição:** O chunking é "inteligente (tamanho + sobreposição)" sem valores; o top-K aparece como "K=3" só num critério de aceite do D9, não como configuração. Não há onde configurar chunk size, overlap, top-K por base ou por agente, nem threshold de similaridade mínima (chunks irrelevantes podem ser injetados).
- **Impacto:** Qualidade do RAG não é ajustável; injeção de chunks irrelevantes degrada o prompt.
- **Recomendação:** Documentar chunk size, overlap, top-K e threshold de similaridade como campos configuráveis (por KnowledgeBase) com defaults.

### L-19 — Recuperação de checkpoint corrompido sem detalhe
- **Severidade:** 🟡 médio
- **Local:** spec seção 14 (mitigação "checkpoint imutável + snapshot periódico"); D6 (6.2)
- **Descrição:** A mitigação de "checkpoint corrompido" é só uma frase ("imutável + snapshot periódico") sem mecanismo: como se detecta corrupção, o que é o "snapshot periódico", de onde se retoma se o último checkpoint é inválido.
- **Impacto:** Falha de checkpoint (risco declarado) não tem fluxo de recuperação implementável.
- **Recomendação:** Especificar validação de integridade do checkpoint, política de fallback ao último checkpoint válido e o estado resultante.

### L-20 — Logs só via WebSocket, sem persistência
- **Severidade:** 🟡 médio
- **Local:** spec seção 9.7 (`pipeline:log`); D6 (6.8)
- **Descrição:** Logs de execução são emitidos apenas no canal WebSocket `pipeline:log`. Não há persistência de logs nem API para consultá-los. Se o cliente estiver desconectado quando o evento é emitido, o log se perde; não há como auditar o que um agente fez depois.
- **Impacto:** Perda de observabilidade; impossível revisar execução após o fato.
- **Recomendação:** Persistir logs (tabela por run) e expor `GET /api/pipelines/:id/runs/:runId/logs` além do stream.

### L-21 — API de Skills incompleta (sem DELETE, sem GET por id)
- **Severidade:** 🟡 médio
- **Local:** spec seção 9.3; D8 (8.1)
- **Descrição:** A seção 9.3 tem só `GET /api/skills` e `POST /api/skills`. D8 8.1 declara "CRUD de skills", mas faltam `GET /api/skills/:id`, `PUT /api/skills/:id` e `DELETE /api/skills/:id`. A associação skill↔agente é via `Agent.skills` (PUT /agents), ok, mas o ciclo de vida da skill em si está incompleto.
- **Impacto:** Não dá para editar/remover skills custom pela API documentada.
- **Recomendação:** Completar a seção 9.3 com os endpoints de CRUD de skills.

### L-22 — Aprovações: sem cancelamento nem histórico
- **Severidade:** 🟡 médio
- **Local:** spec seção 9.6; D7 (7.3)
- **Descrição:** A seção 9.6 tem só `GET /api/approvals?status=pending` e `POST /api/approvals/:id/respond`. Não há: listar aprovações respondidas (histórico), cancelar uma aprovação pendente (ex: pipeline foi stopada mas a aprovação ficou pendente), nem o que acontece com aprovações pendentes quando a pipeline é `stop`ada.
- **Impacto:** Aprovações órfãs após stop; sem auditoria de decisões.
- **Recomendação:** Adicionar listagem por status (incl. resolved), `DELETE`/cancel de aprovação pendente e regra de limpeza ao stopar a pipeline.

### L-23 — Formato de erro, 404 e paginação não padronizados
- **Severidade:** 🔵 baixo
- **Local:** spec seção 9; D5 (5.1 define só o 400 de grafo)
- **Descrição:** Só o erro de validação de grafo tem formato definido (`{"errors": [...]}`). Não há convenção global de corpo de erro (4xx/5xx), tratamento de 404 (recurso inexistente), nem paginação/ordenação nos endpoints de listagem.
- **Impacto:** Clientes (portal) tratam erros de forma inconsistente.
- **Recomendação:** Definir envelope de erro padrão e convenção de paginação para listagens.

### L-24 — Migrations e observabilidade na subida do container não especificadas
- **Severidade:** 🔵 baixo
- **Local:** D1 (1.2, 1.3), D3 (3.2); spec seção 11
- **Descrição:** Não está definido se o container do orchestrator roda `alembic upgrade head` automaticamente na subida (senão o banco fica sem schema após `docker-compose up`). Também não há spec de logging/observabilidade (nível de log, formato, onde vai) além do `/health`.
- **Impacto:** `docker-compose up` pode subir sem schema aplicado; debugging sem padrão de log.
- **Recomendação:** Documentar o comando de migration no entrypoint do container e um padrão mínimo de logging estruturado.

---

## 4. Viabilidade Técnica e Riscos

_Decisões técnicas com risco de não se sustentar na implementação, suposições sobre o comportamento de bibliotecas (LangGraph, pgvector, NextAuth, React Flow) que precisam de validação, gaps de segurança, e riscos não mapeados pelos documentos._

**13 achados (2 críticos, 5 altos, 4 médios, 2 baixos).**

### V-01 — `interrupt()` é primitiva de NÓ, não de aresta; o modelo de HITL da spec/D5/D7 não casa com o LangGraph
- **Severidade:** 🔴 crítico
- **Local:** Spec §5.3 + §4.2 (`PipelineEdge.requiresApproval`) + D5 "requiresApproval no compiler" + D7 §7.1 ("detecta `requiresApproval` na edge, chama `interrupt()` do LangGraph")
- **Descrição:** A spec e os domínios tratam a aprovação como propriedade da **aresta**: o compiler "anota" `requiresApproval` no metadata da edge e o runtime "lê essa anotação e decide se chama `interrupt()` antes de prosseguir". A documentação oficial do LangGraph é explícita: *"Interrupts work by calling the `interrupt()` function at any point in your graph nodes"* — `interrupt()` só pode ser chamado **dentro de uma função de nó**, nunca "em uma aresta". Não existe API para pausar "na aresta". O padrão documentado para approve/reject é: o nó chama `interrupt(payload)`, e ao retomar retorna `Command(goto="proceed"|"cancel")` (ou o nó de aprovação decide o `goto`). Ou seja, a decisão de roteamento pós-aprovação pertence ao nó, não a uma edge condicional pré-definida.
- **Impacto:** O D5 (que "não implementa interrupt, só anota") e o D7 (que "chama interrupt na edge") não têm como ser implementados como descritos. O mapeamento `EdgeCondition → route_fn` + flag na edge não produz o comportamento de pausa. O ciclo pausa→resposta→retomada (critério de aceite do D7) não fecha com esse modelo.
- **Recomendação:** Redesenhar o HITL no modelo do LangGraph: (a) o compiler gera, para cada edge com `requiresApproval`, um **nó de aprovação** dedicado (ou injeta `interrupt()` no nó de origem/destino) que chama `interrupt()` e, ao retomar, retorna `Command(goto=...)` para o target da edge; (b) o D7 passa a implementar o handler **dentro do nó**, não "na edge"; (c) reescrever o contrato de interface D5↔D7 (hoje fala em "anotação no metadata da edge" e "D6 expõe o ponto de interrupt"). Validar com um spike de 1 pipeline A→[aprovação]→B.

### V-02 — Retomada re-executa o nó do zero; efeitos colaterais antes do `interrupt()` se repetem
- **Severidade:** 🔴 crítico
- **Local:** D7 §7.1/§7.2 (criar `ApprovalRequest` "ao pausar") + D6 (checkpoint/resume) + Spec §5.3 passo 2 ("O orquestrador cria um `ApprovalRequest`")
- **Descrição:** A doc oficial é categórica: *"When execution resumes, the runtime restarts the entire node from the beginning—it does not resume from the exact line where interrupt was called. This means any code that ran before the interrupt will execute again."* E a regra: *"Side effects called before interrupt must be idempotent."* O D7 propõe criar/persistir o `ApprovalRequest` no momento do pause. Se essa criação acontece **antes** do `interrupt()` no mesmo nó, ela **re-executa a cada resume** (e o D7 ainda incrementa `retryCount`/`attemptedChannels`), gerando `ApprovalRequest` duplicados e notificações repetidas.
- **Impacto:** Duplicação de aprovações e de notificações (email/in-app) a cada retomada; contadores de retry corrompidos; estado inconsistente no painel de aprovações.
- **Recomendação:** Garantir idempotência: chavear o `ApprovalRequest` por `(pipelineId, nodeId, checkpointId)` com upsert, ou criar o `ApprovalRequest` **após** o `interrupt()` (no ramo de retomada), ou em um nó separado que rode uma única vez. Adicionar teste de ciclo completo pausa→resposta→retomada→re-resposta que asserta "1 único ApprovalRequest".

### V-03 — Fan-out paralelo + `requiresApproval` em múltiplos ramos exige resume multi-interrupt (não mapeado)
- **Severidade:** 🟠 alto
- **Local:** D5 "Fan-out" + D7 (interrupt) + Spec §4.2 (múltiplas flow edges do mesmo source)
- **Descrição:** A doc mostra que quando **ramos paralelos** chamam `interrupt()` simultaneamente, o resume precisa mapear **cada interrupt id para seu valor** (`Command(resume={id1: ..., id2: ...})`). O design do D7 assume um único interrupt por vez (um `ApprovalRequest` por pausa, `Command(resume=valor)` simples). Um fan-out A→[B aprova, C aprova] gera dois interrupts pendentes no mesmo superstep.
- **Impacto:** Com fan-out + aprovação em mais de um ramo, a retomada com um único `resume` falha ou retoma só um ramo; o pipeline trava ou retoma de forma parcial.
- **Recomendação:** No D7, tratar o caso N interrupts pendentes: persistir um `ApprovalRequest` por interrupt id e, ao responder, montar o mapa `resume` completo (ou responder um a um e re-invoke). Documentar que fan-out com HITL em múltiplos ramos é um caso de teste obrigatório.

### V-04 — "Uma conditional edge por nó roteando por action" conflita com fan-out estático e com a semântica de `follow`
- **Severidade:** 🟠 alto
- **Local:** D5 "Mapeamento de FlowAction → Topologia" (tabela) + §5.3 (compiler)
- **Descrição:** O D5 declara que cada nó gera **uma** `add_conditional_edges(node, route_fn, {...})` que roteia por `action`. Mas o mesmo D5 também exige fan-out: `{"follow": [nodeA, nodeB]}`. O problema: a `route_fn` retorna **uma** chave (ex: `"follow"`), e o mapping resolve essa chave para um target (ou lista). Isso funciona para fan-out **incondicional** de `follow`. Porém, quando o nó tem **várias** flow edges condicionais com conditions diferentes (branching, regra 11 do validador: "múltiplas flow edges entre o mesmo par com conditions diferentes são permitidas"), a `route_fn` precisa avaliar **todas** as conditions e decidir o target — e a spec de `EdgeCondition` avalia `field ∈ {action, status, output}`. A suposição de que "uma conditional edge por nó" cobre branching multi-condition + fan-out + loop + maxIterations guard num único `route_fn` é viável **apenas** se o `route_fn` for escrito como uma função de decisão ad-hoc por nó (o que o D5 §5.5 admite: "A route_fn principal de cada nó combina: maxIterations guard + conditions + fallback follow"). O risco real é a **ordem de precedência** não estar definida: se `action=="return"` e `action=="follow"` casam em edges diferentes, e `iterations>=max`, qual vence? O D5 diz que maxIterations → END é "guarda", mas não define precedência relativa às conditions.
- **Impacto:** Comportamento de roteamento ambíguo em nós com múltiplas conditions; loops que deveriam abortar por maxIterations podem seguir o branch errado, ou vice-versa.
- **Recomendação:** Definir explicitamente a ordem de precedência no `route_fn` (sugestão: maxIterations guard → END primeiro; depois conditions específicas; depois fallback `follow`). Adicionar teste de unidade para nó com 2+ conditions concorrentes + maxIterations.

### V-05 — State TypedDict dinâmico: viável, mas o reducer "last" para `iterations` e o checkpoint round-trip têm pegadinhas
- **Severidade:** 🟠 alto
- **Local:** D5 §5.4 (State) + "Node Function Contract" passo 6 (`iterations += 1`) + D6 (checkpoint round-trip)
- **Descrição:** Gerar um `TypedDict` dinamicamente com `typing`/`Annotated` **é suportado** pelo LangGraph (o schema pode ser qualquer type; reducers via `Annotated[key, reducer]`). Porém: (a) o D5 diz "Reducer: `last` (padrão LangGraph) para todas as keys", mas o passo 6 do node function faz `"{agentId}.iterations" += 1` — com reducer "last" (override), o nó precisa **ler o valor atual e somar** (o que o contrato faz: lê do State e retorna o novo valor). Isso funciona, mas é frágil: se dois nós em paralelo incrementarem a mesma key (não é o caso aqui, pois é por agente), haveria conflito. Mais importante: (b) o **round-trip de checkpoint** com um State que tem dezenas de keys `Any` (ports de artefatos/código) depende de **todos os valores serem JSON-serializáveis**. A doc de interrupts avisa: *"Do not return complex values... complex values may not be serializable (e.g. you can't serialize a function)."* Se um `output` de port do tipo `code`/`artifact` carregar um objeto Python (não dict/str), o PostgresSaver falha ao serializar.
- **Impacto:** Checkpoint falha ou perde dados quando um port carrega valor não-JSON-serializável; `iterations` pode não acumular corretamente se o nó não ler o valor prévio.
- **Recomendação:** (a) Enforçar no contrato do node function que **todo** valor escrito em port seja JSON-serializável (validar antes de retornar); (b) para `iterations`, usar um reducer de soma (`Annotated[int, operator.add]`) e o nó retorna `+1`, em vez de ler-e-somar com "last" — mais robusto; (c) teste de round-trip com payload realista (código, artefato) no PostgresSaver, não só dict simples.

### V-06 — `PostgresSaver` não está no escopo do D1 e a imagem `postgres:15` padrão **não** tem pgvector
- **Severidade:** 🟠 alto
- **Local:** D1 §1.1 (dependências: lista `langgraph`, `langchain-core`, mas **não** `langgraph-checkpoint-postgres`) + §1.4 (Postgres init) + D6 §6.2 (`PostgresSaver` configurado com `DATABASE_URL`)
- **Descrição:** O D6 depende do `PostgresSaver` do LangGraph, que vive no pacote **separado** `langgraph-checkpoint-postgres` (não no `langgraph` core). O D1 lista `langgraph` e `langchain-core` mas omite esse pacote. Além disso, a imagem oficial `postgres:15` **não inclui** a extensão `vector`; o D1 §1.4 assume `CREATE EXTENSION vector` num `init-db.sql`, o que **falha** na imagem padrão (a extensão não está instalada no sistema). O próprio D1 anota o risco ("usar imagem já preparada") mas a tarefa 1.4 especifica `postgres:15` + `CREATE EXTENSION`, que é a combinação que quebra.
- **Impacto:** `docker-compose up` sobe o Postgres sem a extensão `vector` (query de RAG do D9 quebra) e o D6 não consegue importar `PostgresSaver` (ImportError) porque o pacote não foi instalado.
- **Recomendação:** (a) No D1, usar a imagem `pgvector/pgvector:pg15` (ou equivalente) em vez de `postgres:15`; (b) adicionar `langgraph-checkpoint-postgres` às dependências do D1; (c) validar que `SELECT extname FROM pg_extension` retorna `vector` **e** que `from langgraph.checkpoint.postgres import PostgresSaver` importa.

### V-07 — Sandbox "subprocesso isolado sem acesso ao filesystem do host" não é isolamento real em Linux
- **Severidade:** 🟠 alto
- **Local:** Spec §6.4 ("sandbox (subprocesso isolado, sem acesso ao filesystem do host)") + D8 §8.6
- **Descrição:** Um `subprocess` Python **não** é um sandbox. Sem `seccomp`/`namespaces`/`user-namespace`, um script Python arbitrário roda com os mesmos UID/capabilities do processo pai e **acessa o filesystem do host** (o `open("/etc/passwd")` funciona). "Sem acesso ao filesystem do host" não é alcançável com `subprocess` + `timeout` sozinho. O D8 anota "Docker-in-Docker ou gVisor como fallback", mas a tarefa 8.6 especifica "subprocesso isolado" como a implementação primária.
- **Impacto:** Tool custom maliciosa ou com bug lê/altera arquivos do host, exfiltra credenciais do env (que são injetadas no subprocess), ou executa comandos arbitrários. Risco de segurança real, não teórico.
- **Recomendação:** Para V1 local, aceitar o risco documentado (usuário confia no próprio código) **ou** usar `firejail`/`bubblewrap`/`nsjail` para namespaces reais; para produção, container por tool (gVisor/Kata). Deixar explícito no D8 que "subprocesso" = isolamento **lógico** (timeout + env controlado), não **segurança**. Não prometer "sem acesso ao host" como garantia.

### V-08 — Socket.IO no frontend vs FastAPI WebSocket no backend: protocolos incompatíveis
- **Severidade:** 🟠 alto
- **Local:** Spec §3 (Stack: "FastAPI WebSocket + Socket.IO (frontend)") + D3 §3.6 (`lib/websocket.ts`: "conexão socket.io") + D6/D7 (canais WebSocket)
- **Descrição:** O frontend usa `socket.io-client` (D1 lista `socket.io-client` no `package.json`; D3 §3.6 diz "conexão socket.io"). O backend é FastAPI, que expõe **WebSocket nativo** (RFC 6455), **não** o protocolo Socket.IO (que tem handshake próprio, namespaces, rooms, e não é WebSocket puro). `socket.io-client` **não** conecta num endpoint `WebSocket` do FastAPI — os protocolos são incompatíveis. A spec lista os dois como se fossem a mesma coisa ("FastAPI WebSocket + Socket.IO (frontend)"), mas não há bridge.
- **Impacto:** O monitor em tempo real (D6/D7/D10) não conecta: o client Socket.IO tenta o handshake Socket.IO num endpoint que fala WebSocket puro e falha. Nenhum dos 5 canais chega ao frontend.
- **Recomendação:** Escolher **um** protocolo: (a) usar `websocket-client` nativo no frontend (recomendado, mais simples, alinha com FastAPI) e trocar `socket.io-client` por `WebSocket` nativo; **ou** (b) rodar um servidor Socket.IO no backend (ex: `python-socketio` + `asgi`), que é compatível com FastAPI. Atualizar D1 (deps), D3 §3.6 e D10 §10.11 para o protocolo escolhido.

### V-09 — NextAuth (credentials) + JWT de delegação: viável, mas a sessão e o JWT têm lifecycles divergentes
- **Severidade:** 🟡 médio
- **Local:** Spec §3 (Auth) + D2 §2.2/§2.3 + "Riscos" do D2
- **Descrição:** A abordagem (NextAuth emite sessão; route handler cunha um JWT com a mesma secret; Python valida) é **viável e segura** se a secret for forte e o JWT tiver `exp`. O D2 já anota o risco de manter `JWT_SECRET == NEXTAUTH_SECRET`. Pontos de atenção reais: (a) o JWT é cunhado **uma vez** no `/api/jwt` e o D3 §3.5 o **cacheia em memória** no frontend — se o JWT expira (por `exp`) mas a sessão NextAuth ainda é válida, o client usa o token expirado em cache e recebe 401 sem tentar re-cunhar; (b) não há revogação: derrubar a sessão NextAuth não invalida o JWT já emitido (JWT stateless); (c) o D2 não especifica `exp`/`iat` no payload (só `sub`, `iss`).
- **Impacto:** 401 intermitentes após expiração do token em cache; sessão encerrada no portal mas API ainda aceita o JWT antigo até expirar.
- **Recomendação:** (a) Definir `exp` curto (ex: 15 min) + `iat` no JWT; (b) no client (D3 §3.5), ao receber 401, **invalidar o cache** e re-cunhar via `/api/jwt` antes de tratar como falha de auth; (c) documentar que revogação de sessão não propaga ao JWT (aceitável em V1 single-user).

### V-10 — MCP client: viável, mas stdio exige gerenciamento de processo e o ecossistema Python é mais jovem que o TS
- **Severidade:** 🟡 médio
- **Local:** Spec §6.7 + D8 §8.11 (`mcp/client.py`: stdio/sse/http, `tools/list`, invocação)
- **Descrição:** Conectar via stdio/sse/http e chamar `tools/list` **é viável** — existe o SDK oficial `mcp` (Python, `modelcontextprotocol`), com `stdio_client`, `sse_client`, `streamablehttp_client` e `ClientSession.list_tools()`. Porém: (a) o SDK Python é **mais recente** que o TypeScript e a API ainda muda entre versões (pinar versão é essencial); (b) stdio **spawna um processo** (`npx -y @acme/mcp-jira`) que precisa de ciclo de vida gerenciado (spawn, healthcheck, kill no timeout, reaproveitamento de conexão) — o D8 anota "gerenciamento de ciclo de vida" mas a tarefa 8.11 não detalha pooling/reconexão; (c) `npx -y` baixa pacotes na primeira execução (rede + tempo), o que conflita com o timeout de teste de conexão.
- **Impacto:** Teste de conexão via stdio pode estourar timeout no primeiro uso (download do pacote); processo MCP órfão se o servidor cair; incompatibilidade de API do SDK entre upgrades.
- **Recomendação:** (a) Pinar a versão do SDK `mcp` no `pyproject.toml`; (b) no client, implementar pool de sessões por serverId com reconexão e `kill` no teardown; (c) para stdio, pre-warm (baixar o pacote) ou aumentar o timeout de teste; (d) mock do transporte para testes (o D8 já prevê mock).

### V-11 — RAG: `ORDER BY embedding <-> query` está correto, mas o fallback de embedding local precisa de dimensão fixa e o índice HNSW é opcional
- **Severidade:** 🟡 médio
- **Local:** D9 §9.3/§9.4 + Spec §7.2
- **Descrição:** A query `ORDER BY embedding <-> query LIMIT top_k` é a **forma correta** de cosine distance no pgvector (operador `<->` = L2 por padrão; para cosine usar `<=>` ou normalizar). O D9 não especifica qual operador — se usar `<->` (L2) com embeddings não-normalizados, o ranking difere de cosine. O fallback "embedding local" (ex: `sentence-transformers`) é viável, mas: (a) a **dimensão** do embedding local deve ser fixa e casar com a coluna `vector(N)` no schema (D3); trocar de modelo muda a dimensão e **invalida** todos os vetores já indexados; (b) sem índice HNSW/IVFFlat, a busca é **linear scan** (OK para V1 local, mas o D9 não cria índice).
- **Impacto:** Ranking de similaridade incorreto se o operador/dimensão não casar; troca de modelo de embedding quebra a KB existente; busca lenta se a KB crescer sem índice.
- **Recomendação:** (a) Especificar o operador (recomendo `<=>` cosine) e normalizar embeddings; (b) fixar a dimensão no schema e versionar o modelo de embedding (coluna `model_version` na KB); (c) criar índice HNSW (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`) mesmo na V1.

### V-12 — Rivvn OAuth + SDK: viável, mas o gate comercial e o refresh de token criam acoplamento a SDK externo não especificado
- **Severidade:** 🟡 médio
- **Local:** Spec §7.4 + D9 §9.7/§9.8
- **Descrição:** Authorization code flow + SDK externo é **viável**. Riscos reais: (a) o SDK do Rivvn é **externo e não versionado** nos documentos — se o SDK mudar a API de token/query, o D9 quebra sem aviso; (b) o **refresh de token** (access expira, refresh renova) precisa de lógica de re-auth automática **dentro** do client, e o D9 §9.8 só diz "wrapper do SDK (token + query)" sem detalhar o refresh; (c) o gate `contractStatus` é validado no backend, mas se o contrato expirar **durante** uma execução de pipeline, a query do agente falha em tempo de execução (o D9 prevê "erro tratável", mas o D6/D4 não têm contrato explícito para esse erro específico).
- **Impacto:** Token expirado no meio de uma execução derruba o agente sem tratamento claro; mudança de API do SDK quebra a integração; contrato expirado em runtime não tem caminho de erro definido no D6.
- **Recomendação:** (a) Pinar/mockar o SDK com uma interface estável (protocolo Python) para isolar o D9 da API real; (b) implementar refresh automático no client com retry; (c) definir um erro tipado `KnowledgeSourceUnavailable` que o D6/D4 tratam como "agente decide como agir" (alinhado com o padrão de falha de tools/MCP).

### V-13 — Concorrência: múltiplas pipelines + fan-out paralelo não têm estratégia de thread_id, pool de conexões nem isolamento de execução
- **Severidade:** 🔵 baixo
- **Local:** D6 (executor, `astream`/`ainvoke`) + Spec §5 (execução) + D3 (session SQLAlchemy)
- **Descrição:** O design não especifica: (a) como **múltiplas pipelines** rodam ao mesmo tempo (cada uma precisa de um `thread_id` único no PostgresSaver — o D6 não define a convenção de `thread_id`, ex: `pipelineId` ou `pipelineId:runId`); (b) o **pool de conexões** do PostgresSaver (cada execução abre conexões; N pipelines paralelas + fan-out podem esgotar o pool); (c) o **fan-out paralelo** dentro de uma pipeline consome workers do event loop (o D6 usa `astream`, mas não limita `max_concurrency` — a doc do LangGraph expõe `configurable.max_concurrency`). Para V1 local single-user o risco é baixo, mas não é mapeado.
- **Impacto:** Em uso real (várias pipelines + fan-out), esgotamento de pool de conexões ou corrida por `thread_id` reutilizado (retomar a pipeline errada).
- **Recomendação:** (a) Definir `thread_id = f"{pipelineId}:{runId}"` (runId novo por execução) e persistir no `Checkpoint`; (b) configurar o pool do PostgresSaver (ex: `pool_size`) e o `max_concurrency` por execução; (c) teste de 2 pipelines simultâneas + 1 com fan-out para validar isolamento.

**Síntese:** Os dois achados críticos (V-01, V-02) são **bloqueantes de design** e afetam o contrato entre D5, D6 e D7 — o modelo de human-in-the-loop precisa ser redesenhado para o paradigma de `interrupt()` em nó + `Command(goto=...)` antes de qualquer implementação do D7. Os achados altos (V-03 a V-08) são viáveis com ajustes concretos, mas V-06 (pacote/imagem pgvector) e V-08 (Socket.IO vs WebSocket) são **quebras de build/conexão** que devem ser corrigidas no D1/D3, não no D6/D7. Os demais são riscos de robustez/segurança a documentar e mitigar, não bloqueios.

---

## 5. Alinhamento com o Protótipo

_Divergências entre o que a spec/plano descrevem e o que o protótipo `prototype/agent-portal.html` efetivamente implementa (views, componentes, fluxos de UI)._

**12 achados (0 críticos, 3 altos, 5 médios, 4 baixos).**

### P-01 — Botões sem ação (violação da regra "todos os botões funcionam")
- **Severidade:** 🟠 alto
- **Local:** Protótipo, ~24 botões sem `onclick` (linhas 1812, 1813, 1820, 1821, 1858, 2034, 2036, 2048, 2050, 2062, 2064, 2078, 2117, 2121, 2125, 2140, 2196, 2197, 2209, 2270, 2271, 2283, 2389, 2401, 2444) vs. D10 "Nota sobre o protótipo" ("todos os menus/botões funcionam, sem links mortos ou telas fake")
- **Descrição:** A regra do projeto exige que todo menu/botão funcione. O protótipo tem ~24 botões inativos: no Flow Editor (`Pausar`, `Executar`, `Agente`, `Conectar`), no Agent Detail (`Salvar`), em todas as cards de Aprovação (`Aprovar`, `Rejeitar`, `Deploy`, `Cancelar`), no Monitor (`Pausar`, `Retomar`×3), em Tools (`Nova Tool`, `Testar`, `Deploy`), em MCP (`Novo Servidor`, `Testar conexão`, `Salvar`), em Skills (`Nova Skill`) e em Knowledge (`Upload`, `Desconectar`, `Gerenciar`). Só funcionam: `Novo Agente`, zoom in/out/fit, `Argumentar`×3, `Ver pipeline`, theme toggle, navegação e seleção de KB.
- **Impacto:** O protótipo é a base declarada do D10 ("Basear a UI no protótipo"). Se o D10 seguir o protótipo como referência de comportamento, há risco de herdar telas com ações inativas. A regra "sem links mortos" é um critério explícito de aceite do D10.
- **Recomendação:** No protótipo, dar feedback mínimo a cada botão (ex.: `alert`/toast, ou estado visual) para demonstrar a ação; ou documentar explicitamente que são placeholders. No D10, garantir que cada botão mapeie para um endpoint real (já está no escopo 10.2–10.10) e tratar "todos os botões funcionam" como critério de aceite testável.

### P-02 — View "Agent Detail" não tem rota própria na spec/D10 (só "new" e "[id]")
- **Severidade:** 🟡 médio
- **Local:** Protótipo `view-agent-detail` (linhas 1853–2020) vs. spec seção 11 (`agents/new/page.tsx` e `agents/[id]/page.tsx`) e D10 "Arquivos que OWNS"
- **Descrição:** O protótipo tem uma única view `agent-detail` que serve tanto para "criar via chat" (botão `Novo Agente` → `showView('agent-detail')`) quanto para "detalhar/editar" (cards → `showView('agent-detail')`). A spec/D10 separam em duas rotas: `agents/new/page.tsx` (chat de construção) e `agents/[id]/page.tsx` (detalhe/editar). No protótipo, o botão "Novo Agente" leva para a MESMA view que o detalhe de um agente existente, com dados de exemplo fixos ("Backend Developer").
- **Impacto:** Na implementação, "Novo Agente" deve abrir o chat vazio (rota `new`), não o detalhe de um agente já populado. O protótipo conflui os dois estados numa view só, o que pode induzir o D10 a tratar como uma única tela.
- **Recomendação:** No protótipo, diferenciar visualmente o estado "novo" (chat vazio, sem config populada) do estado "detalhe" (config preenchida). No D10, confirmar que `new` e `[id]` são rotas distintas consumindo `AgentChat.tsx` (D4) em cenários diferentes.

### P-03 — Flow Editor: toolbar "Agente"/"Conectar" sem base na spec (adicionar nó/aresta)
- **Severidade:** 🟡 médio
- **Local:** Protótipo Flow Editor toolbar (linhas 1820–1821) vs. spec seção 11 (`FlowEditor.tsx` — React Flow wrapper) e ADR-006
- **Descrição:** O protótipo tem botões `Agente` e `Conectar` na toolbar do Flow Editor, sugerindo adicionar um novo nó (agente) e criar conexões. A spec não descreve explicitamente esses botões de toolbar; ela descreve o editor como "React Flow wrapper" com validação de contrato e o ADR-006 define a representação visual (flow/data edges, painel lateral ao clicar na aresta). O protótipo implementa o painel lateral de aresta (`edge-panel`) corretamente, mas os botões de adicionar nó/conectar não têm contraparte textual na spec.
- **Impacto:** Baixo risco funcional (React Flow já suporta drag-and-drop nativo), mas a ausência desses botões na spec pode gerar dúvida sobre se o D10 deve implementá-los ou se o React Flow resolve nativamente.
- **Recomendação:** A spec/D10 podem assumir que o React Flow fornece drag-and-drop nativo para adicionar nós e conexões; os botões do protótipo são conveniência. Documentar no D10 que a adição de nós/arestas segue o padrão React Flow (drag do palette + clique em ports).

### P-04 — Monitor: "Nós (86)" vs. Flow Editor "44 nós" (inconsistência de dados de exemplo)
- **Severidade:** 🔵 baixo
- **Local:** Protótipo Monitor (linha 2086: "Nós (86)") vs. Flow Editor (linha 1809: "44 nós")
- **Descrição:** O Flow Editor declara "44 nós" no subtítulo, mas o Monitor mostra "Nós (86)". Ambos referenciam a mesma pipeline "Feature Development". O número 86 não corresponde a 44 (nem ao dobro, 88).
- **Impacto:** Inconsistência cosmética nos dados de exemplo. Pode confundir quem usa o protótipo como referência de dados.
- **Recomendação:** Alinhar os números: se a pipeline tem 44 nós, o Monitor deve mostrar "Nós (44)". Ou ajustar ambos para um número coerente.

### P-05 — Monitor: "Retomar" em checkpoint "completed" (incoerência de estado)
- **Severidade:** 🔵 baixo
- **Local:** Protótipo Monitor checkpoints (linha 2124–2125: `dev-1.1 · completed` com botão `Retomar`)
- **Descrição:** O terceiro checkpoint mostra status "completed" mas oferece o botão "Retomar". Retomar faz sentido para checkpoints "failed" ou "interrupted", não para "completed" (que já terminou). A spec (seção 9.1) define `POST /pipelines/:id/checkpoints/:cpId/resume` para retomar de checkpoint específico, mas um checkpoint "completed" não é um ponto de retomada típico.
- **Impacto:** Incoerência de UX nos dados de exemplo. Pode induzir o D10 a oferecer "Retomar" para qualquer checkpoint, incluindo os concluídos.
- **Recomendação:** No protótipo, remover o botão "Retomar" do checkpoint "completed" (ou trocar por "Ver estado"). No D10, definir que "Retomar" só aparece para checkpoints "failed" ou "interrupted".

### P-06 — Approvals: botões "Aprovar"/"Rejeitar" sem handler (só "Argumentar" funciona)
- **Severidade:** 🟠 alto
- **Local:** Protótipo Approvals (linhas 2034, 2036, 2048, 2050, 2062, 2064) vs. D10 tarefa 10.6 ("aprovar/rejeitar/argumentar atualiza o grafo")
- **Descrição:** No protótipo, apenas o botão "Argumentar" tem handler (`toggleArg`). Os botões "Aprovar", "Rejeitar", "Deploy" e "Cancelar" não têm `onclick`. A spec (seção 9.6) define `POST /api/approvals/:id/respond` para responder (aprovar/rejeitar/revisar), e o D10 exige que "aprovar/rejeitar/argumentar atualize o grafo". O protótipo não demonstra o fluxo de aprovação/rejeição, apenas o de argumentação.
- **Impacto:** O fluxo central de human-in-the-loop (aprovar/rejeitar) não está demonstrado no protótipo. O D10 precisa implementar esses botões com handler real, mas o protótipo não serve de referência para o comportamento pós-clique (ex.: a card some? aparece confirmação? o badge atualiza?).
- **Recomendação:** No protótipo, adicionar handler mínimo aos botões de aprovação (ex.: remover a card da lista, atualizar o badge). No D10, definir o comportamento pós-resposta: a card é removida, o badge decrementa, e o WebSocket `approval:resolved` é emitido.

### P-07 — Knowledge: "Upload" e "Gerenciar" sem handler; "Desconectar" sem handler
- **Severidade:** 🟡 médio
- **Local:** Protótipo Knowledge (linhas 2389, 2401, 2444) vs. D10 tarefa 10.10 ("sidebar de bases, upload, escopo, Rivvn bar")
- **Descrição:** Os botões "Upload", "Desconectar" e "Gerenciar" na view Knowledge não têm handler. A spec (seção 9.3) define `POST /api/knowledge/upload` para upload de artefato, e o D10 exige "upload" como funcionalidade. O protótipo não demonstra o fluxo de upload nem de desconexão do Rivvn.
- **Impacto:** O fluxo de upload (central para a Knowledge Base) não está demonstrado. O D10 precisa implementar, mas o protótipo não serve de referência para o comportamento (ex.: dialog de upload? progress bar? listagem de arquivos?).
- **Recomendação:** No protótipo, adicionar um handler mínimo ao "Upload" (ex.: abrir um file input ou dialog). No D10, definir o fluxo de upload: seleção de arquivo → upload → confirmação → listagem atualizada.

### P-08 — Skills: "Nova Skill" sem handler; Tools: "Nova Tool", "Testar", "Deploy" sem handler
- **Severidade:** 🟡 médio
- **Local:** Protótipo Skills (linha 2283) e Tools (linhas 2140, 2196, 2197) vs. D10 tarefas 10.7–10.8
- **Descrição:** O botão "Nova Skill" (Skills) e os botões "Nova Tool", "Testar", "Deploy" (Tools) não têm handler. A spec (seção 9.4) define `POST /api/tools` (criar), `POST /api/tools/:id/test` (testar) e `POST /api/tools/:id/deploy` (deploy). O D10 exige "grid de tools, editar, deploy, testar". O protótipo mostra o editor de tool (script + params) mas os botões de ação não funcionam.
- **Impacto:** Os fluxos de criação, teste e deploy de tools não estão demonstrados. O D10 precisa implementar, mas o protótipo não serve de referência para o comportamento pós-clique.
- **Recomendação:** No protótipo, adicionar handlers mínimos (ex.: "Testar" mostra um resultado simulado, "Deploy" muda o status de "draft" para "deployed"). No D10, definir o fluxo: criar → editar → testar → deploy → status atualizado.

### P-09 — MCP: "Novo Servidor", "Testar conexão", "Salvar" sem handler
- **Severidade:** 🟡 médio
- **Local:** Protótipo MCP (linhas 2209, 2270, 2271) vs. D10 tarefa 10.9 ("grid de servidores, detalhe, testar conexão")
- **Descrição:** Os botões "Novo Servidor", "Testar conexão" e "Salvar" na view MCP não têm handler. A spec (seção 9.5) define `POST /api/mcp-servers` (registrar), `POST /api/mcp-servers/:id/test` (testar conexão, chama `tools/list`). O D10 exige "testar conexão". O protótipo mostra o detalhe do servidor (transporte, comando, env, tools descobertas) mas os botões de ação não funcionam.
- **Impacto:** O fluxo de teste de conexão (central para MCP, já que as tools são descobertas via `tools/list`) não está demonstrado. O D10 precisa implementar, mas o protótipo não serve de referência para o comportamento (ex.: spinner? atualização das tools descobertas? mudança de status?).
- **Recomendação:** No protótipo, adicionar handler ao "Testar conexão" (ex.: simular a descoberta de tools, atualizar a lista). No D10, definir o fluxo: registrar → testar conexão → tools descobertas aparecem → salvar.

### P-10 — Agent Detail: "Salvar" sem handler; chat de construção não demonstra o fluxo completo
- **Severidade:** 🟠 alto
- **Local:** Protótipo Agent Detail (linha 1858: `Salvar` sem handler) vs. spec seção 10 (Chat de Construção) e D10 tarefa 10.3
- **Descrição:** O botão "Salvar" no Agent Detail não tem handler. A spec (seção 10.1) descreve o fluxo completo do chat de construção: usuário descreve → IA sugere → usuário ajusta → IA confirma → "Salvar" → agente criado. O protótipo mostra o chat com mensagens de exemplo e o config panel populado, mas o botão "Salvar" não funciona. Além disso, o chat não é interativo (o input não envia mensagens, o botão de send não tem handler).
- **Impacto:** O fluxo central de construção de agentes via chat (um dos pilares do portal, seção 10 da spec) não está demonstrado de forma funcional. O D10 precisa implementar o chat interativo (streaming, via `POST /api/agents/:id/chat`), mas o protótipo não serve de referência para o comportamento (ex.: streaming de resposta? atualização do config panel em tempo real? validação de contrato?).
- **Recomendação:** No protótipo, tornar o chat interativo (input envia mensagem, IA responde com streaming simulado, config panel atualiza). Adicionar handler ao "Salvar" (ex.: mostrar confirmação, voltar ao dashboard). No D10, definir o fluxo: chat interativo → config panel atualiza em tempo real → salvar → agente criado → aparece no dashboard.

### P-11 — Flow Editor: "Pausar"/"Executar" sem handler; não demonstra o estado de execução
- **Severidade:** 🔵 baixo
- **Local:** Protótipo Flow Editor (linhas 1812–1813) vs. spec seção 9.1 (`POST /pipelines/:id/execute`, `POST /pipelines/:id/pause`)
- **Descrição:** Os botões "Pausar" e "Executar" no Flow Editor não têm handler. A spec define endpoints para executar e pausar pipelines. O protótipo não demonstra o estado de execução (ex.: nós com status "running", "completed", "failed" no grafo). O Monitor mostra esses estados, mas o Flow Editor não.
- **Impacto:** Baixo. O Flow Editor é focado em design (grafo), e o Monitor é focado em execução. A separação é coerente com a spec (seção 11: `pipelines/[id]/page.tsx` = editor, `pipelines/[id]/run/page.tsx` = monitor). Os botões "Pausar"/"Executar" no editor podem ser conveniência para iniciar execução sem sair da tela.
- **Recomendação:** No protótipo, adicionar handler ao "Executar" (ex.: redirecionar para o Monitor). No D10, definir que "Executar" inicia a pipeline e redireciona para o Monitor; "Pausar" pausa a execução em andamento.

### P-12 — Dados de exemplo: agentes do dashboard não batem com os tipos da spec (templates vs. tipos livres)
- **Severidade:** 🔵 baixo
- **Local:** Protótipo Dashboard (linhas 1643–1790) vs. spec seção 4.1 (Agent.type é "tipo livre definido pelo usuário")
- **Descrição:** O protótipo mostra 9 agentes com tipos: "Planner", "Épico", "História", "Task", "Developer" (Backend/Frontend), "QA", "Reviewer", "Deployer". A spec (seção 4.1) diz que `type` é "tipo livre definido pelo usuário" e que "planner", "developer", "reviewer", "deployer" são "templates/sugestões, não restrições". O protótipo usa "Épico", "História", "Task" como tipos, que não são templates da spec (são tipos de trabalho, não tipos de agente). Além disso, "QA" não é um template da spec (a spec lista: planner, developer, reviewer, deployer).
- **Impacto:** Baixo. O protótipo demonstra a flexibilidade de tipos livres (que é o objetivo da spec). Mas a mistura de "tipos de agente" (Planner, Developer, Reviewer, Deployer) com "tipos de trabalho" (Épico, História, Task, QA) pode confundir. A spec sugere que os templates são os 4 tipos de agente; os demais são tipos livres criados pelo usuário.
- **Recomendação:** No protótipo, manter a diversidade de tipos (demonstra flexibilidade), mas considerar se "Épico", "História", "Task" são tipos de agente ou apenas labels. No D10, definir que o campo "Tipo" no config panel é um texto livre (não um select), permitindo qualquer tipo.

**Observações gerais:**
1. **Cobertura de views:** O protótipo cobre todas as views da spec/D10 (Dashboard, Agent Detail, Flow Editor, Monitor, Approvals, Skills, Tools, MCP, Knowledge). Não há views na spec que o protótipo não tenha, nem views no protótipo que a spec não cubra. A navegação (sidebar) é completa.
2. **Componentes:** Os componentes da spec (seção 11) têm correspondência no protótipo. O protótipo não tem um componente separado para `KnowledgeView`, mas a view Knowledge está presente.
3. **Regras do projeto:** A regra "sem emojis" é respeitada (o único símbolo não-SVG é o `✕` no botão de fechar o edge panel, linha 1844, que é um glifo tipográfico, não um emoji). A regra "todos os botões funcionam" é violada em ~24 botões (P-01).
4. **Fluxos de UI:** Os fluxos descritos na spec (chat de construção, editor de fluxo, monitor de execução, painel de aprovações) estão representados no protótipo, mas a maioria dos botões de ação não tem handler, o que limita a demonstração dos fluxos completos.
5. **Dados de exemplo:** Os dados de exemplo são coerentes com os modelos da spec, com pequenas inconsistências numéricas (P-04) e de estado (P-05).

---

## Log de Análise

| Data | Dimensão | Status | Achados |
|------|----------|--------|---------|
| 2026-09-22 | Consistência interna | Concluído | 9 (1C, 3A, 4M, 1B) |
| 2026-09-22 | Coerência spec↔plano↔domínios | Concluído | 11 (2C, 4A, 4M, 1B) |
| 2026-09-22 | Completude e lacunas | Concluído | 24 (3C, 8A, 9M, 4B) |
| 2026-09-22 | Viabilidade técnica | Concluído | 13 (2C, 5A, 4M, 2B) |
| 2026-09-22 | Alinhamento com protótipo | Concluído | 12 (0C, 3A, 5M, 4B) |

**Total: 69 achados (8 críticos, 23 altos, 26 médios, 12 baixos).**

> Legenda de severidade: C=crítico, A=alto, M=médio, B=baixo.
