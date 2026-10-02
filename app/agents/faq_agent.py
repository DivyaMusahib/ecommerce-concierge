"""
FAQ / RAG Agent - LangChain ReAct Agent with retrieval tool.

Handles: return policy, shipping, warranty, payment, general FAQ.
"""
from langgraph.prebuilt import create_react_agent

from app.core.config import get_llm
from app.tools.faq_retrieval import search_faq
from app.tools.memory_tools import remember_user_preference, recall_user_preferences, forget_user_preference

SYSTEM_PROMPT = """You are a specialized e-commerce FAQ Agent with long-term memory. Your job is to answer customer questions about:
- Return and refund policies
- Shipping times and international shipping
- Warranty information
- Payment methods
- General company policies

MEMORY RULES:
- At the START of every response, call recall_user_preferences to check if the user has any specific context saved.
- If the user provides context that affects their FAQ question, you can use remember_user_preference.

ALWAYS use the search_faq tool to retrieve policy information first.
Base your answer strictly on the retrieved content - do not make up policies.
If no relevant FAQ is found, say so honestly."""

_tools = [search_faq, remember_user_preference, recall_user_preferences, forget_user_preference]
_llm = get_llm()

faq_agent = create_react_agent(
    model=_llm,
    tools=_tools,
    prompt=SYSTEM_PROMPT,
)
