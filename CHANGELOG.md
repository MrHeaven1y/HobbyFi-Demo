# HobbyFi Copilot Implementation Audit

Date: July 9, 2026  
Purpose: document every meaningful file change, created file, decision, and verification step for the HobbyFi Copilot assessment.

## Executive Summary

The repo already contained a FastAPI/LangGraph/PostgreSQL/pgvector skeleton. The remaining work was to make the workflow complete and defensible:

- Mount the demo UI.
- Preserve vendor authentication for APIs while allowing the page to load.
- Pass authenticated vendor scope into the copilot service.
- Enforce tenant isolation inside tools and approval execution.
- Return enough metadata for the frontend approval card to approve or reject a real audit log.
- Fix the frontend approval URLs and request payloads.
- Add tests for tenant isolation and human-in-the-loop mutation safety.
- Replace corrupted documentation with clean professional submission docs.

## Files Changed

### `app/main.py`

Action:

- Imported and mounted `pages.router`.

Reason:

- The Jinja2 chat UI existed but was never registered with the FastAPI app. Without this, `GET /` could not serve the demo.

### `app/middleware/vendor_auth.py`

Action:

- Added `/`, `/dashboard`, and `/static/*` as public paths.
- Kept API routes protected by `X-Vendor-ID`.

Reason:

- Browsers cannot attach `X-Vendor-ID` before loading the initial HTML page. The page must be public, while API calls remain vendor-authenticated.

### `app/core/deps.py`

Action:

- Injected `Request` into `get_copilot_service`.
- Passed `request.state.vendor_id` into `CopilotService`.

Reason:

- Vendor scope must come from middleware, not from model-generated tool arguments.

### `app/tools/crm_tools.py`

Action:

- Added `authenticated_vendor_id` to `get_crm_tools`.
- Made vendor id inputs optional for read tools.
- Added a scope helper that prefers authenticated vendor id over model-supplied vendor id.
- Added `action` into write payloads so the UI can display the pending operation clearly.

Reason:

- The LLM should not be trusted to choose vendor scope. Deterministic backend code must enforce multi-tenant isolation.

### `app/services/copilot_service.py`

Action:

- Passed authenticated vendor id into the CRM tool factory.

Reason:

- Completes the secure path from middleware -> dependency injection -> service -> tool execution.

### `app/api/v1/endpoints/chat.py`

Action:

- Added request validation with `min_length=1` and `max_length=2000`.
- Added `conversation_id` to request and response models.
- Added `audit_log_id` to response model.
- Passed `conversation_id` into the copilot service.

Reason:

- The frontend needs `audit_log_id` to approve a real pending action.
- Conversation memory needs a stable id across turns.
- Input length guardrail now matches the report.

### `app/api/v1/endpoints/approval.py`

Action:

- Added authenticated request scope to approve, reject, and pending-list endpoints.
- Looked up audit logs by both `audit_log_id` and `vendor_id`.
- Joined `Membership` through `Game` during execution and required `Game.vendor_id` to match the audit vendor.
- Kept reject as a status-only operation with no mutation.

Reason:

- Prevents a vendor from approving, rejecting, or executing another vendor's pending action.
- Makes the approval workflow safe enough to explain professionally.

### `app/templates/chat.html`

Action:

- Added demo vendor id `v_12345_abc`.
- Sent `X-Vendor-ID` in chat and approval requests.
- Stored `conversationId`.
- Attached returned `audit_log_id` to assistant messages and approval payloads.
- Corrected approval endpoints to `/api/v1/approvals/approve` and `/api/v1/approvals/reject`.
- Reset `conversationId` on new chat.

Reason:

- The UI can now drive the actual backend workflow instead of calling missing endpoints with placeholder ids.

### `tests/test_workflow.py`

Action:

- Created focused workflow tests.

Coverage:

- Tool-level authenticated vendor scope overrides model-supplied vendor ids.
- Approval execution refuses cross-vendor mutation and successfully executes valid same-vendor mutation.

Reason:

- These tests prove the most important security and workflow guarantees without needing a live LLM or Docker database.

### `README.md`

Action:

- Replaced corrupted text with clean setup, architecture, workflow, and verification documentation.

Reason:

- The project now reads as a professional assessment submission.

### `REPORT.md`

Action:

- Replaced corrupted report with a clean 3-4 page technical design report.

Reason:

- Matches the assessment prompt: architecture overview, tools/frameworks, memory strategy, guardrails, orchestration, and mock schema.

### `CHANGELOG.md`

Action:

- Created this audit document.

Reason:

- The user requested a professional audit of every change, file created, decision, and action.

## Engineering Decisions

### Decision 1: Keep Python/FastAPI Instead of Introducing Mastra

First principle:

- A good assessment submission should maximize reliability and clarity, not add a second runtime for name recognition.

Decision:

- Keep the existing FastAPI/SQLAlchemy/LangGraph architecture.

Rationale:

- The repo was already Python-based.
- PostgreSQL, pgvector, SQLAlchemy, sentence-transformers, and LangGraph fit cleanly in one service.
- This avoids a TypeScript orchestration service plus Python data service split.

### Decision 2: Vendor Scope Belongs in Code, Not Prompting

First principle:

- Trust boundaries must be deterministic.

Decision:

- Middleware validates the vendor. Tools and approvals enforce that vendor. The model cannot override it.

Rationale:

- Prompt instructions are useful, but not a security boundary.

### Decision 3: Write Tools Draft, Approval Executor Mutates

First principle:

- The LLM should not directly mutate business records.

Decision:

- Write tools return approval payloads. Approval endpoints execute the mutation only after vendor approval.

Rationale:

- This exactly satisfies "write access but only executed on vendor approval".
- It creates a durable audit trail.

### Decision 4: Sliding-Window Conversation Memory

First principle:

- Memory should preserve useful recent context without unbounded cost.

Decision:

- Store conversation messages in PostgreSQL and keep the last 10 exchanges.

Rationale:

- Free, simple, deterministic, and enough for the CRM assistant workflow.

### Decision 5: PostgreSQL + pgvector in Docker

First principle:

- The demo should be free, reproducible, and easy to run.

Decision:

- Use `pgvector/pgvector:pg16` via Docker Compose.

Rationale:

- Avoids paid vector databases and keeps relational data plus embeddings in one local stack.

## Verification Log

Commands run:

```bash
python -m compileall app
.\.env_hfi\Scripts\python.exe -m pytest -q
.\.env_hfi\Scripts\python.exe -c "import app.main; print(app.main.app.title)"
```

Results:

- Compile check passed.
- App import passed and printed `HobbyFi Copilot`.
- Test result at that checkpoint: `2 passed, 1 warning`.

Note:

- The host system Python did not have FastAPI or pytest installed. Verification was completed using the repo-local `.env_hfi` virtual environment.

## Remaining Production Considerations

These are not blockers for the assessment demo, but they are the next professional steps:

- Replace simulated `X-Vendor-ID` auth with JWT/OAuth tied to real vendor users.
- Add database migrations with Alembic instead of `Base.metadata.create_all`.
- Add rate limiting for chat endpoints.
- Add end-to-end browser tests for the approval card.
- Add richer approval payload display using human-readable user and game names.
- Add CI that runs compile and pytest checks automatically.

## July 10, 2026 Fail-Safe and Deployment Update

### Files Changed

#### `app/core/config.py`

Added explicit demo and fallback configuration:

- `ENABLE_LOCAL_DEMO_FALLBACK`
- `DEMO_LLM_CALL_BUDGET`
- `LOCAL_MODEL_ENABLED`
- `LOCAL_MODEL_BASE_URL`
- `LOCAL_MODEL_NAME`
- `LOCAL_MODEL_TIMEOUT_SECONDS`

Reason:

- Free-tier Gemini calls are quota-limited. The app should degrade gracefully instead of failing as a generic 500 error.

#### `app/models/runtime.py`

Created `RuntimeEvent`.

Reason:

- Business mutations are audited in `audit_logs`; runtime fallback decisions need their own operational audit trail.

#### `app/main.py`

Imported the runtime model so startup table creation includes `runtime_events`.

Reason:

- Keeps the demo database self-initializing.

#### `app/services/copilot_service.py`

Added a fail-safe chain:

1. Gemini/LangGraph primary workflow.
2. Optional local Ollama-compatible model if Gemini quota is exhausted.
3. Deterministic audited demo responder if no local model is available.

Also added:

- response mode metadata
- remaining demo LLM call count
- local-model availability probe
- vendor-scoped local model context
- runtime fallback audit events

Reason:

- The reviewer should see an intentional resilience design, not a broken API when free-tier quota runs out.

#### `app/api/v1/endpoints/chat.py`

Extended chat response schema with:

- `mode`
- `warning`
- `remaining_llm_calls`

Reason:

- The UI needs transparent fallback metadata.

#### `app/templates/chat.html`

Added mode and warning badges.

Reason:

- The chat interface now clearly shows `Gemini mode`, `Local model mode`, or `Deterministic fallback`.

Follow-up hardening:

- Added staged loading notices while the app waits on Gemini, including a warning that the organization API may be exhausted and fallback will start automatically.
- Added single-flight approval handling so Approve/Reject buttons disable during the request and repeated clicks cannot spam the server.
- Approval cards now resolve only after a successful server response; failed approvals keep the card actionable and show the server error detail.

#### `.env.example`

Documented fallback-related environment variables.

Reason:

- The project can be configured consistently across local, cloud, and Render deployments.

#### `render.yaml`

Created Render blueprint for deploying the FastAPI app and Postgres database.

Reason:

- Render deployment should be reproducible and environment-driven.

#### `README.md`

Rewritten into a professional engineering README covering:

- architecture
- runtime modes
- local setup
- cloud Postgres migration
- Render deployment
- verification
- production considerations

Reason:

- The repository should read like a maintainable software project, not a generated demo.

### Cloud Postgres Decision

Changing from Docker Postgres to cloud Postgres does not require rewriting the code. The application already reads the database connection from `DATABASE_URL`.

Required change:

```env
DATABASE_URL="postgresql+psycopg2://cloud_user:cloud_password@cloud-host:5432/hobbyfi"
```

Requirements:

- Cloud database must be reachable.
- Database user must be able to create tables for the demo.
- Database must support pgvector.

Production recommendation:

- Replace startup `Base.metadata.create_all` with Alembic migrations before a real production launch.
