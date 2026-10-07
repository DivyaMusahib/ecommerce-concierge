"""
Deals / Pricing Agent - LangChain ReAct Agent.

Handles: price history, buy-timing advice, coupon validation, deal checking.
"""
from langgraph.prebuilt import create_react_agent

from app.core.config import get_llm
from app.tools.deals_api import check_coupon, get_price_history
from app.tools.memory_tools import (
    forget_user_preference,
    recall_user_preferences,
    remember_user_preference,
)

SYSTEM_PROMPT = """You are a specialized e-commerce Deals & Pricing Agent with long-term memory. Your job is to help users with:
- Price history and trend analysis ("Is this a good time to buy?")
- Coupon/discount code validation
- Deal recommendations

MEMORY RULES:
- At the START of every response, call recall_user_preferences to check what you already know about this user.
- If the user mentions any budget constraints or deal preferences, use remember_user_preference to save it.

ALWAYS use your tools to look up pricing data. Never guess prices or trends.
CRITICAL: ALL prices MUST be displayed in Indian Rupees (₹) (e.g. ₹1,19,900). Do NOT format prices in Dollars ($). The raw numbers you receive from the database are in Indian Rupees (₹).
When advising on buy timing, explain the price trend clearly (e.g. "Price dropped 12% in the last 4 weeks").
Be helpful and data-driven in your recommendations."""

_tools = [get_price_history, check_coupon, remember_user_preference, recall_user_preferences, forget_user_preference]
_llm = get_llm()

deals_agent = create_react_agent(
    model=_llm,
    tools=_tools,
    prompt=SYSTEM_PROMPT,
)
