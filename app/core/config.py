import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ── LangSmith Tracing (enable if LANGCHAIN_API_KEY is set) ──────────────────
# Set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY in .env to activate.
# All LangGraph nodes, tool calls, and LLM invocations will be traced automatically.
_tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
if _tracing_enabled:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGCHAIN_PROJECT", "shopmate-ecommerce-ai"))
    print(f"[LangSmith] Tracing ENABLED -> project: {os.environ['LANGCHAIN_PROJECT']}")
else:
    print("[LangSmith] Tracing DISABLED (set LANGCHAIN_TRACING_V2=true in .env to enable)")


class Settings:
    PROJECT_NAME: str = "E-Commerce Multi-Agent AI Assistant"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Model identifiers for LangChain Google GenAI.
    # Override DEFAULT_MODEL via the GEMINI_MODEL env var if needed.
    DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    FAST_MODEL: str = os.getenv("GEMINI_FAST_MODEL", "gemini-2.0-flash")  # For intent classification (cheap/fast)


settings = Settings()


def get_llm(model: str | None = None, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """Factory to create a LangChain ChatModel backed by Gemini."""
    return ChatGoogleGenerativeAI(
        model=model or settings.DEFAULT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
        convert_system_message_to_human=False,
    )
