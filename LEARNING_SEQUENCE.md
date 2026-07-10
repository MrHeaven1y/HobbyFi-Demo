# HobbyFi Copilot — Learning Sequence (Data Flow)

If you are a beginner looking to understand how the HobbyFi Copilot application works, this guide will take you step-by-step through the data flow. By following this sequence, you'll see how a user's request travels from the frontend all the way to the AI and database, and back again.

---

### Phase 1: The Request Starts (Frontend)
When the user types a message in the browser, start here:
1. **`app/templates/chat.html`**: Look at the HTMX form where the user submits their message. Notice how it sends a POST request to the `/api/v1/chat` endpoint.
2. **`app/templates/base.html`**: This shows the overall structure of the page, including Tailwind and HTMX imports.

### Phase 2: Hitting the API (Routing)
The HTTP request arrives at the FastAPI backend:
3. **`app/api/v1/endpoints/pages.py`**: This is how the frontend HTML pages are served.
4. **`app/api/v1/endpoints/chat.py`**: Look at the `chat_with_copilot` endpoint. This receives the chat request and passes it to the Copilot Service. Notice how it uses `Depends()` to inject the service.

### Phase 3: Business Logic (The AI Agent)
This is the brain of the application. The Copilot Service orchestrates the LLM:
5. **`app/services/copilot_service.py`**: This is where the LangGraph agent is defined. Follow the `answer_query` method. You'll see how it loads conversation memory, sets up the tools, and asks the Gemini model for a response.
6. **`app/llm/prompts.py`**: Look at the `AGENT_SYSTEM_PROMPT`. This gives the AI its persona and its strict rules (guardrails) on what it can and cannot do.

### Phase 4: Tools & Actions (Agent connecting to Database)
If the AI decides it needs data, it calls a tool:
7. **`app/tools/crm_tools.py`**: Study how the LangChain tools are defined (e.g., `get_vendor_info`, `update_membership`). Notice how read tools directly query the database, while write tools return a `requires_approval=True` payload.
8. **`app/models/crm.py`**: This is the data structure. It shows what tables exist (User, Game, Membership, Order) and how they relate.

### Phase 5: The Approval Workflow (Safety)
If the AI tried to modify data, it gets intercepted:
9. **`app/models/audit.py`**: Look at how we store pending actions as Audit Logs.
10. **`app/api/v1/endpoints/approval.py`**: Here you see the endpoints that the vendor uses to actually `approve` or `reject` the pending actions that the AI drafted.

### Phase 6: Memory & State
How does the AI remember the conversation?
11. **`app/services/memory.py`**: (If created) This shows the sliding window strategy, keeping the last N messages to save tokens.
12. **`app/models/conversation.py`**: How the chat history is stored in the PostgreSQL database.

### Phase 7: Foundation (Under the Hood)
Once you understand the flow, you can look at the engine making it possible:
13. **`app/main.py`**: The entry point. It wires together the routers, middleware, and database startup.
14. **`app/database/session.py`**: How the application connects to PostgreSQL.
15. **`app/core/config.py`**: How environment variables (like API keys and DB URLs) are loaded securely.

---
**Summary of the Flow:**
`chat.html` -> `chat.py` -> `copilot_service.py` -> `crm_tools.py` -> `PostgreSQL` -> Back to `copilot_service.py` -> `chat.py` -> `chat.html`
