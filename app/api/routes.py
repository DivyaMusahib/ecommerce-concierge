"""
FastAPI Routes - Chat, memory, checkout confirmation, session, and admin endpoints.

Security: All endpoints that handle user-specific data validate the Bearer JWT
when an Authorization header is present. The validated user_id from the token
takes precedence over the body user_id — preventing user_id spoofing.
"""
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_user_from_token
from app.orchestrator.supervisor import supervisor

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "guest"
    session_id: str = "default_session"

class ChatResponse(BaseModel):
    response: str
    intent: str | None = None
    urgency: str | None = None
    agents_used: list[str] = []
    confirmation_required: bool = False
    checkout_summary: dict | None = None
    latency_ms: float | None = None
    memory_updated: bool = False

class CheckoutConfirmRequest(BaseModel):
    session_id: str
    user_id: str = "default"
    draft_summary: dict  # checkout_summary dict from CartAgent
    delivery_fee: float = 0  # client-provided delivery fee (capped server-side)

@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    body: ChatRequest,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Process a user message through the full multi-agent pipeline."""
    # If a valid Bearer token was provided, its user_id overrides the body value.
    # This prevents any client from spoofing another user's identity.
    effective_user_id = token_user_id or (
        f"anon_{body.session_id}" if body.user_id in ("guest", "default") else body.user_id
    )

    t_start = time.perf_counter()

    # Record pre-request memory state for change detection
    from app.memory.long_term import ensure_user_exists, get_user_profile
    ensure_user_exists(effective_user_id)
    pre_profile = get_user_profile(effective_user_id)
    pre_updated = pre_profile.get("updated_at", "") if pre_profile else ""

    response, intent_result, agents_used = await supervisor.process_request(
        body.message,
        session_id=body.session_id,
        user_id=effective_user_id,
    )

    latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

    intent_str = None
    urgency = None
    if intent_result:
        intent_str = ", ".join(intent_result.intents)
        urgency = intent_result.urgency

    # Only surface the checkout UI if the current request was a CART_ACTION.
    # Without this guard, stale draft orders from a previous turn would
    # incorrectly trigger the confirmation modal on every subsequent message.
    confirmation_required = False
    checkout_summary = None
    active_intents = intent_result.intents if intent_result else []

    if "CART_ACTION" in active_intents:
        from app.tools.cart_api import get_latest_checkout_summary
        latest_summary = get_latest_checkout_summary(body.session_id)
        if latest_summary:
            confirmation_required = True
            checkout_summary = latest_summary

            # Clean up any raw JSON the LLM may have echoed in the text response
            response = re.sub(r'```(?:json)?\s*\{.*?\}\s*```', '', response, flags=re.DOTALL).strip()

            # If response is empty or starts with JSON, give a default prompt
            if not response or response.startswith("{"):
                response = "Please review your order summary and confirm below to place the order."

    # Detect if memory was updated during this request
    memory_updated = False
    try:
        post_profile = get_user_profile(effective_user_id)
        if post_profile:
            post_updated = post_profile.get("updated_at", "")
            if post_updated and post_updated != pre_updated:
                memory_updated = True
    except Exception:
        pass

    return ChatResponse(
        response=response,
        intent=intent_str,
        urgency=urgency,
        agents_used=agents_used or [],
        confirmation_required=confirmation_required,
        checkout_summary=checkout_summary,
        latency_ms=latency_ms,
        memory_updated=memory_updated,
    )

# ── Checkout Confirmation ─────────────────────────────────────────────────────

@router.post("/checkout/confirm")
async def confirm_checkout_endpoint(
    body: CheckoutConfirmRequest,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """
    Actually place the order after user confirms in the UI.
    Writes to confirmed_orders, clears the cart for this session.
    """
    effective_user_id = token_user_id or body.user_id

    from app.tools.cart_api import confirm_checkout
    try:
        result = confirm_checkout(
            session_id=body.session_id,
            user_id=effective_user_id,
            draft_summary=body.draft_summary,
            delivery_fee=body.delivery_fee,
        )
        return {"status": "confirmed", **result}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkout failed: {e!s}")

# ── Orders ────────────────────────────────────────────────────────────────────

@router.get("/orders/confirmed/{user_id}")
async def get_confirmed_orders(
    user_id: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Return all confirmed orders placed by the user.
    Requires a valid Bearer token; the token's user_id must match the path param.
    """
    # If a token is present and doesn't match the path user_id, reject access.
    if token_user_id and token_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view another user's orders.",
        )

    from sqlalchemy import text

    from app.database.engine import async_session
    async with async_session() as session:
        rows = (await session.execute(text("""
            SELECT o.order_id, o.status, o.subtotal, o.discount, o.tax,
                   o.delivery_fee, o.total, o.coupon_code, o.placed_at
            FROM orders o
            WHERE o.user_id = :uid
            ORDER BY o.placed_at DESC
        """), {"uid": user_id})).mappings().fetchall()

        orders = []
        for r in rows:
            items_rows = (await session.execute(text("""
                SELECT name, price, quantity FROM order_items WHERE order_id = :oid
            """), {"oid": r["order_id"]})).fetchall()
            orders.append({
                "order_id": r["order_id"],
                "status": r["status"],
                "subtotal": r["subtotal"],
                "discount": r["discount"],
                "tax": r["tax"],
                "delivery_fee": r["delivery_fee"],
                "total": r["total"],
                "coupon_code": r["coupon_code"],
                "placed_at": str(r["placed_at"]),
                "items": [{"name": i[0], "price": i[1], "qty": i[2]} for i in items_rows],
            })
    return {"orders": orders}

# ── Session ───────────────────────────────────────────────────────────────────

@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Clear short-term chat history for a session (used by New Chat button)."""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    from app.memory.session import redis_client
    redis_client.clear(session_id)
    return {"status": "cleared", "session_id": session_id}

@router.delete("/cart/{session_id}")
async def clear_cart(
    session_id: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Clear the cart for a session (used by New Chat button to prevent stale items)."""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    from app.database.db import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM carts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM draft_orders WHERE session_id = ?", (session_id,))
        conn.commit()
    return {"status": "cleared", "session_id": session_id}

# ── Memory Endpoints ──────────────────────────────────────────────────────────

@router.get("/memory/{user_id}")
async def get_memory(
    user_id: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Return the full long-term profile and preferences for a user."""
    # Prevent reading another user's memory when authenticated
    if token_user_id and token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    from app.memory.long_term import ensure_user_exists, get_user_profile
    ensure_user_exists(user_id)
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

@router.delete("/memory/{user_id}/preference/{key}")
async def forget_preference(
    user_id: str,
    key: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Delete a single preference key from a user's long-term memory."""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    from app.memory.long_term import delete_preference
    updated = delete_preference(user_id, key)
    return {"status": "deleted", "remaining_preferences": updated}

@router.delete("/memory/{user_id}/all")
async def clear_memory(
    user_id: str,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Wipe all saved preferences for a user (keeps their profile)."""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    from app.memory.long_term import clear_all_preferences
    clear_all_preferences(user_id)
    return {"status": "cleared", "user_id": user_id}

@router.put("/memory/{user_id}/preference")
async def save_preference_endpoint(
    user_id: str,
    body: dict,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Manually save a preference (key/value). Body: {key: str, value: str}"""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    from app.memory.long_term import save_preference
    key = body.get("key", "").strip()
    value = body.get("value", "").strip()
    if not key or not value:
        raise HTTPException(status_code=400, detail="Both 'key' and 'value' are required.")
    updated = save_preference(user_id, key, value)
    return {"status": "saved", "preferences": updated}

@router.patch("/profile/{user_id}")
async def update_profile(
    user_id: str,
    body: dict,
    token_user_id: str | None = Depends(get_user_from_token),
):
    """Update a top-level profile field (name or default_shipping). Body: {field: str, value: str}"""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    from app.memory.long_term import update_profile_field
    field = body.get("field", "").strip()
    value = body.get("value", "").strip()
    if not field or not value:
        raise HTTPException(status_code=400, detail="Both 'field' and 'value' are required.")
    success = update_profile_field(user_id, field, value)
    if not success:
        raise HTTPException(status_code=400, detail=f"Field '{field}' is not allowed. Only 'name' can be updated via this endpoint.")
    return {"status": "updated", "field": field, "value": value}

# ── Admin / Monitoring Endpoints ──────────────────────────────────────────────

@router.get("/admin/stats")
async def admin_stats(token_user_id: str | None = Depends(get_user_from_token)):
    """"""
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    from app.core.config import get_token_stats
    from app.database.engine import check_db_connection
    db_ok = await check_db_connection()
    return {
        "database": "ok" if db_ok else "degraded",
        "llm_usage": get_token_stats(),
    }
