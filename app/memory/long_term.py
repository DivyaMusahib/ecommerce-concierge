"""
Long-term user memory — PostgreSQL-backed user profiles and preferences.

Stores per-user preferences as individual rows so concurrent agent writes
never clobber each other. All operations are synchronous wrappers around
async PostgreSQL queries.
"""
import asyncio
import concurrent.futures
import logging

logger = logging.getLogger("shopmate.long_term")


async def get_user_profile(user_id: str) -> dict | None:
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        row = (await session.execute(
            text("SELECT * FROM users WHERE user_id = :uid"), {"uid": user_id}
        )).mappings().fetchone()
        if not row:
            return None
        prefs_rows = (await session.execute(
            text("SELECT pref_key, pref_value FROM user_preferences WHERE user_id = :uid"),
            {"uid": user_id}
        )).fetchall()
    return {
        "user_id": user_id,
        "name": row["name"],
        "shipping_address": row.get("shipping_address") or "",
        "preferences": {r[0]: r[1] for r in prefs_rows},
        "updated_at": str(row.get("updated_at", "")),
    }


async def ensure_user_exists(user_id: str):
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(text("""
            INSERT INTO users (user_id, email, password_hash, name)
            VALUES (:uid, :email, '', :uid)
            ON CONFLICT (user_id) DO NOTHING
        """), {"uid": user_id, "email": f"{user_id}@guest.local"})
        await session.commit()


async def save_preference(user_id: str, key: str, value: str) -> dict:
    from sqlalchemy import text

    from app.database.engine import async_session
    await ensure_user_exists(user_id)
    async with async_session() as session:
        await session.execute(text("""
            INSERT INTO user_preferences (user_id, pref_key, pref_value, source, updated_at)
            VALUES (:uid, :k, :v, 'agent', NOW())
            ON CONFLICT (user_id, pref_key) DO UPDATE
            SET pref_value = EXCLUDED.pref_value, updated_at = NOW()
        """), {"uid": user_id, "k": key, "v": value})
        await session.commit()
        rows = (await session.execute(
            text("SELECT pref_key, pref_value FROM user_preferences WHERE user_id = :uid"),
            {"uid": user_id}
        )).fetchall()
    return {r[0]: r[1] for r in rows}


async def delete_preference(user_id: str, key: str) -> dict:
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(text("""
            DELETE FROM user_preferences WHERE user_id = :uid AND pref_key = :k
        """), {"uid": user_id, "k": key})
        await session.commit()
        rows = (await session.execute(
            text("SELECT pref_key, pref_value FROM user_preferences WHERE user_id = :uid"),
            {"uid": user_id}
        )).fetchall()
    return {r[0]: r[1] for r in rows}


async def update_profile_field(user_id: str, field: str, value: str) -> bool:
    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(
            text(f"UPDATE users SET {field} = :v, updated_at = NOW() WHERE user_id = :uid"),
            {"v": value, "uid": user_id}
        )
        await session.commit()
    return True


async def clear_all_preferences(user_id: str) -> bool:
    """Delete all preferences for a user."""
    from sqlalchemy import text
    from app.database.engine import async_session
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM user_preferences WHERE user_id = :uid"), {"uid": user_id}
        )
        await session.commit()
    return True


async def get_all_users() -> list[dict]:
    """Return all user profiles (admin/debug use only)."""
    from sqlalchemy import text
    from app.database.engine import async_session
    async with async_session() as session:
        uids = (await session.execute(text("SELECT user_id FROM users"))).scalars().fetchall()
    return [p for uid in uids if (p := await get_user_profile(uid))]
