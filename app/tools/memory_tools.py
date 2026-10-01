"""
Memory Tools - LangChain tools for the AI to autonomously read/write long-term user memory.

These are injected into agents so the AI can:
  - Remember a user's budget, preferred brands, allergies, etc.
  - Recall previously stated preferences mid-conversation
  - Forget specific facts the user asks to remove
"""
from contextvars import ContextVar
from langchain_core.tools import tool

# The supervisor injects user_id via this ContextVar before agent dispatch
_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="default")


def set_memory_user(user_id: str) -> None:
    """Call this before invoking any agent that has memory tools."""
    _current_user_id.set(user_id)


@tool
def remember_user_preference(key: str, value: str) -> str:
    """
    Save an important fact or preference about the user to long-term memory.
    Use this whenever the user mentions something persistent like their budget,
    preferred brands, allergies, shipping preferences, or any personal detail
    they want remembered. Key should be snake_case (e.g., 'preferred_budget',
    'favorite_brand', 'shoe_size').
    """
    from app.memory.long_term import save_preference
    user_id = _current_user_id.get()
    if user_id == "guest":
        return f"Noted: '{key}' = '{value}'. (Note: As a guest, this preference will only last for this chat session)."
    
    updated = save_preference(user_id, key, value)
    return f"Remembered: '{key}' = '{value}'. You now have {len(updated)} saved preferences."


@tool
def recall_user_preferences() -> str:
    """
    Retrieve all long-term preferences and profile info saved for this user.
    Use this to recall what you know about the user before making recommendations.
    """
    from app.memory.long_term import get_user_profile
    user_id = _current_user_id.get()
    if user_id == "guest":
        return "Guest user - no long-term memory available. Rely on the current chat history for context."
        
    profile = get_user_profile(user_id)
    if not profile:
        return "No memory found for this user yet."
    prefs = profile.get("preferences", {})
    if not prefs:
        return f"User profile: name={profile.get('name')}. No preferences saved yet."
    pref_lines = "\n".join(f"  - {k}: {v}" for k, v in prefs.items())
    return (
        f"User: {profile.get('name')} \n"
        f"Saved preferences:\n{pref_lines}"
    )


@tool
def forget_user_preference(key: str) -> str:
    """
    Remove a specific preference from the user's long-term memory.
    Use this when a user says 'forget that' or 'that's no longer relevant'.
    """
    from app.memory.long_term import delete_preference
    user_id = _current_user_id.get()
    if user_id == "guest":
        return f"Guest user - preference '{key}' will not persist anyway."
        
    updated = delete_preference(user_id, key)
    return f"Forgot preference '{key}'. Remaining preferences: {len(updated)}."
