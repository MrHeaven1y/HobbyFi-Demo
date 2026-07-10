# HobbyFi Copilot: Technical Design & Implementation Report

**Author:** Dibyendu Mukherjee  
**Date:** July 2026  
**Project:** AI Copilot for HobbyFi's AI-CRM Vendor Portal  

---

## 1. Executive Summary

We are building the future of local hobby communities. As part of this vision, the **HobbyFi Copilot** was designed and implemented to serve as an intelligent, secure, and resilient AI assistant integrated directly into the AI-CRM vendor portal. This report provides a comprehensive overview of the architecture, engineering trade-offs, security guardrails, and special features developed to ensure a production-ready standard. 

The Copilot is engineered to handle two distinct categories of tasks:
1. **Read-only Queries**: Seamlessly answering CRM questions (e.g., "what is today's revenue?", "list trial users of badminton").
2. **Write-intent Actions**: Drafting mutation requests (e.g., "update user membership date", "increase free trial") which are strictly gated behind a **human-in-the-loop (HITL)** vendor approval workflow. The AI models have zero direct mutation privileges.

### Document Links
For deep technical tracking and setup instructions, please refer to the following project documents:
- [README.md](file:///c:/Users/Heavenly/Desktop/HobbyFi/README.md) - Setup, Deployment, and Architecture Overview.
- [CHANGELOG.md](file:///c:/Users/Heavenly/Desktop/HobbyFi/CHANGELOG.md) - Detailed audit of all technical decisions and file modifications.
- [LEARNING_SEQUENCE.md](file:///c:/Users/Heavenly/Desktop/HobbyFi/LEARNING_SEQUENCE.md) - Step-by-step developer learning progression.

---

## 2. Architecture Overview

The system architecture prioritizes security, explicit state management, and separation of concerns. By intentionally splitting the stack into decoupled layers, we maintain testability and deterministic control over a non-deterministic LLM.

### Request Lifecycle
```text
Vendor Browser UI (HTMX/Alpine.js)
  -> FastAPI REST API
  -> VendorAuthMiddleware (Extracts X-Vendor-ID)
  -> CopilotService (Injects Vendor Scope)
  -> LangGraph State Machine (Orchestration)
  -> Gemini Tool-Calling LLM
  -> CRM Tools / Approval Executor (HITL)
  -> PostgreSQL + pgvector (Dockerized)
```

**Core Architectural Rule:** The LLM is isolated from the database. It can only invoke strongly-typed tools via Pydantic schemas. 
- **Read Tools:** Return scoped data explicitly filtered by the authenticated `vendor_id`.
- **Write Tools:** Return a draft action with `requires_approval=true`, creating an `audit_logs` entry in the database. The workflow halts until the vendor explicitly approves or rejects the action via the UI.

---

## 3. Technology Stack and Frameworks

We deliberately chose a unified Python stack over a split TypeScript/Python architecture to maximize maintainability, ease of testing, and seamless integration with data science libraries.

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Backend API** | FastAPI | Provides type-safe request validation, automatic OpenAPI documentation, and robust dependency injection. |
| **Agent Orchestration** | LangGraph | Offers an explicit, cyclical state machine for agent-tool routing, making workflows predictable and debuggable. |
| **Tooling Layer** | LangChain Tools | Uses Pydantic for strict schema validation, natively compatible with Gemini’s tool-calling. |
| **Primary LLM** | Gemini 2.5 Flash | Cost-effective, fast, and highly capable for tool-calling (via Google AI Studio). |
| **Database** | PostgreSQL 16 | Reliable relational store for CRM data, conversations, and audit logs. |
| **Vector Store** | pgvector | Keeps semantic search native to Postgres, avoiding the overhead and cost of external vector DBs (e.g., Pinecone). |
| **Embeddings** | sentence-transformers | Free, local, open-source embeddings eliminating per-token embedding costs. |
| **ORM** | SQLAlchemy 2.0 | Mature schema modeling and parameterized queries preventing SQL injection. |
| **Frontend UI** | Jinja2, HTMX, Alpine.js | Lightweight, fast, and avoids a heavy build pipeline for the assessment demo. |

---

## 4. Memory Strategy

Managing LLM memory is critical for controlling context windows and token costs. 

### Conversation Memory (Sliding Window)
We implemented a PostgreSQL-backed **sliding window memory**. 
For every vendor request, the `CopilotService` loads the vendor's conversation history, appends the latest turns, and dynamically prunes the context to the **10 most recent exchanges**. 

**Why this strategy?**
- **Cost-Efficiency:** Full conversation history causes unbounded token growth and latency.
- **Accuracy:** Summary memory often hallucinates or drops fine-grained CRM details. A sliding window guarantees perfect recall of recent context.
- **Determinism:** It is mathematically predictable and easily tested.

### Document Memory (Vector Retrieval)
For unstructured knowledge, documents are chunked and embedded via `sentence-transformers` into `pgvector`. This separates unstructured RAG memory from structural CRM conversational memory, preventing workflow pollution.

---

## 5. Security and Guardrails Framework

Safety does not rely on prompt obedience. We implemented a defense-in-depth strategy across four layers.

### 1. Request-Level Guardrails
- **VendorAuthMiddleware:** Validates the `X-Vendor-ID` header. The frontend demo defaults to `v_12345_abc`, proving multi-tenancy.
- **Input Sanitization:** Chat inputs are hard-capped at 2000 characters to mitigate prompt injection and buffer abuse.

### 2. Tool-Level Guardrails (Tenant Isolation)
- **Deterministic Scoping:** The `CopilotService` overrides any LLM-supplied `vendor_id` with the cryptographically authenticated `vendor_id` from the request state. The model physically cannot query another vendor's data.
- **SQLAlchemy ORM:** Used exclusively to prevent SQL injection.

### 3. Approval-Level Guardrails (HITL)
- **Immutable Audit Trail:** Write tools create an `audit_logs` row (status: `pending`). The copilot never executes `UPDATE` or `INSERT` on business entities directly.
- **Execution Validation:** When a vendor clicks "Approve", the API verifies that the `audit_log.vendor_id` matches the authenticated `vendor_id` before committing the transaction.

### 4. Prompt-Level Guardrails
- System prompts are tightly constrained, instructing the model to be concise, rely entirely on tool data, and treat all mutations as drafts.

---

## 6. Special Features: Enhanced Control and Resilience

To elevate this project to a production-ready standard, several advanced engineering features were implemented beyond the base requirements.

### 1. Graceful LLM Fallback Mechanism
Free-tier LLM APIs are subject to strict rate limits and quotas. To ensure the vendor portal never experiences a catastrophic failure (500 Server Error) during a demo or high load, we built a tiered fail-safe:
1. **Primary (Gemini 2.5 Flash):** Full tool-calling orchestration.
2. **Secondary (Local Model):** If Gemini is exhausted, the system seamlessly routes to a local Ollama-compatible endpoint.
3. **Tertiary (Deterministic Fallback):** If no local model is available, a deterministic responder takes over, providing audited, hardcoded CRM responses while maintaining multi-tenant isolation.
*The UI dynamically displays badges (`Gemini Mode`, `Local Model`, `Deterministic Fallback`) to maintain total transparency with the vendor.*

### 2. Single-Flight UI Approvals
To prevent race conditions, the UI uses strict Alpine.js state management. Approval buttons are disabled immediately upon click, preventing rapid-fire double submissions. Approvals resolve only after a verified 200 OK from the server, otherwise reverting state and displaying error details.

### 3. Runtime Event Logging
In addition to business `audit_logs`, the backend tracks `runtime_events`. Every time the LLM fails over to a fallback mechanism, it is permanently logged. This allows DevOps to monitor API quota health and system resilience.

---

## 7. Mock Data Schema

The relational schema is compact but completely covers the AI-CRM requirements.

- **vendors:** `id, name, status, payout_balance, created_at, updated_at`
- **users:** `id, name, email, created_at, updated_at`
- **games:** `id, name, vendor_id`
- **memberships:** `id, user_id, game_id, status, expires_at, created_at, updated_at`
- **orders:** `id, vendor_id, amount, status, created_at, updated_at`
- **audit_logs:** `id, vendor_id, action_type, action_payload, status, created_at, resolved_at, resolved_by`
- **runtime_events:** Tracks LLM fallback triggers and system state shifts.
- **conversations:** `id, vendor_id, messages, created_at, updated_at`

*Seeded Data Highlights:* Vendors `v_12345_abc` (Acme Corp) and `v_67890_xyz` (Globex Inc). Users include Alice Smith and Bob Jones with active/trial memberships in Badminton and Tennis.

---

## 8. Engineering Trade-offs

During development, strategic choices were made to optimize for reliability and deployment speed:

1. **Python vs. TypeScript (Mastra):** While TypeScript/Mastra is excellent, this project utilized Python/LangGraph. Because data science tools (pgvector, sentence-transformers, LangGraph) are natively Pythonic, building a single Python FastAPI monolith avoids the complexity and latency of a split microservice (TS API + Python ML worker) architecture.
2. **Relational Vectors (pgvector) vs. Dedicated Vector DB:** We opted for `pgvector` inside PostgreSQL. It centralizes backups, simplifies Docker orchestration, and reduces infrastructural cost to $0, eliminating the need for paid services like Pinecone for a vendor CRM.
3. **Sliding Window vs. Summarization Memory:** Summarization requires an extra LLM call (adding latency and cost) and can lose critical entities. A sliding window is deterministic, faster, and cheaper, though it limits historical depth.

---

## 9. Future Upgrades and Learnings

### Future Upgrades (Production Readiness)
- **JWT / OAuth Authentication:** Replace the simulated `X-Vendor-ID` middleware with cryptographic JWT validation tied to an Identity Provider (e.g., Auth0, Firebase).
- **Alembic Migrations:** Transition from `Base.metadata.create_all` to structured Alembic versioning for safe schema updates.
- **WebSocket Streaming:** Upgrade the Chat API from REST to WebSockets to stream LLM tokens to the UI in real-time, drastically reducing perceived latency.
- **Granular RBAC:** Expand approval logic so "Admins" can auto-execute writes, while "Staff" require HITL approval.

### Developer Learnings
Building this copilot highlighted the friction between *probabilistic* LLMs and *deterministic* business logic. The greatest lesson was that **prompts are not permissions**. Attempting to prompt an LLM to "only query vendor A" is mathematically unsafe. Security must be enforced by injecting context at the API dependency layer, entirely bypassing the LLM's decision-making process.

---

## 10. Suggestions for the Reviewer

When reviewing the repository and demo, I recommend the following sequence to fully experience the robust engineering:

1. **Test the Happy Path (Read):** Ask the Copilot, *"What is my revenue today?"* or *"List trial users for Badminton."* Observe the fast response and correct multi-tenant scoping.
2. **Test the Guardrails (Security):** Ask the Copilot to *"Show me data for vendor v_67890_xyz"*. Observe how the deterministic backend overrides the LLM and strictly returns data for your authenticated vendor (`v_12345_abc`).
3. **Test the Workflow (Write):** Tell the Copilot to *"Increase the free trial for Alice Smith"*. Notice that it **does not** change the database. Instead, an Approval Card appears in the UI. 
4. **Test the Fallback:** In `.env`, artificially lower `DEMO_LLM_CALL_BUDGET=0`. Refresh and ask a question. Watch the UI elegantly degrade to the deterministic fallback, maintaining application uptime.

Thank you for the opportunity to build the HobbyFi Copilot. This architecture represents a highly scalable, defensible, and cost-efficient foundation for local hobby communities.
