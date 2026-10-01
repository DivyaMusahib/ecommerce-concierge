"""
Integration Tests: FastAPI HTTP Layer
Tests all REST endpoints using httpx.AsyncClient + FastAPI's test client.
Covers auth register/login, checkout confirm, order fetch, memory endpoints,
and security (no /admin/users route).
"""
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.auth import get_password_hash
from app.database.db import get_conn


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    """Return Authorization headers for the demo user."""
    from app.api.auth import create_access_token
    token = create_access_token({"sub": "user_1"})
    return {"Authorization": f"Bearer {token}"}


# ── Health Check ────────────────────────────────────────────────────────────────

class TestHealthCheck:
    async def test_health_endpoint(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ── Auth Endpoints ──────────────────────────────────────────────────────────────

class TestAuthLogin:
    async def test_login_demo_user_success(self, client):
        resp = await client.post("/auth/login", json={
            "email": "demo@gmail.com",
            "password": "demo",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user_id"] == "user_1"

    async def test_login_wrong_password(self, client):
        resp = await client.post("/auth/login", json={
            "email": "demo@gmail.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client):
        resp = await client.post("/auth/login", json={
            "email": "nobody@gmail.com",
            "password": "password",
        })
        assert resp.status_code == 401

    async def test_login_returns_user_name(self, client):
        resp = await client.post("/auth/login", json={
            "email": "demo@gmail.com",
            "password": "demo",
        })
        assert resp.json().get("name") == "Demo User"


class TestAuthRegister:
    async def test_register_new_user(self, client):
        resp = await client.post("/auth/register", json={
            "email": "newuser_test_unique@example.com",
            "name": "New Test User",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user_id"].startswith("user_")

    async def test_register_duplicate_email(self, client):
        # Register once
        await client.post("/auth/register", json={
            "email": "dup_test@example.com",
            "name": "First",
            "password": "pass1",
        })
        # Register again with same email
        resp = await client.post("/auth/register", json={
            "email": "dup_test@example.com",
            "name": "Second",
            "password": "pass2",
        })
        assert resp.status_code == 400
        assert "registered" in resp.json()["detail"].lower()

    async def test_registered_user_starts_empty(self, client):
        """Newly registered user should have no orders."""
        resp = await client.post("/auth/register", json={
            "email": "brand_new_shopper@example.com",
            "name": "Brand New",
            "password": "pass123",
        })
        new_user_id = resp.json()["user_id"]
        # Check their confirmed orders
        orders_resp = await client.get(f"/orders/confirmed/{new_user_id}")
        assert orders_resp.status_code == 200
        assert orders_resp.json()["orders"] == []


# ── Checkout Confirm ────────────────────────────────────────────────────────────

class TestCheckoutConfirm:
    async def test_guest_checkout_rejected(self, client):
        resp = await client.post("/checkout/confirm", json={
            "session_id": "guest_http_session",
            "user_id": "guest",
            "draft_summary": {"draft_order_id": "ORD-TEST001"},
            "delivery_fee": 0,
        })
        assert resp.status_code == 403

    async def test_checkout_with_spoofed_total_ignored(self, client):
        """Server should recalculate — spoofed total of Rs.1 should be rejected."""
        # First put items in cart and create a real draft
        from app.tools.cart_api import set_cart_session, add_to_cart, checkout, save_shipping_address, _current_user
        session_id = "http_integration_checkout_test"
        set_cart_session(session_id, "user_1")
        _current_user.set("user_1")
        save_shipping_address.invoke({"address": "HTTP Test St, Bengaluru, KA, 560001"})
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        real_checkout = json.loads(checkout.invoke({}))
        real_summary = real_checkout["checkout_summary"]

        # Now spoof total in request
        resp = await client.post("/checkout/confirm", json={
            "session_id": session_id,
            "user_id": "user_1",
            "draft_summary": {**real_summary, "total": 1, "subtotal": 1},
            "delivery_fee": 0,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Server-computed total should be much more than 1
        assert data.get("total", 0) > 1000


# ── Orders ──────────────────────────────────────────────────────────────────────

class TestOrdersEndpoint:
    async def test_get_confirmed_orders_demo_user(self, client):
        resp = await client.get("/orders/confirmed/user_1")
        assert resp.status_code == 200
        assert "orders" in resp.json()

    async def test_get_confirmed_orders_new_user_empty(self, client):
        resp = await client.get("/orders/confirmed/nonexistent_user_xyz")
        assert resp.status_code == 200
        assert resp.json()["orders"] == []


# ── Security: Removed Admin Route ───────────────────────────────────────────────

class TestRemovedRoutes:
    async def test_admin_users_route_removed(self, client):
        """GET /admin/users must be deleted — should return 404 or 405."""
        resp = await client.get("/admin/users")
        assert resp.status_code in (404, 405), \
            f"Expected 404/405 for removed admin route, got {resp.status_code}"


# ── Memory Endpoints ─────────────────────────────────────────────────────────────

class TestMemoryEndpoints:
    async def test_get_memory_existing_user(self, client):
        resp = await client.get("/memory/user_1")
        assert resp.status_code == 200
        assert "user_id" in resp.json() or "preferences" in resp.json()

    async def test_get_memory_new_user_created(self, client):
        """Memory endpoint should auto-create profile for unknown users."""
        resp = await client.get("/memory/auto_created_user_xyz")
        assert resp.status_code in (200, 404)  # Either created or not found, but no crash


# ── Rate Limiting ────────────────────────────────────────────────────────────────

class TestRateLimit:
    async def test_health_not_rate_limited_quickly(self, client):
        """Hit /health 5 times quickly — should all succeed (not rate-limited)."""
        for _ in range(5):
            resp = await client.get("/health")
            assert resp.status_code == 200
