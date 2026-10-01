"""
Unit Tests: Authentication (bcrypt, JWT, register/login)
Tests password hashing, token creation, and auth edge cases.
"""
import pytest
import time
import jwt

from app.api.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
)
from app.database.db import get_conn


class TestPasswordHashing:
    def test_bcrypt_hash_format(self):
        h = get_password_hash("testpass123")
        assert h.startswith("$2"), "bcrypt hash must start with $2b$"

    def test_correct_password_verifies(self):
        h = get_password_hash("mypassword")
        assert verify_password("mypassword", h) is True

    def test_wrong_password_rejected(self):
        h = get_password_hash("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_empty_password_rejected(self):
        h = get_password_hash("validpass")
        assert verify_password("", h) is False

    def test_hashes_are_unique(self):
        """Two hashes of the same password should differ (bcrypt salting)."""
        h1 = get_password_hash("same")
        h2 = get_password_hash("same")
        assert h1 != h2, "bcrypt should produce unique salted hashes"

    def test_demo_user_password_works(self):
        """The seeded demo@gmail.com user should accept password 'demo'."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE email = 'demo@gmail.com'"
            ).fetchone()
        assert row is not None, "demo@gmail.com not found in DB"
        assert verify_password("demo", row["password_hash"]) is True

    def test_demo_user_wrong_password_fails(self):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE email = 'demo@gmail.com'"
            ).fetchone()
        assert verify_password("demo123", row["password_hash"]) is False
        assert verify_password("Demo", row["password_hash"]) is False


class TestJWT:
    def test_token_created_successfully(self):
        token = create_access_token({"sub": "user_1"})
        assert isinstance(token, str) and len(token) > 20

    def test_token_contains_subject(self):
        token = create_access_token({"sub": "user_test_99"})
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "user_test_99"

    def test_token_has_expiry(self):
        token = create_access_token({"sub": "user_1"})
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in decoded
        # Expiry should be in the future (7 days from now)
        assert decoded["exp"] > time.time()
        # And not more than 8 days in the future
        assert decoded["exp"] < time.time() + 3600 * 24 * 8

    def test_tampered_token_rejected(self):
        token = create_access_token({"sub": "user_1"})
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(Exception):
            jwt.decode(tampered, SECRET_KEY, algorithms=[ALGORITHM])

    def test_secret_key_from_env(self):
        """SECRET_KEY should not be the old hardcoded value."""
        assert SECRET_KEY != "super_secret_shopmate_key", \
            "JWT secret key was not updated from the old hardcoded value"
        assert len(SECRET_KEY) > 10
