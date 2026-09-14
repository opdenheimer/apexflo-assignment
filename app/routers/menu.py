from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.menu import MenuResponse
from app.services.menu import get_menu_for_show

router = APIRouter(prefix="/menu", tags=["Menu & Catalog"])

@router.get("/{show_id}", response_model=MenuResponse)
async def get_menu(
    show_id: int,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    menu = await get_menu_for_show(show_id=show_id, db=db, redis=redis)
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Show not found")
    return menu
