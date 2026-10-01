"""
ShopMate FastAPI Application Entry Point.

Features:
- Rate limiting via slowapi (10 requests/minute per IP on /chat)
- Structured request/response logging with latency tracking
- CORS for local Vite frontend (configurable via CORS_ORIGINS env var)
- LangSmith tracing enabled via config.py
- Startup lifespan ensures DB is initialized before serving requests
"""
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.routes import router
from app.api.auth import router as auth_router

# ── Structured Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("shopmate")

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# ── CORS Origins (configurable via environment) ───────────────────────────────
_default_origins = [
    "http://localhost:5173", 
    "http://127.0.0.1:5173",
    "https://shopmate-ecommerce-concierge.vercel.app"
]
_env_origins = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_origins
)


# ── Startup / Shutdown Lifespan ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB is initialized before serving any requests."""
    logger.info("🚀 ShopMate starting up — initializing database...")
    from app.database.db import init_db
    init_db()
    logger.info("✅ Database ready. Allowed CORS origins: %s", ALLOWED_ORIGINS)
    yield
    logger.info("🛑 ShopMate shutting down.")


# ── App Init ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShopMate E-Commerce AI Assistant",
    version="2.0.0",
    description="Production-grade multi-agent AI assistant with LangGraph orchestration.",
    lifespan=lifespan,
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


# ── Request Logging Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        f"{request.method} {request.url.path} "
        f"-> {response.status_code} [{duration_ms}ms] "
        f"client={request.client.host if request.client else 'unknown'}"
    )
    return response


# ── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "ShopMate AI Assistant is running!",
        "version": "2.0.0",
    }
