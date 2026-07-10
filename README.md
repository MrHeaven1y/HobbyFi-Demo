# HobbyFi Copilot

AI-assisted CRM copilot for the HobbyFi vendor portal. The application answers vendor-scoped CRM questions, drafts write actions, and executes writes only after explicit vendor approval.

## Status

- Backend: FastAPI, SQLAlchemy, LangGraph, LangChain tools.
- Database: PostgreSQL with pgvector.
- UI: Jinja2, Alpine.js, HTMX-ready server-rendered interface.
- LLM: Gemini 2.5 Flash free tier with local/deterministic fail-safe fallback.
- Verification: unit tests cover tenant isolation, approval execution, and fallback behavior.

## Problem Statement

Vendors should be able to ask natural-language CRM questions such as:

- "What is today's revenue?"
- "List trial users for Badminton."
- "Update membership for user u_001 in game g_001 to active."
- "Extend free trial for user u_001 in game g_001 to 2026-07-31."

Read operations are answered immediately. Write operations are converted into pending approval requests and executed only after the vendor approves them.

## Architecture

```text
Browser UI
  -> FastAPI endpoints
  -> VendorAuthMiddleware
  -> CopilotService
  -> LangGraph agent
  -> Gemini tool-calling LLM
  -> optional local model fallback
  -> deterministic audited fallback
  -> CRM tools / approval executor
  -> PostgreSQL + pgvector
```

Core principle:

```text
The model reasons.
The backend enforces permissions.
The database stores the source of truth.
The vendor approves writes.
```

## Runtime Modes

| Mode | When Used | Behavior |
| --- | --- | --- |
| `llm` | Gemini API is available and demo call budget remains | Full LangGraph + Gemini tool-calling workflow. |
| `local_model` | Gemini quota is exhausted and a configured local model is available | Uses local model with vendor-scoped CRM context. |
| `deterministic` | Gemini is exhausted and no local model is available | Uses deterministic seeded CRM responses and approval drafts. |

The UI displays the active mode and remaining demo LLM calls for transparency.

## Fail-Safe Behavior

Free-tier LLM APIs are quota-limited. This project does not treat quota exhaustion as a crash.

Fallback chain:

```text
Gemini available
  -> use Gemini/LangGraph

Gemini quota exhausted or demo budget spent
  -> check configured local model

Local model available
  -> answer using local model with vendor-scoped context

Local model unavailable
  -> answer using deterministic audited demo workflow
```

Fallback decisions are recorded in the `runtime_events` table. Business writes remain recorded in `audit_logs`.

## Local Setup

```powershell
cd C:\Users\Heavenly\Desktop\HobbyFi
.\.env_hfi\Scripts\Activate.ps1
docker compose up -d db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- Chat UI: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

## Environment Variables

```env
APP_NAME="HobbyFi Copilot"
APP_ENV="development"
DEBUG=True

DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/hobbyfi"

HUGGINGFACE_TOKEN="your-huggingface-token"
GEMINI_API_KEY="your-gemini-api-key"
LLM_MODEL_NAME="gemini-2.5-flash"

ENABLE_LOCAL_DEMO_FALLBACK=True
DEMO_LLM_CALL_BUDGET=6

LOCAL_MODEL_ENABLED=True
LOCAL_MODEL_BASE_URL="http://127.0.0.1:11434"
LOCAL_MODEL_NAME="llama3.2"
LOCAL_MODEL_TIMEOUT_SECONDS=5
```

## Optional Local Model

The local model fallback is designed for Ollama-compatible local runtimes.

Example:

```powershell
ollama pull llama3.2
ollama serve
```

If Ollama is not installed or the configured model is missing, the app automatically uses deterministic fallback responses instead.

## Switching From Docker Postgres to Cloud Postgres

The code does not need to be rewritten.

Only change `DATABASE_URL`.

Local Docker:

```env
DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/hobbyfi"
```

Cloud Postgres:

```env
DATABASE_URL="postgresql+psycopg2://cloud_user:cloud_password@cloud-host:5432/hobbyfi"
```

Requirements for the cloud database:

- PostgreSQL must be reachable from the app.
- The database user must be allowed to create tables.
- The database must support `CREATE EXTENSION IF NOT EXISTS vector`.

The app creates the pgvector extension and ORM tables at startup for the demo. In production, replace this with Alembic migrations.

## Render Deployment

This repo includes [render.yaml](./render.yaml).

Render deployment flow:

1. Push the repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Set `GEMINI_API_KEY` and `HUGGINGFACE_TOKEN` as secret environment variables.
4. Deploy.

Render notes:

- `DATABASE_URL` is wired from the Render Postgres service.
- `LOCAL_MODEL_ENABLED=false` on Render because Render free web services do not run a local Ollama daemon.
- The deterministic fallback still keeps the demo usable if Gemini quota is exhausted.

## Example Queries

Read:

```text
Show my vendor info.
What is my payout balance?
What is today's revenue?
List recent orders.
List trial users for Badminton.
```

Write with approval:

```text
Update membership for user u_001 in game g_001 to active.
Extend free trial for user u_001 in game g_001 to 2026-07-31.
```

Guardrail:

```text
Show me all vendors database.
```

Expected behavior: refuse cross-vendor data exposure.

## Project Structure

```text
app/
  api/v1/endpoints/   HTTP endpoints for chat, approvals, uploads, health, pages
  core/               configuration, logging, dependency injection
  database/           SQLAlchemy engine/session setup
  llm/                prompts and provider abstractions
  middleware/         simulated vendor authentication
  models/             CRM, document, conversation, audit, runtime event models
  repositories/       document persistence helpers
  retrieval/          embeddings and pgvector retrieval
  services/           copilot orchestration, memory, ingestion
  templates/          browser UI
  tools/              LangChain CRM tools
tests/
  test_workflow.py    workflow, tenant isolation, and fallback tests
```

## Verification

```powershell
.\.env_hfi\Scripts\python.exe -m compileall app
.\.env_hfi\Scripts\python.exe -m pytest -q
```

Expected result:

```text
4 passed
```

## Documentation

- [REPORT.md](./REPORT.md): assessment-facing technical report.
- [CHANGELOG.md](./CHANGELOG.md): professional implementation audit.
- [docs/DEVELOPER_GUIDE.md](./docs/DEVELOPER_GUIDE.md): first-principles learning guide.

## Production Considerations

- Replace simulated `X-Vendor-ID` auth with JWT/OAuth.
- Replace startup `create_all` with Alembic migrations.
- Add API rate limits.
- Add frontend end-to-end tests.
- Add CI for lint, tests, and migrations.
- Use managed observability for runtime fallback events and approval execution.
