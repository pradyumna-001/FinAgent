# FinAgent Deployment Guide

## Local Development

### Prerequisites
- Python 3.11+
- `uv` (Astral package manager) — `pip install uv`
- Docker + Docker Compose
- Git

### Quick Start

```bash
# Clone and enter
git clone https://github.com/pradyumna-001/FinAgent.git
cd FinAgent

# Install dependencies
uv sync --group dev

# Start infrastructure (PostgreSQL + Redis)
docker-compose up -d

# Wait for health checks
docker-compose ps
# All services should show "healthy"

# Run migrations
export MIGRATION_DATABASE_URL="postgresql+psycopg://finagent:finagent_secure_pass@localhost:5432/finagent"
uv run alembic upgrade heads

# Start API server
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
export REDIS_URL="redis://localhost:6379/0"
export TAVILY_API_KEY="tvly-..."
export NVIDIA_API_KEY="nvapi-..."
export LANGCHAIN_API_KEY="lsv2_..."
uv run uvicorn app.main:app --reload --port 8000
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | App runtime DB (finagent_app role) |
| `MIGRATION_DATABASE_URL` | Yes | Migration DB (superuser) |
| `REDIS_URL` | Yes | Redis for Celery + SSE |
| `TAVILY_API_KEY` | Yes | Web search API |
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM API |
| `NVIDIA_BASE_URL` | No | Default: `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | No | Default: `openai/gpt-oss-20b` |
| `NVIDIA_FALLBACK_MODEL` | No | Default: `openai/gpt-oss-20b` |
| `NVIDIA_NEMOTRON_MODEL` | No | Default: `nvidia/nemotron-3-ultra` |
| `LANGCHAIN_API_KEY` | No | LangSmith tracing |
| `LANGCHAIN_TRACING_V2` | No | Set `true` to enable |
| `SECRET_KEY` | Yes | FastAPI secret |

Create `.env` from `.env.example`:
```bash
cp .env.example .env
# Edit .env with your keys
```

### Running Tests

```bash
# Unit tests only (no DB)
uv run pytest tests/unit/ -v

# Integration tests (requires Docker PostgreSQL)
docker-compose up -d postgres_vector redis
export MIGRATION_DATABASE_URL="postgresql+psycopg://finagent:finagent_secure_pass@localhost:5432/finagent"
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
uv run alembic upgrade heads
uv run pytest tests/integration/ -v

# All tests
uv run pytest -v
```

### Manual Pipeline Run

```bash
# Via API
curl -X POST http://localhost:8000/pipeline/trigger \
  -H "Content-Type: application/json" \
  -H "manager-id: 1" \
  -d '{"company_ticker": "PETR4"}'

# Returns: {"pipeline_run_id": "...", "morning_note_id": "..."}

# Watch via SSE
curl -N http://localhost:8000/morning-notes/{note_id}/stream

# Or via script (uses InMemorySaver)
uv run python scripts/run_pipeline.py
```

---

## Production Deployment (AWS)

### Infrastructure (Terraform/CDK — to be created)

```hcl
# Required resources:
# - RDS PostgreSQL 18 Multi-AZ (with age + vector extensions)
# - ElastiCache Redis 7.2 (AOF enabled, cluster mode disabled)
# - ECS Cluster (Fargate)
# - ALB for FastAPI
# - Secrets Manager (all API keys + DB URLs)
# - CloudWatch Log Groups + Dashboards + Alarms
# - S3 + CloudFront for frontend (Phase 5)
```

### Database Setup (RDS)

```bash
# Connect to RDS primary
psql -h <rds-endpoint> -U postgres -d finagent

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
SET search_path = ag_catalog, "$user", public;

-- Create app role (run once)
CREATE ROLE finagent_app WITH NOSUPERUSER NOBYPASSRLS LOGIN PASSWORD '<from-secrets-manager>';
GRANT USAGE ON SCHEMA public TO finagent_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO finagent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finagent_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO finagent_app;

-- Run migrations from CI/CD pipeline
# alembic upgrade heads (uses MIGRATION_DATABASE_URL)
```

### ECS Task Definitions

#### FastAPI (`finagent-api`)
```json
{
  "family": "finagent-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::...:role/ecs-task-execution",
  "taskRoleArn": "arn:aws:iam::...:role/finagent-api-task",
  "containerDefinitions": [{
    "name": "api",
    "image": "<account>.dkr.ecr.<region>.amazonaws.com/finagent:latest",
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/DATABASE_URL"},
      {"name": "REDIS_URL", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/REDIS_URL"},
      {"name": "TAVILY_API_KEY", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/TAVILY_API_KEY"},
      {"name": "NVIDIA_API_KEY", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/NVIDIA_API_KEY"},
      {"name": "LANGCHAIN_API_KEY", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/LANGCHAIN_API_KEY"},
      {"name": "LANGCHAIN_TRACING_V2", "value": "true"},
      {"name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:...:secret:finagent/SECRET_KEY"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/finagent/api",
        "awslogs-region": "<region>",
        "awslogs-stream-prefix": "api"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
      "interval": 30,
      "timeout": 5,
      "retries": 3,
      "startPeriod": 10
    }
  }]
}
```

#### Celery Worker (`finagent-worker`)
```json
{
  "family": "finagent-worker",
  "containerDefinitions": [{
    "name": "worker",
    "image": "<account>.dkr.ecr.<region>.amazonaws.com/finagent:latest",
    "command": ["celery", "-A", "app.workers.pipeline", "worker", "--loglevel=info", "--concurrency=4"],
    "environment": [...same as API...],
    "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-group": "/finagent/celery", ...}}
  }]
}
```

#### Celery Beat (`finagent-beat`)
```json
{
  "family": "finagent-beat",
  "containerDefinitions": [{
    "name": "beat",
    "image": "<account>.dkr.ecr.<region>.amazonaws.com/finagent:latest",
    "command": ["celery", "-A", "app.workers.pipeline", "beat", "--loglevel=info", "--scheduler=celery.beat.PersistentScheduler"],
    "environment": [...same as API...],
    "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-group": "/finagent/celery", ...}}
  }]
}
```

### Docker Image Build

```bash
# Build multi-platform
docker buildx build --platform linux/amd64 -t <account>.dkr.ecr.<region>.amazonaws.com/finagent:latest --push .

# Or use GitHub Actions (recommended)
```

### GitHub Actions Deploy (to be added)

```yaml
# .github/workflows/deploy.yml
name: deploy
on:
  push:
    branches: [main]
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
      - uses: aws-actions/amazon-ecr-login@v2
      - run: docker buildx build --push -t ${{ secrets.ECR_REGISTRY }}/finagent:${{ github.sha }} .
      - run: aws ecs update-service --cluster finagent --service finagent-api --force-new-deployment
```

### Health Checks

```bash
# API
curl https://api.finagent.com/health
# {"status": "ok", "db": "ok"}

# Database
psql $DATABASE_URL -c "SELECT 1"

# Redis
redis-cli -u $REDIS_URL ping

# Celery
celery -A app.workers.pipeline inspect ping
```

### Monitoring

- **LangSmith**: https://smith.langchain.com — traces with tags
- **CloudWatch**: Logs at `/finagent/api`, `/finagent/celery`, `/finagent/pipeline`
- **Dashboards**: Pipeline duration, agent failures, queue depth, token cost
- **Alarms**: SNS → email for pipeline_failure, API error rate, queue depth, Redis memory, confidence score

---

## Rollback Procedure

```bash
# Docker image rollback
aws ecs update-service --cluster finagent --service finagent-api --task-definition finagent-api:<previous-revision>

# Database rollback (if migration issue)
alembic downgrade -1  # or specific revision
```

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| API 503 | `docker-compose logs postgres_vector` — DB unreachable |
| Pipeline stuck | `celery -A app.workers.pipeline inspect active` |
| RLS errors | Verify `manager-id` header; check `finagent_app` grants |
| HNSW slow | Run `scripts/reindex_hnsw.py --list`; check drift |
| SSE not working | Check Redis pub/sub; verify `REDIS_URL` |
| LangSmith missing | Verify `LANGCHAIN_TRACING_V2=true` and API key |