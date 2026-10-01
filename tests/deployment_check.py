"""
ShopMate Deployment Checklist & Test Runner
Runs all checks and generates a readiness report.
"""
import subprocess
import sys
import os
import json
from datetime import datetime

# ── Ensure project root is on sys.path ────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

CHECKS = []

def check(name):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn
    return decorator


# ── Environment Checks ─────────────────────────────────────────────────────────

@check("GEMINI_API_KEY set")
def check_gemini_key():
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY", "")
    assert key and len(key) > 10, "GEMINI_API_KEY is missing or too short"

@check("JWT_SECRET_KEY set")
def check_jwt_key():
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("JWT_SECRET_KEY", "")
    assert key and len(key) > 10, "JWT_SECRET_KEY is missing or too short"

@check("JWT_SECRET_KEY not hardcoded")
def check_jwt_not_hardcoded():
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("JWT_SECRET_KEY", "")
    assert key != "super_secret_shopmate_key", "JWT secret is still the old hardcoded value"

@check("bcrypt installed")
def check_bcrypt():
    import bcrypt
    h = bcrypt.hashpw(b"test", bcrypt.gensalt())
    assert h.startswith(b"$2"), "bcrypt hash format invalid"

@check("PyJWT installed")
def check_pyjwt():
    import jwt
    token = jwt.encode({"sub": "test"}, "secret", algorithm="HS256")
    assert len(token) > 10


# ── Database Checks ────────────────────────────────────────────────────────────

@check("Database initializes without error")
def check_db_init():
    from app.database.db import init_db, get_conn
    init_db()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert count > 0

@check("Demo user exists with correct email")
def check_demo_user():
    from app.database.db import get_conn
    with get_conn() as conn:
        row = conn.execute("SELECT email FROM users WHERE user_id = 'user_1'").fetchone()
    assert row is not None and row["email"] == "demo@gmail.com"

@check("Demo user password is bcrypt hashed")
def check_demo_password_bcrypt():
    from app.database.db import get_conn
    from app.api.auth import verify_password
    with get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE user_id = 'user_1'").fetchone()
    assert row["password_hash"].startswith("$2"), "Not a bcrypt hash"
    assert verify_password("demo", row["password_hash"]), "demo password fails verification"

@check("shipping_address column exists")
def check_shipping_address_col():
    from app.database.db import get_conn
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    assert "shipping_address" in cols

@check("draft_orders table exists")
def check_draft_orders_table():
    from app.database.db import get_conn
    with get_conn() as conn:
        t = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='draft_orders'"
        ).fetchone()
    assert t is not None, "draft_orders table missing"

@check("delivery_fee column in confirmed_orders")
def check_delivery_fee_col():
    from app.database.db import get_conn
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(confirmed_orders)").fetchall()]
    assert "delivery_fee" in cols

@check("Mock orders scoped to user_1 only")
def check_order_scoping():
    from app.database.db import get_conn
    with get_conn() as conn:
        others = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id != 'user_1'"
        ).fetchone()[0]
    assert others == 0, f"{others} orphan orders found"


# ── Security Checks ────────────────────────────────────────────────────────────

@check("Guest blocked from checkout")
def check_guest_checkout_blocked():
    from app.tools.cart_api import set_cart_session, checkout, _current_user
    set_cart_session("deploy_check_guest", "guest")
    _current_user.set("guest")
    import json
    result = json.loads(checkout.invoke({}))
    assert result.get("error") == "guest_restricted"

@check("Guest blocked from refunds")
def check_guest_refund_blocked():
    import json
    from app.tools.complaint_api import set_complaint_context, issue_auto_refund
    set_complaint_context("guest", "guest_session")
    result = json.loads(issue_auto_refund.invoke({"order_id": "1", "amount": 100, "reason": "test"}))
    assert result.get("error") == "guest_restricted"

@check("Server-side price recalculation active")
def check_server_side_totals():
    from app.tools.cart_api import (
        set_cart_session, add_to_cart, checkout, save_shipping_address,
        confirm_checkout, _current_user
    )
    import json
    session = "deploy_price_check"
    set_cart_session(session, "user_1")
    _current_user.set("user_1")
    save_shipping_address.invoke({"address": "Deploy Check Rd, Bengaluru, KA, 560001"})
    add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
    real = json.loads(checkout.invoke({}))
    summary = real.get("checkout_summary", {})
    spoofed = {**summary, "total": 1, "subtotal": 1}
    result = confirm_checkout(session, "user_1", spoofed, 0)
    assert result["total"] > 1000, "Server-side total recalculation is broken!"

@check("Admin /users route removed")
def check_admin_route_removed():
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        resp = c.get("/admin/users")
    assert resp.status_code in (404, 405), f"Admin route still accessible! Status: {resp.status_code}"

@check("_latest_summaries removed from cart_api")
def check_no_inmemory_dict():
    import app.tools.cart_api as cart_module
    assert not hasattr(cart_module, "_latest_summaries"), \
        "_latest_summaries in-memory dict still present in cart_api.py"


# ── API Endpoint Checks ────────────────────────────────────────────────────────

@check("Health endpoint responds")
def check_health():
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200

@check("Login endpoint works")
def check_login():
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        resp = c.post("/auth/login", json={"email": "demo@gmail.com", "password": "demo"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_all():
    print("\n" + "="*65)
    print("  ShopMate Deployment Readiness Check")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    results = []
    passed = 0
    failed = 0

    for name, fn in CHECKS:
        try:
            fn()
            print(f"  [PASS] {name}")
            results.append({"check": name, "status": "PASS"})
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}")
            print(f"         Error: {e}")
            results.append({"check": name, "status": "FAIL", "error": str(e)})
            failed += 1

    print("="*65)
    if failed == 0:
        print(f"  [OK] ALL {passed} CHECKS PASSED -- READY TO DEPLOY!")
    else:
        print(f"  [XX] {failed}/{passed+failed} CHECKS FAILED -- DO NOT DEPLOY")
    print("="*65 + "\n")

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": passed + failed,
        "passed": passed,
        "failed": failed,
        "ready_to_deploy": failed == 0,
        "checks": results,
    }
    out_path = os.path.join(os.path.dirname(__file__), "deployment_readiness.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved: {out_path}\n")
    return report


if __name__ == "__main__":
    report = run_all()
    sys.exit(0 if report["ready_to_deploy"] else 1)
