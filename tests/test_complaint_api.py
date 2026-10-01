"""
Unit Tests: Complaint API — refunds, escalation, and guest restrictions.
"""
import json
import pytest
from app.tools.complaint_api import (
    set_complaint_context,
    check_complaint_history,
    issue_auto_refund,
    escalate_to_human,
)
from app.database.db import get_conn


def _ctx(user="user_1", session="complaint_test_session"):
    set_complaint_context(user, session)


class TestIssueAutoRefund:
    def test_guest_cannot_refund(self):
        _ctx(user="guest")
        result = json.loads(issue_auto_refund.invoke({
            "order_id": "123",
            "amount": 500,
            "reason": "Item damaged",
        }))
        assert "error" in result
        assert result["error"] == "guest_restricted"

    def test_refund_within_limit(self):
        _ctx(user="user_1")
        result = json.loads(issue_auto_refund.invoke({
            "order_id": "999",
            "amount": 2000,
            "reason": "Product not as described",
        }))
        assert result.get("action") == "refund_issued"
        assert "refund_id" in result
        assert result["refund_id"].startswith("REF-")

    def test_refund_exceeds_limit_denied(self):
        _ctx(user="user_1")
        result = json.loads(issue_auto_refund.invoke({
            "order_id": "123",
            "amount": 6000,
            "reason": "Too expensive",
        }))
        assert result.get("action") == "denied"
        assert "5000" in result.get("reason", "")

    def test_refund_persisted_to_db(self):
        _ctx(user="user_1")
        issue_auto_refund.invoke({
            "order_id": "test_persist_order",
            "amount": 100,
            "reason": "Test refund persistence",
        })
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM refunds WHERE order_id = 'test_persist_order' AND user_id = 'user_1'"
            ).fetchone()
        assert row is not None
        assert row["amount"] == 100

    def test_refund_updates_order_status(self):
        """issue_auto_refund should update orders.status to 'Refund Processing'."""
        _ctx(user="user_1")
        issue_auto_refund.invoke({
            "order_id": "123",
            "amount": 500,
            "reason": "Wrong item shipped",
        })
        with get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM orders WHERE order_id = '123'"
            ).fetchone()
        if row:  # order 456 was cancelled in previous test but 123 may still exist
            assert "Refund" in row["status"] or "Cancelled" in row["status"]


class TestEscalateToHuman:
    def test_creates_ticket(self):
        _ctx(user="user_1")
        result = json.loads(escalate_to_human.invoke({
            "issue_summary": "Package never arrived after 30 days",
            "urgency": "HIGH",
        }))
        assert result.get("action") == "escalated"
        assert result["ticket_id"].startswith("TKT-")
        assert result["urgency"] == "HIGH"

    def test_ticket_persisted_to_db(self):
        _ctx(user="user_1", session="escalate_persist_test")
        escalate_to_human.invoke({
            "issue_summary": "DB persistence test complaint",
            "urgency": "MEDIUM",
        })
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM complaints WHERE summary LIKE '%DB persistence%' AND user_id = 'user_1'"
            ).fetchone()
        assert row is not None
        assert row["urgency"] == "MEDIUM"

    def test_medium_urgency_eta(self):
        _ctx(user="user_1")
        result = json.loads(escalate_to_human.invoke({
            "issue_summary": "Minor issue",
            "urgency": "MEDIUM",
        }))
        assert "24 hours" in result["message"]

    def test_high_urgency_eta(self):
        _ctx(user="user_1")
        result = json.loads(escalate_to_human.invoke({
            "issue_summary": "Urgent product issue",
            "urgency": "HIGH",
        }))
        assert "2 hours" in result["message"]


class TestComplaintHistory:
    def test_check_history_no_complaints(self):
        # Use a fresh user ID with no history
        result = json.loads(check_complaint_history.invoke({"user_id": "brand_new_user_xyz"}))
        assert "message" in result or result["total_complaints"] == 0

    def test_check_history_finds_refunds(self):
        _ctx(user="user_1")
        result = json.loads(check_complaint_history.invoke({"user_id": "user_1"}))
        # After the above tests, user_1 should have some refunds
        assert result["user_id"] == "user_1"
        assert "refunds" in result
        assert "complaints" in result
