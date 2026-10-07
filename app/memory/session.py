"""
Session memory — PostgreSQL-backed chat history store.

Keeps the last MAX_MESSAGES messages per session in the sessions/session_messages
tables. The public singleton `redis_client` preserves backward compatibility
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
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        rows = (await session.execute(text("""
            SELECT role, content FROM session_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"sid": session_id, "limit": MAX_MESSAGES})).fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]


async def _pg_add_message(session_id: str, role: str, content: str):
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(text("""
            INSERT INTO sessions (session_id)
            VALUES (:sid)
            ON CONFLICT (session_id) DO UPDATE SET updated_at = NOW()
        """), {"sid": session_id})

        await session.execute(text("""
            INSERT INTO session_messages (session_id, role, content)
            VALUES (:sid, :role, :content)
        """), {"sid": session_id, "role": role, "content": content})

        await session.execute(text("""
            UPDATE sessions
            SET message_count = message_count + 1, updated_at = NOW()
            WHERE session_id = :sid
        """), {"sid": session_id})

        count = (await session.execute(text("""
            SELECT COUNT(*) FROM session_messages WHERE session_id = :sid
        """), {"sid": session_id})).scalar()

        if count and count > MAX_MESSAGES:
            excess = count - MAX_MESSAGES
            logger.info("Pruning %d old messages for session %s", excess, session_id[:16])
            await session.execute(text("""
                DELETE FROM session_messages WHERE id IN (
                    SELECT id FROM session_messages
                    WHERE session_id = :sid
                    ORDER BY created_at ASC
                    LIMIT :excess
                )
            """), {"sid": session_id, "excess": excess})

        await session.commit()


async def _pg_clear(session_id: str):
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM session_messages WHERE session_id = :sid"),
            {"sid": session_id}
        )
        await session.execute(
            text("DELETE FROM sessions WHERE session_id = :sid"),
            {"sid": session_id}
        )
        await session.commit()


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
