"""
Cart / Checkout API — backed by PostgreSQL via app/database/engine.py."""
import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from langchain_core.tools import tool

from app.database.db import get_conn

_current_session: ContextVar[str] = ContextVar("current_session", default="default")
_current_user: ContextVar[str] = ContextVar("current_cart_user", default="default")

MAX_DELIVERY_FEE = 100  # Cap client-supplied delivery fee

def set_cart_session(session_id: str, user_id: str = "") -> None:
    """Call this before invoking the CartAgent to scope operations to the correct session."""
    _current_session.set(session_id)
    if user_id:
        _current_user.set(user_id)

def _sid() -> str:
    return _current_session.get()

def _uid() -> str:
    return _current_user.get()

# ─────────────────────────────────────────────────────────────────────────────
# Internal cart helpers — now using cart_items + cart_sessions tables
# ─────────────────────────────────────────────────────────────────────────────

def _get_cart(session_id: str) -> dict:
    """Return cart contents as {items: [...], coupon_code: str|None}."""
    with get_conn() as conn:
        # Fetch items joined with product prices
        rows = conn.execute("""
            SELECT ci.product_key, p.name, ci.quantity, p.price
            FROM cart_items ci
            JOIN products p ON p.product_key = ci.product_key
            WHERE ci.session_id = ?
        """, (session_id,)).fetchall()

        cs = conn.execute(
            "SELECT coupon_code FROM cart_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

    items = [
        {
            "product_key": r["product_key"],
            "name": r["name"],
            "price": r["price"],
            "quantity": r["quantity"],
        }
        for r in rows
    ]
    return {"items": items, "coupon_code": cs["coupon_code"] if cs else None}

def _ensure_cart_session(session_id: str, coupon_code: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO cart_sessions (session_id, user_id, coupon_code, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                coupon_code = COALESCE(excluded.coupon_code, cart_sessions.coupon_code),
                updated_at  = excluded.updated_at
        """, (session_id, _uid(), coupon_code, datetime.now(timezone.utc).isoformat()))
        conn.commit()

def _upsert_cart_item(session_id: str, product_key: str, quantity: int) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO cart_items (session_id, user_id, product_key, quantity, added_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, product_key) DO UPDATE SET
                quantity = excluded.quantity
        """, (session_id, _uid(), product_key, quantity, datetime.now(timezone.utc).isoformat()))
        conn.commit()

def _delete_cart_item(session_id: str, product_key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM cart_items WHERE session_id = ? AND product_key = ?",
            (session_id, product_key)
        )
        conn.commit()

def _set_cart_coupon(session_id: str, coupon_code: str | None) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO cart_sessions (session_id, user_id, coupon_code, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                coupon_code = excluded.coupon_code,
                updated_at  = excluded.updated_at
        """, (session_id, _uid(), coupon_code, datetime.now(timezone.utc).isoformat()))
        conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# Draft order helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save_draft(session_id: str, order_id: str, summary: dict) -> None:
    """Persist checkout draft to DB."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO draft_orders (session_id, order_id, summary_json, created_at)
            VALUES (?, ?, ?::jsonb, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                order_id     = excluded.order_id,
                summary_json = excluded.summary_json,
                created_at   = excluded.created_at
        """, (session_id, order_id, json.dumps(summary), datetime.now(timezone.utc).isoformat()))
        conn.commit()

def get_latest_checkout_summary(session_id: str) -> dict | None:
    """Retrieve persisted draft summary from DB."""
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

# ─────────────────────────────────────────────────────────────────────────────
# LangChain Tools
# ─────────────────────────────────────────────────────────────────────────────

@tool
def add_to_cart(product_name: str, quantity: int = 1) -> str:
    """
    Add a product to the user's cart by name. Supports fuzzy/synonym search.
    If the item is already in the cart, its quantity is updated instead of duplicating.
    Returns the updated cart summary.
    """
    if quantity <= 0:
        return json.dumps({"error": "Quantity must be greater than 0."})

    from app.tools.product_api import _format_product, _fuzzy_match
    match = _fuzzy_match(product_name)

    if match is None:
        return json.dumps({"error": f"Product '{product_name}' not found in catalog.",
                          "suggestion": "Try searching with a different name or check available products."})

    if isinstance(match, list):
        return json.dumps({
            "action": "STOP_AND_ASK_USER",
            "error": "Ambiguous product — multiple matches found. Do NOT add any item. You MUST ask the user to pick one.",
            "message": f"I found {len(match)} products matching '{product_name}'. Which one would you like to add?\n" + "\n".join(f"{i+1}. {r['name']} — ₹{r['price']:,}" for i, r in enumerate(match)),
            "matches": [{"name": r["name"], "category": r["category"], "price": f"₹{r['price']:,}"} for r in match],
        })

    row = match
    product = _format_product(row)
    if product["stock"] <= 0:
        return json.dumps({"error": f"Sorry, {product['name']} is currently out of stock."})

    key = row["product_key"]
    sid = _sid()

    # Check if already in cart
    cart = _get_cart(sid)
    for item in cart["items"]:
        if item["product_key"] == key:
            new_qty = item["quantity"] + quantity
            _upsert_cart_item(sid, key, new_qty)
            return json.dumps({
                "action": "updated_quantity",
                "product": product["name"],
                "new_quantity": new_qty,
                "cart_size": len(cart["items"]),
            })

    _ensure_cart_session(sid)
    _upsert_cart_item(sid, key, quantity)
    return json.dumps({
        "action": "added",
        "product": product["name"],
        "quantity": quantity,
        "cart_size": len(cart["items"]) + 1,
    })

@tool
def remove_from_cart(product_name: str, quantity: int = 1) -> str:
    """Remove a product from the user's cart by name. Will decrement quantity if available."""
    from app.tools.product_api import _fuzzy_match

    sid = _sid()
    cart = _get_cart(sid)
    items = cart["items"]

    match = _fuzzy_match(product_name)
    if not match:
        return json.dumps({"error": f"Product '{product_name}' not found."})
    if isinstance(match, list):
        return json.dumps({
            "error": "Ambiguous product — multiple matches found.",
            "message": f"I found {len(match)} products matching '{product_name}'. Please be more specific."
        })

    key = match["product_key"]

    for item in items:
        if item["product_key"] == key:
            if item["quantity"] > quantity:
                new_qty = item["quantity"] - quantity
                _upsert_cart_item(sid, key, new_qty)
                return json.dumps({"action": "decremented", "product": item["name"],
                                   "new_quantity": new_qty, "cart_size": len(items)})
            else:
                _delete_cart_item(sid, key)
                return json.dumps({"action": "removed", "product": item["name"],
                                   "cart_size": len(items) - 1})

    return json.dumps({"error": f"'{match['name']}' is not in your cart."})

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

    if code == "NEWUSER":
        with get_conn() as conn:
            user_id = _uid()
            prev = conn.execute(
                "SELECT 1 FROM orders WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if prev:
                return json.dumps({"error": "Coupon 'NEWUSER' is only valid for first-time customers."})

    if subtotal < coupon["min_order"]:
        return json.dumps({
            "error": f"Coupon '{code}' requires a minimum order of Rs.{coupon['min_order']}. "
                     f"Your subtotal is Rs.{subtotal}."
        })

    _set_cart_coupon(sid, code)
    return json.dumps({"action": "coupon_applied", "code": code, "description": coupon["description"]})

@tool
def check_shipping_address() -> str:
    """
    Check whether the current user has a saved shipping address.
    Returns the address if it exists, or prompts the user to provide one.
    """
    uid = _uid()
    if uid in ("guest", "default") or uid.startswith("anon_"):
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
    if uid in ("guest", "default") or uid.startswith("anon_"):
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
    if uid in ("guest", "default") or uid.startswith("anon_"):
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

    summary = {
        "items": [
            {
                "product_key": i["product_key"],
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
    }

    _save_draft(sid, order_id, summary)

    return json.dumps({
        "checkout_summary": summary,
        "confirmation_required": True,
        "message": f"Your order total is Rs.{total}. Please confirm to place this order.",
    })

@tool
def confirm_order() -> str:
    """
    Confirm and place the pending order. Call this AFTER the user has agreed to the checkout summary.
    """
    sid = _sid()
    uid = _uid()
    db_draft = get_latest_checkout_summary(sid)
    
    if not db_draft:
        return json.dumps({"error": "No pending checkout found. Please run checkout first."})
        
    try:
        res = confirm_checkout(sid, uid, db_draft)
        return json.dumps({"action": "order_placed", "order_id": res["order_id"], "status": res["status"]})
    except Exception as e:
        return json.dumps({"error": str(e)})

def confirm_checkout(session_id: str, user_id: str, draft_summary: dict, delivery_fee: float = 0) -> dict:
    """
    Actually place the order: write to orders + order_items tables in a single
    transaction and clear the cart.

    SECURITY: All financial totals are recalculated server-side from DB state.
    """
    if user_id in ("guest", "default") or user_id.startswith("anon_"):
        raise ValueError("Guest users cannot place orders. Please sign in.")

    # Retrieve and validate the draft from DB
    db_draft = get_latest_checkout_summary(session_id)
    if not db_draft:
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
                verified_items.append(item)

    if not verified_items:
        raise ValueError("No valid items to confirm.")

    subtotal = sum(int(i["price"]) * int(i.get("qty", i.get("quantity", 1))) for i in verified_items)
    tax = round(subtotal * 0.08, 2)
    discount = _calc_discount(coupon_code, subtotal)
    safe_delivery_fee = max(0.0, min(float(delivery_fee or 0), MAX_DELIVERY_FEE))
    total = round(subtotal - discount + tax + safe_delivery_fee, 2)
    placed_at = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        try:
            # Write order header
            conn.execute("""
                INSERT INTO orders
                (order_id, user_id, status, subtotal, discount, tax, delivery_fee, total, coupon_code, placed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (order_id, user_id, "On the way", subtotal, discount, tax,
                  safe_delivery_fee, total, coupon_code, placed_at))

            # Write order items
            for item in verified_items:
                conn.execute("""
                    INSERT INTO order_items (order_id, product_key, name, price, quantity)
                    VALUES (?,?,?,?,?)
                """, (order_id, item.get("product_key"), item["name"],
                      item["price"], item.get("qty", 1)))

            # Clear cart items + session
            conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM cart_sessions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM draft_orders WHERE session_id = ?", (session_id,))

            # Deduct stock
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
            err_str = str(e).lower()
            if "unique constraint failed" in err_str or "duplicate key value violates unique constraint" in err_str:
                return {
                    "order_id": order_id,
                    "status": "already_confirmed",
                    "message": "This order has already been placed.",
                }
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
    if c["type"] == "percent":
        raw = round(subtotal * c["value"] / 100, 2)
        # Respect max_discount cap if set
        cap = c.get("max_discount", 0)
        return min(raw, cap) if cap > 0 else raw
    return float(c["value"])
