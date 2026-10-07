"""
Session memory — PostgreSQL-backed chat history store.

Keeps the last MAX_MESSAGES messages per session in the sessions/session_messages
tables. Uses raw asyncpg (no SQLAlchemy).

The public singleton `redis_client` preserves backward compatibility
with existing import sites.
"""
import asyncio
import concurrent.futures
import logging

logger = logging.getLogger("shopmate.session")

MAX_MESSAGES = 20


def _run(coro):
    """Run an async coroutine from synchronous context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _pg_get_history(session_id: str) -> list[dict]:
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM session_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT $2
        """, session_id, MAX_MESSAGES)
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _pg_add_message(session_id: str, role: str, content: str):
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sessions (session_id)
            VALUES ($1)
            ON CONFLICT (session_id) DO UPDATE SET updated_at = NOW()
        """, session_id)

        await conn.execute("""
            INSERT INTO session_messages (session_id, role, content)
            VALUES ($1, $2, $3)
        """, session_id, role, content)

        await conn.execute("""
            UPDATE sessions
            SET message_count = message_count + 1, updated_at = NOW()
            WHERE session_id = $1
        """, session_id)

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = $1",
            session_id,
        )

        if count and count > MAX_MESSAGES:
            excess = count - MAX_MESSAGES
            logger.info("Pruning %d old messages for session %s", excess, session_id[:16])
            await conn.execute("""
                DELETE FROM session_messages WHERE id IN (
                    SELECT id FROM session_messages
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    LIMIT $2
                )
            """, session_id, excess)


async def _pg_clear(session_id: str):
    from app.database.engine import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM session_messages WHERE session_id = $1", session_id
        )
        await conn.execute(
            "DELETE FROM sessions WHERE session_id = $1", session_id
        )


class SessionStore:
    """PostgreSQL-backed session store for chat history."""

    def get_history(self, session_id: str) -> list[dict]:
        """Return the last MAX_MESSAGES messages for a session."""
        return _run(_pg_get_history(session_id))

    def add_message(self, session_id: str, role: str, content: str):
        """Append a message to the session history."""
        _run(_pg_add_message(session_id, role, content))

    def clear(self, session_id: str):
        """Clear all messages for a session."""
        _run(_pg_clear(session_id))


# Singleton — named redis_client for backward compat with existing import sites
redis_client = SessionStore()
