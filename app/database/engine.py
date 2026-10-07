"""
Async SQLAlchemy engine for PostgreSQL.

A single shared engine and session factory for the entire application.
Supabase pgBouncer (transaction pooler) requires statement_cache_size=0
and SSL. Both are set in connect_args below.
"""
import logging
import os
import re
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger("shopmate.engine")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Example: DATABASE_URL=postgresql://user:pass@host/dbname"
    )

# Normalise scheme to the asyncpg dialect
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Percent-encode passwords that contain special characters (common with Supabase)
try:
    _pw_match = re.match(r'^(postgresql\+asyncpg://[^:]+:)(.+?)(@[^@]+)$', DATABASE_URL)
    if _pw_match:
        _prefix, _raw_pw, _suffix = _pw_match.groups()
        if any(c in _raw_pw for c in '[]@:/?#'):
            DATABASE_URL = _prefix + quote(_raw_pw, safe='') + _suffix
except Exception as e:
    logger.warning("URL normalisation warning: %s", e)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=False,
    connect_args={
        "ssl": "require",
        "statement_cache_size": 0,
        "server_settings": {"application_name": "shopmate"},
    },
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a scoped async DB session."""
    async with async_session() as session:
        yield session


async def check_db_connection() -> bool:
    """Health check — returns True if the database is reachable."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        return False
