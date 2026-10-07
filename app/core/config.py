"""
Application configuration & LLM factory."""
import logging
import os

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger("shopmate.config")

# LangSmith Tracing
_tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
if _tracing_enabled:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGCHAIN_PROJECT", "shopmate-ecommerce-ai"))
    logger.info("[LangSmith] Tracing ENABLED -> project: %s", os.environ['LANGCHAIN_PROJECT'])
else:
    logger.info("[LangSmith] Tracing DISABLED (set LANGCHAIN_TRACING_V2=true in .env to enable)")

# Settings

class Settings:
    PROJECT_NAME: str = "E-Commerce Multi-Agent AI Assistant"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    FAST_MODEL: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")

settings = Settings()

# Token Tracking

class TokenTracker(BaseCallbackHandler):
    """
    Lightweight callback that logs per-call token usage and accumulates
    session totals. Cost estimates are based on Gemini 2.0 Flash pricing.
    """
    COST_PER_1M_INPUT = 0.075
    COST_PER_1M_OUTPUT = 0.30

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def on_llm_end(self, response, **kwargs):
        try:
            usage = {}
            if response.llm_output:
                usage = (response.llm_output.get("usage_metadata", {})
                         or response.llm_output.get("usage", {}))
            in_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out_tok = usage.get("output_tokens", usage.get("completion_tokens", 0))
            self.total_input_tokens += in_tok
            self.total_output_tokens += out_tok
            self.total_calls += 1
            est_cost = (in_tok * self.COST_PER_1M_INPUT
                        + out_tok * self.COST_PER_1M_OUTPUT) / 1_000_000
            logger.debug("[LLM] call=%d in=%d out=%d est_cost=$%.5f",
                         self.total_calls, in_tok, out_tok, est_cost)
        except Exception:
            pass  # Never crash the request due to tracking failure

    def get_stats(self) -> dict:
        total_cost = (
            self.total_input_tokens * self.COST_PER_1M_INPUT
            + self.total_output_tokens * self.COST_PER_1M_OUTPUT
        ) / 1_000_000
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(total_cost, 6),
        }

# Singleton tracker
_token_tracker = TokenTracker()

def get_token_stats() -> dict:
    """Return accumulated token usage stats."""
    return _token_tracker.get_stats()

def reset_token_stats() -> None:
    """Reset the token tracker (useful for testing)."""
    global _token_tracker
    _token_tracker = TokenTracker()

# LLM Factory

def get_llm(model: str | None = None, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """
    Factory to create a LangChain ChatModel backed by Gemini.
    Token tracking callback is injected automatically.
    """
    return ChatGoogleGenerativeAI(
        model=model or settings.DEFAULT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
        convert_system_message_to_human=False,
        callbacks=[_token_tracker],
    )
