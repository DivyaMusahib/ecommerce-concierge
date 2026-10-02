"""
Session Memory - SQLite-backed short-term conversational context.

Replaces the old MockRedisSession (in-process dict) that was wiped on
every server restart. This implementation:
  - Persists across server restarts
  - Works correctly in multi-worker deployments
  - Keeps the last 6 messages (3 turns) per session
  - Thread-safe via SQLite WAL mode
"""
import json
from datetime import datetime
from app.database.db import get_conn


class SQLiteSession:
    """
    SQLite-backed session store. Replaces MockRedisSession.
    API-compatible with the old MockRedisSession so no other code changes needed.
    """

    def get_history(self, session_id: str) -> list[dict]:
        """Retrieve the message history for a session."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT history_json FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return []
        try:
            return json.loads(row["history_json"])
        except Exception:
            return []

    def add_message(self, session_id: str, role: str, content: str):
        """Append a message to the session history, keeping only the last 6."""
        history = self.get_history(session_id)
        history.append({"role": role, "content": content})
        # Keep only last 12 messages (6 turns) to preserve enough cart/checkout context
        if len(history) > 12:
            history = history[-12:]

        with get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (session_id, history_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    history_json = excluded.history_json,
                    updated_at = excluded.updated_at
            """, (session_id, json.dumps(history), datetime.utcnow().isoformat()))

    def clear(self, session_id: str):
        """Clear session history (e.g., on new chat)."""
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


redis_client = SQLiteSession()
