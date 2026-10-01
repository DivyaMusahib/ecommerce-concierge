"""
conftest.py — shared pytest fixtures for ShopMate test suite.

Creates a fresh in-memory SQLite test database for every test session,
ensuring tests are fully isolated from the production data/shopmate.db.
"""
import json
import os
import sys
import pytest
import sqlite3
from datetime import datetime
from unittest.mock import patch

# ── Make sure the project root is on sys.path ─────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Point the DB at a temp path BEFORE any app module is imported ─────────────
TEST_DB = os.path.join(os.path.dirname(__file__), "test_shopmate.db")

import app.database.db as _db_module
_db_module.DB_PATH = TEST_DB           # Redirect to test DB

# Now safe to import the rest of the app
from app.database.db import get_conn, init_db
from app.api.auth import get_password_hash, verify_password


@pytest.fixture(autouse=True, scope="session")
def fresh_db():
    """Create a clean test database once for the whole session."""
    # Remove stale test DB if it exists
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except PermissionError:
            pass
    init_db()
    yield
    # Teardown — ignore Windows file-lock errors on cleanup
    try:
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
    except (PermissionError, OSError):
        pass  # File will be cleaned up on next run



@pytest.fixture
def demo_user():
    """Return the seeded demo user record."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = 'user_1'").fetchone()
    return dict(row)


@pytest.fixture
def test_session_id():
    return "test_session_pytest"


@pytest.fixture
def guest_user():
    return "guest"


@pytest.fixture
def demo_user_id():
    return "user_1"
