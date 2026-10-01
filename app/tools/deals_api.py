"""
Deals / Pricing API - backed by SQLite via app/database/db.py.

Provides price history analysis, coupon validation, and deal checking.
All data is now sourced from the SQLite database instead of hardcoded dicts.
"""
import json
from langchain_core.tools import tool
from app.database.db import get_conn


@tool
def get_price_history(product_name: str) -> str:
    """
    Get the 4-week price history for a product to determine if it's a good
    time to buy. Shows current price, 4-week high/low, trend, and recommendation.
    """
    q = product_name.lower().strip()

    with get_conn() as conn:
        # Try exact key match first
        row = conn.execute(
            "SELECT ph.*, p.name, p.price FROM price_history ph "
            "JOIN products p ON p.product_key = ph.product_key "
            "WHERE ph.product_key = ?", (q,)
        ).fetchone()

        if not row:
            # Fuzzy: check if query matches any product name or synonym
            products = conn.execute(
                "SELECT ph.*, p.name, p.price, p.synonyms FROM price_history ph "
                "JOIN products p ON p.product_key = ph.product_key"
            ).fetchall()
            for p in products:
                synonyms = (p["synonyms"] or "").lower()
                if q in p["product_key"] or q in p["name"].lower() or q in synonyms:
                    row = p
                    break

    if not row:
        return json.dumps({"error": f"No price history for '{product_name}'."})

    prices = json.loads(row["prices_json"])
    current = prices[-1]
    highest = max(prices)
    lowest = min(prices)
    trend = "stable" if prices[-1] == prices[-2] else ("dropping" if prices[-1] < prices[-2] else "rising")
    drop_pct = round((highest - current) / highest * 100, 1) if highest > current else 0

    return json.dumps({
        "product": row["name"],
        "weekly_prices": prices,
        "current_price": current,
        "4_week_high": highest,
        "4_week_low": lowest,
        "trend": trend,
        "drop_from_high_pct": drop_pct,
        "recommendation": "Good time to buy!" if drop_pct >= 5 else "Price is stable — no urgency to buy now.",
    })


@tool
def check_coupon(coupon_code: str) -> str:
    """
    Validate a coupon/discount code and return its discount details.
    Returns whether the coupon is valid, its type, value, and minimum order requirement.
    """
    code = coupon_code.upper().strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM coupons WHERE code = ? AND active = 1", (code,)
        ).fetchone()

    if row:
        return json.dumps({
            "code": code,
            "valid": True,
            "type": row["type"],
            "value": row["value"],
            "min_order": row["min_order"],
            "description": row["description"],
        })
    return json.dumps({"code": code, "valid": False, "error": f"Coupon '{code}' is not valid or has expired."})


def get_coupon_by_code(code: str) -> dict | None:
    """Internal helper: get a coupon dict by code (used by cart_api)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM coupons WHERE code = ? AND active = 1", (code.upper(),)
        ).fetchone()
    return dict(row) if row else None
