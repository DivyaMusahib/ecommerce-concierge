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

    # Guest restriction
    if uid == "guest":
        return json.dumps({
            "error": "guest_restricted",
            "message": "You need to sign in or create an account to request a refund. "
                       "Please use the Sign In button to continue.",
        })

    if amount > 5000:
        return json.dumps({
            "action": "denied",
            "reason": f"Auto-refund limit is Rs.5000. Requested Rs.{amount} exceeds this limit. Please use escalate_to_human instead.",
        })

    refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
    created_at = datetime.utcnow().isoformat()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO refunds (refund_id, order_id, user_id, amount, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'Processing', ?)
        """, (refund_id, order_id, uid, amount, reason, created_at))
        
        # Also update the order status so the Order Agent reflects the change
        clean_id = order_id.strip().lstrip("#").replace("ORD-", "")
        conn.execute("UPDATE orders SET status = 'Refund Processing' WHERE order_id = ?", (clean_id,))
        conn.execute("UPDATE confirmed_orders SET status = 'Refund Processing' WHERE order_id LIKE ?", (f"%{clean_id}%",))
        
        conn.commit()

    return json.dumps({
        "action": "refund_issued",
        "refund_id": refund_id,
        "order_id": order_id,
        "amount": amount,
        "reason": reason,
        "status": "Processing — will reflect in 3-5 business days",
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
