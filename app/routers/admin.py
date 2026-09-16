import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.auth import require_admin
from app.models.menu import MenuItem, Inventory
from app.models.order import Order, OrderStatus
from app.schemas.menu import MenuItemResponse
from app.services.orders import get_order_by_id

router = APIRouter(prefix="/admin", tags=["Admin Surface"])

class MenuItemCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    category: str
    price: float = Field(gt=0)
    is_active: bool = True

class StockAdjustmentRequest(BaseModel):
    menu_item_id: int
    cinema_id: int
    show_id: int
    new_quantity: int = Field(ge=0, description="New absolute stock quantity")

# Menu Management

@router.post("/menu", response_model=MenuItemResponse, dependencies=[Depends(require_admin)])
async def create_menu_item(item_in: MenuItemCreate, db: AsyncSession = Depends(get_db)):
    item = MenuItem(**item_in.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return MenuItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        category=item.category,
        price=item.price,
        is_active=item.is_active,
        available_stock=0,
        is_available=False,
    )

@router.patch("/menu/{item_id}/toggle", dependencies=[Depends(require_admin)])
async def toggle_menu_item_active(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    item = await db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
    item.is_active = not item.is_active
    await db.commit()

    # Invalidate all cached menus
    if redis:
        try:
            keys = await redis.keys("menu:show:*")
            if keys:
                await redis.delete(*keys)
        except Exception:
            pass

    return {"item_id": item.id, "is_active": item.is_active}

# -------------------------------------------------------------
# 2. Authoritative Stock Adjustments (Restock / Inventory Override)
# -------------------------------------------------------------
@router.post("/inventory/adjust", dependencies=[Depends(require_admin)])
async def adjust_inventory(
    req: StockAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Admin stock override:
    1. Updates PostgreSQL authoritative inventory row and increments version.
    2. Emits StockChanged event to Redis Streams so connected WebSockets update instantly.
    """
    query = select(Inventory).where(
        Inventory.menu_item_id == req.menu_item_id,
        Inventory.cinema_id == req.cinema_id,
        Inventory.show_id == req.show_id,
    )
    result = await db.execute(query)
    inv = result.scalar_one_or_none()

    if not inv:
        inv = Inventory(
            menu_item_id=req.menu_item_id,
            cinema_id=req.cinema_id,
            show_id=req.show_id,
            quantity=req.new_quantity,
            version=1,
        )
        db.add(inv)
    else:
        inv.quantity = req.new_quantity
        inv.version += 1

    await db.commit()
    await db.refresh(inv)

    # Post-commit: publish event to Redis Streams & update projection
    if redis:
        try:
            # Update Redis projection
            proj_key = f"stock:{req.show_id}:{req.menu_item_id}"
            await redis.set(proj_key, json.dumps({
                "quantity": inv.quantity,
                "version": inv.version,
            }))
            # Invalidate menu cache
            await redis.delete(f"menu:show:{req.show_id}")
            # Emit StockChanged to stream
            await redis.xadd(
                "stock-events",
                {
                    "event_type": "StockChanged",
                    "menu_item_id": str(req.menu_item_id),
                    "show_id": str(req.show_id),
                    "cinema_id": str(req.cinema_id),
                    "new_quantity": str(inv.quantity),
                    "version": str(inv.version),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception:
            pass

    return {
        "status": "success",
        "menu_item_id": inv.menu_item_id,
        "show_id": inv.show_id,
        "new_quantity": inv.quantity,
        "version": inv.version,
    }


# Live Order Queue for Kitchen View
@router.get("/orders", dependencies=[Depends(require_admin)])
async def list_live_orders(
    status_filter: Optional[OrderStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).order_by(Order.created_at.desc()).limit(50)
    if status_filter:
        query = query.where(Order.status == status_filter)
    res = await db.execute(query)
    orders = res.scalars().all()
    
    # Load items for each order
    result = []
    for o in orders:
        full_order = await get_order_by_id(db, o.id)
        result.append({
            "id": o.id,
            "seat": o.seat,
            "show_id": o.show_id,
            "screen_id": o.screen_id,
            "status": o.status.value,
            "total": o.total,
            "subtotal": o.subtotal,
            "discount": o.discount,
            "created_at": o.created_at,
            "items": full_order.get("items", []) if full_order else [],
        })
    return result

# ---------------------------------------------------------------------------
# Detailed order view for admin (includes patron items)
# ---------------------------------------------------------------------------
@router.get("/orders/{order_id}", dependencies=[Depends(require_admin)])
async def get_order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return full order information, including each ordered item.

    The response mirrors the structure used in the live‑order queue but is
    limited to a single order identified by ``order_id``.
    """
    full_order = await get_order_by_id(db, order_id)
    if not full_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return full_order
