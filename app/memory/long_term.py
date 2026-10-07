"""
Long-term user memory — PostgreSQL-backed user profiles and preferences.

Uses raw asyncpg (no SQLAlchemy) so that statement_cache_size=0 is respected
and no prepared statements are sent to pgBouncer (transaction mode).

Async-native functions (async_*) should be used from async FastAPI routes.
Sync wrappers are kept for LangChain tool callbacks that run synchronously.
"""
import asyncio
import concurrent.futures
import logging

logger = logging.getLogger("shopmate.long_term")


def _run(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ── Private async implementations ─────────────────────────────────────────────

async def _pg_get_profile(user_id: str) -> dict | None:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        if not row:
            return None
        prefs_rows = await conn.fetch(
            "SELECT pref_key, pref_value FROM user_preferences WHERE user_id = $1",
            user_id,
        )
    return {
        "user_id": user_id,
        "name": row["name"],
        "shipping_address": row["shipping_address"] or "",
        "preferences": {r["pref_key"]: r["pref_value"] for r in prefs_rows},
        "updated_at": str(row["updated_at"]) if row["updated_at"] else "",
    }


async def _pg_ensure_user(user_id: str) -> None:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, email, password_hash, name)
            VALUES ($1, $2, '', $1)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, f"{user_id}@guest.local")


async def _pg_save_pref(user_id: str, key: str, value: str) -> dict:
    await _pg_ensure_user(user_id)
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_preferences (user_id, pref_key, pref_value, source, updated_at)
            VALUES ($1, $2, $3, 'agent', NOW())
            ON CONFLICT (user_id, pref_key) DO UPDATE
            SET pref_value = EXCLUDED.pref_value, updated_at = NOW()
        """, user_id, key, value)
        rows = await conn.fetch(
            "SELECT pref_key, pref_value FROM user_preferences WHERE user_id = $1",
            user_id,
        )
    return {r["pref_key"]: r["pref_value"] for r in rows}


async def _pg_delete_pref(user_id: str, key: str) -> dict:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_preferences WHERE user_id = $1 AND pref_key = $2",
            user_id, key,
        )
        rows = await conn.fetch(
            "SELECT pref_key, pref_value FROM user_preferences WHERE user_id = $1",
            user_id,
        )
    return {r["pref_key"]: r["pref_value"] for r in rows}


async def _pg_clear_prefs(user_id: str) -> bool:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_preferences WHERE user_id = $1", user_id
        )
    return True


async def _pg_update_field(user_id: str, field: str, value: str) -> bool:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {field} = $1, updated_at = NOW() WHERE user_id = $2",
            value, user_id,
        )
    return True


# ── Public async API (use from async routes / LangGraph nodes) ────────────────

async def async_get_user_profile(user_id: str) -> dict | None:
    """Async — await from async contexts."""
    return await _pg_get_profile(user_id)


async def async_ensure_user_exists(user_id: str) -> None:
    """Async — await from async contexts."""
    await _pg_ensure_user(user_id)


async def async_save_preference(user_id: str, key: str, value: str) -> dict:
    """Async — await from async contexts."""
    return await _pg_save_pref(user_id, key, value)


async def async_delete_preference(user_id: str, key: str) -> dict:
    """Async — await from async contexts."""
    return await _pg_delete_pref(user_id, key)


async def async_clear_all_preferences(user_id: str) -> bool:
    """Async — await from async contexts."""
    return await _pg_clear_prefs(user_id)


async def async_update_profile_field(user_id: str, field: str, value) -> bool:
    """Async — await from async contexts."""
    if field not in {"name", "shipping_address"}:
        return False
    return await _pg_update_field(user_id, field, str(value))


# ── Public sync API (for LangChain tool callbacks) ────────────────────────────

def get_user_profile(user_id: str) -> dict | None:
    """Return the full user profile including preferences."""
    return _run(_pg_get_profile(user_id))


def ensure_user_exists(user_id: str) -> None:
    """Create a minimal user record if one does not exist yet."""
    _run(_pg_ensure_user(user_id))


def save_preference(user_id: str, key: str, value: str) -> dict:
    """Save or update a single preference. Returns updated preferences dict."""
    return _run(_pg_save_pref(user_id, key, value))


def delete_preference(user_id: str, key: str) -> dict:
    """Remove a preference key. Returns updated preferences dict."""
    return _run(_pg_delete_pref(user_id, key))


def clear_all_preferences(user_id: str) -> bool:
    """Delete all preferences for a user."""
    return _run(_pg_clear_prefs(user_id))


def update_profile_field(user_id: str, field: str, value) -> bool:
    """Update name or shipping_address on the user record."""
    if field not in {"name", "shipping_address"}:
        return False
    return _run(_pg_update_field(user_id, field, str(value)))


def get_all_users() -> list[dict]:
    """Return all user profiles (admin/debug use only)."""
    async def _all():
        from app.database.engine import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            uids = [r["user_id"] for r in await conn.fetch("SELECT user_id FROM users")]
        return [p for uid in uids if (p := _run(_pg_get_profile(uid)))]
    return _run(_all())
