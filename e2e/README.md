# Agent Portal UI QA

Executar no host Windows com o stack existente saudável, `LLM_PROVIDER=mock` e `EMBEDDING_PROVIDER=mock`:

```powershell
cd e2e
npm run typecheck
npx playwright test tests/01-auth.spec.ts --reporter=line   # rode por arquivo (rate limit de login)
npm run report
```

Dependências já instaladas. Para uma instalação nova: `npm ci` e `npx playwright install chromium`. O helper SQL usa `tests/integration/.venv/Scripts/python.exe` e psycopg instalado pela suíte de integração.

- `E2E_BASE_URL`: padrão `http://localhost`; neste host `127.0.0.1:80` atende outro serviço.
- `E2E_DB_DSN`: conexão de fixture, padrão de desenvolvimento local conforme `tools/db.py`.
- Um usuário novo por worker (fixture `user` com `scope: "worker"`; um worker novo por arquivo e após cada falha), prefixo `qa-e2e-`; cleanup restrito a esse prefixo. Nenhum volume é apagado. **Não comprova startup com banco vazio**; execute contra uma instalação isolada vazia para esse aceite.
- Um worker, sem retries automáticos. Login NextAuth pode mascarar rate limit como 401; helper permite apenas um cooldown antes da segunda tentativa.
- `test-results/results.json`, relatório HTML, screenshots e traces são locais e ignorados. Traces podem conter tokens/cookies: não versionar nem publicar.

## Interpretação

F1–F20 vêm de `docs/superpowers/handoffs/qa-integration.md`. CRUD/validate de pipelines são simulados para contornar F9; execução usa backend real. Aprovações são semeadas, portanto suas respostas não comprovam resume LangGraph. O chat inicial usa SSE real; os casos seguintes usam draft simulado e persistem pela API de agentes para permitir testar detalhes. Falhas novas da UI são nomeadas E1–E15 nas mensagens das asserções (várias como `expect.soft`, para a jornada seguir até o fim). O loop é bloqueado por F1/F6/F7, sem simular sucesso de maxIterations.

Um teste verde com simulação não aprova a jornada integrada. Consulte `docs/superpowers/handoffs/qa-e2e.md` para mapa jornada → falha e limitações residuais.
