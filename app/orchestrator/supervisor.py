"""
Supervisor / Orchestrator - LangGraph StateGraph.

Central coordinator that manages the full pipeline:
  Input Guardrails -> Intent Classification -> Agent Dispatch (parallel)
  -> Aggregation -> Self-Critique Evaluation -> Output Guardrails

Uses LangGraph StateGraph for structured, observable workflow management.
"""
import re
import time
import asyncio
from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from app.orchestrator.classifier import classify_intent, rule_based_classify, IntentResult
from app.orchestrator.aggregator import aggregate_responses
from app.core.guardrails import mask_pii, check_prompt_injection, check_output_guardrails
from app.evaluation.evaluator import evaluate_response
from app.memory.session import redis_client
from app.memory.long_term import get_user_profile
from app.tools.memory_tools import set_memory_user
from app.tools.complaint_api import set_complaint_context
from app.tools.order_api import set_order_user
from app.tools.cart_api import set_cart_session


# ── LangGraph State Schema ──────────────────────────────────────────────────

class SupervisorState(TypedDict):
    user_message: str
    session_id: str
    user_id: str
    safe_message: str
    augmented_message: str
    intent_result: IntentResult | None
    agent_responses: list[str]
    agents_used: list[str]
    raw_response: str
    final_response: str
    error: str | None
    start_time: float


# ── Node Functions ───────────────────────────────────────────────────────────

async def input_guardrails_node(state: SupervisorState) -> dict:
    """Check for prompt injection and mask PII."""
    if check_prompt_injection(state["user_message"]):
        return {"error": "blocked", "final_response": "I cannot process that request."}
    safe = mask_pii(state["user_message"])
    return {"safe_message": safe}


async def memory_node(state: SupervisorState) -> dict:
    """Load session history and user profile, build augmented context."""
    user_id = state["user_id"]

    # Scope memory and order tools to this user for the duration of this request
    set_memory_user(user_id)
    set_order_user(user_id)
    set_complaint_context(user_id, state["session_id"])
    set_cart_session(state["session_id"], user_id)

    profile = get_user_profile(user_id)
    history = redis_client.get_history(state["session_id"])
    redis_client.add_message(state["session_id"], "user", state["user_message"])

    # Build a rich context string injected into every agent's system prompt
    profile_str = "Unknown user"
    if user_id == "guest":
        profile_str = "Guest User - No persistent memory."
    elif profile:
        prefs = profile.get("preferences", {})
        pref_str = ", ".join(f"{k}={v}" for k, v in prefs.items()) if prefs else "none"
        profile_str = (
            f"Name={profile.get('name')}, "
            f"Shipping={profile.get('default_shipping', 'None')}, Preferences=[{pref_str}]"
        )

    history_str = " | ".join(
        f"{m['role']}: {m['content'][:80]}" for m in history
    ) if history else "No prior context"

    augmented = (
        f"[System Context] User Profile: {profile_str} | "
        f"Recent Chat: {history_str}\n\n"
        f"[User Message] {state['safe_message']}"
    )
    return {"augmented_message": augmented}


async def classify_node(state: SupervisorState) -> dict:
    """Dual intent classification: rule-based fast path, async LLM fallback."""
    result = rule_based_classify(state["safe_message"])
    if result:
        print(f"[Router] Rule-based match: {result.intents}")
    else:
        print("[Router] Rule miss -> LLM fallback")
        result = await classify_intent(state["augmented_message"])
        print(f"[Router] LLM classified: {result.intents} (urgency: {result.urgency})")
    return {"intent_result": result}


def _extract_text(content) -> str:
    """Extract plain text from LangChain message content (str, list, or dict)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                # Gemini returns [{'type': 'text', 'text': '...', 'extras': {...}}]
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        return "".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or content)
    return str(content)


async def _invoke_agent(agent, message: str) -> str:
    """Invoke a LangGraph ReAct agent and extract the final text response."""
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
    messages = result.get("messages", [])
    if messages:
        return _extract_text(messages[-1].content)
    return "Agent returned no response."


async def dispatch_node(state: SupervisorState) -> dict:
    """Route to appropriate agents and execute in parallel."""
    intent_result = state["intent_result"]
    if not intent_result:
        return {"error": "no_intent", "final_response": "I couldn't understand your request. Could you rephrase?"}

    tasks = []
    agents_used = []
    msg = state["augmented_message"]
    user_msg_lower = state["safe_message"].lower()

    # Import agents lazily to avoid circular imports
    from app.agents.product_agent import product_agent
    from app.agents.order_agent import order_agent
    from app.agents.faq_agent import faq_agent
    from app.agents.deals_agent import deals_agent
    from app.agents.cart_agent import cart_agent
    from app.agents.complaint_agent import complaint_agent
    from app.tools.cart_api import set_cart_session
    from app.tools.order_api import set_order_user

    # Scope cart, memory, order, and complaint operations to this user's session before dispatch
    set_cart_session(state["session_id"], state["user_id"])
    set_memory_user(state["user_id"])
    set_complaint_context(state["user_id"], state["session_id"])
    set_order_user(state["user_id"])

    agent_map = {
        "ORDER_TRACKING": ("OrderAgent", order_agent),
        "PRODUCT_INQUIRY": ("ProductAgent", product_agent),
        "FAQ": ("FaqAgent", faq_agent),
        "PRICE_INQUIRY": ("DealsAgent", deals_agent),
        "CART_ACTION": ("CartAgent", cart_agent),
        "COMPLAINT": ("ComplaintAgent", complaint_agent),
    }

    active_intents = list(intent_result.intents)

    # Suppress PRODUCT_INQUIRY when CART_ACTION is present and the user is doing a simple
    # cart operation (add/remove/view/checkout) — the CartAgent already handles product lookup
    # internally via add_to_cart's fuzzy match. Running ProductAgent in parallel just creates
    # a double-response with redundant product details.
    if "CART_ACTION" in active_intents and "PRODUCT_INQUIRY" in active_intents:
        # Only suppress if the message is primarily a cart action (add/remove/view/checkout)
        # Keep PRODUCT_INQUIRY if user is comparing or asking for detailed specs alongside cart
        cart_primary = re.search(
            r'\b(add|remove|checkout|check.?out|what.s in|view|show|clear|apply coupon)\b',
            user_msg_lower
        )
        product_detail_request = re.search(
            r'\b(compare|versus|vs|specs|specifications|details|tell me about|show me details)\b',
            user_msg_lower
        )
        if cart_primary and not product_detail_request:
            active_intents.remove("PRODUCT_INQUIRY")
            print("[Dispatch] Suppressed PRODUCT_INQUIRY (CART_ACTION primary)")

    for intent in active_intents:
        entry = agent_map.get(intent)
        if entry:
            name, agent = entry
            tasks.append(_invoke_agent(agent, msg))
            agents_used.append(name)

    if not tasks:
        return {
            "agents_used": ["Fallback"],
            "final_response": f"I detected intents {intent_result.intents} but no matching agent is available yet.",
        }

    # Execute agents concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions from individual agents
    clean_responses = []
    last_exc = None
    for i, r in enumerate(responses):
        if isinstance(r, Exception):
            last_exc = r
            import traceback
            print(f"[Dispatch] {agents_used[i]} FAILED: {type(r).__name__}: {r}")
            traceback.print_exc()
            # Don't add a fake "sorry" message — skip the failed agent silently
            # The aggregator will work with whatever good responses we do have
        else:
            clean_responses.append(r)

    # If ALL agents failed, re-raise the exception so the API returns a real error
    if not clean_responses and last_exc:
        raise last_exc

    return {"agent_responses": clean_responses, "agents_used": agents_used}


async def aggregate_node(state: SupervisorState) -> dict:
    """Synthesize multi-agent responses into a single cohesive answer."""
    responses = state.get("agent_responses", [])
    if not responses:
        # No agent responses — return a graceful fallback
        return {"raw_response": "I'm sorry, I wasn't able to process your request at this time. Could you please rephrase or try again?"}

    if len(responses) == 1:
        return {"raw_response": responses[0]}

    combined = await aggregate_responses(state["augmented_message"], responses)
    return {"raw_response": combined}


async def evaluate_node(state: SupervisorState) -> dict:
    """Self-critique evaluation loop."""
    raw = state.get("raw_response", state.get("final_response", ""))
    if not raw:
        return {}

    eval_result = await evaluate_response(state["user_message"], raw)
    if eval_result.is_passing:
        return {"final_response": raw}

    # Retry with critique feedback injected into the augmented context
    print(f"[Evaluator] FAILED: {eval_result.critique}")
    context = state.get("augmented_message") or state["user_message"]
    fix_prompt = (
        f"Previous draft failed QA. Critique: {eval_result.critique}\n"
        f"Previous draft: {raw}\n"
        f"Please fix the response based on the critique."
    )
    fixed = await aggregate_responses(context, [fix_prompt])
    return {"final_response": fixed}


async def output_guardrails_node(state: SupervisorState) -> dict:
    """Check final response for safety."""
    response = state.get("final_response", "")
    
    # Safety catch in case it's a list
    if isinstance(response, list):
        print(f"[Warning] final_response was a list: {response}")
        response = " ".join(str(x) for x in response)
    else:
        response = str(response)

    if not check_output_guardrails(response):
        return {"final_response": "I encountered an error generating a safe response. Please try again."}

    # Save to session memory
    redis_client.add_message(state["session_id"], "assistant", response)

    elapsed = time.time() - state.get("start_time", time.time())
    print(f"[Supervisor] Completed in {elapsed:.2f}s | Agents: {state.get('agents_used', [])}")
    return {}


# ── Conditional Routing ──────────────────────────────────────────────────────

def should_continue(state: SupervisorState) -> str:
    """Route based on whether an error/early-exit occurred."""
    if state.get("error"):
        return "end"
    return "continue"


def has_response_already(state: SupervisorState) -> str:
    """Check if dispatch already set final_response (fallback case)."""
    if state.get("final_response"):
        return "skip_to_output"
    return "aggregate"


# ── Build the LangGraph Workflow ─────────────────────────────────────────────

def build_supervisor_graph() -> StateGraph:
    """Construct the supervisor workflow as a LangGraph StateGraph."""
    graph = StateGraph(SupervisorState)

    # Add nodes
    graph.add_node("input_guardrails", input_guardrails_node)
    graph.add_node("memory", memory_node)
    graph.add_node("classify", classify_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("output_guardrails", output_guardrails_node)

    # Define edges
    graph.add_edge(START, "input_guardrails")
    graph.add_conditional_edges("input_guardrails", should_continue, {
        "end": "output_guardrails",
        "continue": "memory",
    })
    graph.add_edge("memory", "classify")
    graph.add_edge("classify", "dispatch")
    graph.add_conditional_edges("dispatch", has_response_already, {
        "skip_to_output": "output_guardrails",
        "aggregate": "aggregate",
    })
    graph.add_edge("aggregate", "evaluate")
    graph.add_edge("evaluate", "output_guardrails")
    graph.add_edge("output_guardrails", END)

    return graph.compile()


# ── Public Interface ─────────────────────────────────────────────────────────

_workflow = build_supervisor_graph()


class Supervisor:
    """Wrapper to maintain backward-compatible API with routes.py."""

    async def process_request(
        self, user_message: str, session_id: str = "default", user_id: str = "default"
    ) -> tuple[str, IntentResult | None, list[str]]:
        """Run the full LangGraph supervisor pipeline."""
        initial_state: SupervisorState = {
            "user_message": user_message,
            "session_id": session_id,
            "user_id": user_id,
            "safe_message": "",
            "augmented_message": "",
            "intent_result": None,
            "agent_responses": [],
            "agents_used": [],
            "raw_response": "",
            "final_response": "",
            "error": None,
            "start_time": time.time(),
        }

        result = await _workflow.ainvoke(initial_state)

        return (
            result.get("final_response", "Something went wrong."),
            result.get("intent_result"),
            result.get("agents_used", []),
        )


supervisor = Supervisor()
