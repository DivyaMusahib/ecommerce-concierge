"""
Complaint / Escalation API - backed by SQLite via app/database/db.py.

All complaint tickets and refunds are now written to real SQLite tables,
replacing the old in-memory escalation log that disappeared on restart.
Session context is injected via ContextVar set by the supervisor.
"""
import json
import uuid
from contextvars import ContextVar
from datetime import datetime
from langchain_core.tools import tool
from app.database.db import get_conn

_current_user: ContextVar[str] = ContextVar("complaint_user", default="default")
_current_session: ContextVar[str] = ContextVar("complaint_session", default="default")


def set_complaint_context(user_id: str, session_id: str) -> None:
    """Bind user/session context before invoking the ComplaintAgent."""
    _current_user.set(user_id)
    _current_session.set(session_id)


@tool
def check_complaint_history(user_id: str = "") -> str:
    """
    Check a user's past complaint and ticket history.
    Retrieves both previous complaints and any issued refunds for this user.
    """
    uid = user_id or _current_user.get()
    with get_conn() as conn:
        complaints = conn.execute(
            "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        refunds = conn.execute(
            "SELECT * FROM refunds WHERE user_id = ? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()

    result = {
        "user_id": uid,
        "total_complaints": len(complaints),
        "complaints": [dict(r) for r in complaints],
        "refunds": [dict(r) for r in refunds],
    }
    if not complaints and not refunds:
        result["message"] = "No previous complaints or refunds found."
    return json.dumps(result)


@tool
def issue_auto_refund(order_id: str, amount: float, reason: str) -> str:
    """
    Issue an automatic refund for a customer order.
    Only allowed for amounts under Rs.5000. Higher amounts must be escalated.
    Refund is recorded in the database and will reflect in 3-5 business days.
    """
    uid = _current_user.get()

    if uid == "guest":
        return json.dumps({"error": "guest_restricted", "message": "Please sign in to request a refund."})

    if amount <= 0:
        return json.dumps({"error": "Refund amount must be greater than 0."})

    if amount > 5000:
        return json.dumps({"action": "denied", "reason": f"Auto-refund limit is Rs.5000. Requested Rs.{amount} exceeds this limit. Please escalate."})

    clean_id = order_id.strip().lstrip("#").replace("ORD-", "").replace("ORD", "").lstrip("0") or "0"
    
    with get_conn() as conn:
        # Check if already refunded
        existing_refund = conn.execute(
            "SELECT 1 FROM refunds WHERE (order_id = ? OR order_id = ?) AND user_id = ?",
            (clean_id, f"ORD-{clean_id}", uid)
        ).fetchone()
        if existing_refund:
            return json.dumps({"error": "A refund has already been issued or is processing for this order."})

        # Fetch from orders (numeric ID) and confirmed_orders (ORD- prefixed or numeric)
        row = conn.execute(
            "SELECT amount FROM orders WHERE order_id = ? AND user_id = ?",
            (clean_id, uid)
        ).fetchone()
        conf = conn.execute(
            "SELECT total as amount FROM confirmed_orders "
            "WHERE (order_id = ? OR order_id = ?) AND user_id = ?",
            (f"ORD-{clean_id}", clean_id, uid)
        ).fetchone()

        if not row and not conf:
            return json.dumps({"error": f"Order '{order_id}' not found or does not belong to you."})

        # Parse order amount safely
        order_record = row or conf
        raw_amt = str(order_record["amount"]).replace("Rs.", "").replace(",", "").strip()
        try:
            order_total = float(raw_amt)
        except ValueError:
            order_total = 0.0

        if amount > order_total:
            return json.dumps({"error": f"Refund amount (Rs.{amount}) cannot exceed the order total (Rs.{order_total})."})

        refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
        created_at = datetime.utcnow().isoformat()
        db_order_id = f"ORD-{clean_id}" if conf else clean_id
        
        conn.execute("""
            INSERT INTO refunds (refund_id, order_id, user_id, amount, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'Processing', ?)
        """, (refund_id, db_order_id, uid, amount, reason, created_at))
        
        if row:
            conn.execute("UPDATE orders SET status = 'Refund Processing' WHERE order_id = ? AND user_id = ?", (clean_id, uid))
        if conf:
            conn.execute("UPDATE confirmed_orders SET status = 'Refund Processing' WHERE order_id = ? AND user_id = ?", (f"ORD-{clean_id}", uid))
        
        conn.commit()

    return json.dumps({
        "action": "refund_issued",
        "refund_id": refund_id,
        "order_id": order_id,
        "amount": amount,
        "reason": reason,
        "status": "Processing — will reflect in 3-5 business days"
    })


@tool
def escalate_to_human(issue_summary: str, urgency: str = "HIGH") -> str:
    """
    Escalate a customer issue to the human support team.
    Creates a support ticket in the database. Use when auto-resolution isn't possible
    or the refund amount exceeds ₹5000.
    urgency: 'HIGH' (2 hours response) or 'MEDIUM' (24 hours response).
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    created_at = datetime.utcnow().isoformat()
    uid = _current_user.get()
    sid = _current_session.get()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO complaints (ticket_id, user_id, session_id, summary, urgency, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'QUEUED', ?)
        """, (ticket_id, uid, sid, issue_summary, urgency.upper(), created_at))
        conn.commit()

    eta = "2 hours" if urgency.upper() == "HIGH" else "24 hours"
    return json.dumps({
        "action": "escalated",
        "ticket_id": ticket_id,
        "urgency": urgency.upper(),
        "message": f"Your issue has been escalated. A human agent will contact you within {eta}. Ticket: {ticket_id}",
    })
