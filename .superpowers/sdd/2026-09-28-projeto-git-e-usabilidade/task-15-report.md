# Task 15 — Knowledge backend

## Entrega

- `KnowledgeDocument.content_hash` guarda SHA-256, com índice para consulta e unicidade por base. Upload repetido retorna `409 duplicate_document` com os dados do documento existente; `?replace=<id>` troca o documento, chunks e arquivo, mantendo `document_count` estável.
- Conversas e mensagens foram adicionadas ao SQLAlchemy e à migração Alembic, com exclusão em cascata para base/conversa e índice de mensagens por conversa.
- A API permite listar/criar/abrir/excluir conversas e enviar mensagens. As rotas verificam ownership da base e conversa; pergunta inicial define o título até 60 caracteres.
- O serviço de chat consulta RAG com o `top_k` da base, inclui até seis mensagens recentes e trechos numerados no prompt pt-BR e usa `app.core.llm.get_llm_client()`, preservando o provedor configurado. Sem resultados, responde com a frase padrão e não chama o LLM. Fontes guardam documento, chunk, texto e score.
- O teste de rate limit agora envia conteúdo distinto em cada upload para medir o limite sem colidir com a nova regra de duplicidade.

## Arquivos alterados

- `agent-orchestrator/app/api/knowledge.py`
- `agent-orchestrator/app/db/models.py`
- `agent-orchestrator/app/knowledge/rag.py`
- `agent-orchestrator/app/knowledge/chat.py` (novo)
- `agent-orchestrator/alembic/versions/3b91c0d4a6e7_knowledge_hash_and_chat.py` (novo)
- `agent-orchestrator/tests/test_knowledge_crud.py`
- `agent-orchestrator/tests/test_knowledge_duplicates.py` (novo)
- `agent-orchestrator/tests/test_knowledge_chat.py` (novo)
- `agent-orchestrator/tests/test_migration.py`

## Validação

- RED observado nos testes novos: duplicado sem conflito, replace mantendo documentos antigos e rotas de conversa ausentes; 26 testes existentes passaram nessa etapa.
- `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock pytest -q -p no:cacheprovider`: **628 passed**, incluindo `test_migration.py` e `alembic check`.
- `ruff check app/db/models.py app/api/knowledge.py app/knowledge/chat.py app/knowledge/rag.py tests/test_knowledge_crud.py tests/test_knowledge_duplicates.py tests/test_knowledge_chat.py tests/test_migration.py`: **All checks passed**.
- `git diff --check`: passou.
- A suíte completa emitiu avisos existentes de escopo do `pytest-asyncio`, alias deprecated do Starlette e corrotinas `Connection._cancel` do `test_rt_executor`; sem falhas.

## Ajustes após revisão

- Captura de `IntegrityError` no `flush` inicial: concorrência por hash retorna 409 com o documento vencedor.
- Replace agora usa um único commit de banco para liberar o hash antigo, indexar o novo e remover o anterior; qualquer falha antes do commit faz rollback e remove apenas o arquivo novo.
- Pergunta e resposta recebem timestamps UTC monotônicos, e a rota bloqueia a conversa durante o turno para preservar ordem em gravações simultâneas.
- O chat passa `scope_ref` como `agent_id` ou `pipeline_id` para o RAG conforme o escopo da base.
- Novos testes reproduziram corrida de unicidade com sessões separadas, falha de replace, ordenação dos turnos e parâmetros de escopo; todos passaram.
- Todos os uploads agora deixam indexação e gravação de documento no mesmo commit. A regressão falha o primeiro embed e comprova que retry do mesmo arquivo é aceito, sem documento/hash parcial.

## Estado

Sem commit e sem arquivos staged; aguardando revisão do coordenador. `.codex/` já estava untracked no início e não foi lido nem alterado. `agent-portal/` não foi tocado. O preflight não encontrou `learning/INDEX.md`; o trabalho seguiu os briefings e o código atual.
