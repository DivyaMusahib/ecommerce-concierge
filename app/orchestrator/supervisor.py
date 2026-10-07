"""
Supervisor / Orchestrator — LangGraph StateGraph."""
import asyncio
import logging
import re
import time
from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.core.guardrails import (
    check_output_guardrails,
    check_prompt_injection,
    mask_pii,
)
from app.core.request_context import RequestContext
from app.evaluation.evaluator import evaluate_response
from app.memory.long_term import async_get_user_profile
from app.memory.session import redis_client
from app.orchestrator.aggregator import aggregate_responses
from app.orchestrator.classifier import (
    IntentResult,
    classify_intent,
    rule_based_classify,
)

logger = logging.getLogger(__name__)

# ── LangGraph State Schema ────────────────────────────────────────────────────

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
    ctx: RequestContext | None

# ── Node Functions ────────────────────────────────────────────────────────────

async def input_guardrails_node(state: SupervisorState) -> dict:
    """Check for prompt injection and mask PII."""
    if check_prompt_injection(state["user_message"]):
        return {"error": "blocked", "final_response": "I cannot process that request."}
    safe = mask_pii(state["user_message"])
    return {"safe_message": safe}

async def memory_node(state: SupervisorState) -> dict:
    """Load session history and user profile, build augmented context. Build RequestContext."""
    user_id = state["user_id"]
    session_id = state["session_id"]

    # Build the request context once — passed through all subsequent nodes
    ctx = RequestContext(user_id=user_id, session_id=session_id)

    profile = await async_get_user_profile(user_id)
    history = redis_client.get_history(session_id)
    redis_client.add_message(session_id, "user", state["user_message"])

    # Build rich context string for agent system prompts
    profile_str = "Unknown user"
    if ctx.is_guest:
        profile_str = "Guest User — No persistent memory."
    elif profile:
        prefs = profile.get("preferences", {})
        pref_str = ", ".join(f"{k}={v}" for k, v in prefs.items()) if prefs else "none"
        profile_str = (
            f"Name={profile.get('name')}, "
            f"Shipping={profile.get('shipping_address', 'None')}, Preferences=[{pref_str}]"
        )

    history_str = " | ".join(
        f"{m['role']}: {m['content'][:80]}" for m in history
    ) if history else "No prior context"

    augmented = (
        f"[System Context] User Profile: {profile_str} | "
        f"Recent Chat: {history_str}\n\n"
        f"[User Message] {state['safe_message']}"
    )
    return {"augmented_message": augmented, "ctx": ctx}

async def classify_node(state: SupervisorState) -> dict:
    """Dual intent classification: rule-based fast path, async LLM fallback."""
    result = rule_based_classify(state["safe_message"])
    if result:
        logger.info(f"[Router] Rule-based match: {result.intents}")
    else:
        logger.info("[Router] Rule miss → LLM fallback")
        result = await classify_intent(state["augmented_message"])
        logger.info(f"[Router] LLM classified: {result.intents} (urgency: {result.urgency})")
    return {"intent_result": result}

def _extract_text(content) -> str:
    """Extract plain text from LangChain message content (str, list, or dict)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        return "".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or content)
    return str(content)

async def _invoke_agent(agent, message: str, agent_name: str) -> str:
    """Invoke a LangGraph ReAct agent and extract the final text response."""
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        messages = result.get("messages", [])
        if messages:
            return _extract_text(messages[-1].content)
        return "Agent returned no response."
    except Exception as e:
        import traceback
        logger.warning(f"[Dispatch] {agent_name} FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise

async def dispatch_node(state: SupervisorState) -> dict:
    """Route to appropriate agents and execute in parallel using per-request factory instances."""
    intent_result = state["intent_result"]
    if not intent_result:
        return {"error": "no_intent",
                "final_response": "I couldn't understand your request. Could you rephrase?"}

    ctx: RequestContext = state["ctx"]
    msg = state["augmented_message"]
    user_msg_lower = state["safe_message"].lower()

    # Import agent factories lazily
    from app.agents.agent_factories import (
        build_cart_agent,
        build_complaint_agent,
        build_deals_agent,
        build_faq_agent,
        build_order_agent,
        build_product_agent,
    )

    # Build per-request agent instances (tools bound to ctx)
    agent_factory_map = {
        "ORDER_TRACKING": ("OrderAgent",    lambda: build_order_agent(ctx)),
        "PRODUCT_INQUIRY": ("ProductAgent", lambda: build_product_agent(ctx)),
        "FAQ":             ("FaqAgent",     lambda: build_faq_agent(ctx)),
        "PRICE_INQUIRY":   ("DealsAgent",   lambda: build_deals_agent(ctx)),
        "CART_ACTION":     ("CartAgent",    lambda: build_cart_agent(ctx)),
        "COMPLAINT":       ("ComplaintAgent", lambda: build_complaint_agent(ctx)),
    }

    active_intents = list(intent_result.intents)

    # Suppress PRODUCT_INQUIRY when CART_ACTION is primary (avoids double-response)
    if "CART_ACTION" in active_intents and "PRODUCT_INQUIRY" in active_intents:
        cart_primary = re.search(
            r'\b(add|remove|checkout|check.?out|what.s in|view|show|clear|apply coupon)\b',
            user_msg_lower
        )
        product_detail = re.search(
            r'\b(compare|versus|vs|specs|specifications|details|tell me about)\b',
            user_msg_lower
        )
        if cart_primary and not product_detail:
            active_intents.remove("PRODUCT_INQUIRY")
            print("[Dispatch] Suppressed PRODUCT_INQUIRY (CART_ACTION primary)")

    tasks = []
    agents_used = []
    for intent in active_intents:
        entry = agent_factory_map.get(intent)
        if entry:
            name, factory = entry
            agent = factory()  # Build fresh agent instance
            tasks.append(_invoke_agent(agent, msg, name))
            agents_used.append(name)

    if not tasks:
        return {
            "agents_used": ["Fallback"],
            "final_response": f"I detected intents {intent_result.intents} but no matching agent is available.",
        }

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    clean_responses = []
    last_exc = None
    for i, r in enumerate(responses):
        if isinstance(r, Exception):
            last_exc = r
        else:
            clean_responses.append(r)

    if not clean_responses and last_exc:
        raise last_exc

    return {"agent_responses": clean_responses, "agents_used": agents_used}

async def aggregate_node(state: SupervisorState) -> dict:
    """Synthesize multi-agent responses into a single cohesive answer.

    Optimization: For single-agent responses, skip the LLM aggregator entirely.
    The aggregator adds ~1-2s of latency and an extra LLM call for no gain.
    """
    responses = state.get("agent_responses", [])
    if not responses:
        return {"raw_response": "I'm sorry, I wasn't able to process your request. Please try again."}
    # Single agent — return directly, no aggregation needed
    if len(responses) == 1:
        return {"raw_response": responses[0]}
    # Multi-agent — synthesize with LLM
    logger.info(f"[Aggregate] Merging {len(responses)} agent responses…")
    combined = await aggregate_responses(state["augmented_message"], responses)
    return {"raw_response": combined}

async def evaluate_node(state: SupervisorState) -> dict:
    """Self-critique evaluation loop — conditional."""
    raw = state.get("raw_response", state.get("final_response", ""))
    if not raw:
        return {}

    agents_used = state.get("agents_used", [])
    intent_result = state.get("intent_result")
    urgency = getattr(intent_result, "urgency", "LOW") if intent_result else "LOW"

    # Skip for fast path: single agent + non-urgent
    if len(agents_used) <= 1 and urgency != "HIGH":
        logger.info(f"[Evaluator] Skipped (single agent, urgency={urgency})")
        return {"final_response": raw}

    logger.info(f"[Evaluator] Running QA ({len(agents_used)} agents, urgency={urgency})")
    eval_result = await evaluate_response(state["user_message"], raw)
    if eval_result.is_passing:
        return {"final_response": raw}

    # Retry with critique feedback
    logger.warning(f"[Evaluator] FAILED — retrying. Critique: {eval_result.critique}")
    context = state.get("augmented_message") or state["user_message"]
    fix_prompt = (
        f"Previous draft failed QA. Critique: {eval_result.critique}\n"
        f"Previous draft: {raw}\n"
        "Please fix the response based on the critique."
    )
    fixed = await aggregate_responses(context, [fix_prompt])
    return {"final_response": fixed}

async def output_guardrails_node(state: SupervisorState) -> dict:
    """Check final response for safety and persist to session memory."""
    response = state.get("final_response", "")
    if isinstance(response, list):
        response = " ".join(str(x) for x in response)
    else:
        response = str(response)

    if not check_output_guardrails(response):
        return {"final_response": "I encountered an error generating a safe response. Please try again."}

    redis_client.add_message(state["session_id"], "assistant", response)
    elapsed = time.time() - state.get("start_time", time.time())
    logger.info(f"[Supervisor] Completed in {elapsed:.2f}s | Agents: {state.get('agents_used', [])}")
    return {}

# ── Conditional Routing ───────────────────────────────────────────────────────

def should_continue(state: SupervisorState) -> str:
    return "end" if state.get("error") else "continue"

def has_response_already(state: SupervisorState) -> str:
    return "skip_to_output" if state.get("final_response") else "aggregate"

# ── Build the LangGraph Workflow ──────────────────────────────────────────────

def build_supervisor_graph() -> StateGraph:
    """Construct the supervisor workflow as a LangGraph StateGraph."""
    graph = StateGraph(SupervisorState)

    graph.add_node("input_guardrails", input_guardrails_node)
    graph.add_node("memory", memory_node)
    graph.add_node("classify", classify_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("output_guardrails", output_guardrails_node)

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

# ── Public Interface ──────────────────────────────────────────────────────────

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
            "ctx": None,
        }

        result = await _workflow.ainvoke(initial_state)

        return (
            result.get("final_response", "Something went wrong."),
            result.get("intent_result"),
            result.get("agents_used", []),
        )

supervisor = Supervisor()
