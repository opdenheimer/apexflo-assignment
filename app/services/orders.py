import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.order import Order, OrderItem, OrderStatus
from app.models.menu import MenuItem
from app.schemas.order import CartItemResponse

logger = logging.getLogger(__name__)

# Valid state transitions for the kitchen/staff workflow
VALID_TRANSITIONS = {
    OrderStatus.PLACED: [OrderStatus.PREPARING, OrderStatus.CANCELLED],
    OrderStatus.PREPARING: [OrderStatus.READY, OrderStatus.CANCELLED],
    OrderStatus.READY: [OrderStatus.DELIVERED, OrderStatus.CANCELLED],
    OrderStatus.DELIVERED: [],   # Terminal state
    OrderStatus.CANCELLED: [],   # Terminal state
}

async def get_order_by_id(db: AsyncSession, order_id: int) -> Optional[dict]:
    """Retrieve full order details including line items for a patron."""
    order = await db.get(Order, order_id)
    if not order:
        return None

    # Load line items
    items_query = (
        select(OrderItem, MenuItem.name)
        .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)
        .where(OrderItem.order_id == order.id)
    )
    items_result = await db.execute(items_query)
    items = [
        CartItemResponse(
            menu_item_id=oi.menu_item_id,
            name=name,
            unit_price=oi.unit_price,
            quantity=oi.quantity,
            total_price=oi.unit_price * oi.quantity - oi.discount,
        )
        for oi, name in items_result.all()
    ]

    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "status": order.status.value,
        "show_id": order.show_id,
        "screen_id": order.screen_id,
        "seat": order.seat,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "total": order.total,
        "idempotency_key": order.idempotency_key,
        "items": items,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }

async def update_order_status(db: AsyncSession, order_id: int, new_status: OrderStatus) -> dict:
    """
    Advance order status through the kitchen workflow with strict state machine validation.
    Prevents regressions (e.g. DELIVERED -> PLACED).
    """
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    allowed_next_states = VALID_TRANSITIONS.get(order.status, [])
    if new_status not in allowed_next_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Illegal state transition from {order.status.value} to {new_status.value}. Allowed: {[s.value for s in allowed_next_states]}",
        )

    order.status = new_status
    await db.commit()
    await db.refresh(order)

    return {
        "order_id": order.id,
        "previous_status": order.status.value,
        "new_status": new_status.value,
        "seat": order.seat,
        "updated_at": order.updated_at,
    }
