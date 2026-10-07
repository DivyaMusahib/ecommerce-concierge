"""
Order Management API — backed by PostgreSQL via app/database/engine.py."""
import json
from contextvars import ContextVar

from langchain_core.tools import tool

from app.database.db import get_conn

_current_order_user: ContextVar[str] = ContextVar("current_order_user", default="guest")

def set_order_user(user_id: str) -> None:
    if user_id:
        _current_order_user.set(user_id)

@tool
def get_order_status(order_id: str) -> str:
    """
    Look up the status, tracking info, and delivery timeline for a customer
    order. Accepts order IDs like '123', '#123', 'ORD-123', '#ORD-123'.
    Demo orders available: 123, 456, 999.
    """
    clean_id = (
        order_id.strip()
        .lstrip("#")
        .replace("ORD-", "")
        .replace("ORD", "")
        .lstrip("0") or "0"
    )

    user_id = _current_order_user.get()

    with get_conn() as conn:
        # Try exact order_id first (handles demo orders: 123, 456, 999)
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
            (clean_id, user_id)
        ).fetchone()

        # Also try with ORD- prefix (checkout orders)
        if not row:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                (f"ORD-{clean_id}", user_id)
            ).fetchone()

        # Partial match fallback
        if not row:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id LIKE ? AND user_id = ?",
                (f"%{clean_id}%", user_id)
            ).fetchone()

        if not row:
            return json.dumps({
                "error": f"Order '{order_id}' not found.",
                "suggestion": "Valid demo orders: 123, 456, 999. Or use a confirmed order ID from your checkout.",
            })

        oid = row["order_id"]

        # Fetch order items
        items_rows = conn.execute(
            "SELECT name, price, quantity FROM order_items WHERE order_id = ?", (oid,)
        ).fetchall()
        product_names = ", ".join(r["name"] for r in items_rows)
        items = [{"name": r["name"], "price": r["price"], "qty": r["quantity"]} for r in items_rows]

        # Fetch timeline
        timeline_rows = conn.execute(
            "SELECT step, occurred_at, completed FROM order_timeline WHERE order_id = ? ORDER BY id",
            (oid,)
        ).fetchall()
        timeline = [{"step": r["step"], "time": r["occurred_at"], "done": bool(r["completed"])}
                    for r in timeline_rows]

    return json.dumps({
        "order_id": f"#ORD-{clean_id}",
        "product": product_names or row.get("product", ""),
        "status": row["status"],
        "eta": row.get("eta", "3-5 business days"),
        "carrier": row.get("carrier"),
        "tracking_number": row.get("tracking_num"),
        "placed_on": str(row.get("placed_at", "")),
        "amount": f"Rs.{row['total']}",
        "items": items,
        "timeline": timeline,
    })

@tool
def cancel_order(order_id: str) -> str:
    """
    Cancel a customer order. Sets the status to 'Cancelled'.
    Only orders that are not already delivered or refunded can be cancelled.
    """
    clean_id = (
        order_id.strip()
        .lstrip("#")
        .replace("ORD-", "")
        .replace("ORD", "")
        .lstrip("0") or "0"
    )

    user_id = _current_order_user.get()
    terminal_statuses = {"Delivered", "Cancelled", "Refund Processing", "Refunded"}

    with get_conn() as conn:
        # Try both plain and ORD- prefixed IDs
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
            (clean_id, user_id)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
                (f"ORD-{clean_id}", user_id)
            ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id LIKE ? AND user_id = ?",
                (f"%{clean_id}%", user_id)
            ).fetchone()

        if not row:
            return json.dumps({
                "error": f"Order '{order_id}' not found or does not belong to your account.",
            })

        current_status = row["status"]
        if current_status in terminal_statuses:
            return json.dumps({
                "error": f"Order '{order_id}' cannot be cancelled. Current status: {current_status}.",
            })

        conn.execute(
            "UPDATE orders SET status = 'Cancelled' WHERE order_id = ? AND user_id = ?",
            (row["order_id"], user_id)
        )
        conn.commit()

    display_id = row["order_id"]
    return json.dumps({
        "action": "cancelled",
        "order_id": display_id,
        "status": "Cancelled",
        "message": f"Order {display_id} has been successfully cancelled. "
                   "If payment was made, a refund will be processed within 5-7 business days.",
    })
