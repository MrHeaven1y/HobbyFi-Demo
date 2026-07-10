# HobbyFi Copilot Developer Guide

Personal learning documentation for understanding the project from first principles.

Audience: a developer who understands AI systems, model behavior, training/inference, and prompting, but wants a clear backend/product engineering explanation of how this repo works.

## 0. The Whole Project in One Sentence

HobbyFi Copilot is a FastAPI web application where a vendor asks natural-language CRM questions, an LLM decides which backend tool to call, backend code reads or drafts changes against PostgreSQL, and any write action is executed only after a human vendor approval.

The most important idea:

```text
The model reasons.
The backend enforces.
The database remembers.
The vendor approves writes.
```

## 1. First Principles

### What Problem Am I Solving?

HobbyFi has vendors. Vendors need answers about business data:

- Revenue today.
- Trial users for a hobby.
- Recent orders.
- Membership status.
- Free-trial extension.

In a normal dashboard, vendors click filters and buttons. In this project, the vendor types natural language:

```text
List trial users for Badminton.
```

The copilot translates that intent into safe backend operations.

### Why Not Let the LLM Query the Database Directly?

Because LLMs are probabilistic. They can misunderstand, hallucinate, or follow malicious instructions.

First principle:

```text
Never put a probabilistic system directly on a critical mutation path.
```

So the design gives the LLM only a tool interface. The model can request:

```text
call get_trial_users(game_name="Badminton")
```

But the actual database query is deterministic Python code.

### Why Human Approval for Writes?

Reads are reversible. Writes are not always reversible.

Read:

```text
Show revenue today.
```

If the answer is wrong, no business data changed.

Write:

```text
Extend this user's trial.
```

If this executes incorrectly, the database changes.

So every write is converted into a pending action:

```text
draft -> audit log -> vendor approval -> execute
```

This is human-in-the-loop control.

### Why PostgreSQL and pgvector?

PostgreSQL stores the normal business data:

- vendors
- users
- games
- memberships
- orders
- conversations
- audit logs

pgvector stores embeddings inside PostgreSQL. That means the same database can support both:

- relational CRM queries
- semantic document retrieval

No separate paid vector database is needed.

## 2. Mental Model of the Runtime

Think of the app as five layers.

```text
Layer 1: Browser UI
Layer 2: FastAPI endpoints
Layer 3: Services and workflows
Layer 4: Tools and database models
Layer 5: PostgreSQL + pgvector
```

Each layer has one job.

| Layer | Job | Example |
| --- | --- | --- |
| Browser UI | Collect user input and show answers | `chat.html` |
| FastAPI endpoints | Validate HTTP requests and call services | `chat.py`, `approval.py` |
| Services | Own business workflow | `copilot_service.py`, `memory.py` |
| Tools/models | Safely access data | `crm_tools.py`, `crm.py` |
| Database | Persist facts and audit trail | PostgreSQL tables |

## 3. End-to-End Read Workflow

Example:

```text
User: List trial users for Badminton.
```

Step by step:

1. Browser sends `POST /api/v1/chat`.
2. Browser includes `X-Vendor-ID: v_12345_abc`.
3. `VendorAuthMiddleware` validates that this vendor exists.
4. FastAPI builds a `ChatRequest`.
5. Dependency injection creates `CopilotService(db, vendor_id="v_12345_abc")`.
6. `CopilotService` loads conversation memory.
7. Gemini receives the system prompt, memory, user question, and tool schemas.
8. Gemini chooses `get_trial_users`.
9. Backend tool ignores any unsafe vendor id and uses authenticated vendor scope.
10. SQLAlchemy queries `users`, `memberships`, and `games`.
11. Tool returns structured data.
12. Gemini turns that result into a natural-language answer.
13. Conversation memory saves the turn.
14. API returns answer to browser.
15. Browser renders the answer.

Important principle:

```text
The LLM can choose a tool, but Python decides what data the tool can access.
```

## 4. End-to-End Write Workflow

Example:

```text
User: Update membership for user u_001 in game g_001 to active.
```

Step by step:

1. Browser sends `POST /api/v1/chat`.
2. Middleware validates `X-Vendor-ID`.
3. Copilot service passes vendor scope into tools.
4. Gemini chooses `update_membership`.
5. The write tool does not update the membership.
6. The tool returns:

```json
{
  "action": "update_membership",
  "requires_approval": true,
  "payload": {
    "action": "update_membership",
    "user_id": "u_001",
    "game_id": "g_001",
    "new_status": "active"
  }
}
```

7. Copilot service sees `requires_approval=true`.
8. Copilot service creates an `audit_logs` row with status `pending`.
9. API response includes `audit_log_id`.
10. Browser renders an approval card.
11. Vendor clicks Approve.
12. Browser sends `POST /api/v1/approvals/approve`.
13. Approval endpoint checks:
    - audit log exists
    - audit log belongs to this vendor
    - audit log is still pending
14. Executor joins `memberships` through `games`.
15. Executor checks `Game.vendor_id == authenticated vendor`.
16. Membership is updated.
17. Audit log becomes `executed`.

Important principle:

```text
The model drafts the mutation.
The vendor authorizes the mutation.
The backend executes the mutation.
```

## 5. Database First Principles

The database is the source of truth.

### Tables as Business Concepts

| Table | Meaning |
| --- | --- |
| `vendors` | Companies/partners using HobbyFi |
| `users` | End users/customers |
| `games` | Hobbies or activities a vendor offers |
| `memberships` | User participation in a game |
| `orders` | Payments/orders for a vendor |
| `audit_logs` | Pending/resolved write actions |
| `conversations` | Chat memory |
| `documents` | Uploaded documents |
| `document_chunks` | RAG chunks and embeddings |

### Relationships

```text
Vendor -> Games
Vendor -> Orders
Game -> Memberships
User -> Memberships
Vendor -> AuditLogs
Vendor -> Conversations
Document -> DocumentChunks
```

### Why Relationships Matter

The security model depends on relationships.

For example, a membership does not directly contain `vendor_id`.

```text
membership -> game -> vendor
```

So the approval executor joins `Membership` to `Game` before updating. That prevents vendor A from updating a membership attached to vendor B's game.

## 6. Project Tree Explained

This section explains every file that matters in the repository.

```text
HobbyFi/
  app/
  tests/
  README.md
  REPORT.md
  CHANGELOG.md
  docker-compose.yml
  Dockerfile
  requirements.txt
```

### Root Files

#### `README.md`

Purpose:

- Fast project overview.
- Quick start commands.
- Example queries.
- Architecture summary.
- Verification commands.

How to read it:

- Use this when you need to run the project or explain it quickly to a reviewer.

#### `REPORT.md`

Purpose:

- Assessment-facing technical report.
- Covers architecture, tools, memory, guardrails, orchestration, schema, cost, and verification.

How to read it:

- Use this when submitting or presenting the project.

#### `CHANGELOG.md`

Purpose:

- Professional audit trail.
- Explains what changed, why it changed, and how it was verified.

How to read it:

- Use this when someone asks "what exactly did you build or fix?"

#### `docs/DEVELOPER_GUIDE.md`

Purpose:

- This file.
- Teacher-style explanation from first principles to implementation details.

#### `requirements.txt`

Purpose:

- Python dependencies.

Important packages:

- `fastapi`: HTTP API framework.
- `uvicorn`: ASGI server that runs FastAPI.
- `sqlalchemy`: ORM and query builder.
- `psycopg2-binary`: Python PostgreSQL driver.
- `pgvector`: Python integration for pgvector columns.
- `langchain`: tool abstraction and LLM integration support.
- `langgraph`: graph/state-machine orchestration.
- `langchain-google-genai`: Gemini integration for LangChain.
- `sentence-transformers`: local embedding model.
- `structlog`: structured logging.
- `pydantic-settings`: environment configuration.

#### `docker-compose.yml`

Purpose:

- Runs PostgreSQL with pgvector and the FastAPI app.

Low-level behavior:

- `db` service uses `pgvector/pgvector:pg16`.
- Database port `5432` is exposed to your machine.
- `app` service builds from `Dockerfile`.
- App receives `DATABASE_URL` pointing to the Docker service name `db`.
- `depends_on` waits for database health check.

#### `Dockerfile`

Purpose:

- Defines how to build the FastAPI app container.

Typical flow:

- Start from Python image.
- Install dependencies.
- Copy source code.
- Run Uvicorn.

## 7. Application Package Explained

The `app` folder is the actual backend/frontend application.

### `app/__init__.py`

Purpose:

- Marks `app` as a Python package.

First principle:

- Python imports work by packages and modules. An `__init__.py` tells Python this directory can be imported.

### `app/main.py`

Purpose:

- Application entry point.
- Creates the FastAPI app.
- Registers middleware.
- Mounts routers.
- Initializes database tables.
- Seeds demo data.

Important concepts:

- `lifespan`: code that runs on startup and shutdown.
- `CREATE EXTENSION IF NOT EXISTS vector`: enables pgvector in Postgres.
- `Base.metadata.create_all`: creates SQLAlchemy tables.
- seed data: inserts demo vendors, users, games, memberships, and orders.
- `app.add_middleware`: adds CORS and vendor authentication.
- `app.include_router`: connects endpoint files to URL paths.

How to read this file:

1. Imports define app dependencies.
2. `setup_logging()` starts structured logging.
3. `lifespan()` prepares database state.
4. `app = FastAPI(...)` creates the server object.
5. Middleware is attached.
6. Static files are mounted.
7. API and page routers are mounted.

### `app/core/config.py`

Purpose:

- Loads environment variables into a typed settings object.

Important variables:

- `DATABASE_URL`
- `GEMINI_API_KEY`
- `LLM_MODEL_NAME`
- `APP_ENV`
- `DEBUG`

First principle:

- Config should not be hardcoded in application logic. It should come from environment variables so development, staging, and production can differ.

### `app/core/deps.py`

Purpose:

- Defines FastAPI dependency functions.

Important function:

```python
get_copilot_service(request, db)
```

What it does:

- Receives the current request.
- Receives a database session.
- Reads `request.state.vendor_id`.
- Creates `CopilotService`.

First principle:

- Dependency injection makes hidden context explicit. Endpoints do not manually construct database sessions or services.

### `app/core/logging.py`

Purpose:

- Configures structured logging.

Why it matters:

- AI workflows need traceability. Logs help explain what the app did and when.

### `app/database/base.py`

Purpose:

- Defines the shared SQLAlchemy declarative base.

First principle:

- Every ORM model class must inherit from the same base so SQLAlchemy can discover tables.

### `app/database/session.py`

Purpose:

- Creates the SQLAlchemy engine and session factory.

Important pieces:

- `engine`: connection manager for PostgreSQL.
- `SessionLocal`: creates per-request database sessions.
- `get_db`: FastAPI dependency that yields a session and closes it safely.

First principle:

- Database connections are scarce resources. Open them when needed, close them after use.

## 8. API Endpoint Files

Endpoints are the HTTP boundary of the system.

### `app/api/__init__.py`, `app/api/v1/__init__.py`, `app/api/v1/endpoints/__init__.py`

Purpose:

- Package marker files.

They usually contain no logic. They make imports clean and versioned.

### `app/api/v1/endpoints/health.py`

Purpose:

- Simple health endpoint.

Use:

```text
GET /api/v1/health
```

Why it matters:

- Health checks let Docker, load balancers, or humans confirm the app is alive.

### `app/api/v1/endpoints/pages.py`

Purpose:

- Serves Jinja2 HTML pages.

Routes:

- `/`: chat UI.
- `/dashboard`: dashboard placeholder.

First principle:

- The same FastAPI app can serve both JSON APIs and HTML pages.

### `app/api/v1/endpoints/chat.py`

Purpose:

- Main chat API.

Request model:

- `question`: user text, 1 to 2000 characters.
- `chat_history`: optional legacy history.
- `conversation_id`: optional persistent conversation id.

Response model:

- `answer`
- `sources`
- `requires_approval`
- `approval_payload`
- `audit_log_id`
- `conversation_id`

Low-level flow:

1. FastAPI validates JSON into `ChatRequest`.
2. Dependency injection gives `CopilotService`.
3. Endpoint calls `copilot.answer_query(...)`.
4. Result is returned as `ChatResponse`.

First principle:

- Endpoints should be thin. Business logic belongs in services.

### `app/api/v1/endpoints/approval.py`

Purpose:

- Human-in-the-loop approval API.

Routes:

- `POST /api/v1/approvals/approve`
- `POST /api/v1/approvals/reject`
- `GET /api/v1/approvals/pending`

Important functions:

- `_get_vendor_id`: reads authenticated vendor from request state.
- `_execute_action`: dispatches a stored audit payload to the correct executor.
- `_execute_update_membership`: mutates membership status after vendor check.
- `_execute_update_user_free_trial`: mutates free-trial expiry after vendor check.

Line-level concepts:

- Request models define required JSON.
- Response model defines what the API returns.
- Executor functions are internal helpers, not public endpoints.
- Endpoint functions enforce status transitions.

Status lifecycle:

```text
pending -> executed
pending -> rejected
```

Security detail:

```text
AuditLog.id AND AuditLog.vendor_id must match.
```

That prevents cross-vendor approval.

### `app/api/v1/endpoints/documents.py`

Purpose:

- Accepts document uploads for RAG ingestion.

Flow:

1. Browser/API uploads a file.
2. Endpoint validates file name.
3. Background task starts ingestion.
4. Service extracts text, chunks it, embeds it, stores it.

First principle:

- Long-running work should not block the HTTP response.

## 9. Middleware and Auth

### `app/middleware/vendor_auth.py`

Purpose:

- Simulated vendor authentication.

How it works:

1. Some paths are public: `/`, `/dashboard`, docs, health, static files.
2. Protected API paths require `X-Vendor-ID`.
3. Middleware checks the database for that vendor.
4. If valid, it sets:

```python
request.state.vendor_id = vendor_id
```

Why this matters:

- Later code can trust `request.state.vendor_id` as authenticated scope.

First principle:

- Authentication should happen before business logic.

Production note:

- Real systems should use JWT/OAuth/session auth instead of a raw header.

## 10. Models: Database Tables as Python Classes

Models define database tables.

### `app/models/crm.py`

Purpose:

- Core CRM schema.

Classes:

- `Vendor`
- `Order`
- `User`
- `Game`
- `Membership`

Important line patterns:

- `__tablename__`: actual SQL table name.
- `mapped_column`: SQL column.
- `primary_key=True`: unique row identity.
- `ForeignKey`: relationship to another table.
- `relationship`: Python-side navigation between models.
- `server_default=func.now()`: database fills timestamp.

How to think about it:

```text
Class = table
Object = row
Attribute = column
Relationship = join path
```

### `app/models/audit.py`

Purpose:

- Stores pending and resolved write actions.

Fields:

- `id`: unique audit action id.
- `vendor_id`: owner of the action.
- `action_type`: what executor should run.
- `action_payload`: JSON string with mutation arguments.
- `status`: pending, rejected, executed.
- `created_at`, `resolved_at`, `resolved_by`: audit metadata.

First principle:

- If a system changes business data, keep a durable record of why and by whom.

### `app/models/conversation.py`

Purpose:

- Stores chat memory.

Important field:

- `messages`: JSON list of `{role, content}` objects.

First principle:

- Chat history is application state and should be persisted if the user expects continuity.

### `app/models/document.py`

Purpose:

- Stores uploaded documents and vector chunks.

Classes:

- `Document`: file metadata.
- `DocumentChunk`: chunk text plus embedding vector.

Important field:

```python
embedding = mapped_column(Vector(384))
```

Meaning:

- Each chunk stores a 384-dimensional embedding from `all-MiniLM-L6-v2`.

## 11. Tools: Where LLM Intent Becomes Deterministic Code

### `app/tools/crm_tools.py`

Purpose:

- Defines the tools Gemini can call through LangChain.

First principle:

```text
Tools are the contract between probabilistic reasoning and deterministic execution.
```

Main structure:

1. Pydantic input schemas.
2. `get_crm_tools(db, authenticated_vendor_id)`.
3. Inner functions decorated with `@tool`.
4. Tool list returned to the agent.

Why inner functions?

- They capture `db` and `authenticated_vendor_id` through closure.
- LangChain can call them later without needing FastAPI dependency injection.

Read tools:

- `get_vendor_info`
- `get_trial_users`
- `get_todays_revenue`
- `list_vendor_orders`

Write tools:

- `update_membership`
- `update_user_free_trial`

Important safety pattern:

```python
def scoped_vendor_id(requested_vendor_id=None):
    return authenticated_vendor_id or requested_vendor_id
```

Meaning:

- If the request has an authenticated vendor, it wins.
- The model cannot override vendor scope.

Write tool pattern:

```python
return {
    "action": "...",
    "requires_approval": True,
    "payload": {...}
}
```

Meaning:

- This is not execution.
- This is a draft.

## 12. Services: Business Workflow

### `app/services/copilot_service.py`

Purpose:

- The brain of the backend workflow.

Key responsibilities:

- Create Gemini client.
- Bind CRM tools.
- Build LangGraph state machine.
- Load memory.
- Run agent.
- Execute tools.
- Create audit logs for write requests.
- Save memory.
- Return API-ready response.

Important classes:

#### `AgentState`

This defines what travels through the graph:

- `messages`: conversation messages.
- `requires_approval`: whether any tool requested approval.
- `approval_payload`: write action data.
- `audit_log_id`: created audit id.

#### `CopilotService.__init__`

Creates:

- database reference
- vendor id
- Gemini model
- CRM tools
- tool-bound LLM
- compiled graph

#### `_build_graph`

Builds this state machine:

```text
agent -> tools -> agent -> END
```

The condition:

- If the LLM emitted tool calls, go to tools.
- If not, stop.

#### `_run_agent`

Calls Gemini with current messages.

Output:

- an AI message, possibly with tool calls.

#### `_run_tools`

Loops over each model-requested tool call.

If read tool:

- run it
- send result back to model

If write tool:

- create audit log
- send approval-required message back to model

#### `_create_audit_log`

Inserts a pending row into `audit_logs`.

Important:

- It calls `db.flush()` so SQLAlchemy asks the database for the generated id before final commit.

#### `answer_query`

Public method used by the chat endpoint.

Flow:

1. Build memory object.
2. Build message list.
3. Add system prompt.
4. Add memory or legacy chat history.
5. Add current user question.
6. Run graph.
7. Extract final assistant answer.
8. Save memory.
9. Return structured response.

### `app/services/memory.py`

Purpose:

- Manages conversation memory.

Important constant:

```python
DEFAULT_WINDOW_SIZE = 10
```

Meaning:

- Keep last 10 exchanges.
- Since each exchange has user plus assistant, max stored messages is 20.

Important methods:

- `_get_or_create_conversation`
- `load`
- `save`
- `clear`

First principle:

- Keep enough context for useful follow-up, but not unlimited context.

### `app/services/ingestion_service.py`

Purpose:

- Processes uploaded documents for RAG.

Typical responsibilities:

- Read uploaded file.
- Extract text.
- Split text into chunks.
- Generate embeddings.
- Save document and chunks.

First principle:

- RAG is a pipeline: document -> text -> chunks -> embeddings -> vector search.

## 13. LLM and Prompt Files

### `app/llm/prompts.py`

Purpose:

- Central place for system prompts.

Prompts:

- `AGENT_SYSTEM_PROMPT`: CRM agent behavior and guardrails.
- `RAG_SYSTEM_PROMPT`: document QA behavior.
- `format_rag_prompt`: inserts retrieved context into a prompt.

First principle:

- Prompts define desired model behavior, but they do not replace backend enforcement.

### `app/llm/provider.py`

Purpose:

- Base abstraction for LLM providers.

Why abstractions exist:

- You can swap Gemini for another provider without rewriting business logic.

### `app/llm/gemini.py`

Purpose:

- Gemini-specific provider implementation.

How to think about it:

- `provider.py` says "what an LLM provider should do."
- `gemini.py` says "how Gemini does it."

## 14. Retrieval and RAG

### `app/retrieval/embedder.py`

Purpose:

- Creates vector embeddings for text.

First principle:

- An embedding is a numeric representation of text meaning.

Example:

```text
"trial membership" -> [0.12, -0.04, ..., 0.09]
```

### `app/retrieval/service.py`

Purpose:

- Searches document chunks by vector similarity.

First principle:

- RAG first retrieves relevant chunks, then asks the model to answer only from those chunks.

### `app/repositories/document_repository.py`

Purpose:

- Data-access helper for documents and chunks.

Why repositories exist:

- Services should not need to know every query detail.
- Repositories keep persistence logic organized.

## 15. Frontend Templates

### `app/templates/base.html`

Purpose:

- Shared HTML shell.

Contains:

- HTML head.
- Tailwind config.
- HTMX, Alpine.js, Marked.js script imports.
- Shared CSS.
- Block placeholders for page content.

First principle:

- Templates reuse common page structure so each page only defines its unique body.

### `app/templates/chat.html`

Purpose:

- Main interactive demo UI.

Important parts:

- Sidebar.
- Welcome screen.
- Suggested prompts.
- Chat messages.
- Approval card.
- JavaScript `chatApp()` state.

Important frontend state:

- `vendorId`: demo authenticated vendor.
- `conversationId`: backend conversation memory id.
- `messages`: local visible chat messages.
- `isLoading`: request in progress.

Important frontend actions:

- `sendMessage()`: calls `/api/v1/chat`.
- `handleApproval()`: calls approve/reject endpoints.
- `newChat()`: clears messages and conversation id.

Low-level request detail:

Every protected API call includes:

```javascript
'X-Vendor-ID': this.vendorId
```

That is why middleware can authenticate the request.

### `app/templates/dashboard.html`

Purpose:

- Placeholder dashboard page.

Why it exists:

- Shows how the app could expand beyond chat.

## 16. Auth and RBAC

### `app/auth/rbac.py`

Purpose:

- Intended place for role-based access control helpers.

First principle:

- Authentication answers "who are you?"
- Authorization answers "what are you allowed to do?"

Current implementation mainly uses vendor scoping in middleware, tools, and approval endpoints. A production system would expand RBAC here.

## 17. Utilities

### `app/utils/text.py`

Purpose:

- Text helper functions.

Why utilities exist:

- Shared small operations should not be duplicated across services.

## 18. Tests

### `tests/__init__.py`

Purpose:

- Marks tests as a package.

### `tests/test_workflow.py`

Purpose:

- Tests critical safety behavior.

Test 1:

```text
CRM tools enforce authenticated vendor scope.
```

Meaning:

- Even if a tool call asks for `v_67890_xyz`, the tool uses `v_12345_abc` when that is the authenticated request vendor.

Test 2:

```text
Approval execution is vendor scoped.
```

Meaning:

- A vendor cannot execute a write action against another vendor's game membership.

Why these tests matter:

- They test the hard safety boundary without needing Gemini or Docker.

### `tests/llm.py`

Purpose:

- Scratch/manual Gemini test file.

Note:

- It is not a proper pytest test because the filename does not start with `test_`.
- It also appears to contain experimental code and should not be treated as a production test.

## 19. Line-Level Reading Guide for Key Files

This section explains how to mentally parse important files line by line without pasting every source line into this document.

### Reading `app/main.py`

Read it in this order:

1. Module docstring: tells you this is the app entry point.
2. Imports: external libraries first, internal app modules second.
3. Model imports: force SQLAlchemy to register tables.
4. Logging setup: prepares structured logs.
5. Path setup: computes template/static directories.
6. `lifespan`: startup/shutdown lifecycle.
7. Database extension/table creation.
8. Seed data creation.
9. `FastAPI(...)`: constructs app object.
10. Middleware registration.
11. Static mount.
12. Router registration.

If you understand these twelve parts, you understand the file.

### Reading `app/tools/crm_tools.py`

Read it in this order:

1. Input schema classes: define what tool arguments are valid.
2. `get_crm_tools`: factory function.
3. `scoped_vendor_id`: security rule.
4. Read tools: deterministic SQLAlchemy queries.
5. Write tools: approval payloads, no mutation.
6. Return list: exposes tools to LangChain/Gemini.

The most important line-level idea:

```text
Read tools query.
Write tools draft.
```

### Reading `app/services/copilot_service.py`

Read it in this order:

1. `AgentState`: graph state shape.
2. `__init__`: dependencies and graph construction.
3. `_build_graph`: graph topology.
4. `_run_agent`: model call.
5. `_run_tools`: tool execution and approval detection.
6. `_create_audit_log`: durable pending write.
7. `answer_query`: public orchestration method.

The most important line-level idea:

```text
The graph loops until the model stops asking for tools.
```

### Reading `app/api/v1/endpoints/approval.py`

Read it in this order:

1. Request/response Pydantic models.
2. `_execute_action`: dispatch by action type.
3. Concrete executor functions.
4. `_get_vendor_id`: request scope.
5. `approve_action`: validate pending action, execute, mark executed.
6. `reject_action`: validate pending action, mark rejected.
7. `list_pending_approvals`: show pending actions for current vendor.

The most important line-level idea:

```text
Approval is scoped by audit id plus vendor id.
```

### Reading `app/templates/chat.html`

Read it in this order:

1. HTML layout: sidebar, header, chat container, input area.
2. Message rendering templates.
3. Approval card template.
4. `chatApp()` JavaScript state.
5. `sendMessage()`: chat API request.
6. `handleApproval()`: approval API request.
7. UI helpers: markdown, scroll, resize, new chat.

The most important line-level idea:

```text
The frontend is not trusted for security.
It only sends the vendor header and displays backend decisions.
```

## 20. How FastAPI Works Here

FastAPI is built around type annotations.

Example:

```python
async def chat_with_copilot(
    request: ChatRequest,
    copilot: CopilotService = Depends(get_copilot_service),
):
```

Meaning:

- Parse incoming JSON into `ChatRequest`.
- Run `get_copilot_service`.
- Pass both into the function.

If validation fails, FastAPI returns a 422 response automatically.

## 21. How SQLAlchemy Works Here

SQLAlchemy converts Python model operations into SQL.

Example:

```python
db.query(Vendor).filter(Vendor.id == effective_vendor_id).first()
```

Means:

```sql
SELECT * FROM vendors WHERE id = ... LIMIT 1;
```

But SQLAlchemy parameterizes values, which protects against SQL injection.

## 22. How LangGraph Works Here

LangGraph treats the agent as a state machine.

The state contains messages and approval metadata.

Nodes:

- `agent`: call Gemini.
- `tools`: run selected tools.

Edges:

- `agent -> tools` when tool calls exist.
- `agent -> END` when no tool calls exist.
- `tools -> agent` after tool results are produced.

This makes the workflow explainable:

```text
reason -> act -> reason -> answer
```

## 23. How the LLM Sees Tools

The LLM does not see your Python source code. It sees tool names, descriptions, and argument schemas.

Example:

```text
Tool: get_trial_users
Arguments:
  game_name: string
  vendor_id: optional string
```

Gemini decides:

```json
{
  "name": "get_trial_users",
  "args": {
    "game_name": "Badminton"
  }
}
```

Then LangChain invokes the Python function.

## 24. What Happens When Something Goes Wrong?

### Missing Vendor Header

Protected API request without `X-Vendor-ID`:

```text
401 Unauthorized
```

### Invalid Vendor

Header contains vendor id not in database:

```text
401 Unauthorized
```

### Approval Already Resolved

Trying to approve/reject an executed or rejected audit log:

```text
409 Conflict
```

### Membership Not Found

Approval payload references membership outside vendor scope:

```text
400 Bad Request
```

### LLM Tool Needs Write

Tool returns pending approval instead of mutation.

## 25. Local Running Model

Native flow:

```powershell
cd C:\Users\Heavenly\Desktop\HobbyFi
.\.env_hfi\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Database options:

- Use Docker for PostgreSQL/pgvector: `docker compose up -d db`.
- Or use local PostgreSQL with pgvector installed.

Required `.env`:

```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/hobbyfi
GEMINI_API_KEY=your_key
LLM_MODEL_NAME=gemini-2.5-flash
```

## 26. How to Explain This in an Interview

Short version:

```text
I built a tool-calling AI copilot for a vendor CRM. The LLM can answer read queries through typed backend tools, but write actions are intercepted into a pending audit workflow. The backend enforces vendor scope from middleware through tools and approval execution. PostgreSQL stores CRM data, chat memory, audit logs, and pgvector embeddings for future RAG. The design is free to run locally with Docker and has tests for tenant isolation.
```

If asked why this stands out:

- It is not just a chatbot.
- It has real workflow orchestration.
- It has human-in-the-loop write control.
- It has auditability.
- It has vendor isolation.
- It has a real database model.
- It uses pgvector without paid infrastructure.

## 27. What You Should Study Next

Study in this order:

1. FastAPI dependency injection.
2. SQLAlchemy model relationships.
3. Middleware request lifecycle.
4. LangChain tool calling.
5. LangGraph state machines.
6. Human-in-the-loop workflows.
7. pgvector similarity search.
8. Alembic migrations.
9. JWT/OAuth authentication.
10. End-to-end browser testing.

## 28. Quick Glossary

| Term | Meaning |
| --- | --- |
| ASGI | Python server interface for async web apps. |
| Uvicorn | Server that runs FastAPI. |
| Endpoint | Function that handles an HTTP route. |
| Middleware | Code that runs before/after endpoints. |
| Dependency | Object FastAPI prepares for an endpoint. |
| ORM | Maps Python classes to database tables. |
| Session | Unit of database work. |
| Tool calling | LLM requests a named function with arguments. |
| LangGraph | State-machine orchestration for LLM workflows. |
| Audit log | Durable record of a proposed or executed action. |
| RAG | Retrieval-augmented generation. |
| Embedding | Numeric vector representing text meaning. |
| pgvector | PostgreSQL extension for vector storage/search. |

## 29. Final Mental Model

If you remember only one diagram, remember this:

```text
User question
  -> FastAPI validates request
  -> Middleware authenticates vendor
  -> CopilotService builds agent state
  -> Gemini chooses a tool
  -> Python tool enforces vendor scope
  -> Read result returns directly
  -> Write result becomes pending audit log
  -> Vendor approves
  -> Backend executes safely
  -> Database stores everything important
```

That is the whole system.
