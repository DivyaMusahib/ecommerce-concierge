"""
ShopMate — FastAPI application entry point.

Handles CORS, rate limiting, request logging, database initialisation,
and route registration. All routes are available under both /api/v1/ (canonical)
and the root path (backward compatibility with the existing frontend).
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.auth import router as auth_router
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("shopmate")

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://shopmate-ecommerce-concierge.vercel.app",
]
_env_origins = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_origins
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ShopMate starting up...")
    from app.database.db import init_schema, seed_data
    try:
        await init_schema()
        await seed_data()
        logger.info("Database ready.")
    except Exception as e:
        logger.error("Database initialisation failed: %s", e)
        raise
    logger.info("Server ready. CORS origins: %s", ALLOWED_ORIGINS)
    yield
    # Close the asyncpg pool gracefully on shutdown
    from app.database.engine import close_pool
    await close_pool()
    logger.info("ShopMate shutting down.")


app = FastAPI(
    title="ShopMate E-Commerce AI Assistant",
    version="2.0.0",
    description="Multi-agent AI shopping assistant powered by LangGraph and Gemini.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "%s %s -> %d [%sms]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Versioned routes (canonical)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")

# Unversioned routes (backward compatibility)
app.include_router(auth_router)
app.include_router(router)


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    from app.database.engine import check_db_connection
    checks: dict = {"api": "ok"}
    checks["database"] = "ok" if await check_db_connection() else "error: unreachable"
    try:
        from app.core.config import get_llm
        get_llm()
        checks["llm"] = "ok"
    except Exception as e:
        checks["llm"] = f"error: {e}"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks, "version": "2.0.0"}
