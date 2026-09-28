# Teste de usabilidade com LLM e embeddings reais (2026-09-27/28)

Provedor: `Qwen3.8-27B-Q8_0` (chat e execução de agentes) e `nomic-embed-text-v1.5` (768 dimensões, completadas até 1536), ambos em `http://192.168.18.4:1234/v1`.

Método: um usuário novo percorreu a plataforma inteira no navegador (Chromium via Playwright, com digitação tecla a tecla e screenshots analisados a cada etapa). Cada defeito encontrado foi corrigido pela causa raiz, coberto por teste que falha sem a correção e verificado de novo na tela.

## Jornada executada

1. Cadastro e entrada no dashboard (estado vazio).
2. Agente "Redator de Especificações" criado pelo chat de construção: rascunho completo em ~12s.
3. Edição pelo chat (ação "devolver") e salvamento.
4. Segundo agente "Revisor de Especificações" pelo chat.
5. Biblioteca:
   - skill com template;
   - tool `contar-palavras` (teste no sandbox e deploy);
   - servidor MCP inalcançável (mensagem de falha).
6. Knowledge "Normas internas" com um Markdown e um PDF. A consulta devolve o trecho certo nos dois casos (score 0,77 e 0,72).
7. Mochila do Redator (skill, tool e knowledge) salva, com nomes nos chips.
8. Pipeline pelo editor: Redator → Revisor com aresta de dados `especificacao → especificacao` e aprovação humana.
9. Execução com a ideia informada no formulário, acompanhada no monitor. A aprovação chega em tempo real (sino e sidebar).
10. Aprovar: o Revisor produz a revisão (5.592 caracteres) e cita o padrão "Dado/Quando/Então" da knowledge base.
11. Segundo e terceiro runs com Argumentar: o Revisor recebe a especificação e o feedback (LGPD) e os trata.
12. Dashboard e todas as telas em 390px: sem rolagem horizontal.

## Defeitos encontrados e corrigidos

| # | Defeito | Causa | Correção |
|---|---|---|---|
| 1 | Run com ferramentas falhava no LLM local (500) | `tool_calls` sem `type: "function"` ao voltar ao modelo | worker normaliza o campo |
| 2 | Monitor sem logs e run "Falhou" sem motivo | `pipeline:log` (contrato §7) nunca era emitido; `pipeline_runs.error` nunca gravado | logs e erro do worker viram estado do nó, evento WS e erro do run; aviso "Falha na execução" |
| 3 | Cabeçalho do monitor não saía de "Executando" | status agregado (sem `nodeId`) era ignorado | atualiza o run e recarrega o erro |
| 4 | Deploy de tool sempre falhava com `def execute(**kwargs)` | validador exigia parâmetro posicional | aceita `**kwargs`, `*args` e keyword-only; toast mostra o motivo |
| 5 | Edição pelo chat não era salva ("Pronto! Adicionei…") | chat só altera o formulário; Salvar fica no fim da página | aviso "Alterações do assistente ainda não salvas" com Salvar/Descartar |
| 6 | Markdown cru no chat | texto renderizado literal | negrito e código inline formatados, sem HTML |
| 7 | "Excluir" cortado no card da tool | 4 botões sem quebra | `flexWrap` |
| 8 | Teste de MCP mostrava "Falha" mesmo conectado, sem motivo | UI lia `{success,tools}`, o contrato devolve `{status,discoveredTools}` | mapeamento pelo contrato e campo `error` legível |
| 9 | Garage não subia após reiniciar o Docker (stack inteiro fora) | init subia a versão do layout; `--single-node` recusa layout > 1 | daemon em modo normal, layout aplicado só uma vez |
| 10 | Sessão travada em "Sessão expirada" sem ir ao login | refresh store em memória perdido no restart; cliente não redirecionava | token válido desconhecido é aceito; cliente renova uma vez e depois vai a `/login` com mensagem, sem loop |
| 11 | Renovação concorrente derrubava a sessão | NextAuth renovava em paralelo com o mesmo refresh token | renovação única compartilhada no portal; rotação estrita mantida (contrato §5) |
| 12 | Busca na KB perdia o trecho do PDF | `nomic-embed-text` exige prefixos de tarefa; limiar 0,7 fixo | `EMBEDDING_QUERY_PREFIX`/`DOCUMENT_PREFIX`; limiar e Top K na criação da base |
| 13 | Pipeline não executava se o 1º agente tinha entrada obrigatória | regra 6 aplicada ao nó de entrada | nó de entrada isento (spec: agente *target*); editor trata UUID nulo como "sem entrada" |
| 14 | Aprovação marcada na aresta de dados era ignorada | aresta de fluxo injetada (regra 7) nascia sem aprovação | herda aprovação, canal e mensagem |
| 15 | O 1º agente rodava sem nenhum dado ("Execute your task.") | execute ignorava o corpo; nó de entrada não lia inputs iniciais | `execute {inputs}`, estado `run_inputs`, formulário ao executar |
| 16 | Aprovador não via o que aprovava; card com UUIDs | card não renderizava `context` | conteúdo para revisão e nomes de pipeline/agente |
| 17 | Mensagem de aprovação sumia | editor descartava `approvalMessage`/`Channel` ao carregar (Executar re-salvava) | conversão preserva os campos |
| 18 | Monitor não mostrava saída do nó ao reabrir | checkpoint gravado com o estado do passo anterior (data vazio) | snapshot inclui a atualização do nó; monitor restaura do checkpoint |
| 19 | Saída do nó ilegível; UUID de skill no card do agente | JSON com `\n` escapado; id cru | texto por porta; "N skills" |
| 20 | **Argumentar apagava a saída do agente**: Revisor dizia "nenhum documento fornecido" | merge raso do estado substituía `data[source]` pelo feedback | feedback mesclado e entregue ao agente target como `humanFeedback` |
| 21 | Aviso setState-during-render nas aprovações | contagem enviada ao pai dentro do updater | efeito após o render |
| 22 | Celular: menu cobria o Voltar; grafo do monitor sumia | botão absoluto sobre o conteúdo; grid fixo | conteúdo abaixo do menu; layout que quebra em coluna |

## Verificação final (modo mock, stack recriado com o código final)

| Suíte | Resultado |
|---|---|
| orchestrator | 526 passed |
| worker | 25 passed |
| portal (vitest, tsc, lint) | 391 passed, ok, ok |
| integração | 90 passed, 1 skipped + `test_01_auth` 21 passed após a correção da rotação |
| E2E | 34 passed, 1 skipped (Jornada 8, skip conhecido) |
| `npm run build` | ok |

O stack foi devolvido ao provedor real ao final.

## Pendências (baixa) — ver `PENDENCIAS.md`

- O detalhe do agente mostra o `model` salvo (ex.: `gpt-4o`), mas quem executa é `LLM_MODEL` quando definido.
- No celular, o minimapa do monitor ocupa muito espaço.
- Avisos só de dev do React Flow (`defs/marker/path`).
- Logs anteriores à abertura do monitor não voltam (sem histórico de logs no contrato); status e saída dos nós voltam pelos checkpoints.
- Documentos indexados antes dos prefixos de embedding precisam ser reenviados para melhor relevância.
