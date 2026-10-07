"""
Auth Routes — register/login endpoints, JWT creation.

Auth routes — register, login, and JWT token creation.
"""
import logging
import os
import time
import uuid

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
logger = logging.getLogger("shopmate.auth")
limiter = Limiter(key_func=get_remote_address)

# JWT secret — MUST be set via JWT_SECRET_KEY env var.
# The server will refuse to start if this is missing — no insecure fallback.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "FATAL: JWT_SECRET_KEY environment variable is not set. "
        "The server cannot start without it. "
        "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
    )
ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": time.time() + 3600 * 24 * 7})  # 7 days
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/auth/register")
@limiter.limit("3/minute")
async def register(request: Request, req: RegisterRequest):
    from sqlalchemy import text

    from app.database.engine import async_session

    async with async_session() as session:
        existing = (await session.execute(
            text("SELECT 1 FROM users WHERE email = :email"),
            {"email": req.email}
        )).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = f"user_{uuid.uuid4().hex[:8]}"
        hashed_pw = get_password_hash(req.password)
        await session.execute(text("""
            INSERT INTO users (user_id, email, password_hash, name, shipping_address)
            VALUES (:uid, :email, :pw, :name, '')
        """), {"uid": user_id, "email": req.email, "pw": hashed_pw, "name": req.name})
        await session.commit()

    # Initialize long-term memory profile
    from app.memory.long_term import ensure_user_exists
    ensure_user_exists(user_id)

    token = create_access_token({"sub": user_id})
    return {"access_token": token, "user_id": user_id, "name": req.name}


@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest):
    from sqlalchemy import text

    from app.database.engine import async_session

    async with async_session() as session:
        row = (await session.execute(
            text("SELECT user_id, name, password_hash FROM users WHERE email = :email"),
            {"email": req.email}
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if not verify_password(req.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": row["user_id"]})
    return {"access_token": token, "user_id": row["user_id"], "name": row["name"]}
