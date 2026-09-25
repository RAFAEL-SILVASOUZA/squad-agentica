# Validação: pe-review (FASE 5 - Pipeline engine)

| Data | Veredito | Resumo |
|------|----------|--------|
| 2026-09-24 | APROVADO | 10/10 lacunas da análise cobertas. 72 testes passam (10 compiler + 32 validator + 23 loader + 7 integration). Lint limpo. Compiler puro e determinístico. Validator 11 regras com formato spec 4.2. Loader conforme contrato de injeção. Padrões iguais ao spike. |

## Detalhes da verificação

### 1. Merges
- pe-compiler: `ddf0ab0` (merge no main)
- pe-validator: `b86f4d9` (merge no main)
- pe-loader: `0ae4e53` (merge no main)
- Nenhum branch `wt/*` pendente.

### 2. Testes
- `pytest tests/test_compiler_graph_builder.py -v` -> 10 passed in 0.84s
- `pytest tests/test_compiler_validator.py -v` -> 32 passed in 0.86s
- `pytest tests/test_skills_loader.py -v` -> 23 passed in 9.05s
- `pytest tests/test_pe_review_integration.py -v` -> 7 passed in 0.87s
- `ruff check app/compiler/ app/skills/loader.py app/agents/base.py tests/...` -> All checks passed!

### 3. 10 lacunas da ANALISE-PRONTIDAO

| # | Lacuna | Veredito | Evidência |
|---|--------|----------|-----------|
| 1 | TypedDict dinâmico | OK | `state.py` usa TypedDict fixo com 6 keys. Sem `types.new_class()`. |
| 2 | Raise na node function | OK | `graph_builder.py:329` try/except ao redor de `worker_client.execute()`. Nunca propaga. |
| 3 | Resume sem recompilar | OK | `compile_pipeline()` é a única entrada. ADR-004: recompila sempre do JSON. |
| 4 | Command(goto) com label | OK | `graph_builder.py:411,413` usa `approve_target`/`reject_target` (IDs reais). |
| 5 | PostgresSaver com string | OK | `compile_pipeline(checkpointer=Any)` aceita instância. Não há `PostgresSaver(DATABASE_URL)`. |
| 6 | Ordem de precedência route_fn | OK | `_make_route_fn`: conditions -> finalize -> follow. Documentado. |
| 7 | Stream "termina" | N/A | Gap do executor (D6/rt-executor), não do compiler. |
| 8 | Fan-out chave vs lista | OK | `route_fn` retorna `unconditional_targets` (lista de IDs). Teste `test_fan_out` passa. |
| 9 | Contador fora do State | OK | `iterations` no State com reducer `_sum_dicts`. Sobrevive a checkpoints. |
| 10 | Loader simples | OK | `SkillLoader` com injeção de db, storage, rag, mcp_client_factory. Roda no worker (ADR-008). |

### 4. Critérios bloqueantes

| # | Critério | Veredito |
|---|----------|----------|
| 1 | Nenhuma das 10 lacunas cometida | PASS |
| 2 | Compiler puro e determinístico | PASS (teste `test_determinism`) |
| 3 | Validator 11 regras, formato spec 4.2, chamado antes do compile | PASS (teste `test_validator_format_spec_4_2`) |
| 4 | Data edges mapeiam outputs para inputs; data edge sem flow edge implica flow | PASS (teste `test_data_edge_without_flow_edge`) |
| 5 | requiresApproval gera nó de aprovação com IDs reais e reject target | PASS (teste `test_approval_uses_real_node_ids`) |
| 6 | Loader conforme contrato de injeção, JSON-serializável, tolerante a falha parcial | PASS (testes `test_capabilities_json_serializable`, `test_skill_missing_in_garage_is_partial_failure`) |
| 7 | Padrões iguais aos do spike | PASS (mesmos reducers, mesma estrutura de node function, mesmo padrão de approval node) |

### 5. Achados não bloqueantes

1. **Duplicação de AgentSnapshot**: `graph_builder.py` define `AgentSnapshot` (dataclass) e `app/agents/base.py` define outro `AgentSnapshot` (dataclass) com campos ligeiramente diferentes. O loader importa de `app/agents/base.py`; o compiler usa o seu próprio. Funciona porque os campos de refs (`skills`, `tools`, `mcp_servers`, `knowledge`, `integrations`) existem nos dois. Unificação é pendência para FASE 6 (rt-executor).

2. **Nó de aprovação sem arestas saídas explícitas**: o compiler adiciona apenas `source -> approval_node` (incondicional). As arestas saídas do approval_node são definidas pelo `Command(goto)` retornado. Isso é correto no LangGraph (o `Command(goto)` define o roteamento dinamicamente), mas difere do D5 que descreve `approval_node -> target` e `approval_node -> reject_handler` como arestas explícitas. O comportamento é equivalente e os testes confirmam.

3. **`pipeline_status` com reducer de precedência**: o ADR-002 do contrato pede `last` (default LangGraph) para `pipeline_status`, mas o compiler usa `_pipeline_status_reducer` (failed > running > completed). Justificado: em fan-out, dois nós escrevem `pipeline_status` no mesmo superstep e o reducer de precedência evita que "completed" sobrescreva "failed". Desvio registrado no handoff do pe-compiler.

4. **`maxIterations` checado na node function**: o D5 diz "O compiler não verifica maxIterations na route_fn" e "A enforcement é exclusiva do runtime (D6)". O contrato técnico (ADR-005/007) diz "node function checa `iterations[nodeId] >= maxIterations` no início". O compiler implementa a verificação na node function (conforme ADR-005/007), não na route_fn. A route_fn apenas roteia com base na action. Isso é consistente: a node function é parte do compiler (ela é gerada pelo compiler), mas a enforcement é "no runtime" no sentido de que roda durante a execução, não durante a validação.
