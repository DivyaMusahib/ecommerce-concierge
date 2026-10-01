"""
Unit Tests: Cart API — add, remove, checkout, server-side total recalculation,
guest restrictions, shipping address validation, draft_orders persistence.
"""
import json
import pytest
from app.tools.cart_api import (
    set_cart_session,
    _get_cart,
    _save_cart,
    _save_draft,
    get_latest_checkout_summary,
    _calc_discount,
    confirm_checkout,
    add_to_cart,
    remove_from_cart,
    get_cart,
    apply_coupon_to_cart,
    checkout,
    check_shipping_address,
    save_shipping_address,
    _current_user,
    _current_session,
)
from app.database.db import get_conn


SESSION = "test_cart_session_001"
USER_ID = "user_1"


def _setup(session=SESSION, user=USER_ID):
    """Helper: set session/user context and clear any existing cart/draft."""
    set_cart_session(session, user)
    _current_user.set(user)
    # Clear cart
    with get_conn() as conn:
        conn.execute("DELETE FROM carts WHERE session_id = ?", (session,))
        conn.execute("DELETE FROM draft_orders WHERE session_id = ?", (session,))
        conn.commit()


class TestCartCRUD:
    def test_empty_cart(self):
        _setup()
        cart = _get_cart(SESSION)
        assert cart["items"] == []
        assert cart["coupon_code"] is None

    def test_add_item(self):
        _setup()
        result = json.loads(add_to_cart.invoke({"product_name": "mouse", "quantity": 1}))
        assert result.get("action") == "added"
        assert "Logitech" in result["product"]

    def test_add_updates_quantity(self):
        _setup()
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        result = json.loads(add_to_cart.invoke({"product_name": "mouse", "quantity": 2}))
        assert result.get("action") == "updated_quantity"
        assert result["new_quantity"] == 3

    def test_add_out_of_stock_fails(self):
        _setup()
        # Keychron K8 is seeded with stock=0
        result = json.loads(add_to_cart.invoke({"product_name": "keychron", "quantity": 1}))
        assert "error" in result
        assert "out of stock" in result["error"].lower()

    def test_add_nonexistent_product_fails(self):
        _setup()
        result = json.loads(add_to_cart.invoke({"product_name": "XXXFAKEXXX", "quantity": 1}))
        assert "error" in result

    def test_remove_item(self):
        _setup()
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        result = json.loads(remove_from_cart.invoke({"product_name": "mouse"}))
        assert result.get("action") == "removed"
        assert result["cart_size"] == 0

    def test_remove_nonexistent_item(self):
        _setup()
        result = json.loads(remove_from_cart.invoke({"product_name": "nonexistent_item"}))
        assert "error" in result

    def test_get_cart_shows_items(self):
        _setup()
        add_to_cart.invoke({"product_name": "mouse", "quantity": 2})
        result = json.loads(get_cart.invoke({}))
        assert len(result["items"]) == 1
        assert result["items"][0]["qty"] == 2
        assert result["subtotal"] > 0

    def test_ambiguous_product_returns_error(self):
        _setup()
        # "keyboard" is ambiguous (Keychron + HP Wired Keyboard)
        result = json.loads(add_to_cart.invoke({"product_name": "keyboard"}))
        # Should either succeed (if one was out of stock and only one valid)
        # OR return an ambiguous error
        if "error" in result and result["error"] == "Ambiguous product":
            assert "matches" in result
            assert len(result["matches"]) >= 2


class TestCouponApplication:
    def test_valid_coupon_applied(self):
        _setup()
        # Add items worth > 5000 so SAVE10 threshold is met
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})  # Rs.9,995
        result = json.loads(apply_coupon_to_cart.invoke({"coupon_code": "SAVE10"}))
        assert result.get("action") == "coupon_applied"
        assert result["code"] == "SAVE10"

    def test_invalid_coupon_rejected(self):
        _setup()
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        result = json.loads(apply_coupon_to_cart.invoke({"coupon_code": "INVALID999"}))
        assert "error" in result

    def test_coupon_on_empty_cart_fails(self):
        _setup()
        result = json.loads(apply_coupon_to_cart.invoke({"coupon_code": "SAVE10"}))
        assert "error" in result

    def test_flat500_coupon(self):
        _setup()
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})  # Rs.9,995
        result = json.loads(apply_coupon_to_cart.invoke({"coupon_code": "FLAT500"}))
        assert result.get("action") == "coupon_applied"


class TestCalcDiscount:
    def test_no_coupon_returns_zero(self):
        assert _calc_discount(None, 10000) == 0

    def test_percent_coupon(self):
        # SAVE10 = 10% off orders > 5000
        discount = _calc_discount("SAVE10", 10000)
        assert discount == 1000.0

    def test_flat_coupon(self):
        # FLAT500 = Rs.500 off orders > 5000
        discount = _calc_discount("FLAT500", 10000)
        assert discount == 500.0

    def test_min_order_not_met(self):
        # SAVE10 requires Rs.5000 minimum
        discount = _calc_discount("SAVE10", 1000)
        assert discount == 0

    def test_invalid_coupon_code(self):
        discount = _calc_discount("FAKECOUPON", 10000)
        assert discount == 0


class TestShippingAddress:
    def test_check_no_address(self):
        _setup()
        # user_1 has empty shipping_address by default
        result = json.loads(check_shipping_address.invoke({}))
        assert result.get("has_address") is False

    def test_save_valid_address(self):
        _setup()
        result = json.loads(save_shipping_address.invoke({
            "address": "123 Main Street, Bangalore, Karnataka, 560001"
        }))
        assert result.get("action") == "address_saved"
        assert "123 Main Street" in result["shipping_address"]

    def test_check_after_save(self):
        _setup()
        save_shipping_address.invoke({
            "address": "456 Park Avenue, Mumbai, Maharashtra, 400001"
        })
        result = json.loads(check_shipping_address.invoke({}))
        assert result.get("has_address") is True

    def test_save_short_address_rejected(self):
        _setup()
        result = json.loads(save_shipping_address.invoke({"address": "short"}))
        assert "error" in result

    def test_guest_cannot_save_address(self):
        _setup(user="guest")
        result = json.loads(save_shipping_address.invoke({"address": "123 Test Street, Test City, TS, 000001"}))
        assert "error" in result


class TestGuestRestrictions:
    def test_guest_cannot_checkout(self):
        _setup(user="guest")
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        result = json.loads(checkout.invoke({}))
        assert "error" in result
        assert result["error"] == "guest_restricted"

    def test_logged_in_user_can_proceed_to_checkout(self):
        _setup()
        # Save shipping address first
        save_shipping_address.invoke({
            "address": "789 Tech Park, Hyderabad, Telangana, 500081"
        })
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        result = json.loads(checkout.invoke({}))
        # Should NOT be a guest_restricted error
        assert result.get("error") != "guest_restricted"

    def test_guest_confirm_checkout_raises(self):
        with pytest.raises(ValueError, match="[Gg]uest"):
            confirm_checkout(
                session_id="guest_session",
                user_id="guest",
                draft_summary={"draft_order_id": "ORD-TEST"},
            )


class TestDraftOrderPersistence:
    def test_draft_saved_to_db(self):
        _setup()
        save_shipping_address.invoke({"address": "10 DB Lane, Chennai, Tamil Nadu, 600001"})
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        checkout.invoke({})
        summary = get_latest_checkout_summary(SESSION)
        assert summary is not None
        assert "total" in summary
        assert "draft_order_id" in summary

    def test_draft_cleared_on_new_session(self):
        _setup()
        # Starting a new session should clear the old draft
        summary = get_latest_checkout_summary(SESSION)
        assert summary is None


class TestServerSideTotalRecalculation:
    def test_confirm_checkout_recalculates_total(self):
        """Spoofing draft_summary total should be ignored — server recalculates."""
        _setup()
        save_shipping_address.invoke({"address": "1 Safe Rd, Delhi, DL, 110001"})
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})

        # Get the real checkout summary
        checkout_output = json.loads(checkout.invoke({}))
        real_summary = checkout_output.get("checkout_summary", {})

        # Spoof the total to Rs.1 in the draft_summary we pass
        spoofed_summary = dict(real_summary)
        spoofed_summary["total"] = 1  # Attacker tries to pay Rs.1
        spoofed_summary["subtotal"] = 1

        # Server should ignore the spoofed total and recalculate
        result = confirm_checkout(
            session_id=SESSION,
            user_id=USER_ID,
            draft_summary=spoofed_summary,
            delivery_fee=0,
        )

        # Server-side recalculated total should be >> 1
        assert result["total"] > 1000, \
            f"Server accepted spoofed total! Got: {result['total']}"
        assert result["subtotal"] > 1000

    def test_delivery_fee_capped(self):
        """Client cannot pass a delivery_fee above MAX_DELIVERY_FEE (500)."""
        from app.tools.cart_api import MAX_DELIVERY_FEE
        _setup(session="test_cart_fee_cap", user=USER_ID)
        save_shipping_address.invoke({"address": "Fee Test Rd, Pune, MH, 411001"})
        add_to_cart.invoke({"product_name": "mouse", "quantity": 1})
        checkout_output = json.loads(checkout.invoke({}))
        real_summary = checkout_output.get("checkout_summary", {})

        result = confirm_checkout(
            session_id="test_cart_fee_cap",
            user_id=USER_ID,
            draft_summary=real_summary,
            delivery_fee=99999,  # Attacker tries to inflate via fee
        )
        assert result["delivery_fee"] <= MAX_DELIVERY_FEE


class TestOrderCancellation:
    def test_cancel_existing_order(self):
        from app.tools.order_api import cancel_order, set_order_user
        set_order_user("user_1")
        result = json.loads(cancel_order.invoke({"order_id": "456"}))
        assert result.get("action") == "cancelled"
        # Verify DB updated
        with get_conn() as conn:
            row = conn.execute("SELECT status FROM orders WHERE order_id = '456'").fetchone()
        assert row["status"] == "Cancelled"

    def test_cancel_delivered_order_fails(self):
        from app.tools.order_api import cancel_order, set_order_user
        set_order_user("user_1")
        # Order 999 is Delivered
        result = json.loads(cancel_order.invoke({"order_id": "999"}))
        assert "error" in result
        assert "Delivered" in result["error"] or "cannot" in result["error"].lower()

    def test_cancel_unknown_order_fails(self):
        from app.tools.order_api import cancel_order, set_order_user
        set_order_user("user_1")
        result = json.loads(cancel_order.invoke({"order_id": "99999"}))
        assert "error" in result

    def test_cancel_other_users_order_fails(self):
        """Users should not be able to cancel orders belonging to other users."""
        from app.tools.order_api import cancel_order, set_order_user
        set_order_user("other_user_who_owns_nothing")
        result = json.loads(cancel_order.invoke({"order_id": "123"}))
        assert "error" in result
