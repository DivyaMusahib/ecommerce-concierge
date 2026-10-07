"""
Structured agent output envelope.

Each agent now returns an AgentResult instead of a raw string.
This gives the supervisor structured metadata to use in routing,
aggregation, and evaluation without relying on string parsing.
"""
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(str, Enum):
    SUCCESS = "success"        # Agent answered and tools executed OK
    NEEDS_CLARIFICATION = "needs_clarification"  # Agent needs user input
    BLOCKED = "blocked"        # Guest restriction or missing auth
    ERROR = "error"            # Tool or LLM failure


@dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    response: str
    # Optional metadata for the supervisor
    tool_calls_made: list[str] = field(default_factory=list)
    requires_confirmation: bool = False   # True when checkout summary was generated
    checkout_payload: dict | None = None  # Forwarded to UI if requires_confirmation
