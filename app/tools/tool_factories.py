"""
Tool factories — creates per-request-bound LangChain tools."""
import json
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool

from app.core.request_context import RequestContext

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers (shared between tool factories)
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    from app.database.db import get_conn
    return get_conn()

def _row_get(row, key: str, default=None):
    """sqlite3.Row-safe .get() — falls back to default if key is missing or None."""
    try:
        val = row[key]
        return val if val is not None else default
    except (IndexError, KeyError):
        return default

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
        cap = c.get("max_discount", 0)
        return min(raw, cap) if cap > 0 else raw
    return float(c["value"])

def _get_cart_data(session_id: str) -> dict:
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT ci.product_key, p.name, ci.quantity, p.price
            FROM cart_items ci
            JOIN products p ON p.product_key = ci.product_key
            WHERE ci.session_id = ?
        """, (session_id,)).fetchall()
        cs = conn.execute(
            "SELECT coupon_code FROM cart_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    items = [{"product_key": r["product_key"], "name": r["name"],
               "price": r["price"], "quantity": r["quantity"]} for r in rows]
    return {"items": items, "coupon_code": cs["coupon_code"] if cs else None}

# ─────────────────────────────────────────────────────────────────────────────
# Cart Tools Factory
# ─────────────────────────────────────────────────────────────────────────────

def build_cart_tools(ctx: RequestContext) -> list:
    """Return a list of cart tools bound to the given RequestContext."""

    @tool
    def add_to_cart(product_name: str, quantity: int = 1) -> str:
        """Add a product to the cart. Supports fuzzy/synonym search. Updates quantity if already present."""
        if quantity <= 0:
            return json.dumps({"error": "Quantity must be greater than 0."})

        from app.tools.product_api import _format_product, _fuzzy_match
        match = _fuzzy_match(product_name)
        if match is None:
            return json.dumps({"error": f"Product '{product_name}' not found in catalog."})
        if isinstance(match, list):
            return json.dumps({
                "action": "STOP_AND_ASK_USER",
                "error": "Ambiguous product — multiple matches found. You MUST ask the user to pick one.",
                "message": f"I found {len(match)} products matching '{product_name}'. Which one would you like?",
                "matches": [{"name": r["name"], "category": r["category"], "price": f"₹{r['price']:,}"} for r in match],
            })

        product = _format_product(match)
        if product["stock"] <= 0:
            return json.dumps({"error": f"Sorry, {product['name']} is currently out of stock."})

        key = match["product_key"]
        cart = _get_cart_data(ctx.session_id)
        for item in cart["items"]:
            if item["product_key"] == key:
                new_qty = item["quantity"] + quantity
                with _get_conn() as conn:
                    conn.execute("""
                        UPDATE cart_items SET quantity = ? WHERE session_id = ? AND product_key = ?
                    """, (new_qty, ctx.session_id, key))
                    conn.commit()
                return json.dumps({"action": "updated_quantity", "product": product["name"],
                                   "new_quantity": new_qty, "cart_size": len(cart["items"])})

        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO cart_sessions (session_id, user_id, coupon_code, updated_at)
                VALUES (?, ?, NULL, ?)
                ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at
            """, (ctx.session_id, ctx.user_id, datetime.now(timezone.utc).isoformat()))
            conn.execute("""
                INSERT INTO cart_items (session_id, user_id, product_key, quantity, added_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, product_key) DO UPDATE SET quantity = excluded.quantity
            """, (ctx.session_id, ctx.user_id, key, quantity, datetime.now(timezone.utc).isoformat()))
            conn.commit()

        return json.dumps({"action": "added", "product": product["name"],
                           "quantity": quantity, "cart_size": len(cart["items"]) + 1})

    @tool
    def remove_from_cart(product_name: str, quantity: int = 1) -> str:
        """Remove a product from the cart. Decrements quantity if > 1, removes if last."""
        from app.tools.product_api import _fuzzy_match
        match = _fuzzy_match(product_name)
        if not match:
            return json.dumps({"error": f"Product '{product_name}' not found."})
        if isinstance(match, list):
            return json.dumps({"error": "Ambiguous product name. Please be more specific.",
                               "matches": [r["name"] for r in match]})

        key = match["product_key"]
        cart = _get_cart_data(ctx.session_id)
        for item in cart["items"]:
            if item["product_key"] == key:
                if item["quantity"] > quantity:
                    new_qty = item["quantity"] - quantity
                    with _get_conn() as conn:
                        conn.execute("UPDATE cart_items SET quantity = ? WHERE session_id = ? AND product_key = ?",
                                     (new_qty, ctx.session_id, key))
                        conn.commit()
                    return json.dumps({"action": "decremented", "product": item["name"],
                                       "new_quantity": new_qty, "cart_size": len(cart["items"])})
                else:
                    with _get_conn() as conn:
                        conn.execute("DELETE FROM cart_items WHERE session_id = ? AND product_key = ?",
                                     (ctx.session_id, key))
                        conn.commit()
                    return json.dumps({"action": "removed", "product": item["name"],
                                       "cart_size": len(cart["items"]) - 1})
        return json.dumps({"error": f"'{match['name']}' is not in your cart."})

    @tool
    def get_cart() -> str:
        """View the current cart contents with item list, subtotal, discount, and total."""
        cart = _get_cart_data(ctx.session_id)
        items = cart["items"]
        if not items:
            return json.dumps({"cart": [], "message": "Your cart is empty."})
        subtotal = sum(int(i["price"]) * int(i["quantity"]) for i in items)
        discount = _calc_discount(cart["coupon_code"], subtotal)
        return json.dumps({
            "items": [{"name": i["name"], "price": int(i["price"]), "qty": int(i["quantity"])} for i in items],
            "subtotal": subtotal, "discount": discount,
            "coupon_applied": cart["coupon_code"],
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

        cart = _get_cart_data(ctx.session_id)
        if not cart["items"]:
            return json.dumps({"error": "Cannot apply coupon. Your cart is empty."})

        subtotal = sum(int(i["price"]) * int(i["quantity"]) for i in cart["items"])
        if code == "NEWUSER":
            with _get_conn() as conn:
                prev = conn.execute("SELECT 1 FROM orders WHERE user_id = ? LIMIT 1",
                                    (ctx.user_id,)).fetchone()
                if prev:
                    return json.dumps({"error": "Coupon 'NEWUSER' is only valid for first-time customers."})
        if subtotal < coupon["min_order"]:
            return json.dumps({"error": f"Coupon '{code}' requires minimum order of Rs.{coupon['min_order']}. "
                                        f"Your subtotal is Rs.{subtotal}."})

        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO cart_sessions (session_id, user_id, coupon_code, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET coupon_code = excluded.coupon_code,
                                                       updated_at  = excluded.updated_at
            """, (ctx.session_id, ctx.user_id, code, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        return json.dumps({"action": "coupon_applied", "code": code, "description": coupon["description"]})

    @tool
    def check_shipping_address() -> str:
        """Check whether the current user has a saved shipping address."""
        if ctx.is_guest:
            return json.dumps({"error": "Please sign in to manage your shipping address."})
        with _get_conn() as conn:
            row = conn.execute("SELECT shipping_address FROM users WHERE user_id = ?",
                               (ctx.user_id,)).fetchone()
        if not row or not (row["shipping_address"] or "").strip():
            return json.dumps({"has_address": False,
                               "message": "No shipping address saved. Please provide one."})
        return json.dumps({"has_address": True, "shipping_address": row["shipping_address"]})

    @tool
    def save_shipping_address(address: str) -> str:
        """Save or update the user's shipping address. Include street, city, state, and PIN."""
        if ctx.is_guest:
            return json.dumps({"error": "Please sign in to save a shipping address."})
        address = address.strip()
        if len(address) < 10:
            return json.dumps({"error": "Please provide a complete address (street, city, state, PIN)."})
        with _get_conn() as conn:
            conn.execute(
                "UPDATE users SET shipping_address = ?, updated_at = NOW() WHERE user_id = ?",
                (address, ctx.user_id)
            )
            conn.commit()
        return json.dumps({"action": "address_saved", "shipping_address": address})

    @tool
    def checkout() -> str:
        """
        Generate a checkout summary for the current cart. Returns confirmation_required=True.
        The user must confirm in the UI before the order is placed. Includes tax (8%) + discount.
        IMPORTANT: If no shipping address is saved, prompt the user to provide one first.
        """
        if ctx.is_guest:
            return json.dumps({"error": "guest_restricted",
                               "message": "Please sign in to place an order."})

        with _get_conn() as conn:
            user_row = conn.execute("SELECT shipping_address FROM users WHERE user_id = ?",
                                    (ctx.user_id,)).fetchone()

        if not user_row or not (user_row["shipping_address"] or "").strip():
            return json.dumps({"error": "no_shipping_address",
                               "message": "Please provide your delivery address first."})

        cart = _get_cart_data(ctx.session_id)
        items = cart["items"]
        if not items:
            return json.dumps({"error": "Cart is empty. Add items before checkout."})

        subtotal = sum(int(i["price"]) * int(i["quantity"]) for i in items)
        tax = round(subtotal * 0.08, 2)
        discount = _calc_discount(cart["coupon_code"], subtotal)
        total = round(subtotal - discount + tax, 2)
        order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"

        summary = {
            "items": [{"product_key": i["product_key"], "name": i["name"],
                        "qty": i["quantity"], "price": i["price"]} for i in items],
            "subtotal": subtotal, "discount": discount, "tax": tax, "total": total,
            "coupon": cart["coupon_code"], "draft_order_id": order_id,
            "shipping_address": user_row["shipping_address"],
        }
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO draft_orders (session_id, order_id, summary_json, created_at)
                VALUES (?, ?, ?::jsonb, ?)
                ON CONFLICT(session_id) DO UPDATE SET order_id=excluded.order_id,
                    summary_json=excluded.summary_json, created_at=excluded.created_at
            """, (ctx.session_id, order_id, json.dumps(summary), datetime.now(timezone.utc).isoformat()))
            conn.commit()
        return json.dumps({"checkout_summary": summary, "confirmation_required": True,
                           "message": f"Your order total is Rs.{total}. Please confirm to place this order."})

    @tool
    def confirm_order() -> str:
        """
        Confirm and place the pending order after the user agrees to the checkout summary.
        Call this ONLY after the user has reviewed and explicitly confirmed the checkout.
        """
        from app.tools.cart_api import get_latest_checkout_summary, confirm_checkout
        db_draft = get_latest_checkout_summary(ctx.session_id)
        if not db_draft:
            return json.dumps({"error": "No pending checkout found. Please run checkout first."})
        try:
            res = confirm_checkout(ctx.session_id, ctx.user_id, db_draft)
            return json.dumps({"action": "order_placed", "order_id": res["order_id"], "status": res["status"]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [add_to_cart, remove_from_cart, get_cart, apply_coupon_to_cart,
            checkout, confirm_order, check_shipping_address, save_shipping_address]

# ─────────────────────────────────────────────────────────────────────────────
# Memory Tools Factory
# ─────────────────────────────────────────────────────────────────────────────

def build_memory_tools(ctx: RequestContext) -> list:
    """Return memory tools bound to the given RequestContext."""

    @tool
    async def remember_user_preference(key: str, value: str) -> str:
        """Save an important fact or preference about the user to long-term memory."""
        if ctx.is_guest:
            return f"Noted: '{key}' = '{value}'. (Note: As a guest, this won't persist.)"
        from app.memory.long_term import async_save_preference
        updated = await async_save_preference(ctx.user_id, key, value)
        return f"Remembered: '{key}' = '{value}'. You now have {len(updated)} saved preferences."

    @tool
    async def recall_user_preferences() -> str:
        """Retrieve all long-term preferences and profile info saved for this user, including name and shipping address."""
        if ctx.is_guest:
            return "Guest user — no long-term memory. Rely on current chat history for context."
        from app.memory.long_term import async_get_user_profile
        profile = await async_get_user_profile(ctx.user_id)
        if not profile:
            return "No memory found for this user yet."
        prefs = profile.get("preferences", {})
        shipping = profile.get("shipping_address", "") or "Not saved yet"
        pref_lines = "\n".join(f"  - {k}: {v}" for k, v in prefs.items()) if prefs else "  (none)"
        return (
            f"User: {profile.get('name')}\n"
            f"Shipping address: {shipping}\n"
            f"Saved preferences:\n{pref_lines}"
        )

    @tool
    async def forget_user_preference(key: str) -> str:
        """Remove a specific preference from the user's long-term memory."""
        if ctx.is_guest:
            return f"Guest user — preference '{key}' won't persist anyway."
        from app.memory.long_term import async_delete_preference
        updated = await async_delete_preference(ctx.user_id, key)
        return f"Forgot preference '{key}'. Remaining preferences: {len(updated)}."

    return [remember_user_preference, recall_user_preferences, forget_user_preference]

# ─────────────────────────────────────────────────────────────────────────────
# Order Tools Factory
# ─────────────────────────────────────────────────────────────────────────────

def build_order_tools(ctx: RequestContext) -> list:
    """Return order tools bound to the given RequestContext."""

    @tool
    def get_order_status(order_id: str) -> str:
        """Look up status, tracking info, and timeline for a specific customer order by ID."""
        clean_id = (order_id.strip().lstrip("#")
                    .replace("ORD-", "").replace("ORD", "").lstrip("0") or "0")

        with _get_conn() as conn:
            # First try current user's orders
            row = (conn.execute("SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                                (clean_id, ctx.user_id)).fetchone() or
                   conn.execute("SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                                (f"ORD-{clean_id}", ctx.user_id)).fetchone() or
                   conn.execute("SELECT * FROM orders WHERE order_id LIKE ? AND user_id = ?",
                                (f"%{clean_id}%", ctx.user_id)).fetchone())

            # Fallback: allow access to demo orders (user_1) for any user
            if not row and clean_id in ("123", "456", "999"):
                row = conn.execute("SELECT * FROM orders WHERE order_id = ? AND user_id = 'user_1'",
                                   (clean_id,)).fetchone()

            if not row:
                return json.dumps({"error": f"Order '{order_id}' not found.",
                                   "suggestion": "Demo orders: 123, 456, 999. Or use get_my_orders to see all your placed orders."})

            oid = row["order_id"]
            items_rows = conn.execute(
                "SELECT name, price, quantity FROM order_items WHERE order_id = ?", (oid,)).fetchall()
            timeline_rows = conn.execute(
                "SELECT step, occurred_at, completed FROM order_timeline WHERE order_id = ? ORDER BY id",
                (oid,)).fetchall()

        return json.dumps({
            "order_id": f"#ORD-{clean_id}",
            "product": ", ".join(r["name"] for r in items_rows),
            "status": row["status"],
            "eta": _row_get(row, "eta", "3-5 business days"),
            "carrier": _row_get(row, "carrier"),
            "tracking_number": _row_get(row, "tracking_num"),
            "placed_on": str(_row_get(row, "placed_at", _row_get(row, "placed_on", ""))),
            "amount": f"Rs.{_row_get(row, 'total', _row_get(row, 'amount', 0))}",
            "items": [{"name": r["name"], "price": r["price"], "qty": r["quantity"]} for r in items_rows],
            "timeline": [{"step": r["step"], "time": r["occurred_at"], "done": bool(r["completed"])}
                         for r in timeline_rows],
        })

    @tool
    def get_my_orders() -> str:
        """Retrieve all orders placed by the current user. Use this when the user asks to see their orders, order history, or past purchases."""
        if ctx.is_guest:
            return json.dumps({"error": "Please sign in to view your order history."})
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT order_id, status, total, placed_at, coupon_code FROM orders WHERE user_id = ? ORDER BY placed_at DESC",
                (ctx.user_id,)
            ).fetchall()
        if not rows:
            return json.dumps({"orders": [], "message": "You have no orders yet."})
        order_ids = [r["order_id"] for r in rows]
        # Batch-fetch all order items in one query (avoids N+1 connections)
        placeholders = ", ".join(["%s"] * len(order_ids))
        with _get_conn() as conn:
            all_items = conn.execute(
                f"SELECT order_id, name, price, quantity FROM order_items WHERE order_id IN ({placeholders})",
                tuple(order_ids)
            ).fetchall()
        items_by_order: dict = {}
        for item in all_items:
            items_by_order.setdefault(item["order_id"], []).append(item)
        orders = []
        for r in rows:
            oid = r["order_id"]
            order_items = items_by_order.get(oid, [])
            orders.append({
                "order_id": oid,
                "status": r["status"],
                "total": r["total"],
                "placed_at": str(r["placed_at"]),
                "items": [{"name": i["name"], "qty": i["quantity"]} for i in order_items],
            })
        return json.dumps({"orders": orders, "count": len(orders)})

    @tool
    def cancel_order(order_id: str) -> str:
        """Cancel a customer order. Only orders not yet delivered or refunded can be cancelled."""
        clean_id = (order_id.strip().lstrip("#")
                    .replace("ORD-", "").replace("ORD", "").lstrip("0") or "0")
        terminal = {"Delivered", "Cancelled", "Refund Processing", "Refunded"}

        with _get_conn() as conn:
            row = (conn.execute("SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                                (clean_id, ctx.user_id)).fetchone() or
                   conn.execute("SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                                (f"ORD-{clean_id}", ctx.user_id)).fetchone() or
                   conn.execute("SELECT * FROM orders WHERE order_id LIKE ? AND user_id = ?",
                                (f"%{clean_id}%", ctx.user_id)).fetchone())
            if not row:
                return json.dumps({"error": f"Order '{order_id}' not found."})
            if row["status"] in terminal:
                return json.dumps({"error": f"Cannot cancel. Status: {row['status']}."})
            conn.execute("UPDATE orders SET status = 'Cancelled' WHERE order_id = ? AND user_id = ?",
                         (row["order_id"], ctx.user_id))
            conn.commit()
        return json.dumps({"action": "cancelled", "order_id": row["order_id"], "status": "Cancelled",
                           "message": f"Order {row['order_id']} cancelled. Refund within 5-7 business days."})

    return [get_order_status, get_my_orders, cancel_order]

# ─────────────────────────────────────────────────────────────────────────────
# Complaint Tools Factory
# ─────────────────────────────────────────────────────────────────────────────

def build_complaint_tools(ctx: RequestContext) -> list:
    """Return complaint tools bound to the given RequestContext."""

    @tool
    def check_complaint_history(user_id: str = "") -> str:
        """Check a user's past complaint and ticket history."""
        uid = user_id or ctx.user_id
        with _get_conn() as conn:
            complaints = conn.execute(
                "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
            refunds = conn.execute(
                "SELECT * FROM refunds WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
        result = {"user_id": uid, "total_complaints": len(complaints),
                  "complaints": [dict(r) for r in complaints],
                  "refunds": [dict(r) for r in refunds]}
        if not complaints and not refunds:
            result["message"] = "No previous complaints or refunds found."
        return json.dumps(result)

    @tool
    def issue_auto_refund(order_id: str, amount: float, reason: str) -> str:
        """Issue an automatic refund for a customer order. Only allowed for amounts under Rs.5000."""
        if ctx.is_guest:
            return json.dumps({"error": "guest_restricted", "message": "Please sign in to request a refund."})
        if amount <= 0:
            return json.dumps({"error": "Refund amount must be greater than 0."})
        if amount > 5000:
            return json.dumps({"action": "denied",
                               "reason": f"Auto-refund limit is Rs.5000. Rs.{amount} exceeds limit. Please escalate."})

        clean_id = (order_id.strip().lstrip("#").replace("ORD-", "").replace("ORD", "").lstrip("0") or "0")
        with _get_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM refunds WHERE (order_id = ? OR order_id = ?) AND user_id = ?",
                (clean_id, f"ORD-{clean_id}", ctx.user_id)).fetchone()
            if existing:
                return json.dumps({"error": "A refund has already been issued for this order."})
            row = conn.execute("SELECT amount FROM orders WHERE order_id = ? AND user_id = ?",
                               (clean_id, ctx.user_id)).fetchone()
            conf = conn.execute("SELECT total as amount FROM orders WHERE (order_id = ? OR order_id = ?) AND user_id = ?",
                                (f"ORD-{clean_id}", clean_id, ctx.user_id)).fetchone()
            order_record = row or conf
            if not order_record:
                return json.dumps({"error": f"Order '{order_id}' not found."})
            raw_amt = str(order_record["amount"]).replace("Rs.", "").replace(",", "").strip()
            try:
                order_total = float(raw_amt)
            except ValueError:
                order_total = 0.0
            if amount > order_total:
                return json.dumps({"error": f"Refund Rs.{amount} cannot exceed order total Rs.{order_total}."})

            refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
            created_at = datetime.now(timezone.utc).isoformat()
            db_order_id = f"ORD-{clean_id}" if conf else clean_id
            conn.execute("""
                INSERT INTO refunds (refund_id, order_id, user_id, amount, reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'Processing', ?)
            """, (refund_id, db_order_id, ctx.user_id, amount, reason, created_at))
            conn.execute("UPDATE orders SET status = 'Refund Processing' WHERE order_id = ? AND user_id = ?",
                         (clean_id, ctx.user_id))
            conn.commit()

        return json.dumps({"action": "refund_issued", "refund_id": refund_id, "order_id": order_id,
                           "amount": amount, "reason": reason,
                           "status": "Processing — will reflect in 3-5 business days"})

    @tool
    def escalate_to_human(issue_summary: str, urgency: str = "HIGH") -> str:
        """Escalate a customer issue to the human support team. urgency: 'HIGH' or 'MEDIUM'."""
        ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO complaints (ticket_id, user_id, session_id, summary, urgency, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'QUEUED', ?)
            """, (ticket_id, ctx.user_id, ctx.session_id, issue_summary, urgency.upper(), created_at))
            conn.commit()
        eta = "2 hours" if urgency.upper() == "HIGH" else "24 hours"
        return json.dumps({"action": "escalated", "ticket_id": ticket_id, "urgency": urgency.upper(),
                           "message": f"Issue escalated. Human agent will respond within {eta}. Ticket: {ticket_id}"})

    return [check_complaint_history, issue_auto_refund, escalate_to_human]

# ─────────────────────────────────────────────────────────────────────────────
# Product Tools (stateless — no context needed, safe to share across requests)
# ─────────────────────────────────────────────────────────────────────────────

def build_product_tools() -> list:
    """Product tools are stateless — return the shared singletons."""
    from app.tools.product_api import (
        compare_products,
        get_product_details,
        search_products,
    )
    return [get_product_details, search_products, compare_products]

def build_deals_tools() -> list:
    """Deals/pricing tools are stateless — return the shared singletons."""
    from app.tools.deals_api import check_coupon, get_price_history
    return [get_price_history, check_coupon]
