"""
Aggregator - LangChain-based response synthesis.

Combines outputs from multiple agents into a single cohesive response.
Handles conflict resolution and source attribution.
"""
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import get_llm


async def aggregate_responses(user_message: str, agent_responses: list[str]) -> str:
    """
    Takes multiple agent responses from parallel execution and synthesizes
    them into a single cohesive, natural response for the user.
    """
    llm = get_llm(temperature=0.2)

    system = SystemMessage(content="""You are the final response synthesizer for an e-commerce assistant.
You will be given the original user message and responses from specialized agents.
Your job:
1. Combine the agent outputs into ONE cohesive, friendly message.
2. If agents' data conflicts, note the discrepancy clearly.
3. Do NOT mention the background agents. Speak directly as the assistant.
4. Use markdown formatting (bold, lists, etc.) for clarity.
5. Be concise but thorough.""")

    responses_text = "\n\n".join(f"--- Agent Response ---\n{r}" for r in agent_responses)
    user = HumanMessage(
        content=f"Original user message: '{user_message}'\n\nAgent responses:\n{responses_text}"
    )

    try:
        result = await llm.ainvoke([system, user])
        content = result.content
        if isinstance(content, list):
            # Gemini flash models may return list[{'type': 'text', 'text': '...'}]
            return "".join(
                p.get("text") or p.get("content") or "" if isinstance(p, dict) else str(p)
                for p in content
            ).strip()
        return str(content)
    except Exception as e:
        print(f"[Aggregator] Error: {e}")
        return "\n\n".join(agent_responses)  # Fallback: join raw responses
