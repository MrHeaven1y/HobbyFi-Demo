"""
Copilot orchestration service using LangGraph.

Builds a stateful agent graph that:
1. Receives user queries with system-level guardrails.
2. Invokes LLM (Gemini) with bound CRM tools.
3. Executes tool calls, detecting write operations that need approval.
4. Creates AuditLog entries for write ops and returns audit_log_id.
5. Loads/saves conversation memory via the ConversationMemory service.
"""

import json
import re
from urllib import error as url_error
from urllib import request as url_request
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any, TypedDict, Annotated
import operator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.core.config import settings
from app.core.logging import get_logger
from app.tools.crm_tools import get_crm_tools
from app.models.audit import AuditLog
from app.models.runtime import RuntimeEvent
from app.services.memory import ConversationMemory
from app.llm.prompts import AGENT_SYSTEM_PROMPT

logger = get_logger("app.services.copilot")

_remaining_demo_llm_calls = settings.DEMO_LLM_CALL_BUDGET


class AgentState(TypedDict):
    """State schema threaded through every node of the LangGraph agent."""
    messages: Annotated[list, operator.add]
    requires_approval: bool
    approval_payload: Optional[Dict[str, Any]]
    audit_log_id: Optional[str]


class CopilotService:
    """
    Orchestrates the LangGraph agent for the HobbyFi Copilot.

    Responsibilities:
        - Build the LangGraph workflow (agent → tools → agent loop).
        - Detect write operations and create AuditLog entries.
        - Manage per-vendor conversation memory.
    """

    def __init__(self, db: Session, vendor_id: Optional[str] = None):
        self.db = db
        self.vendor_id = vendor_id

        # Instantiate the LangChain-wrapped Gemini LLM
        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            max_retries=0,
        )
        self.tools = get_crm_tools(db, authenticated_vendor_id=vendor_id)
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        self.graph = self._build_graph_for_llm(self.llm_with_tools)

    # ──────────────────────── Graph construction ──────────────────────────────

    def _build_graph_for_llm(self, bound_llm):
        """Build and compile the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        def run_agent(state: AgentState):
            messages = state["messages"]
            response = bound_llm.invoke(messages)
            return {"messages": [response]}

        workflow.add_node("agent", run_agent)
        workflow.add_node("tools", self._run_tools)

        workflow.set_entry_point("agent")

        def should_continue(state: AgentState):
            """Route to tools if the LLM emitted tool calls, else terminate."""
            messages = state["messages"]
            last_message = messages[-1]
            if not last_message.tool_calls:
                return END
            return "tools"

        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    def _run_tools(self, state: AgentState):
        """
        Tool execution node.

        For each tool call from the LLM:
        - Execute the tool.
        - If the tool returns ``requires_approval=True``, create an AuditLog
          entry and inform the agent that vendor approval is needed.
        """
        messages = state["messages"]
        last_message = messages[-1]

        tool_responses = []
        requires_approval = False
        approval_payload = None
        audit_log_id = None

        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            # Look up the tool instance by name
            tool_instance = next(
                (t for t in self.tools if t.name == tool_name), None
            )

            if tool_instance:
                result = tool_instance.invoke(tool_args)

                # Detect write operations that need human approval
                if isinstance(result, dict) and result.get("requires_approval"):
                    requires_approval = True
                    approval_payload = result.get("payload")

                    # Create an AuditLog entry in the database
                    audit_log_id = self._create_audit_log(
                        action_type=result.get("action", tool_name),
                        payload=approval_payload,
                    )

                    result_msg = (
                        f"This action requires vendor approval. "
                        f"An approval request has been created (ID: {audit_log_id}). "
                        f"Please inform the user that they need to approve or reject this action."
                    )
                else:
                    result_msg = str(result)

                tool_responses.append(
                    ToolMessage(
                        content=result_msg,
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )
            else:
                tool_responses.append(
                    ToolMessage(
                        content=f"Tool {tool_name} not found",
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )

        return {
            "messages": tool_responses,
            "requires_approval": requires_approval,
            "approval_payload": approval_payload,
            "audit_log_id": audit_log_id,
        }

    # ──────────────────────── Audit log helper ───────────────────────────────

    def _create_audit_log(self, action_type: str, payload: dict) -> str:
        """
        Persist an AuditLog entry with status='pending'.

        Args:
            action_type: e.g. 'update_membership', 'update_user_free_trial'.
            payload: The tool arguments to replay on approval.

        Returns:
            The generated audit_log_id.
        """
        audit_log = AuditLog(
            vendor_id=self.vendor_id or "unknown",
            action_type=action_type,
            action_payload=json.dumps(payload),
            status="pending",
        )
        self.db.add(audit_log)
        self.db.flush()  # Populate the auto-generated id

        logger.info(
            "audit_log_created",
            audit_log_id=audit_log.id,
            action_type=action_type,
            vendor_id=self.vendor_id,
        )
        return audit_log.id

    def _normalize_content(self, content: Any) -> str:
        """
        Convert provider-specific message content into a plain string.

        LangChain/Gemini may return either a normal string or a list of content
        blocks such as {"type": "text", "text": "..."} depending on the model
        response. The API contract and conversation memory both expect strings.
        """
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: List[str] = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if text:
                        text_parts.append(str(text))
            if text_parts:
                return "\n".join(text_parts)

        return str(content)

    def _tool_by_name(self, name: str):
        """Return a bound CRM tool by name."""
        return next((tool for tool in self.tools if tool.name == name), None)

    def _remaining_llm_calls(self) -> int:
        """Return remaining demo LLM calls for this app process."""
        return max(_remaining_demo_llm_calls, 0)

    def _should_use_failsafe(self) -> bool:
        """Use local demo mode once the configured LLM call budget is spent."""
        return settings.ENABLE_LOCAL_DEMO_FALLBACK and self._remaining_llm_calls() <= 0

    def _consume_demo_llm_call(self) -> None:
        """Spend one configured demo LLM call before invoking the external model."""
        global _remaining_demo_llm_calls
        if settings.ENABLE_LOCAL_DEMO_FALLBACK and _remaining_demo_llm_calls > 0:
            _remaining_demo_llm_calls -= 1

    def _decorate_response(
        self,
        result: dict,
        mode: str,
        warning: Optional[str] = None,
    ) -> dict:
        """Attach demo observability metadata to an API result."""
        result.setdefault("sources", [])
        result["mode"] = mode
        result["warning"] = warning
        result["remaining_llm_calls"] = self._remaining_llm_calls()
        return result

    def _record_runtime_event(
        self,
        event_type: str,
        mode: str,
        reason: str,
        detail: Optional[str] = None,
    ) -> None:
        """Persist an operational audit event without blocking the user flow."""
        try:
            event = RuntimeEvent(
                vendor_id=self.vendor_id,
                event_type=event_type,
                mode=mode,
                reason=reason,
                detail=detail,
            )
            self.db.add(event)
            self.db.flush()
        except Exception as exc:
            logger.warning("runtime_audit_event_failed", error=str(exc))

    def _is_write_like_query(self, query: str) -> bool:
        """Detect demo write-intent prompts that must preserve approval cards."""
        normalized_query = query.lower()
        return any(
            marker in normalized_query
            for marker in ("update membership", "change membership", "extend free trial")
        )

    def _local_model_warning(self) -> str:
        return (
            f"Gemini free-tier quota is exhausted. A local model ({settings.LOCAL_MODEL_NAME}) is handling this response."
        )

    def _deterministic_warning(self) -> str:
        return (
            "Gemini quota is exhausted and no configured local model is available. "
            "Using deterministic audited demo responses."
        )

    def _build_local_model_context(self) -> str:
        """Build a compact vendor-scoped context pack for a local model."""
        vendor_tool = self._tool_by_name("get_vendor_info")
        revenue_tool = self._tool_by_name("get_todays_revenue")
        orders_tool = self._tool_by_name("list_vendor_orders")
        trial_tool = self._tool_by_name("get_trial_users")

        vendor = vendor_tool.invoke({}) if vendor_tool else {}
        revenue = revenue_tool.invoke({}) if revenue_tool else {}
        orders = orders_tool.invoke({"limit": 5}) if orders_tool else []
        trial_users = trial_tool.invoke({"game_name": "Badminton"}) if trial_tool else []

        return (
            "Vendor-scoped CRM context only:\n"
            f"Vendor: {json.dumps(vendor, default=str)}\n"
            f"Today revenue: {json.dumps(revenue, default=str)}\n"
            f"Recent orders: {json.dumps(orders, default=str)}\n"
            f"Badminton trial users: {json.dumps(trial_users, default=str)}\n"
            "Rules: do not expose other vendors; do not claim writes are executed; "
            "tell the user writes require approval."
        )

    def _answer_with_local_graph(self, messages: list) -> Optional[dict]:
        """
        Use ChatOllama to execute the exact same tools graph as Gemini.
        Returns None if local fallback is disabled or Ollama probe fails.
        """
        if not settings.LOCAL_MODEL_ENABLED:
            return None

        try:
            from langchain_ollama import ChatOllama
            
            # Fast probe to see if Ollama is up before building graph
            tags_url = f"{settings.LOCAL_MODEL_BASE_URL.rstrip('/')}/api/tags"
            with url_request.urlopen(tags_url, timeout=2) as response:
                pass

            local_llm = ChatOllama(
                model=settings.LOCAL_MODEL_NAME,
                base_url=settings.LOCAL_MODEL_BASE_URL,
                temperature=0.2,
            )
            local_llm_with_tools = local_llm.bind_tools(self.tools)
            local_graph = self._build_graph_for_llm(local_llm_with_tools)

            initial_state = {
                "messages": messages,
                "requires_approval": False,
                "approval_payload": None,
                "audit_log_id": None,
            }
            final_state = local_graph.invoke(initial_state)
            final_response = self._normalize_content(final_state["messages"][-1].content)

            self._record_runtime_event(
                event_type="llm_fallback",
                mode="local_model",
                reason="gemini_quota_or_demo_budget_exhausted",
                detail=f"model={settings.LOCAL_MODEL_NAME}",
            )
            
            if final_state.get("requires_approval"):
                return self._decorate_response({
                    "answer": final_response,
                    "requires_approval": True,
                    "approval_payload": final_state.get("approval_payload"),
                    "audit_log_id": final_state.get("audit_log_id"),
                    "sources": [],
                }, "local_model", self._local_model_warning())

            return self._decorate_response({
                "answer": final_response,
                "requires_approval": False,
                "audit_log_id": None,
                "sources": [],
            }, "local_model", self._local_model_warning())
            
        except Exception as exc:
            self._record_runtime_event(
                event_type="local_model_unavailable",
                mode="deterministic",
                reason="local_model_probe_failed",
                detail=str(exc),
            )
            return None

    def _answer_with_failsafe(self, query: str, reason: str, messages: list) -> dict:
        """
        Fallback chain after Gemini is unavailable:
        1. local model graph if configured and available;
        2. deterministic audited demo response.
        """
        local_model_result = self._answer_with_local_graph(messages)
        if local_model_result:
            return local_model_result

        result = self._answer_with_local_fallback(query, warning=self._deterministic_warning())
        self._record_runtime_event(
            event_type="llm_fallback",
            mode="deterministic",
            reason=reason,
            detail="Gemini unavailable; local model unavailable or write flow requires deterministic approval.",
        )
        return result

    def _answer_with_local_fallback(
        self,
        query: str,
        warning: Optional[str] = None,
    ) -> dict:
        """
        Deterministic fallback for demo-critical queries when LLM quota is hit.

        This keeps the assessment demo usable without paid API credits. It does
        not replace the LangGraph/Gemini workflow; it only covers the seeded CRM
        questions and approval examples from the prompt.
        """
        normalized_query = query.lower()

        if not self.vendor_id:
            return self._decorate_response({
                "answer": "I need an authenticated vendor before I can answer CRM questions.",
                "requires_approval": False,
                "audit_log_id": None,
                "conversation_id": None,
                "sources": [],
            }, "deterministic", warning)

        if "all vendors" in normalized_query or "database" in normalized_query:
            return self._decorate_response({
                "answer": (
                    "I can only access data for the currently authenticated vendor. "
                    "I cannot show all vendors in the database from a vendor portal session."
                ),
                "requires_approval": False,
                "audit_log_id": None,
                "sources": [],
            }, "deterministic", warning)

        if "vendor info" in normalized_query or "payout" in normalized_query:
            tool = self._tool_by_name("get_vendor_info")
            result = tool.invoke({}) if tool else {}
            answer = (
                f"Vendor: {result.get('name')}\n"
                f"Status: {result.get('status')}\n"
                f"Payout balance: {result.get('payout_balance')}"
            )
            return self._decorate_response({"answer": answer, "requires_approval": False, "audit_log_id": None, "sources": []}, "deterministic", warning)

        if "revenue" in normalized_query:
            tool = self._tool_by_name("get_todays_revenue")
            result = tool.invoke({}) if tool else {}
            answer = (
                f"Today's revenue for this vendor is {result.get('total_revenue')} "
                f"on {result.get('date')}."
            )
            return self._decorate_response({"answer": answer, "requires_approval": False, "audit_log_id": None, "sources": []}, "deterministic", warning)

        if "trial" in normalized_query and "badminton" in normalized_query:
            tool = self._tool_by_name("get_trial_users")
            result = tool.invoke({"game_name": "Badminton"}) if tool else []
            if not result:
                answer = "No trial users found for Badminton."
            else:
                rows = [
                    f"- {user['name']} ({user['email']}), user_id={user['user_id']}, membership_id={user['membership_id']}"
                    for user in result
                ]
                answer = "Trial users for Badminton:\n" + "\n".join(rows)
            return self._decorate_response({"answer": answer, "requires_approval": False, "audit_log_id": None, "sources": []}, "deterministic", warning)

        if "recent orders" in normalized_query or "orders" in normalized_query:
            tool = self._tool_by_name("list_vendor_orders")
            result = tool.invoke({"limit": 10}) if tool else []
            if not result:
                answer = "No recent orders found for this vendor."
            else:
                rows = [
                    f"- {order['order_id']}: {order['amount']} ({order['status']})"
                    for order in result
                ]
                answer = "Recent orders:\n" + "\n".join(rows)
            return self._decorate_response({"answer": answer, "requires_approval": False, "audit_log_id": None, "sources": []}, "deterministic", warning)

        membership_match = re.search(
            r"user\s+(u_[\w-]+).*game\s+(g_[\w-]+).*to\s+(\w+)",
            normalized_query,
        )
        if ("membership" in normalized_query or "status" in normalized_query) and membership_match:
            user_id, game_id, new_status = membership_match.groups()
            payload = {
                "action": "update_membership",
                "user_id": user_id,
                "game_id": game_id,
                "new_status": new_status,
            }
            audit_log_id = self._create_audit_log("update_membership", payload)
            return self._decorate_response({
                "answer": (
                    f"I drafted a membership update for user {user_id} in game {game_id} "
                    f"to status '{new_status}'. It requires vendor approval before execution."
                ),
                "requires_approval": True,
                "approval_payload": payload,
                "audit_log_id": audit_log_id,
                "sources": [],
            }, "deterministic", warning)

        trial_match = re.search(
            r"user\s+(u_[\w-]+).*game\s+(g_[\w-]+).*?(20\d{2}-\d{2}-\d{2})",
            normalized_query,
        )
        if "trial" in normalized_query and trial_match:
            user_id, game_id, new_expiry_date = trial_match.groups()
            payload = {
                "action": "update_user_free_trial",
                "user_id": user_id,
                "game_id": game_id,
                "new_expiry_date": new_expiry_date,
            }
            audit_log_id = self._create_audit_log("update_user_free_trial", payload)
            return self._decorate_response({
                "answer": (
                    f"I drafted a free-trial expiry update for user {user_id} in game {game_id} "
                    f"to {new_expiry_date}. It requires vendor approval before execution."
                ),
                "requires_approval": True,
                "approval_payload": payload,
                "audit_log_id": audit_log_id,
                "sources": [],
            }, "deterministic", warning)

        return self._decorate_response({
            "answer": (
                "The live LLM quota is currently exhausted, so I can only answer the seeded demo "
                "queries locally right now. Try: 'show my vendor info', 'what is today's revenue', "
                "'list trial users for Badminton', or an approval example with user u_001 and game g_001."
            ),
            "requires_approval": False,
            "audit_log_id": None,
            "sources": [],
        }, "deterministic", warning)

    # ──────────────────────── Public API ──────────────────────────────────────

    async def answer_query(
        self,
        query: str,
        chat_history: Optional[List[Dict]] = None,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """
        Process a user query through the LangGraph agent.

        Args:
            query: The user's natural-language question or command.
            chat_history: Optional list of prior messages (legacy; prefer conversation_id).
            conversation_id: Optional id to load/save persistent memory.

        Returns:
            Dict with keys: answer, requires_approval, approval_payload,
            audit_log_id, conversation_id, sources.
        """
        logger.info("processing_copilot_query", query=query, vendor_id=self.vendor_id)

        # ── Load conversation memory ────────────────────────────────────────
        memory = None
        if self.vendor_id:
            memory = ConversationMemory(
                db=self.db,
                vendor_id=self.vendor_id,
                conversation_id=conversation_id,
            )

        # ── Build the message list ──────────────────────────────────────────
        system_prompt = SystemMessage(content=AGENT_SYSTEM_PROMPT)
        messages = [system_prompt]

        # Load persistent memory (takes priority over ad-hoc chat_history)
        if memory:
            for msg in memory.load():
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg.get("content", "")))
                else:
                    messages.append(AIMessage(content=msg.get("content", "")))
        elif chat_history:
            # Fallback: use the ad-hoc chat history from the request body
            for msg in chat_history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg.get("content", "")))
                else:
                    messages.append(AIMessage(content=msg.get("content", "")))

        messages.append(HumanMessage(content=query))

        # ── Handle Gemini Exhaustion Cooldown ───────────────────────────────
        consecutive_fallbacks = 0
        if memory:
            for msg in reversed(memory.load()):
                if msg.get("role") == "assistant":
                    if msg.get("mode") in ("local_model", "deterministic"):
                        consecutive_fallbacks += 1
                    else:
                        break
        
        should_skip_gemini = False
        if consecutive_fallbacks > 0 and (consecutive_fallbacks % getattr(settings, "GEMINI_RETRY_AFTER_MESSAGES", 3)) != 0:
            should_skip_gemini = True

        if self._should_use_failsafe() or should_skip_gemini:
            reason = "gemini_cooldown" if should_skip_gemini else "demo_llm_call_budget_exhausted"
            logger.info("using_local_fallback", vendor_id=self.vendor_id, reason=reason)
            fallback_result = self._answer_with_failsafe(query, reason, messages)
            final_response = fallback_result["answer"]
            saved_conversation_id = conversation_id
            if memory:
                saved_conversation_id = memory.save(query, final_response, mode=fallback_result.get("mode", "local_model"))
            fallback_result["conversation_id"] = saved_conversation_id
            return fallback_result

        # ── Run the graph ───────────────────────────────────────────────────
        initial_state = {
            "messages": messages,
            "requires_approval": False,
            "approval_payload": None,
            "audit_log_id": None,
        }
        try:
            self._consume_demo_llm_call()
            final_state = self.graph.invoke(initial_state)
        except Exception as exc:
            error_text = str(exc)
            if "RESOURCE_EXHAUSTED" in error_text or "429" in error_text:
                logger.warning("llm_quota_exhausted_using_local_fallback", vendor_id=self.vendor_id)
                fallback_result = self._answer_with_failsafe(query, "gemini_resource_exhausted", messages)
                final_response = fallback_result["answer"]
                saved_conversation_id = conversation_id
                if memory:
                    saved_conversation_id = memory.save(query, final_response, mode=fallback_result.get("mode", "local_model"))
                fallback_result["conversation_id"] = saved_conversation_id
                return fallback_result
            raise

        # ── Extract the response ────────────────────────────────────────────
        final_response = self._normalize_content(final_state["messages"][-1].content)

        # ── Save to memory ──────────────────────────────────────────────────
        saved_conversation_id = conversation_id
        if memory:
            saved_conversation_id = memory.save(query, final_response)

        # ── Handle approval flow ────────────────────────────────────────────
        if final_state.get("requires_approval"):
            return self._decorate_response({
                "answer": final_response,
                "requires_approval": True,
                "approval_payload": final_state["approval_payload"],
                "audit_log_id": final_state.get("audit_log_id"),
                "conversation_id": saved_conversation_id,
                "sources": [],
            }, "llm")

        return self._decorate_response({
            "answer": final_response,
            "requires_approval": False,
            "audit_log_id": None,
            "conversation_id": saved_conversation_id,
            "sources": [],
        }, "llm")
