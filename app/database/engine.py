"""
Async PostgreSQL connection pool — raw asyncpg (no SQLAlchemy).

SQLAlchemy's asyncpg dialect unconditionally uses prepared statements even
for internal queries (e.g. 'select pg_catalog.version()'), making it
fundamentally incompatible with Supabase's pgBouncer in transaction mode.

Raw asyncpg with statement_cache_size=0 uses the simple-query protocol:
no PREPARE statements are ever sent, so pgBouncer works correctly.
"""
import logging
import os
import re
from urllib.parse import quote

import asyncpg

logger = logging.getLogger("shopmate.db")

# ── URL normalisation ─────────────────────────────────────────────────────────

_RAW_URL = os.getenv("DATABASE_URL")
if not _RAW_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Example: DATABASE_URL=postgresql://user:pass@host/dbname"
    )

# Strip SQLAlchemy dialect prefix if present
DATABASE_URL: str = (
    _RAW_URL
    .replace("postgresql+asyncpg://", "postgresql://", 1)
    .replace("postgres+asyncpg://",   "postgresql://", 1)
    .replace("postgres://",            "postgresql://", 1)
)

# Percent-encode passwords that contain special characters (common with Supabase)
try:
    _pw_match = re.match(r'^(postgresql://[^:]+:)(.+?)(@[^@]+)$', DATABASE_URL)
    if _pw_match:
        _prefix, _raw_pw, _suffix = _pw_match.groups()
        if any(c in _raw_pw for c in '[]@:/?#'):
            DATABASE_URL = _prefix + quote(_raw_pw, safe='') + _suffix
except Exception as e:
    logger.warning("URL normalisation warning: %s", e)

# ── Connection pool ───────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared asyncpg pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            # statement_cache_size=0 → simple-query protocol, no PREPARE sent.
            # This is the ONLY correct setting for pgBouncer transaction mode.
            statement_cache_size=0,
            ssl="require",
            server_settings={"application_name": "shopmate"},
        )
    return _pool


async def close_pool() -> None:
    """Gracefully close the pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def check_db_connection() -> bool:
    """Health check — returns True if the database is reachable."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        return False
