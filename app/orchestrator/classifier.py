"""
Intent Classifier - LangChain structured output.

Dual implementation: fast rule-based router + LLM-based fallback with
Pydantic structured output via LangChain's with_structured_output().

Rule-based fixes (v2):
- ORDER_TRACKING: "delayed" is no longer a COMPLAINT trigger alone
- COMPLAINT: requires stronger frustration signals (not just "waiting")
- "refund" routes to COMPLAINT, not FAQ
- Multi-intent: all matching intents are always returned
- Edge case: "show me products ... and track order" now fires both intents
"""
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.config import get_llm

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    """Structured output schema for intent classification."""
    intents: list[str] = Field(
        description="Detected intents. Valid values: ORDER_TRACKING, PRODUCT_INQUIRY, FAQ, COMPLAINT, CART_ACTION, PRICE_INQUIRY"
    )
    urgency: str = Field(description="LOW, MEDIUM, or HIGH based on user sentiment/frustration.")
    entities: dict = Field(
        default_factory=dict,
        description="Extracted entities: order_id, product_name, coupon_code, etc.",
    )


async def classify_intent(message: str) -> IntentResult:
    """
    LLM-based intent classification using LangChain structured output.
    Fully async — uses ainvoke to avoid blocking the event loop.
    """
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(IntentResult)

    system = SystemMessage(content="""You are an intent classification system for an e-commerce platform.
Analyze the user's message and determine ALL primary intents.
Valid intents: ORDER_TRACKING, PRODUCT_INQUIRY, FAQ, COMPLAINT, CART_ACTION, PRICE_INQUIRY

CRITICAL RULES:
- If the user is ADDING/REMOVING items, VIEWING their cart, or CHECKING OUT -> use CART_ACTION ONLY.
  Do NOT also add PRODUCT_INQUIRY for simple add/view/checkout requests. The CartAgent handles product lookup.
- PRODUCT_INQUIRY is ONLY for pure product browsing: search, specs, compare, recommendations.
- If the user asks to COMPARE products AND THEN add one -> use both PRODUCT_INQUIRY and CART_ACTION.
- "refund" requests are COMPLAINT, not FAQ. "delayed" order status questions are ORDER_TRACKING.
- A single message can have MULTIPLE intents (e.g., asking about an order AND complaining about delays).

Extract relevant entities: order_id, product_name, coupon_code, etc.
Assess urgency based on sentiment: LOW (neutral), MEDIUM (mild concern), HIGH (frustrated/angry).""")

    user = HumanMessage(content=message)

    try:
        result = await structured_llm.ainvoke([system, user])
        return result
    except Exception as e:
        logger.warning(f"[Classifier] LLM classification error: {e}")
        return IntentResult(intents=["PRODUCT_INQUIRY"], urgency="LOW", entities={})


def rule_based_classify(message: str) -> IntentResult | None:
    """
    Fast rule-based router. Avoids LLM calls for obvious intents.
    Supports multi-intent detection. Returns None to fall back to LLM.

    Priority rules:
    - All matching intents are collected (no early return)
    - COMPLAINT requires strong frustration, NOT just "delayed" or "waiting"
    - "refund" routes to COMPLAINT (not FAQ)
    - ORDER_TRACKING captures "delayed" when combined with order reference
    """
    msg = message.lower()
    intents = []
    entities = {}

    # ── ORDER_TRACKING ──────────────────────────────────────────────────────
    # Match: explicit order reference + tracking/status intent
    order_ref = re.search(r'\border\b|\border\s*#?\s*(\d+)', msg)
    tracking_words = re.search(r'\b(where|status|track|delivery|deliver|arrive|when|delayed|delay)\b', msg)
    if order_ref and tracking_words:
        intents.append("ORDER_TRACKING")
        id_match = re.search(r'order\s*#?\s*(\d+)', msg)
        if id_match:
            entities["order_id"] = id_match.group(1)

    # "show me all my orders", "my order history", "what are my orders"
    if re.search(r'\b(all\s+(my\s+)?orders|my\s+orders|order\s+history|past\s+(purchases?|orders?)|all\s+orders)\b', msg):
        intents.append("ORDER_TRACKING")

    # "what is my address", "show my address"
    if re.search(r'\b(my\s+address|shipping\s+address|saved\s+address|delivery\s+address)\b', msg):
        intents.append("ORDER_TRACKING")

    # ── PRODUCT_INQUIRY ─────────────────────────────────────────────────────
    product_keywords = r'\b(price|cost|how much|stock|in stock|details|specs|compare|comparison|rating|review|reviews|tell me about|show me|laptops|under|available)\b'
    known_products = [
        "laptop", "macbook", "iphone", "iphone18", "samsung", "mouse", "keyboard",
        "headphones", "monitor", "phone", "earbuds", "tablet", "ipad", "watch", "ps5",
    ]
    product_word_hit = re.search(product_keywords, msg)
    product_name_hit = any(p in msg for p in known_products)

    if product_word_hit or product_name_hit:
        intents.append("PRODUCT_INQUIRY")
        for p in known_products:
            if p in msg:
                entities["product_name"] = p
                break

    # ── FAQ ─────────────────────────────────────────────────────────────────
    # Note: "refund" is intentionally excluded here — it routes to COMPLAINT below
    if re.search(r'\b(policy|return policy|shipping time|warranty|payment method|accept|faq|international ship|how long does ship)\b', msg):
        intents.append("FAQ")

    # ── CART_ACTION ─────────────────────────────────────────────────────────
    # Catches: "add to cart", "add iPhone to my cart", "checkout", explicit + natural language
    cart_exact = re.search(
        r'(add to cart|remove from cart|my cart|checkout|check\s*out|apply coupon|apply code|'
        r'what.s in my cart|view cart|show cart|clear cart|what is (in|there in) my cart|'
        r'remove .+ from (my )?cart|what.s in the cart)',
        msg
    )
    # Conversational checkout: "check it out" in context of shopping
    cart_checkout_conv = re.search(r'\bcheck\b.{0,6}\bout\b', msg)
    # Natural: "add X to my/the cart", "add X and Y to cart"
    cart_natural = re.search(r'\badd\b.{0,60}\b(cart|bag)\b', msg)
    # Conversational: "add X also", "add the braided one", standalone add with known product hint
    cart_conversational = (
        re.search(r'^\s*add\b.{0,80}$', msg) and
        re.search(r'\b(also|too|as well|one|it|them|the braided|the cable|the mouse|the keyboard|the earphone|the bulb|the stand)\b', msg)
    )
    # Direct add without cart word (e.g. "add iphone 18 pro max and boat wired earphones")
    cart_direct_add = re.search(r'^\s*add\b\s+(.+)', msg)

    if cart_exact or cart_checkout_conv or cart_natural or cart_conversational or cart_direct_add:
        intents.append("CART_ACTION")
        coupon_match = re.search(r'\b(SAVE\d+|FLAT\d+|NEWUSER|ELECTRONICS\d+)\b', msg, re.IGNORECASE)
        if coupon_match:
            entities["coupon_code"] = coupon_match.group(1).upper()

    # ── PRICE_INQUIRY ───────────────────────────────────────────────────────
    if re.search(r'\b(price drop|good time to buy|cheaper|deal|coupon|discount|price history|price trend|is .* valid)\b', msg):
        intents.append("PRICE_INQUIRY")

    # ── COMPLAINT ───────────────────────────────────────────────────────────
    # Strong frustration signals only — "delayed" alone is ORDER_TRACKING, not COMPLAINT
    # "refund" (without policy context) is a COMPLAINT action
    strong_frustration = re.search(
        r'\b(frustrated|angry|furious|ridiculous|terrible|worst|unacceptable|escalate|nobody is helping|this is ridiculous|i demand|i want a refund|issue my refund|give me a refund)\b',
        msg
    )
    refund_action = re.search(r'\b(refund)\b', msg) and not re.search(r'\b(refund policy|return policy)\b', msg)

    if strong_frustration or refund_action:
        intents.append("COMPLAINT")

    if intents:
        # Deduplicate while preserving order
        intents = list(dict.fromkeys(intents))
        # Urgency heuristic
        has_complaint = "COMPLAINT" in intents
        has_frustration = re.search(r'\b(annoyed|disappointed|upset|waiting|late|slow)\b', msg)
        urgency = "HIGH" if has_complaint else ("MEDIUM" if has_frustration else "LOW")
        return IntentResult(intents=intents, urgency=urgency, entities=entities)

    return None  # Fall back to LLM
