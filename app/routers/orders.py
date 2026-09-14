from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth import require_admin, require_patron
from app.models.order import User
from app.models.order import OrderStatus
from app.services.orders import get_order_by_id, update_order_status

router = APIRouter(prefix="/orders", tags=["Order Lifecycle"])

class StatusUpdateRequest(BaseModel):
    status: OrderStatus

@router.get("/{order_id}")
async def get_order(order_id: int, user: User = Depends(require_patron), db: AsyncSession = Depends(get_db)):
    """Patron endpoint: Live order tracking from seat."""
    order = await get_order_by_id(db=db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order["user_id"] != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Order belongs to another patron")
    return order

@router.patch("/{order_id}/status")
async def update_status(
    order_id: int,
    request: StatusUpdateRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Kitchen / Staff endpoint: Advance order status."""
    return await update_order_status(db=db, order_id=order_id, new_status=request.status)
