"""
Long-Term Memory - SQLite-backed persistent user profiles.

Stores user identity + arbitrary key-value preferences per user.
The AI can read and write preferences via LangChain tools, so facts
the user mentions (budget, brands, allergies, etc.) persist across sessions.

Schema:
  users(user_id, name, default_shipping, preferences_json, updated_at)
"""
import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "users.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Safe concurrent reads across threads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables and seed demo users if not already present."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          TEXT PRIMARY KEY,
                name             TEXT,
                preferences_json TEXT DEFAULT '{}',
                updated_at       TEXT
            )
        """)
        # Seed demo user to match the auth DB user_1
        conn.execute("""
            INSERT OR IGNORE INTO users
                (user_id, name, preferences_json, updated_at)
            VALUES
                ('user_1', 'Demo User', '{"preferred_budget": "flexible", "interests": "electronics, gadgets"}', ?)
        """, (datetime.utcnow().isoformat(),))
        conn.execute("""
            INSERT OR IGNORE INTO users
                (user_id, name, preferences_json, updated_at)
            VALUES
                ('user_2', 'Bob', '{"preferred_brands": "Samsung, Apple"}', ?)
        """, (datetime.utcnow().isoformat(),))
        conn.commit()


# Auto-initialize on import
init_db()


# ── Read ────────────────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> dict | None:
    """Return the full user profile including parsed preferences."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    if not row:
        return None

    prefs = {}
    try:
        prefs = json.loads(row["preferences_json"] or "{}")
    except json.JSONDecodeError:
        pass

    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "preferences": prefs,
        "updated_at": row["updated_at"],
    }


def get_all_users() -> list[dict]:
    """Return all user profiles (for admin/debug)."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
    result = []
    for row in rows:
        prefs = {}
        try:
            prefs = json.loads(row["preferences_json"] or "{}")
        except json.JSONDecodeError:
            pass
        result.append({
            "user_id": row["user_id"],
            "name": row["name"],
            "preferences": prefs,
            "updated_at": row["updated_at"],
        })
    return result


# ── Write ───────────────────────────────────────────────────────────────────

def ensure_user_exists(user_id: str) -> None:
    """Create a minimal user record if one doesn't exist yet."""
    with _connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, name, preferences_json, updated_at)
            VALUES (?, ?, '{}', ?)
        """, (user_id, user_id, datetime.utcnow().isoformat()))
        conn.commit()


def save_preference(user_id: str, key: str, value: str) -> dict:
    """
    Save or update a single preference for a user.
    Creates the user automatically if they don't exist.
    Returns the full updated preferences dict.
    """
    ensure_user_exists(user_id)

    with _connect() as conn:
        row = conn.execute(
            "SELECT preferences_json FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        prefs = {}
        try:
            prefs = json.loads(row["preferences_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        prefs[key] = value
        conn.execute("""
            UPDATE users SET preferences_json = ?, updated_at = ? WHERE user_id = ?
        """, (json.dumps(prefs), datetime.utcnow().isoformat(), user_id))
        conn.commit()

    return prefs


def delete_preference(user_id: str, key: str) -> dict:
    """Remove a single preference key. Returns updated preferences."""
    ensure_user_exists(user_id)

    with _connect() as conn:
        row = conn.execute(
            "SELECT preferences_json FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        prefs = {}
        try:
            prefs = json.loads(row["preferences_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        prefs.pop(key, None)
        conn.execute("""
            UPDATE users SET preferences_json = ?, updated_at = ? WHERE user_id = ?
        """, (json.dumps(prefs), datetime.utcnow().isoformat(), user_id))
        conn.commit()

    return prefs


def clear_all_preferences(user_id: str) -> bool:
    """Wipe all preferences for a user (keep profile fields). Returns True on success."""
    ensure_user_exists(user_id)
    with _connect() as conn:
        conn.execute("""
            UPDATE users SET preferences_json = '{}', updated_at = ? WHERE user_id = ?
        """, (datetime.utcnow().isoformat(), user_id))
        conn.commit()
    return True


def update_profile_field(user_id: str, field: str, value) -> bool:
    """Update a top-level profile field. Currently only 'name' is supported
    in the users.db (long-term memory) table. Shipping address is managed
    separately in shopmate.db via the cart/checkout flow."""
    allowed = {"name"}
    if field not in allowed:
        return False
    ensure_user_exists(user_id)
    with _connect() as conn:
        conn.execute(
            f"UPDATE users SET {field} = ?, updated_at = ? WHERE user_id = ?",
            (value, datetime.utcnow().isoformat(), user_id)
        )
        conn.commit()
    return True
