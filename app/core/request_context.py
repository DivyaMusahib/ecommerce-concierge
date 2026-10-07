"""
Single request-scoped context object.
  cart_api.py, memory_tools.py, order_api.py, complaint_api.py

Passed explicitly to every tool factory — no global mutable state.
This eliminates cross-request contamination in concurrent scenarios.
"""
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    user_id: str
    session_id: str
    is_guest: bool = field(init=False)

    def __post_init__(self):
        self.is_guest = self.user_id in ("guest", "default") or self.user_id.startswith("anon_")
