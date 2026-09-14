from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.auth import require_patron
from app.models.order import User
from app.schemas.order import CheckoutRequest, CheckoutResponse
from app.services.checkout import process_checkout

router = APIRouter(prefix="/checkout", tags=["Checkout & Ordering"])

@router.post("", response_model=CheckoutResponse)
async def checkout(
    request: CheckoutRequest,
    user: User = Depends(require_patron),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Transactional Checkout Endpoint:
    - Atomically claims stock across all items.
    - Resolves idempotency.
    - Emits stock projection events to Redis.
    """
    return await process_checkout(
        db=db,
        redis=redis,
        user_id=user.id,
        request=request,
    )
