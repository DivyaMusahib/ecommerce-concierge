import os
import time
import bcrypt
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database.db import get_conn
import uuid
from datetime import datetime

router = APIRouter()

# JWT secret loaded from environment with a secure fallback
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "shopmate_dev_secret_change_in_production")
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
def register(req: RegisterRequest):
    with get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (req.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = f"user_{uuid.uuid4().hex[:8]}"
        hashed_pw = get_password_hash(req.password)
        conn.execute("""
            INSERT INTO users (user_id, email, password_hash, name, created_at, shipping_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, req.email, hashed_pw, req.name, datetime.utcnow().isoformat(), ""))
        conn.commit()

    # Initialize long term memory profile
    from app.memory.long_term import ensure_user_exists, update_profile_field
    ensure_user_exists(user_id)
    update_profile_field(user_id, "name", req.name)

    token = create_access_token({"sub": user_id})
    return {"access_token": token, "user_id": user_id, "name": req.name}


@router.post("/auth/login")
def login(req: LoginRequest):
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        try:
            if not verify_password(req.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user["user_id"]})
    return {"access_token": token, "user_id": user["user_id"], "name": user["name"]}
