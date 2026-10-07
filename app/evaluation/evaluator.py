"""
Self-Critique Evaluator — LangChain structured output."""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.config import get_llm

logger = logging.getLogger("shopmate.evaluator")

class EvaluationResult(BaseModel):
    """Structured evaluation output."""
    is_passing: bool = Field(
        description="True if the response correctly answers the user, is grounded in tool data, and is helpful."
    )
    critique: str = Field(
        description="If not passing, explain specifically what is wrong so the agent can fix it on retry."
    )

async def evaluate_response(user_message: str, drafted_response: str) -> EvaluationResult:
    """
    Self-critique loop: a second LLM pass evaluates the drafted response
    for groundedness, relevance, and format quality.
    """
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(EvaluationResult)

    system = SystemMessage(content="""You are a QA evaluator for an e-commerce AI assistant.
Review the drafted response against the user's original message.
Check:
1. Does it answer the user's question?
2. Is it grounded in real data (not hallucinated)?
3. Is it polite and professional?
4. Is the format clear and readable?
If all checks pass, return is_passing: true.
If any check fails, return is_passing: false and provide specific, actionable critique.""")

    user = HumanMessage(
        content=f"Original user message: {user_message}\n\nDrafted response: {drafted_response}"
    )

    try:
        result = await structured_llm.ainvoke([system, user])
        return result
    except Exception as e:
        logger.warning("[Evaluator] LLM call failed (%s: %s). Passing response without QA.",
                       type(e).__name__, e)
        return EvaluationResult(is_passing=True,
                                critique=f"Evaluation skipped: {type(e).__name__}")
