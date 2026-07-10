# HobbyFi Copilot Technical Design Report

Author: Dibyendu Mukherjee  
Date: July 2026  
Scope: AI copilot for HobbyFi's AI-CRM vendor portal

## 1. Architecture Overview

HobbyFi Copilot is designed as a tool-augmented AI assistant inside the vendor portal. It supports two classes of work:

1. Read-only CRM questions, such as "what is today's revenue?" and "list trial users for Badminton".
2. Write-intent actions, such as "update this user's membership date" or "increase the free trial", which are never executed directly by the model. They are converted into pending approval records and only executed after the authenticated vendor approves them.

The system is intentionally split into small layers so each responsibility is explicit and testable.

```text
Vendor Browser UI
  -> FastAPI REST API
  -> VendorAuthMiddleware
  -> CopilotService
  -> LangGraph agent loop
  -> Gemini tool-calling LLM
  -> CRM tools / approval executor
  -> PostgreSQL + pgvector in Docker
```

The most important architectural decision is that the LLM is not allowed to directly query or mutate the database. It can only call typed tools. Read tools return scoped data. Write tools return a draft action with `requires_approval=true`. The backend then creates an `audit_logs` row and pauses the workflow until the vendor approves or rejects the action.

This creates a defensible first-principles design:

- Data access must be scoped to the authenticated vendor.
- The model should reason, but deterministic code should enforce permissions.
- Any mutation should be auditable, replayable, and reversible at the workflow level.
- The demo should run locally with free infrastructure.

## 2. Tools and Frameworks Chosen

| Layer | Technology | Reason |
| --- | --- | --- |
| Backend API | FastAPI | Type-safe request validation, dependency injection, automatic OpenAPI docs, strong Python ecosystem. |
| Agent orchestration | LangGraph | Explicit state machine for agent -> tools -> approval routing. Easier to explain than an opaque agent loop. |
| Tooling layer | LangChain tools | Pydantic schemas for tool inputs and native compatibility with Gemini tool calling. |
| LLM | Gemini 2.5 Flash via Google AI Studio | Free-tier primary model for live tool-calling. |
| Fallback | Local model + deterministic responder | Keeps the demo usable when free-tier Gemini quota is exhausted. |
| Database | PostgreSQL 16 | Reliable relational store for CRM data, conversations, audit logs, and documents. |
| Vector store | pgvector | Keeps semantic search inside Postgres and avoids a paid external vector database. |
| Embeddings | sentence-transformers | Free local embeddings, no per-token embedding cost. |
| ORM | SQLAlchemy 2.0 | Mature schema modeling, relationship mapping, and parameterized queries. |
| UI | Jinja2, HTMX/Alpine.js, Tailwind CDN | No paid frontend service or build pipeline required; fast assessment-friendly demo. |
| Containerization | Docker Compose | One-command local stack for FastAPI plus PostgreSQL/pgvector. |
| Logging | structlog | Structured logs for auditability and production-style observability. |

Mastra is a good TypeScript-native option, and HobbyFi mentioned it as an example. This implementation uses Python because the existing project is FastAPI/SQLAlchemy-based and because pgvector, LangGraph, sentence-transformers, and backend testing fit naturally in one Python service. The choice avoids a split TypeScript/Python architecture for an assessment demo.

## 3. Memory Strategy

The memory strategy uses PostgreSQL-backed conversation persistence with a sliding window.

```text
conversations
  id
  vendor_id
  messages JSON
  created_at
  updated_at
```

For each request, the copilot loads the current conversation for the authenticated vendor, appends the latest user and assistant turn, then keeps only the most recent 10 exchanges. This keeps the model context relevant while preventing unbounded token growth.

Why this memory strategy:

- Full conversation history becomes expensive and noisy.
- Summary memory requires another LLM call and can lose details.
- Vector memory is useful for long-term semantic recall but is overkill for a vendor CRM chat thread.
- A sliding window is simple, deterministic, free, and easy to test.

The implementation also keeps document memory separate from conversation memory. Documents are ingested into `documents` and `document_chunks`, and each chunk stores a pgvector embedding. That supports future RAG questions without mixing uploaded knowledge with the CRM action workflow.

## 4. Guardrails Framework

The guardrails are layered so safety does not depend on prompt obedience alone.

### Request-Level Guardrails

- `VendorAuthMiddleware` validates the `X-Vendor-ID` header for API requests.
- Public pages and health/docs routes can render without auth, but protected API calls require a valid seeded vendor.
- Chat input is limited to 2000 characters to reduce prompt-injection and accidental abuse risk.

### Tool-Level Guardrails

- CRM tools use Pydantic input schemas.
- Read tools enforce authenticated vendor scope server-side. If the model supplies another vendor id, the backend ignores it and uses the authenticated vendor.
- Write tools do not mutate database rows. They return an approval payload.
- SQLAlchemy ORM queries are used instead of string-built SQL.

### Approval-Level Guardrails

- Approvals are stored in `audit_logs` with action type, JSON payload, vendor id, status, timestamps, and resolver.
- Approval and rejection endpoints look up audit logs by both `audit_log_id` and authenticated `vendor_id`.
- The executor joins memberships through games and requires `Game.vendor_id` to match the audit log vendor before mutating a membership.

### Prompt-Level Guardrails

The system prompt tells the model to:

- Use tools for data.
- Avoid fabricating values.
- Keep responses concise and actionable.
- Treat all writes as approval-required.
- Never attempt cross-vendor access.

Prompt guardrails improve model behavior, but deterministic middleware, tools, and approval executors are the real enforcement boundary.

## 5. Workflow Orchestration

The core workflow is a LangGraph state machine:

```text
START
  -> Agent node
      -> no tool call: return answer
      -> tool call: execute tool node
          -> read tool: return result to agent
          -> write tool: create pending audit log, return approval-required message
  -> END
```

Read workflow:

1. Vendor asks a question.
2. FastAPI validates the request and vendor header.
3. CopilotService loads recent conversation memory.
4. Gemini decides which read tool to call.
5. The tool queries only authenticated vendor data.
6. The final answer is saved into conversation memory and returned.

Write workflow:

1. Vendor asks for a mutation.
2. Gemini calls a write tool such as `update_membership`.
3. The write tool returns a draft payload with `requires_approval=true`.
4. CopilotService creates an `audit_logs` row with status `pending`.
5. The UI renders an approval card with Approve and Reject actions.
6. Approve executes the stored action and marks the audit log `executed`.
7. Reject marks the audit log `rejected` and makes no data change.

This satisfies the assessment requirement: write access exists, but execution happens only after vendor approval.

## 6. Mock Data Schema

The mock schema is intentionally small but covers the required CRM behavior.

```text
vendors
  id, name, status, payout_balance, created_at, updated_at

users
  id, name, email, created_at, updated_at

games
  id, name, vendor_id

memberships
  id, user_id, game_id, status, expires_at, created_at, updated_at

orders
  id, vendor_id, amount, status, created_at, updated_at

audit_logs
  id, vendor_id, action_type, action_payload, status,
  created_at, resolved_at, resolved_by

conversations
  id, vendor_id, messages, created_at, updated_at

documents / document_chunks
  uploaded document metadata and pgvector-backed text embeddings
```

Seeded demo records:

| Entity | Seed |
| --- | --- |
| Vendor | `v_12345_abc` Acme Corp, `v_67890_xyz` Globex Inc |
| Users | Alice Smith, Bob Jones |
| Games | Badminton, Tennis |
| Memberships | Alice trial for Badminton, Bob active for Badminton |
| Orders | Completed and pending orders for Acme Corp |

The seeded vendor in the UI is `v_12345_abc`, which allows the reviewer to run the chat and approval flow immediately after Docker startup.

## 7. Deployment and Cost

The local deployment is Docker Compose:

```text
db:  pgvector/pgvector:pg16
app: FastAPI application container
```

The database service runs PostgreSQL with pgvector preinstalled. No Pinecone, Weaviate, hosted Postgres, or paid queue is required. Gemini uses Google AI Studio's free tier, and sentence-transformers runs embeddings locally.

Free LLM tiers are quota-limited, so the implementation includes a fail-safe chain:

```text
Gemini available -> LangGraph/Gemini tool-calling
Gemini exhausted -> optional local Ollama-compatible model
No local model -> deterministic audited demo responder
```

The UI shows the active response mode (`llm`, `local_model`, or `deterministic`) and the backend records fallback decisions in `runtime_events`.

Estimated monthly cost for the assessment demo: `$0`.

## 8. Verification

Current implemented checks:

```bash
.\.env_hfi\Scripts\python.exe -m compileall app
.\.env_hfi\Scripts\python.exe -m pytest -q
```

Result:

```text
4 passed
```

The tests validate the most critical guarantees:

- CRM tools enforce authenticated vendor scope even when a different vendor id is supplied.
- Approval execution cannot mutate another vendor's membership.
- Provider-specific LLM content blocks are normalized before API response validation.
- Fallback behavior refuses cross-vendor database exposure.
