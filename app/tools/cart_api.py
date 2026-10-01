"""
Cart / Checkout API - backed by SQLite via app/database/db.py.

Thread-safe via SQLite WAL mode (works correctly across multiple workers).
Session-scope: session_id injected via ContextVar before agent dispatch.

Key security improvements:
- Removed _latest_summaries in-memory dict; draft summaries are persisted in
  the `draft_orders` SQLite table (safe for multi-worker deployments).
- confirm_checkout recalculates subtotal/discount/tax server-side — the client
  draft_summary is used only for the draft_order_id; all financial figures are
  recomputed from DB state.
- delivery_fee is accepted from the client but capped and stored explicitly —
  the client total is never trusted directly.
- Guest users (user_id == 'guest') are blocked from checkout.
- Ambiguous product names return a structured error for the LLM to handle.
- Shipping address check is enforced at checkout time.
"""
import json
import uuid
from contextvars import ContextVar
from datetime import datetime
from langchain_core.tools import tool
from app.database.db import get_conn

_current_session: ContextVar[str] = ContextVar("current_session", default="default")
_current_user: ContextVar[str] = ContextVar("current_cart_user", default="default")

MAX_DELIVERY_FEE = 500  # Cap client-supplied delivery fee to prevent inflation


def set_cart_session(session_id: str, user_id: str = "") -> None:
    """Call this before invoking the CartAgent to scope operations to the correct session.
    
    IMPORTANT: This only sets the ContextVars — it does NOT delete the cart or drafts.
    Draft cleanup happens only inside checkout() itself after confirmation.
    """
    _current_session.set(session_id)
    if user_id:
        _current_user.set(user_id)


def _sid() -> str:
    return _current_session.get()


def _uid() -> str:
    return _current_user.get()


def _get_cart(session_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM carts WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return {"items": [], "coupon_code": None}
    try:
        items = json.loads(row["items_json"])
    except Exception:
        items = []
    return {"items": items, "coupon_code": row["coupon_code"]}


def _save_cart(session_id: str, items: list, coupon_code: str | None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO carts (session_id, items_json, coupon_code, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                items_json = excluded.items_json,
                coupon_code = excluded.coupon_code,
                updated_at = excluded.updated_at
        """, (session_id, json.dumps(items), coupon_code, datetime.utcnow().isoformat()))


def _save_draft(session_id: str, summary: dict) -> None:
    """Persist checkout draft to DB (replaces _latest_summaries dict)."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO draft_orders (session_id, summary_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary_json = excluded.summary_json,
                created_at = excluded.created_at
        """, (session_id, json.dumps(summary), datetime.utcnow().isoformat()))


def get_latest_checkout_summary(session_id: str) -> dict | None:
    """Retrieve persisted draft summary from DB (replaces _latest_summaries.get)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary_json FROM draft_orders WHERE session_id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["summary_json"])
    except Exception:
        return None


@tool
def add_to_cart(product_name: str, quantity: int = 1) -> str:
    """
    Add a product to the user's cart by name. Supports fuzzy/synonym search.
    If the item is already in the cart, its quantity is updated instead of duplicating.
    Returns the updated cart summary.
    """
    from app.tools.product_api import _fuzzy_match, _format_product
    match = _fuzzy_match(product_name)

    if match is None:
        return json.dumps({"error": f"Product '{product_name}' not found in catalog.",
                          "suggestion": "Try searching with a different name or check available products."})

    # Ambiguous: MUST stop and ask user — do NOT add any item
    if isinstance(match, list):
        return json.dumps({
            "action": "STOP_AND_ASK_USER",
            "error": "Ambiguous product — multiple matches found. Do NOT add any item. You MUST ask the user to pick one.",
            "message": f"I found {len(match)} products matching '{product_name}'. Which one would you like to add?",
            "matches": [{"name": r["name"], "category": r["category"], "price": f"₹{r['price']:,}"} for r in match],
        })

    row = match
    product = _format_product(row)
    if product["stock"] <= 0:
        return json.dumps({"error": f"Sorry, {product['name']} is currently out of stock."})

    key = row["product_key"]
    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]

    for item in items:
        if item["product_key"] == key:
            item["quantity"] += quantity
            _save_cart(sid, items, cart["coupon_code"])
            return json.dumps({
                "action": "updated_quantity",
                "product": product["name"],
                "new_quantity": item["quantity"],
                "cart_size": len(items),
            })

    items.append({
        "product_key": key,
        "name": product["name"],
        "price": product["raw_price"],  # Always store as integer, not formatted string
        "quantity": quantity,
        "idempotency_key": str(uuid.uuid4())[:8],
    })
    _save_cart(sid, items, cart["coupon_code"])
    return json.dumps({
        "action": "added",
        "product": product["name"],
        "quantity": quantity,
        "cart_size": len(items),
    })


@tool
def remove_from_cart(product_name: str) -> str:
    """Remove a product from the user's cart by name."""
    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]
    q = product_name.lower()

    for i, item in enumerate(items):
        if q in item["product_key"] or q in item["name"].lower():
            removed = items.pop(i)
            _save_cart(sid, items, cart["coupon_code"])
            return json.dumps({"action": "removed", "product": removed["name"], "cart_size": len(items)})

    return json.dumps({"error": f"'{product_name}' is not in your cart."})


@tool
def get_cart() -> str:
    """View the current cart contents with item list, subtotal, discount, and total."""
    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]
    coupon_code = cart["coupon_code"]

    if not items:
        return json.dumps({"cart": [], "message": "Your cart is empty."})

    subtotal = sum(int(item["price"]) * int(item["quantity"]) for item in items)
    discount = _calc_discount(coupon_code, subtotal)

    return json.dumps({
        "items": [{"name": i["name"], "price": int(i["price"]), "qty": int(i["quantity"])} for i in items],
        "subtotal": subtotal,
        "discount": discount,
        "coupon_applied": coupon_code,
        "total": round(subtotal - discount, 2),
    })


@tool
def apply_coupon_to_cart(coupon_code: str) -> str:
    """Apply a coupon/discount code to the current cart. Validates the code first."""
    from app.tools.deals_api import get_coupon_by_code
    code = coupon_code.upper().strip()
    coupon = get_coupon_by_code(code)
    if not coupon:
        return json.dumps({"error": f"Coupon '{code}' is invalid or expired."})

    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]

    if not items:
        return json.dumps({"error": "Cannot apply coupon. Your cart is empty."})

    subtotal = sum(int(item["price"]) * int(item["quantity"]) for item in items)

    # NEWUSER check
    if code == "NEWUSER":
        with get_conn() as conn:
            user_id = _uid()
            prev_orders = conn.execute(
                "SELECT 1 FROM confirmed_orders WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if prev_orders:
                return json.dumps({"error": "Coupon 'NEWUSER' is only valid for first-time customers."})

    if subtotal < coupon["min_order"]:
        return json.dumps({
            "error": f"Coupon '{code}' requires a minimum order of Rs.{coupon['min_order']}. "
                     f"Your subtotal is Rs.{subtotal}."
        })

    _save_cart(sid, items, code)
    return json.dumps({"action": "coupon_applied", "code": code, "description": coupon["description"]})


@tool
def check_shipping_address() -> str:
    """
    Check whether the current user has a saved shipping address.
    Returns the address if it exists, or prompts the user to provide one.
    """
    uid = _uid()
    if uid == "guest":
        return json.dumps({"error": "Please sign in to manage your shipping address."})

    with get_conn() as conn:
        row = conn.execute(
            "SELECT shipping_address FROM users WHERE user_id = ?", (uid,)
        ).fetchone()

    if not row or not (row["shipping_address"] or "").strip():
        return json.dumps({
            "has_address": False,
            "message": "You don't have a shipping address saved. "
                       "Please provide your full shipping address so we can deliver your order.",
        })

    return json.dumps({"has_address": True, "shipping_address": row["shipping_address"]})


@tool
def save_shipping_address(address: str) -> str:
    """
    Save or update the user's shipping address in their profile.
    The address should include street, city, state, and PIN code.
    """
    uid = _uid()
    if uid == "guest":
        return json.dumps({"error": "Please sign in to save a shipping address."})

    address = address.strip()
    if len(address) < 10:
        return json.dumps({"error": "Please provide a complete address (street, city, state, PIN code)."})

    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET shipping_address = ? WHERE user_id = ?", (address, uid)
        )
        conn.commit()

    return json.dumps({"action": "address_saved", "shipping_address": address})


@tool
def checkout() -> str:
    """
    Generate a checkout summary for the current cart.
    Returns confirmation_required=True. The user must confirm in the UI
    before the order is placed. Includes tax (8%) and any applied discount.

    IMPORTANT: If the user is a guest, this will return an error prompting sign-in.
    IMPORTANT: If no shipping address is saved, this will prompt the user to provide one first.
    """
    uid = _uid()

    # Guest restriction
    if uid == "guest":
        return json.dumps({
            "error": "guest_restricted",
            "message": "You need to sign in or create an account before checking out. "
                       "Please use the Sign In button to continue.",
        })

    # Shipping address check
    with get_conn() as conn:
        user_row = conn.execute(
            "SELECT shipping_address FROM users WHERE user_id = ?", (uid,)
        ).fetchone()

    if not user_row or not (user_row["shipping_address"] or "").strip():
        return json.dumps({
            "error": "no_shipping_address",
            "message": "You don't have a shipping address on file. "
                       "Please provide your delivery address before we can proceed with checkout.",
        })

    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]
    coupon_code = cart["coupon_code"]

    if not items:
        return json.dumps({"error": "Cart is empty. Add items before checkout."})

    subtotal = sum(int(item["price"]) * int(item["quantity"]) for item in items)
    tax = round(subtotal * 0.08, 2)
    discount = _calc_discount(coupon_code, subtotal)
    total = round(subtotal - discount + tax, 2)
    order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"

    summary_data = {
        "checkout_summary": {
            "items": [
                {
                    "product_key": i.get("product_key", ""),
                    "name": i["name"],
                    "qty": i["quantity"],
                    "price": i["price"],
                }
                for i in items
            ],
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
            "coupon": coupon_code,
            "draft_order_id": order_id,
            "shipping_address": user_row["shipping_address"],
        },
        "confirmation_required": True,
        "message": f"Your order total is Rs.{total}. Please confirm to place this order.",
    }

    # Persist to DB instead of in-memory dict
    _save_draft(sid, summary_data["checkout_summary"])

    return json.dumps(summary_data)


def confirm_checkout(session_id: str, user_id: str, draft_summary: dict, delivery_fee: float = 0) -> dict:
    """
    Actually place the order: write to confirmed_orders table and clear the cart.
    Called by the API route after user clicks Confirm in the UI.

    SECURITY: All financial totals are recalculated server-side from DB state.
    The client-supplied draft_summary is used only to recover the draft_order_id.
    The delivery_fee is accepted from the client but capped at MAX_DELIVERY_FEE.
    """
    # Guest restriction
    if user_id == "guest":
        raise ValueError("Guest users cannot place orders. Please sign in.")

    # Retrieve and validate the draft from DB (not from the client payload)
    db_draft = get_latest_checkout_summary(session_id)
    if not db_draft:
        # Fallback: recalculate from live cart if draft expired
        cart = _get_cart(session_id)
        items = cart["items"]
        coupon_code = cart.get("coupon_code")
        order_id = draft_summary.get("draft_order_id", f"ORD-{uuid.uuid4().hex[:6].upper()}")
    else:
        items = db_draft.get("items", [])
        coupon_code = db_draft.get("coupon")
        order_id = db_draft.get("draft_order_id", draft_summary.get("draft_order_id", f"ORD-{uuid.uuid4().hex[:6].upper()}"))

    # Recalculate totals server-side from live product prices
    with get_conn() as conn:
        # Rebuild items with current DB prices to prevent price spoofing
        verified_items = []
        for item in items:
            pkey = item.get("product_key")
            qty = int(item.get("qty", item.get("quantity", 1)))
            if pkey:
                db_item = conn.execute(
                    "SELECT name, price FROM products WHERE product_key = ?", (pkey,)
                ).fetchone()
                if db_item:
                    verified_items.append({
                        "product_key": pkey,
                        "name": db_item["name"],
                        "qty": qty,
                        "price": db_item["price"],
                    })
            else:
                # No product_key — keep the stored price but don't trust client total
                verified_items.append(item)

    if not verified_items:
        raise ValueError("No valid items to confirm.")

    subtotal = sum(int(i["price"]) * int(i.get("qty", i.get("quantity", 1))) for i in verified_items)
    tax = round(subtotal * 0.08, 2)
    discount = _calc_discount(coupon_code, subtotal)

    # Cap delivery_fee to MAX_DELIVERY_FEE — never trust client total
    safe_delivery_fee = max(0.0, min(float(delivery_fee or 0), MAX_DELIVERY_FEE))
    total = round(subtotal - discount + tax + safe_delivery_fee, 2)

    placed_at = datetime.utcnow().isoformat()

    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO confirmed_orders
                (order_id, session_id, user_id, items_json, subtotal, discount, tax, delivery_fee, total,
                 coupon_code, placed_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                order_id, session_id, user_id,
                json.dumps(verified_items),
                subtotal, discount, tax, safe_delivery_fee, total,
                coupon_code, placed_at,
                "On the way",
            ))
            # Clear the cart
            conn.execute("DELETE FROM carts WHERE session_id = ?", (session_id,))
            # Clear the draft
            conn.execute("DELETE FROM draft_orders WHERE session_id = ?", (session_id,))

            # Deduct stock using verified DB quantities
            for item in verified_items:
                pkey = item.get("product_key")
                qty = item.get("qty", 1)
                if pkey:
                    conn.execute(
                        "UPDATE products SET stock = MAX(0, stock - ?) WHERE product_key = ?",
                        (qty, pkey)
                    )

            conn.commit()
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                pass  # Already placed, return idempotently
            else:
                raise

    return {
        "order_id": order_id,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "delivery_fee": safe_delivery_fee,
        "total": total,
        "items": verified_items,
        "placed_at": placed_at,
        "status": "confirmed",
    }


def _calc_discount(coupon_code: str | None, subtotal: float) -> float:
    if not coupon_code:
        return 0
    from app.tools.deals_api import get_coupon_by_code
    c = get_coupon_by_code(coupon_code)
    if not c:
        return 0
    if subtotal < c["min_order"]:
        return 0
    return round(subtotal * c["value"] / 100, 2) if c["type"] == "percent" else float(c["value"])
