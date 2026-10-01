"""
Unit Tests: Database Layer
Tests schema correctness, seeding logic, demo user, migrations.
"""
import json
import pytest
from app.database.db import get_conn


class TestSchema:
    def test_products_table_exists(self):
        with get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "products" in tables

    def test_users_table_has_shipping_address(self):
        with get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        assert "shipping_address" in cols, "shipping_address column missing from users"

    def test_confirmed_orders_has_delivery_fee(self):
        with get_conn() as conn:
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(confirmed_orders)"
            ).fetchall()]
        assert "delivery_fee" in cols, "delivery_fee column missing from confirmed_orders"

    def test_draft_orders_table_exists(self):
        with get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "draft_orders" in tables, "draft_orders table missing"

    def test_all_required_tables_exist(self):
        required = {
            "products", "users", "orders", "price_history",
            "coupons", "carts", "draft_orders", "confirmed_orders",
            "complaints", "refunds", "sessions",
        }
        with get_conn() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        missing = required - tables
        assert not missing, f"Missing tables: {missing}"


class TestDemoUser:
    def test_demo_user_seeded(self):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = 'user_1'"
            ).fetchone()
        assert row is not None, "Demo user user_1 not seeded"

    def test_demo_user_email(self):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT email FROM users WHERE user_id = 'user_1'"
            ).fetchone()
        assert row["email"] == "demo@gmail.com", f"Expected demo@gmail.com, got {row['email']}"

    def test_demo_user_bcrypt_hash(self):
        """Password hash must look like a bcrypt hash ($2b$...)."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = 'user_1'"
            ).fetchone()
        assert row["password_hash"].startswith("$2"), \
            "Password is not bcrypt-hashed (should start with $2b$)"

    def test_only_demo_user_exists(self):
        """Fresh DB should have exactly 1 user — the demo user."""
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == 1, f"Expected 1 user, got {count}"

    def test_demo_orders_belong_to_user_1(self):
        """All seeded orders must belong to user_1 only."""
        with get_conn() as conn:
            other_orders = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id != 'user_1'"
            ).fetchone()[0]
        assert other_orders == 0, f"{other_orders} orders found for non-demo users"


class TestSeedData:
    def test_products_seeded(self):
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        assert count >= 20, f"Expected ≥20 products, got {count}"

    def test_coupons_seeded(self):
        with get_conn() as conn:
            codes = [r[0] for r in conn.execute("SELECT code FROM coupons").fetchall()]
        assert "SAVE10" in codes
        assert "FLAT500" in codes
        assert "NEWUSER" in codes

    def test_mock_orders_count(self):
        """Three demo orders: 123, 456, 999."""
        with get_conn() as conn:
            ids = [r[0] for r in conn.execute("SELECT order_id FROM orders").fetchall()]
        assert set(ids) == {"123", "456", "999"}, f"Unexpected order IDs: {ids}"

    def test_price_history_seeded(self):
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        assert count >= 10
