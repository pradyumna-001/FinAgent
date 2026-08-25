FinAgent — Checklists de Implementação
30 issues · 8 semanas · use ☐ para marcar tarefas concluídas
Regra: não avança de semana sem o entregável da semana anterior funcionando.

Semana 1 — Fundação

#01 Estrutura do repositório  ·  Segunda  ·  setup
☑  git init + criar repositório público no GitHub
☑  Criar estrutura de pastas completa
→ app/api, app/agents, app/graph, app/memory, app/db, app/services, app/workers
→ tests/unit, tests/integration, tests/e2e, tests/eval, docs/adrs
☑  Criar .env.example com todas as variáveis necessárias
→ OPENAI_API_KEY, TAVILY_API_KEY, LANGCHAIN_API_KEY, DATABASE_URL, REDIS_URL, SECRET_KEY
☑  Copiar README.md, DEPLOYMENT.md e CLAUDE.md para a raiz
☑  Criar .gitignore (Python, Docker, .env)
☑  Fazer primeiro commit e push
Entregável: repositório público no GitHub com estrutura e documentação inicial.

#02 Docker Compose  ·  Terça  ·  infra
☑  Criar docker-compose.yml
☑  Serviço PostgreSQL 16 com health check
☑  Serviço Redis com AOF habilitado (appendonly yes) e health check
☑  Serviço Celery worker
☑  Serviço Celery Beat
☑  Criar script init.sql que ativa extensões: CREATE EXTENSION vector; CREATE EXTENSION age;
☑  Criar Dockerfile da aplicação FastAPI
☑  Testar: docker-compose up → todos os serviços healthy
☑  Testar: verificar que extensões estão ativas no PostgreSQL
→ SELECT * FROM pg_extension WHERE extname IN ('vector', 'age');
Entregável: docker-compose up sobe tudo sem erro. Todos os serviços healthy.

#03 Modelos SQLAlchemy e Migrations  ·  Quarta  ·  feature
☑  Criar modelo Manager (gestor_id, name, email)
☑  Criar modelo Company (empresa_id, ticker, nome, setor)
☑  Criar modelo Portfolio (gestor_id FK, empresa_id FK)
☑  Criar modelo MorningNote com todos os campos críticos
→ pipeline_run_id, morning_note_id, gestor_id, empresa_id, data
→ conteudo, confidence_scores JSONB, data_freshness JSONB, flags JSONB[]
→ status enum: pending | generating | completed | failed
☑  Criar modelo Recommendation (morning_note_id FK, acao, justificativa, confianca)
☑  Configurar Alembic para migrations async
☑  Criar migration inicial com todas as tabelas
☑  Criar índices na migration: B-tree composto (gestor_id, empresa_id, data)
☑  Criar Partial Index: (data) WHERE status = 'completed'
☑  Criar HNSW index para embeddings dos morning notes
☑  Criar políticas RLS: nenhuma query sem gestor_id passa
☑  Testar: alembic upgrade head sem erro
☑  Testar: RLS rejeita query sem gestor_id
Entregável: tabelas, índices e RLS existem no banco após alembic upgrade head.

Issue #03 fechado. Branch `rebuild/issue-03-models` virou `main` em `b6500c2`.
PR #30 fechado (não mergeado — divergência com o `main` histórico; rebuild
começa em `b6500c2`). Três follow-ups abertos:

#03a RLS nas cinco tabelas restantes  ·  **concluído**  ·  feature
☑  Adicionar política RLS em managers (decidir: por gestor ou `USING (true)`)
☑  Adicionar política RLS em companies (decidir: por gestor ou `USING (true)`)
☑  Adicionar política RLS em portfolios (por gestor)
☑  Adicionar política RLS em portfolio_holdings (por gestor via portfolio)
☑  Adicionar política RLS em recommendations (via morning_notes.manager_id)
☑  Adicionar probe por tabela em tests/integration/
☑  Adicionar probe comportamental para recommendations
GitHub: issue #31

#03b App role split + DATABASE_URL split  ·  **concluído**  ·  feature
☑  Criar role `finagent_app` com NOSUPERUSER NOBYPASSRLS LOGIN
☑  GRANT DML apenas (sem DDL)
☑  Split env: MIGRATION_DATABASE_URL (elevated) e DATABASE_URL (app)
☑  Atualizar app/config.py para expor ambas URLs
☑  alembic/env.py lê MIGRATION_DATABASE_URL
☑  Atualizar probe comportamental para conectar como `finagent_app`
☑  Probe: `finagent_app` não pode DROP/CREATE em public
GitHub: issue #32

#03c HNSW reindex-on-insert operator script  ·  **concluído**  ·  infra
☑  Drift detection (idx_scan / row count thresholds)
☑  scripts/reindex_hnsw.py — REINDEX INDEX CONCURRENTLY + state table
☑  Flags --dry-run e --force
☑  Cron config documentado (6h BRT = 9h UTC)
☑  tests/integration/test_reindex_hnsw.py
GitHub: issue #33

#04 FastAPI base + endpoints mínimos  ·  Quinta  ·  feature
Issue quebrado em três sub-issues para viabilizar chunks de ~25 linhas.

#04a FastAPI lifespan + engine async + /health  ·  **concluído**  ·  feature
☑  app/main.py com lifespan que cria engine async e dispose no shutdown
☑  app/db/session.py com async session factory e get_session dependency
☑  GET /health → {status: ok, db: ok} via SELECT 1; 503 se DB inalcançável
☑  Probe smoke em tests/integration/ via httpx.AsyncClient
GitHub: issue #34

#04b Logging middleware + GET /morning-notes  ·  **concluído**  ·  feature
☑  app/core/logging_config.py — logger estruturado com filtro que lê contextvars
☑  ContextVars: current_pipeline_run_id, current_morning_note_id
☑  ASGI middleware — lê headers X-Pipeline-Run-Id e X-Morning-Note-Id, reseta no exit
☑  GET /morning-notes → filtra por gestor-id header, 400 sem header, SET LOCAL app.manager_id
☑  Probe middleware (unit) + probe endpoint (integration) em tests/integration/
GitHub: issue #35

#04c POST /pipeline/trigger + SSE stub  ·  **concluído**  ·  feature
☑  POST /pipeline/trigger → 202 Accepted com UUID pipeline_run_id
☑  Background task stub — loga e sai (implementação real vem em #08–14)
☑  GET /morning-notes/{id}/stream → text/event-stream com 1 evento ready e fecha
☑  Probes trigger e stream em tests/integration/
GitHub: issue #36

Entregável dos três juntos: endpoints respondem. RLS ativo em produção.

#05 Testes unitários base + CI/CD  ·  Quinta  ·  test
Issue quebrado em quatro sub-issues para viabilizar chunks de ~25 linhas e
revisões pequenas. Decisões de escopo em 2026-08-05:
- Módulos separados por responsabilidade (`freshness.py`, `confidence.py`, `flags.py`) em vez de um `utils.py` monolítico.
- `DataFlag` como `@dataclass(frozen=True)` para que #07 possa anotar `state["flags"]` e helpers como `.is_fatal()` existam desde o dia 1.
- CI começa unit-only; cobertura de integração fica em issue separada (#05d) porque exige `services:` Postgres no runner e pode ser ruidoso se vier junto.

#05a Unit-test base: freshness + confidence threshold  ·  **concluído**  ·  test
☑  app/utils/__init__.py (módulo vazio — namespace marker)
☑  app/utils/freshness.py — `is_data_fresh(source: str, fetched_at: datetime, *, now: datetime | None = None, max_age: timedelta = timedelta(hours=24)) -> bool`
☑  app/utils/confidence.py — `confidence_flag(score: float, *, threshold: float = 0.75) -> bool` (ou retorna `DataFlag` direto — decidir no chunk)
☑  tests/unit/test_freshness.py com `test_data_freshness_check` (dado > 24h retorna False; fresh retorna True; boundary em exatamente 24h retorna True)
☑  tests/unit/test_confidence.py com `test_confidence_threshold` (score < 0.75 retorna flag; score == 0.75 retorna flag; score > 0.75 retorna False)
☑  Pure Python — sem fixtures Docker, sem `conftest.py` import
GitHub: issue #41

#05b DataFlag frozen dataclass + helper methods  ·  **concluído**  ·  test
☑  app/utils/flags.py — `@dataclass(frozen=True) class DataFlag`
→ Campos: `source: str`, `severity: Severity` (enum: INFO / WARNING / FATAL), `message: str`, `created_at: datetime` (default factory)
☑  Métodos: `.is_fatal() -> bool`, `.is_warning() -> bool`, `.to_dict() -> dict` (para serializar no JSONB)
☑  `__post_init__` valida `message` não-vazio e `source` não-vazio
☑  tests/unit/test_dataflag.py com `test_dataflag_generation`
→ Falha de fonte gera DataFlag com `severity=WARNING`, `source="tavily"`, message contendo a falha
→ `__post_init__` rejeita `source=""` com `ValueError`
→ `.to_dict()` serializa datetime como ISO-8601
☑  Sem dependência do #07 — `#05b` define o shape que #07 consome
GitHub: issue #42

#05c CI workflow — unit-only, green-on-push  ·  **concluído**  ·  infra
☑  Criar .github/workflows/ci.yml
→ Trigger: push em qualquer branch + PR contra main
→ Setup: `actions/checkout@v4`, `actions/setup-python@v5` com Python 3.11, `pip install -e ".[dev]"`
→ Run: `ruff check .`, `mypy app`, `pytest tests/unit/ -v`
→ Cache pip baseado em `uv.lock` ou `requirements` (decidir no chunk)
☑  Branch protection rule: "Require status checks to pass before merging" → marcar `ci / unit-tests` como required
☑  Verificar: push de um commit com teste vermelho bloqueia merge
☑  Verificar: push de um commit com teste verde passa
GitHub: issue #43

#05d CI: full integration coverage  ·  **concluído**  ·  infra
☑  Adicionar job `integration-tests` ao mesmo workflow
→ Postgres service container (`postgres:16` com `pgvector` instalado via init script)
→ Migration step antes do pytest
→ Run: `pytest tests/integration/ -v`
☑  Mover `pg_container` fixture de testcontainers para Postgres-in-GHA
☑  Adicionar `services:` block no job e `DATABASE_URL` apontando para `localhost:5432`
☑  Cache: layers do Docker para acelerar runs subsequentes
☑  Branch protection: marcar `ci / integration-tests` como required check
☑  Verificar: pipeline inteira roda em < 5 min
GitHub: issue #44

Entregável dos quatro juntos: CI verde em todo push; três unit tests passando; DataFlag tipado pronto para #07 consumir.

#06 Revisão da Semana 1  ·  Sexta  ·  review
☑  Clonar o repositório numa pasta nova e seguir o DEPLOYMENT.md do zero
☑  docker-compose up funciona sem configuração manual extra
☑  pytest passa sem configuração manual
☑  RLS funciona: query sem gestor_id é rejeitada
☑  Atualizar CLAUDE.md com decisões que mudaram
☑  Atualizar progress tracker no CLAUDE.md — marcar Semana 1 como concluída
Entregável: qualquer pessoa consegue rodar o projeto do zero seguindo o DEPLOYMENT.md.


Semana 2 — Agentes Base

#07 Typed AgentState  ·  Segunda  ·  feature
☑  Criar app/graph/state.py
☑  Definir tipos auxiliares: MacroOutput, CompanyEvent, QuantOutput, RiskFlag, DataFlag, Recommendation
☑  Definir AgentState com TypedDict — todos os campos obrigatórios e opcionais
→ pipeline_run_id: str, morning_note_id: str, gestor_id: int, empresa_ticker: str
→ macro_context: MacroOutput | None, company_events: list[CompanyEvent]
→ quant_metrics: QuantOutput | None, risk_flags: list[RiskFlag]
→ morning_note: str | None, recommendation: Recommendation | None
→ confidence_scores: dict[str, float], data_freshness: dict[str, datetime]
→ flags: list[DataFlag]
☑  Criar validate_state() que verifica invariantes antes de cada nó
☑  Criar create_initial_state() com valores padrão
☑  Testar: validate_state() rejeita estado sem gestor_id com erro explícito
Entregável: AgentState tipado importável. validate_state() funciona.

#08 MacroAgent  ·  Tuesday  ·  feature
☑  Create app/agents/macro.py
☑  Implement macro_agent_node(state: AgentState) → AgentState
☑  Integrate Tavily API for macro BR news search
→ Sources: Central Bank, IBGE, Reuters BR, Bloomberg BR
☑  Use NVIDIA NIM (primary + fallback model) for extraction and summary
☑  Fill state['macro_context'] with MacroOutput typed
☑  Fill state['data_freshness']['macro'] with datetime.now()
☑  If Tavily fails: append DataFlag and return state with macro_context=None
→ NEVER leave silent failures — always append DataFlag
☑  Log with pipeline_run_id and morning_note_id
☑  Test: MacroAgent returns MacroOutput with real-time data
Deliverable: MacroAgent processes and returns macro context with real data.


#09 CompanyAgent  ·  Wednesday  ·  feature
☑  Create app/agents/company.py
☑  Implement company_agent_node(state: AgentState) → AgentState
☑  Integrate Tavily to search for company news by ticker
→ Sources: CVM, Company RI, InfoMoney, Valor Economico
☑  Use NVIDIA NIM (primary + fallback model) for extraction
☑  Fill state['company_events'] with list[CompanyEvent]
☑  Fill state['data_freshness']['company'] with datetime.now()
☑  If Tavily fails: append DataFlag and return with company_events=[]
☑  Test: CompanyAgent returns real events from a B3 stock
Deliverable: CompanyAgent returns real events from a B3 company.

#10 QuantAgent  ·  Quarta  ·  feature
☑  Criar app/agents/quant.py
☑  Implementar quant_agent_node(state: AgentState) → AgentState
☑  Integrar API B3 ou Yahoo Finance para dados financeiros
☑  CRITICAL RULE: Python does ALL calculations — LLM never calculates
☑  Verificar data_freshness ANTES de qualquer cálculo
→ Se dado > 24h: append DataFlag('b3_api', 'data_outdated') e retornar sem calcular
☑  Calcular em Python: P/L, EV/EBITDA, P/VPA, dividend yield, variação vs IBOV
☑  Usar NVIDIA NIM APENAS para interpretar os resultados calculados
☑  Preencher state['quant_metrics'] com QuantOutput tipado
☑  Testar: dado de 48h → DataFlag no state, sem cálculo
☑  Testar: dado fresco → métricas calculadas corretamente
Entregável: QuantAgent calcula métricas reais com data_freshness verificada.

#11 Testes de integração dos agentes base  ·  Quinta–Sexta  ·  test
☑  Criar tests/integration/test_agents.py
☑  Mock Tavily com erro 500 → verifica DataFlag no state após MacroAgent
☑  Mock Tavily com erro 500 → verifica DataFlag no state após CompanyAgent
☑  Mock B3 com dado de 48h → verifica que QuantAgent não calcula e appenda DataFlag
☑  Verificar que state['data_freshness'] tem timestamp após cada agente
☑  Todos os testes com LLM mockado (monkeypatch)
☑  Todos os testes passando no CI
Entregável: 3 testes de integração verdes no CI com LLM mockado.


Semana 3 — RiskAgent, EditorAgent e Grafo

#12 RiskAgent  ·  Segunda–Terça  ·  feature
☑  Criar app/agents/risk.py
☑  Implementar risk_agent_node(state: AgentState) → AgentState
☑  Usar GPT-4o para raciocínio complexo
☑  Prompt adversarial explícito: 'Você é um analista cético. Encontre inconsistências, riscos ignorados e vieses'
☑  RiskAgent lê macro_context, company_events e quant_metrics do state
☑  RiskAgent NÃO busca dados externos — só analisa o que os outros produziram
☑  Preencher state['risk_flags'] com list[RiskFlag] — cada flag com probabilidade e impacto
☑  Se state tiver DataFlags: RiskAgent menciona as lacunas de dados como risco adicional
☑  Testar: RiskAgent identifica ao menos 1 risco real num cenário de teste
Entregável: RiskAgent identifica riscos reais num cenário de teste com dados reais.
GitHub: issue #77
Pré-requisito β1 ("RiskAgent precisa de `market_time`?") resolvido por #68 / PR #76.

#13 EditorAgent  ·  Terça  ·  feature
☑  Criar app/agents/editor.py
☑  Implementar editor_agent_node(state: AgentState) → AgentState
☑  Usar GPT-4o para geração do morning note
☑  Morning note em português com seções: contexto macro, eventos, métricas, riscos, recomendação
☑  Preencher confidence_scores por seção baseado nos scores dos outros agentes
→ Seção com DataFlag → confidence_score < 0.5 + aviso explícito no texto
☑  Preencher state['morning_note'] com texto completo
☑  Preencher state['recommendation'] com Recommendation tipado
☑  Se qualquer seção tiver DataFlag: incluir aviso explícito no texto (Fail Visible)
☑  Testar: EditorAgent gera morning note legível e recomendação estruturada
Entregável: EditorAgent gera morning note completo com recomendação e confidence scores.

#14 LangGraph StateGraph completo  ·  Quarta  ·  feature
☑  Criar app/graph/pipeline.py
☑  Montar StateGraph: MacroAgent → [CompanyAgent, QuantAgent] paralelo → RiskAgent → EditorAgent
☑  Configurar PostgresSaver como checkpointer
☑  Adicionar validate_state() antes de cada nó
☑  Configurar tags LangSmith: gestor_id, empresa, data, pipeline_run_id, morning_note_id
☑  Criar script scripts/run_pipeline.py para testar no terminal
☑  Testar: run_pipeline.py processa PETR4 e imprime morning note no terminal
☑  Verificar trace no LangSmith com tags corretas
Entregável: run_pipeline.py processa uma empresa completa e imprime morning note.

#15 Testes do grafo completo  ·  Quinta–Sexta  ·  test
☑  test_parallel_execution: CompanyAgent e QuantAgent têm timestamps sobrepostos
☑  test_fail_visible_invariant: mock Tavily com erro → morning note contém aviso explícito
☑  test_confidence_scores_populated: todo morning note tem confidence_scores em todas as seções
☑  test_validate_state_rejects_invalid: state sem gestor_id lança erro
☑  LLM mockado em todos os testes
☑  Todos os testes passando no CI
Entregável: 4 testes de integração do grafo verdes no CI.


Semana 4 — MAGMA

#16 Estudo do paper MAGMA  ·  Segunda–Terça  ·  research
☐  Ler paper completo: arxiv.org/abs/2601.03236
☐  Clonar repositório: github.com/FredJiang0324/MAGMA
☐  Instalar dependências e rodar testes deles no LoCoMo dataset
☐  Entender os 4 grafos: semântico, temporal, causal, entidades
☐  Entender policy-guided traversal — componente RL
☐  Desenhar arquitetura da SUA implementação no caderno antes de codar
☐  Documentar diferenças entre implementação deles e a sua em docs/magma-notes.md
☐  Identificar onde o RL entra e qual reward function faz sentido para o FinAgent
Entregável: docs/magma-notes.md com arquitetura da sua versão desenhada e diferenças documentadas.

#17 Grafos MAGMA — estrutura base  ·  Quarta  ·  feature
☐  Criar grafos no Apache AGE via migration: magma_semantic, magma_temporal, magma_causal, magma_entity
☐  Criar app/memory/semantic.py — add_semantic_node(), query_semantic()
☐  Criar app/memory/temporal.py — add_temporal_edge(), query_temporal_history()
☐  Criar app/memory/causal.py — add_causal_relation(), query_causal_chain()
☐  Criar app/memory/entity.py — add_entity(), query_entity()
☐  Criar app/memory/magma.py — interface unificada para os 4 grafos
☐  Testar inserção e leitura em cada grafo
→ Ex: inserir 'Selic alta → impacta empresas alavancadas' no grafo causal e recuperar
Entregável: inserção e leitura funcionando nos 4 grafos via Apache AGE.

#18 Policy-guided traversal + integração EditorAgent  ·  Quinta–Sexta  ·  feature
☐  Implementar traversal básico por regras primeiro (sem RL)
→ Macro query → prioriza grafo causal e semântico
→ Company query → prioriza grafo entidades e temporal
→ Quant query → prioriza grafo temporal
☐  Implementar componente RL para otimizar traversal
→ Estado: tipo de query + contexto do estado do agente
→ Ação: qual grafo e profundidade de traversal
→ Reward: relevância dos resultados para a recomendação final
☐  Integrar ao EditorAgent: consultar MAGMA antes de gerar o morning note
☐  Implementar update_magma_after_note(): atualiza grafos após morning note gerado
☐  Implementar update_magma_from_feedback(): atualiza grafos com feedback do gestor
☐  Testar: EditorAgent com MAGMA inclui contexto histórico no morning note
Entregável: EditorAgent consulta MAGMA e inclui contexto histórico. Feedback atualiza os grafos.


Semana 5 — Pipeline Completo + Celery

#19 Celery Beat — scheduler diário  ·  Segunda–Terça  ·  feature
☐  Criar app/workers/pipeline.py com task run_daily_pipeline()
☐  Task processa todos os gestores ativos e suas empresas
☐  Implementar batch idempotente: verificar pipeline_run_id + status antes de processar
→ Se MorningNote já existe com status=completed para hoje → skip
☐  Configurar autoretry_for=(OperationalError,) com backoff exponencial
→ retry_backoff=True, max_retries=5
☐  Configurar CELERYD_CONCURRENCY baseado no rate limit da OpenAI
☐  Configurar Celery Beat: crontab(hour=9, minute=0) — 9 UTC = 6h BRT
☐  Testar: disparar pipeline manualmente para 2 gestores
☐  Testar: rodar pipeline duas vezes no mesmo dia — segundo run não duplica
Entregável: pipeline roda automaticamente. Idempotente: duas execuções no mesmo dia não duplicam.

#20 Escrita atômica — morning note + MAGMA  ·  Quarta  ·  feature
☐  Implementar transação atômica no EditorAgent
→ BEGIN → INSERT morning_notes → INSERT recommendations → UPDATE AGE → COMMIT
☐  Implementar SELECT FOR UPDATE no início do worker
→ Previne race condition: dois workers pegando mesmo morning_note_id
☐  Garantir ROLLBACK automático se qualquer escrita falhar
☐  Testar: simular falha no AGE → verificar que morning_note também não foi salvo
☐  Testar: dois workers simultâneos → apenas um processa
Entregável: falha no AGE faz rollback completo. Race condition impossível.

#21 SSE — atualizações em tempo real  ·  Quinta  ·  feature
☐  Implementar GET /morning-notes/{id}/stream → endpoint SSE
☐  Emitir evento agent_started quando agente começa
☐  Emitir evento agent_completed quando agente termina (com confidence score)
☐  Emitir evento note_ready quando EditorAgent termina (com morning_note_id)
☐  Emitir evento pipeline_failed com DataFlags se pipeline falhar
☐  Incluir pipeline_run_id e morning_note_id em cada evento
☐  Fechar conexão SSE após note_ready ou pipeline_failed
☐  Testar: curl -N /morning-notes/{id}/stream exibe eventos corretos
Entregável: SSE emite eventos em tempo real durante o pipeline.

#22 Testes de integração do pipeline  ·  Sexta  ·  test
☐  test_atomic_write_invariant: falha no AGE faz rollback do morning_note
☐  test_idempotent_pipeline: duas execuções no mesmo dia → apenas 1 morning_note
☐  test_sse_events_order: eventos chegam na ordem correta
☐  test_rls_isolation_invariant: gestor A não acessa morning note do gestor B → 403
☐  Todos os testes passando no CI
Entregável: 4 testes de integração do pipeline verdes no CI.


Semana 6 — Observabilidade + Testes Finais

#23 LangSmith — traces completos  ·  Segunda–Terça  ·  infra
☐  Verificar que LANGCHAIN_TRACING_V2=true está configurado
☐  Adicionar tags em todas as execuções: gestor_id, empresa, data, pipeline_run_id, morning_note_id
☐  Verificar no dashboard: 15 traces paralelos distinguíveis por tag
☐  Criar alerta no LangSmith: confidence_score médio < 0.70
☐  Criar alerta no LangSmith: taxa de DataFlags > 30%
☐  Verificar que agent_span_id aparece nos logs de cada agente
Entregável: toda execução aparece no LangSmith com tags corretas.

#24 CloudWatch — logs, métricas e alarmes  ·  Quarta  ·  infra
☐  Verificar logging estruturado com os 3 correlation IDs em todos os componentes
☐  Criar CloudWatch Log Groups: /finagent/api, /finagent/celery, /finagent/pipeline
☐  Criar métricas customizadas: pipeline_duration, agent_failures, queue_depth, token_cost_per_note
☐  Criar CloudWatch Dashboard com todas as métricas
☐  Criar alarme: pipeline_failure > 0 → SNS email
☐  Criar alarme: API error rate > 5% em 5min → SNS email
☐  Criar alarme: Celery queue > 50 tasks → SNS email
☐  Criar alarme: Redis memory > 80% → SNS email
☐  Criar alarme: confidence_score médio < 0.70 → SNS email
☐  Testar: disparar alarme manualmente e verificar email recebido
Entregável: dashboard com métricas em tempo real. Email recebido ao testar alarme.

#25 Evals — dataset e runner  ·  Quinta  ·  test
☐  Criar tests/evals/scenarios.json com 20 cenários de mercado brasileiro
→ Cenários: alta Selic, queda IBOV, earnings positivo, earnings negativo, mudança de CEO, crise cambial...
☐  Cada cenário tem: contexto de entrada + recomendação correta esperada (compra/venda/neutro)
☐  Criar tests/evals/eval_runner.py que roda pipeline em cada cenário
☐  Salvar pontuação no banco com timestamp e pipeline_version
☐  Criar baseline: rodar evals e salvar como baseline_v1
☐  Configurar GitHub Actions: rodar evals antes de deploy, bloquear se score cair > 5%
Entregável: evals rodando. Baseline salvo. Deploy bloqueado se qualidade cair.

#26 Revisão e testes dos 3 invariantes  ·  Sexta  ·  test
☐  test_freshness_invariant: mock B3 com dado de 48h → DataFlag no morning note
☐  test_rls_isolation_invariant: gestor A acessa note do gestor B → HTTP 403 + rejeição RLS
☐  test_fail_visible_invariant: mock Tavily com erro 500 → morning note com aviso explícito
☐  Verificar que os 3 testes bloqueiam merge no CI se falharem
☐  Atualizar progress tracker no CLAUDE.md
Entregável: 3 invariantes testados, verdes e bloqueando merge no CI.


Semana 7 — Deploy AWS

#27 AWS RDS + ElastiCache + ECS  ·  Segunda–Terça  ·  infra
☐  Provisionar RDS PostgreSQL 16 Multi-AZ
☐  Instalar extensões no RDS: pgvector e Apache AGE
☐  Provisionar ElastiCache Redis com AOF habilitado
☐  Criar ECS Cluster
☐  Criar Task Definition para FastAPI
☐  Criar Task Definition para Celery worker
☐  Criar Task Definition para Celery Beat
☐  Configurar variáveis de ambiente via AWS Secrets Manager
☐  Rodar alembic upgrade head no RDS e verificar RLS
☐  Build e push Docker image para ECR
☐  Deploy das tasks no ECS
☐  Verificar: POST /pipeline/trigger funciona via URL pública
Entregável: sistema rodando na AWS. Pipeline trigger funciona via URL pública.

#28 Onboarding dos 3 gestores  ·  Quarta–Quinta  ·  feature
☐  Criar endpoints de onboarding: POST /managers e POST /managers/{id}/companies
☐  Cadastrar os 3 gestores via API
☐  Cadastrar portfólios de cada gestor (5 empresas cada)
☐  Executar pipeline manualmente para os 3 gestores
☐  Verificar morning notes gerados no banco
☐  Implementar POST /morning-notes/{id}/feedback para coleta de feedback
☐  Coletar feedback dos gestores na primeira versão
☐  Documentar feedback para ajustar o sistema
Entregável: 3 gestores cadastrados. Primeiro morning note aprovado por ao menos 1 gestor.

#29 Smoke tests em produção  ·  Sexta  ·  review
☐  Executar fluxo completo em produção: trigger → SSE → morning note
☐  Verificar logs no CloudWatch com os 3 correlation IDs
☐  Verificar traces no LangSmith com tags corretas
☐  Testar RLS em produção: gestor A não acessa note do gestor B
☐  Verificar todos os alarmes CloudWatch configurados
☐  Verificar Celery Beat rodando e agendado para 6h
☐  Verificar pipeline roda automaticamente no próximo dia
Entregável: sistema em produção com observabilidade funcionando e gestores usando.


Semana 8 — Frontend + Benchmark MAGMA

#30 Frontend + Benchmark MAGMA + README final  ·  Semana 8  ·  feature
Frontend
☐  Criar app de frontend (HTML + JS vanilla ou React simples)
☐  Dashboard: lista de morning notes do dia com status e confidence score
☐  Tela de morning note: texto completo, recomendação, confidence scores por seção, DataFlags visíveis
☐  Pipeline em tempo real via SSE: mostrar agentes sendo executados
☐  Botão de feedback: gestor pode editar recomendação e comentar
☐  Feedback enviado para POST /morning-notes/{id}/feedback → atualiza MAGMA
☐  Deploy do frontend na AWS (S3 + CloudFront ou ECS)

Benchmark MAGMA
☐  Rodar evals com MAGMA ativado
☐  Rodar evals com pgvector simples como baseline (desativar MAGMA temporariamente)
☐  Calcular diferença de accuracy entre MAGMA e baseline
☐  Documentar resultado: 'MAGMA melhorou accuracy em X% vs baseline pgvector'
☐  Adicionar benchmark ao README

README e Demo Final
☐  Atualizar README com benchmark, arquitetura atualizada, link do demo
☐  Gravar demo de 2 minutos: trigger do pipeline → SSE em tempo real → morning note final
☐  Publicar demo no YouTube ou Loom e linkar no README
☐  Atualizar currículo com números reais: MRR, gestores, benchmark MAGMA
☐  Atualizar progress tracker no CLAUDE.md — marcar projeto como concluído
Entregável: frontend em produção. Benchmark documentado. Demo gravada. README final publicado.

Resumo — Checklist por Semana

☑  Semana 1 — Fundação: repositório, Docker, RLS, CI/CD (#01–06)
☑  Semana 2 — Agentes base: AgentState, MacroAgent, CompanyAgent, QuantAgent (#07–11)
☑  Semana 3 — RiskAgent, EditorAgent, Grafo completo (#12–15)
☐  Semana 4 — MAGMA: estudo, 4 grafos, policy-guided traversal (#16–18)
☐  Semana 5 — Celery Beat, transação atômica, SSE (#19–22)
☐  Semana 6 — LangSmith, CloudWatch, Evals, Invariantes (#23–26)
☐  Semana 7 — Deploy AWS, onboarding de gestores, smoke tests (#27–29)
☐  Semana 8 — Frontend, benchmark MAGMA, demo, README final (#30)

Regra de ouro: não avança de semana sem o entregável da semana anterior funcionando.