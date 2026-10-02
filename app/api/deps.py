"""
FastAPI Dependencies - Shared auth utilities.

Provides a reusable JWT validation dependency for protected routes.
If a valid Bearer token is present in the Authorization header, the
user_id is extracted from the token payload (cannot be spoofed).
Routes can then use this to enforce the authenticated user_id instead
of blindly trusting the request body.
"""
import os
import jwt
from fastapi import Header, HTTPException
from typing import Optional

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "shopmate_dev_secret_change_in_production")
ALGORITHM = "HS256"


def get_user_from_token(authorization: Optional[str] = Header(default=None)) -> str | None:
    """
    Extract and validate user_id from a Bearer JWT token.

    Returns:
      - The authenticated user_id string if a valid token is provided.
      - None if no Authorization header is present (guest/body fallback).

    Raises:
      - 401 HTTPException if a token IS provided but is invalid or expired.
    """
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None

    token = authorization[7:].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject claim.")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")
