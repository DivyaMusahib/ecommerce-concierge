"""
Order Management API - backed by SQLite via app/database/db.py.

Replaces the old hardcoded ORDERS dict with real database queries.
Includes order cancellation that syncs status across both orders and
confirmed_orders tables atomically.
"""
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

    # Also check confirmed orders placed via checkout
    with get_conn() as conn:
        # Check original demo orders first
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND user_id = ?", (clean_id, user_id)
        ).fetchone()

        if row:
            timeline = []
            try:
                timeline = json.loads(row["timeline_json"])
            except Exception:
                pass
            return json.dumps({
                "order_id": f"#ORD-{row['order_id']}",
                "product": row["product"],
                "status": row["status"],
                "eta": row["eta"],
                "carrier": row["carrier"],
                "tracking_number": row["tracking_num"],
                "placed_on": row["placed_on"],
                "amount": row["amount"],
                "timeline": timeline,
            })

        # Check confirmed orders from checkout
        conf = conn.execute(
            "SELECT * FROM confirmed_orders WHERE order_id = ? AND user_id = ?", (f"ORD-{clean_id}", user_id)
        ).fetchone()
        if not conf:
            conf = conn.execute(
                "SELECT * FROM confirmed_orders WHERE order_id LIKE ? AND user_id = ?", (f"%{clean_id}%", user_id)
            ).fetchone()

        if conf:
            items = json.loads(conf["items_json"])
            product_names = ", ".join(i["name"] for i in items)

            return json.dumps({
                "order_id": conf["order_id"],
                "product": product_names,
                "status": conf["status"],
                "eta": "3-5 business days",
                "amount": f"Rs.{conf['total']}",
                "placed_at": conf["placed_at"],
            })

    return json.dumps({
        "error": f"Order '{order_id}' not found.",
        "suggestion": "Valid demo orders: 123, 456, 999. Or use a confirmed order ID from your checkout.",
    })


@tool
def cancel_order(order_id: str) -> str:
    """
    Cancel a customer order. Sets the status to 'Cancelled' in both the
    orders table and the confirmed_orders table (if present).
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

    # Non-cancellable statuses
    terminal_statuses = {"Delivered", "Cancelled", "Refund Processing", "Refunded"}

    with get_conn() as conn:
        # Check orders table
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND user_id = ?", (clean_id, user_id)
        ).fetchone()

        conf = conn.execute(
            "SELECT * FROM confirmed_orders WHERE (order_id = ? OR order_id LIKE ?) AND user_id = ?",
            (f"ORD-{clean_id}", f"%{clean_id}%", user_id)
        ).fetchone()

        if not row and not conf:
            return json.dumps({
                "error": f"Order '{order_id}' not found or does not belong to your account.",
            })

        # Check if already in a terminal state
        current_status = (row or conf)["status"]
        if current_status in terminal_statuses:
            return json.dumps({
                "error": f"Order '{order_id}' cannot be cancelled. Current status: {current_status}.",
            })

        # Synchronously cancel in both tables
        if row:
            conn.execute(
                "UPDATE orders SET status = 'Cancelled' WHERE order_id = ? AND user_id = ?",
                (clean_id, user_id)
            )
        if conf:
            conn.execute(
                "UPDATE confirmed_orders SET status = 'Cancelled' WHERE order_id = ? AND user_id = ?",
                (conf["order_id"], user_id)
            )

        conn.commit()

    display_id = f"ORD-{clean_id}" if not order_id.startswith("ORD-") else order_id
    return json.dumps({
        "action": "cancelled",
        "order_id": display_id,
        "status": "Cancelled",
        "message": f"Order {display_id} has been successfully cancelled. "
                   "If payment was made, a refund will be processed within 5-7 business days.",
    })
